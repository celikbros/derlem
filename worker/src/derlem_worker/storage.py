from __future__ import annotations

from dataclasses import dataclass
import codecs
import hashlib
import os
from pathlib import Path
import shutil
import stat
import tempfile
from typing import Callable
from uuid import UUID


ProgressCallback = Callable[[dict[str, int]], None]
PROGRESS_INTERVAL_BYTES = 64 * 1024 * 1024


@dataclass(frozen=True)
class StoredObject:
    sha256: str
    storage_key: str
    byte_size: int
    line_count: int
    detected_encoding: str


@dataclass(frozen=True)
class IngestOutcome:
    stored: StoredObject
    resumed_from_bytes: int
    checkpoint_revalidated_bytes: int
    checkpoint_reset: bool


class ContentAddressedStore:
    def __init__(self, root: Path) -> None:
        self.root = root.resolve()
        self.temp_root = self.root / ".tmp"
        self.object_root = self.root / "objects" / "sha256"
        self.temp_root.mkdir(parents=True, exist_ok=True)
        self.object_root.mkdir(parents=True, exist_ok=True)

    def ingest_file(
        self,
        source_path: Path,
        *,
        progress_callback: ProgressCallback | None = None,
        progress_interval_bytes: int = PROGRESS_INTERVAL_BYTES,
    ) -> StoredObject:
        return self._ingest_file(
            source_path,
            progress_callback=progress_callback,
            progress_interval_bytes=progress_interval_bytes,
            checkpoint_path=None,
        ).stored

    def ingest_file_resumable(
        self,
        source_path: Path,
        *,
        checkpoint_id: UUID | str,
        progress_callback: ProgressCallback | None = None,
        progress_interval_bytes: int = PROGRESS_INTERVAL_BYTES,
    ) -> IngestOutcome:
        checkpoint_path = self.checkpoint_path(checkpoint_id)
        return self._ingest_file(
            source_path,
            progress_callback=progress_callback,
            progress_interval_bytes=progress_interval_bytes,
            checkpoint_path=checkpoint_path,
        )

    def checkpoint_path(self, checkpoint_id: UUID | str) -> Path:
        identifier = UUID(str(checkpoint_id))
        path = (self.temp_root / f"ingest-{identifier}.part").resolve()
        path.relative_to(self.temp_root)
        return path

    def discard_checkpoint(self, checkpoint_id: UUID | str) -> None:
        self._discard_checkpoint_path(self.checkpoint_path(checkpoint_id))

    def _discard_checkpoint_path(self, checkpoint_path: Path) -> None:
        if not checkpoint_path.exists():
            return
        linked_target: Path | None = None
        if checkpoint_path.stat().st_nlink > 1:
            hasher = hashlib.sha256()
            with checkpoint_path.open("rb") as checkpoint:
                while chunk := checkpoint.read(1024 * 1024):
                    hasher.update(chunk)
            digest = hasher.hexdigest()
            linked_target = self.root / f"objects/sha256/{digest[:2]}/{digest[2:4]}/{digest}"
        checkpoint_path.chmod(stat.S_IWRITE)
        checkpoint_path.unlink()
        if linked_target is not None and linked_target.exists():
            linked_target.chmod(stat.S_IREAD)

    def finalize_checkpoint(self, checkpoint_id: UUID | str, stored: StoredObject) -> None:
        checkpoint_path = self.checkpoint_path(checkpoint_id)
        if checkpoint_path.exists():
            checkpoint_path.chmod(stat.S_IWRITE)
            checkpoint_path.unlink()
        target = self.root / stored.storage_key
        target.chmod(stat.S_IREAD)

    def _ingest_file(
        self,
        source_path: Path,
        *,
        progress_callback: ProgressCallback | None,
        progress_interval_bytes: int,
        checkpoint_path: Path | None,
    ) -> IngestOutcome:
        source_path = source_path.resolve(strict=True)
        if not source_path.is_file():
            raise ValueError(f"Not a regular file: {source_path}")
        if progress_interval_bytes <= 0:
            raise ValueError("progress_interval_bytes must be positive")

        hasher = hashlib.sha256()
        decoder = codecs.getincrementaldecoder("utf-8")("strict")
        source_stat = source_path.stat()
        total_bytes = source_stat.st_size
        byte_size = 0
        newline_count = 0
        last_byte: int | None = None
        next_progress_at = progress_interval_bytes
        resumed_from_bytes = 0
        checkpoint_revalidated_bytes = 0
        checkpoint_reset = False

        if checkpoint_path is None:
            file_descriptor, temp_name = tempfile.mkstemp(prefix="ingest-", dir=self.temp_root)
            temp_path = Path(temp_name)
            os.close(file_descriptor)
            remove_temp = True
        else:
            temp_path = checkpoint_path
            remove_temp = False
        try:
            if temp_path.is_symlink():
                raise ValueError(f"Invalid ingest checkpoint: {temp_path}")
            if temp_path.exists():
                if not temp_path.is_file():
                    raise ValueError(f"Invalid ingest checkpoint: {temp_path}")
                checkpoint_size = temp_path.stat().st_size
                if checkpoint_size > total_bytes:
                    self._discard_checkpoint_path(temp_path)
                    checkpoint_reset = True
                    checkpoint_size = 0

                if checkpoint_size > 0:
                    mismatch = False
                    validation_progress_at = progress_interval_bytes
                    with source_path.open("rb") as source, temp_path.open("rb") as checkpoint:
                        while chunk := checkpoint.read(1024 * 1024):
                            source_chunk = source.read(len(chunk))
                            if source_chunk != chunk:
                                mismatch = True
                                break
                            hasher.update(chunk)
                            decoder.decode(chunk, final=False)
                            byte_size += len(chunk)
                            checkpoint_revalidated_bytes += len(chunk)
                            newline_count += chunk.count(b"\n")
                            last_byte = chunk[-1]
                            if progress_callback is not None and byte_size >= validation_progress_at:
                                progress_callback(
                                    {
                                        "input_bytes_processed": byte_size,
                                        "input_bytes_total": total_bytes,
                                        "lines_read": newline_count,
                                        "checkpoint_bytes_validated": checkpoint_revalidated_bytes,
                                        "checkpoint_bytes_total": checkpoint_size,
                                    }
                                )
                                while validation_progress_at <= byte_size:
                                    validation_progress_at += progress_interval_bytes

                    if mismatch:
                        self._discard_checkpoint_path(temp_path)
                        checkpoint_reset = True
                        hasher = hashlib.sha256()
                        decoder = codecs.getincrementaldecoder("utf-8")("strict")
                        byte_size = 0
                        checkpoint_revalidated_bytes = 0
                        newline_count = 0
                        last_byte = None
                    else:
                        resumed_from_bytes = checkpoint_size
                        if progress_callback is not None:
                            progress_callback(
                                {
                                    "input_bytes_processed": byte_size,
                                    "input_bytes_total": total_bytes,
                                    "lines_read": newline_count,
                                    "checkpoint_bytes_validated": checkpoint_revalidated_bytes,
                                    "checkpoint_bytes_total": checkpoint_size,
                                }
                            )

            if byte_size < total_bytes or not temp_path.exists():
                if temp_path.exists() and temp_path.stat().st_nlink > 1:
                    checkpoint_digest = hasher.hexdigest()
                    published_target = (
                        self.object_root
                        / checkpoint_digest[:2]
                        / checkpoint_digest[2:4]
                        / checkpoint_digest
                    )
                    self._detach_published_checkpoint(temp_path, published_target)
                mode = "ab" if temp_path.exists() else "xb"
                with temp_path.open(mode) as destination, source_path.open("rb") as source:
                    source.seek(byte_size)
                    while chunk := source.read(1024 * 1024):
                        hasher.update(chunk)
                        decoder.decode(chunk, final=False)
                        destination.write(chunk)
                        byte_size += len(chunk)
                        newline_count += chunk.count(b"\n")
                        last_byte = chunk[-1]
                        if progress_callback is not None and byte_size >= next_progress_at:
                            destination.flush()
                            os.fsync(destination.fileno())
                            progress = {
                                "input_bytes_processed": byte_size,
                                "input_bytes_total": total_bytes,
                                "lines_read": newline_count,
                            }
                            if checkpoint_path is not None:
                                progress.update(
                                    {
                                        "resumed_from_bytes": resumed_from_bytes,
                                        "checkpoint_revalidated_bytes": checkpoint_revalidated_bytes,
                                        "checkpoint_reset": int(checkpoint_reset),
                                    }
                                )
                            progress_callback(progress)
                            while next_progress_at <= byte_size:
                                next_progress_at += progress_interval_bytes
                    destination.flush()
                    os.fsync(destination.fileno())
            decoder.decode(b"", final=True)

            final_source_stat = source_path.stat()
            if (
                final_source_stat.st_size != source_stat.st_size
                or final_source_stat.st_mtime_ns != source_stat.st_mtime_ns
                or final_source_stat.st_ino != source_stat.st_ino
            ):
                raise RuntimeError("Source file changed during ingest")

            digest = hasher.hexdigest()
            storage_key = f"objects/sha256/{digest[:2]}/{digest[2:4]}/{digest}"
            target = self.root / Path(storage_key)
            target.parent.mkdir(parents=True, exist_ok=True)
            self._publish_create_only(temp_path, target, remove_source=remove_temp)
            line_count = newline_count + (1 if byte_size > 0 and last_byte != ord("\n") else 0)
            if progress_callback is not None:
                progress = {
                    "input_bytes_processed": byte_size,
                    "input_bytes_total": total_bytes,
                    "lines_read": line_count,
                }
                if checkpoint_path is not None:
                    progress.update(
                        {
                            "resumed_from_bytes": resumed_from_bytes,
                            "checkpoint_revalidated_bytes": checkpoint_revalidated_bytes,
                            "checkpoint_reset": int(checkpoint_reset),
                        }
                    )
                progress_callback(progress)
            return IngestOutcome(
                stored=StoredObject(
                    sha256=digest,
                    storage_key=storage_key,
                    byte_size=byte_size,
                    line_count=line_count,
                    detected_encoding="UTF-8",
                ),
                resumed_from_bytes=resumed_from_bytes,
                checkpoint_revalidated_bytes=checkpoint_revalidated_bytes,
                checkpoint_reset=checkpoint_reset,
            )
        finally:
            if remove_temp:
                temp_path.unlink(missing_ok=True)

    def ingest_bytes(self, content: bytes) -> StoredObject:
        decoder = codecs.getincrementaldecoder("utf-8")("strict")
        decoder.decode(content, final=True)
        digest = hashlib.sha256(content).hexdigest()
        storage_key = f"objects/sha256/{digest[:2]}/{digest[2:4]}/{digest}"
        target = self.root / Path(storage_key)
        target.parent.mkdir(parents=True, exist_ok=True)

        file_descriptor, temp_name = tempfile.mkstemp(prefix="ingest-", dir=self.temp_root)
        temp_path = Path(temp_name)
        try:
            with os.fdopen(file_descriptor, "wb") as destination:
                destination.write(content)
                destination.flush()
                os.fsync(destination.fileno())
            self._publish_create_only(temp_path, target)
        finally:
            temp_path.unlink(missing_ok=True)

        newline_count = content.count(b"\n")
        line_count = newline_count + (1 if content and not content.endswith(b"\n") else 0)
        return StoredObject(
            sha256=digest,
            storage_key=storage_key,
            byte_size=len(content),
            line_count=line_count,
            detected_encoding="UTF-8",
        )

    @staticmethod
    def _publish_create_only(temp_path: Path, target: Path, *, remove_source: bool = True) -> None:
        try:
            os.link(temp_path, target)
            if remove_source:
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

    @staticmethod
    def _detach_published_checkpoint(checkpoint_path: Path, published_target: Path) -> None:
        file_descriptor, detached_name = tempfile.mkstemp(
            prefix="checkpoint-detach-",
            dir=checkpoint_path.parent,
        )
        detached_path = Path(detached_name)
        try:
            with os.fdopen(file_descriptor, "wb") as destination, checkpoint_path.open("rb") as source:
                shutil.copyfileobj(source, destination, length=1024 * 1024)
                destination.flush()
                os.fsync(destination.fileno())
            checkpoint_path.chmod(stat.S_IWRITE)
            checkpoint_path.unlink()
            if published_target.exists():
                published_target.chmod(stat.S_IREAD)
            os.replace(detached_path, checkpoint_path)
        finally:
            detached_path.unlink(missing_ok=True)
