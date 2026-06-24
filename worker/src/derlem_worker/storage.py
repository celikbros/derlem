from __future__ import annotations

from dataclasses import dataclass
import codecs
import hashlib
import os
from pathlib import Path
import shutil
import stat
import tempfile


@dataclass(frozen=True)
class StoredObject:
    sha256: str
    storage_key: str
    byte_size: int
    line_count: int
    detected_encoding: str


class ContentAddressedStore:
    def __init__(self, root: Path) -> None:
        self.root = root.resolve()
        self.temp_root = self.root / ".tmp"
        self.object_root = self.root / "objects" / "sha256"
        self.temp_root.mkdir(parents=True, exist_ok=True)
        self.object_root.mkdir(parents=True, exist_ok=True)

    def ingest_file(self, source_path: Path) -> StoredObject:
        source_path = source_path.resolve(strict=True)
        if not source_path.is_file():
            raise ValueError(f"Not a regular file: {source_path}")

        hasher = hashlib.sha256()
        decoder = codecs.getincrementaldecoder("utf-8")("strict")
        byte_size = 0
        newline_count = 0
        last_byte: int | None = None

        file_descriptor, temp_name = tempfile.mkstemp(prefix="ingest-", dir=self.temp_root)
        temp_path = Path(temp_name)
        try:
            with os.fdopen(file_descriptor, "wb") as destination, source_path.open("rb") as source:
                while chunk := source.read(1024 * 1024):
                    hasher.update(chunk)
                    decoder.decode(chunk, final=False)
                    destination.write(chunk)
                    byte_size += len(chunk)
                    newline_count += chunk.count(b"\n")
                    last_byte = chunk[-1]
                decoder.decode(b"", final=True)
                destination.flush()
                os.fsync(destination.fileno())

            digest = hasher.hexdigest()
            storage_key = f"objects/sha256/{digest[:2]}/{digest[2:4]}/{digest}"
            target = self.root / Path(storage_key)
            target.parent.mkdir(parents=True, exist_ok=True)
            self._publish_create_only(temp_path, target)
            line_count = newline_count + (1 if byte_size > 0 and last_byte != ord("\n") else 0)
            return StoredObject(
                sha256=digest,
                storage_key=storage_key,
                byte_size=byte_size,
                line_count=line_count,
                detected_encoding="UTF-8",
            )
        finally:
            temp_path.unlink(missing_ok=True)

    @staticmethod
    def _publish_create_only(temp_path: Path, target: Path) -> None:
        try:
            os.link(temp_path, target)
            temp_path.unlink()
        except FileExistsError:
            return
        except OSError:
            try:
                with target.open("xb") as destination, temp_path.open("rb") as source:
                    shutil.copyfileobj(source, destination, length=1024 * 1024)
            except FileExistsError:
                return
        target.chmod(stat.S_IREAD)
