from __future__ import annotations

from dataclasses import dataclass
import codecs
import hashlib
import os
from pathlib import Path
import re
import shutil
import stat
import tempfile
from typing import Callable
from uuid import UUID


ProgressCallback = Callable[[dict[str, int]], None]
PROGRESS_INTERVAL_BYTES = 64 * 1024 * 1024
CHECKPOINT_ID_RE = re.compile(
    r"^([0-9a-fA-F-]{36})(?:-attempt-([1-9][0-9]*))?$"
)


def _normalize_checkpoint_id(checkpoint_id: UUID | str) -> str:
    value = str(checkpoint_id)
    match = CHECKPOINT_ID_RE.fullmatch(value)
    if match is None:
        raise ValueError("checkpoint_id must be a UUID or UUID-attempt-N")
    identifier = str(UUID(match.group(1)))
    attempt = match.group(2)
    return identifier if attempt is None else f"{identifier}-attempt-{int(attempt)}"


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

    def ingest_raw_file(self, source_path: Path) -> StoredObject:
        """UTF-8 dogrulamasi olmadan ikili dosyayi (PDF/DOCX vb.) depoya alir.

        Ekstraksiyon kaynaklarinin ham hali lineage kaniti olarak saklanir;
        satir sayimi ve encoding tespiti ikili icerik icin anlamsizdir.
        """
        hasher = hashlib.sha256()
        byte_size = 0
        fd, temp_name = tempfile.mkstemp(dir=str(self.temp_root), prefix="raw-")
        temp_path = Path(temp_name)
        try:
            with os.fdopen(fd, "wb") as temp, source_path.open("rb") as source:
                while True:
                    chunk = source.read(4 * 1024 * 1024)
                    if not chunk:
                        break
                    hasher.update(chunk)
                    byte_size += len(chunk)
                    temp.write(chunk)
                temp.flush()
                os.fsync(temp.fileno())
            digest = hasher.hexdigest()
            storage_key = f"objects/sha256/{digest[:2]}/{digest[2:4]}/{digest}"
            target = self.root / Path(storage_key)
            target.parent.mkdir(parents=True, exist_ok=True)
            self._publish_create_only(
                temp_path,
                target,
                expected_sha256=digest,
                expected_size=byte_size,
                remove_source=True,
            )
            return StoredObject(
                sha256=digest,
                storage_key=storage_key,
                byte_size=byte_size,
                line_count=0,
                detected_encoding="binary",
            )
        finally:
            temp_path.unlink(missing_ok=True)

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
        identifier = _normalize_checkpoint_id(checkpoint_id)
        path = (self.temp_root / f"ingest-{identifier}.part").resolve()
        path.relative_to(self.temp_root)
        return path

    def discard_checkpoint(self, checkpoint_id: UUID | str) -> None:
        self._discard_checkpoint_path(self.checkpoint_path(checkpoint_id))

    def promote_checkpoint(
        self, current_id: UUID | str, next_id: UUID | str
    ) -> bool:
        """Atomically hand a closed checkpoint to the next retry attempt."""
        current = self.checkpoint_path(current_id)
        target = self.checkpoint_path(next_id)
        if current.is_symlink():
            current.unlink()
            raise ValueError(f"Invalid ingest checkpoint: {current}")
        if not current.exists():
            return False
        if not current.is_file():
            raise ValueError(f"Invalid ingest checkpoint: {current}")
        # Create-only link is the fence: if attempt N+1 has already started,
        # never replace or delete its active checkpoint.
        os.link(current, target)
        try:
            self._discard_checkpoint_path(current)
        except OSError:
            # The promoted link is already complete and safe to use. A stale
            # alias is harmless and is removed by the DB-aware sweeper later.
            pass
        return True

    def _discard_checkpoint_path(
        self,
        checkpoint_path: Path,
        *,
        known_cas_target: Path | None = None,
    ) -> None:
        if checkpoint_path.is_symlink():
            checkpoint_path.unlink()
            return
        if not checkpoint_path.exists():
            return
        if not checkpoint_path.is_file():
            raise ValueError(f"Invalid ingest checkpoint: {checkpoint_path}")
        try:
            checkpoint_path.unlink()
        except PermissionError:
            # Windows may refuse to unlink a read-only hard link. Only then
            # relax the shared inode mode, and restore a verified CAS sibling.
            linked_target = self._linked_cas_target(
                checkpoint_path, known_target=known_cas_target
            )
            checkpoint_path.chmod(stat.S_IREAD | stat.S_IWRITE)
            try:
                checkpoint_path.unlink()
            finally:
                if linked_target is not None and linked_target.exists():
                    linked_target.chmod(stat.S_IREAD)

    def _linked_cas_target(
        self,
        checkpoint_path: Path,
        *,
        known_target: Path | None = None,
    ) -> Path | None:
        if checkpoint_path.stat().st_nlink <= 1:
            return None
        candidate = known_target
        if candidate is None:
            hasher = hashlib.sha256()
            with checkpoint_path.open("rb") as checkpoint:
                while chunk := checkpoint.read(1024 * 1024):
                    hasher.update(chunk)
            digest = hasher.hexdigest()
            candidate = self.object_root / digest[:2] / digest[2:4] / digest
        try:
            if candidate.is_file() and os.path.samefile(checkpoint_path, candidate):
                return candidate
        except OSError:
            pass
        return None

    def finalize_checkpoint(self, checkpoint_id: UUID | str, stored: StoredObject) -> None:
        checkpoint_path = self.checkpoint_path(checkpoint_id)
        target = self.root / stored.storage_key
        if checkpoint_path.exists():
            self._discard_checkpoint_path(
                checkpoint_path, known_cas_target=target
            )
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
                final_source_stat.st_dev != source_stat.st_dev
                or final_source_stat.st_ino != source_stat.st_ino
                or final_source_stat.st_mode != source_stat.st_mode
                or final_source_stat.st_size != source_stat.st_size
                or final_source_stat.st_mtime_ns != source_stat.st_mtime_ns
                or final_source_stat.st_ctime_ns != source_stat.st_ctime_ns
            ):
                raise RuntimeError("Source file changed during ingest")

            digest = hasher.hexdigest()
            storage_key = f"objects/sha256/{digest[:2]}/{digest[2:4]}/{digest}"
            target = self.root / Path(storage_key)
            target.parent.mkdir(parents=True, exist_ok=True)
            self._publish_create_only(
                temp_path,
                target,
                expected_sha256=digest,
                expected_size=byte_size,
                remove_source=remove_temp,
            )
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
            self._publish_create_only(
                temp_path,
                target,
                expected_sha256=digest,
                expected_size=len(content),
            )
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

    @classmethod
    def _publish_create_only(
        cls,
        temp_path: Path,
        target: Path,
        *,
        expected_sha256: str,
        expected_size: int,
        remove_source: bool = True,
    ) -> None:
        """Atomically publish a complete, verified content-addressed object.

        The final path is never streamed into directly. If the source cannot be
        hard-linked, a fully written and fsynced sibling is linked create-only;
        concurrent publishers either win atomically or verify the winner.
        """
        try:
            published_source = temp_path.open("r+b")
        except PermissionError as open_error:
            # A completed checkpoint may already be a read-only alias of this
            # digest. Otherwise copy it to a writable, complete sibling before
            # attempting the same create-only publication protocol.
            if target.exists():
                cls._accept_existing_object(
                    temp_path,
                    target,
                    expected_sha256=expected_sha256,
                    expected_size=expected_size,
                    remove_source=remove_source,
                )
            else:
                cls._publish_via_complete_sibling(
                    temp_path,
                    target,
                    expected_sha256=expected_sha256,
                    expected_size=expected_size,
                    remove_source=remove_source,
                    link_error=open_error,
                )
            return

        try:
            # Make the candidate self-contained and durable even when it came
            # from a checkpoint completed by an earlier process attempt.
            os.fsync(published_source.fileno())
            try:
                os.link(temp_path, target)
            except FileExistsError:
                published_source.close()
                cls._accept_existing_object(
                    temp_path,
                    target,
                    expected_sha256=expected_sha256,
                    expected_size=expected_size,
                    remove_source=remove_source,
                )
                return
            except OSError as link_error:
                published_source.close()
                cls._publish_via_complete_sibling(
                    temp_path,
                    target,
                    expected_sha256=expected_sha256,
                    expected_size=expected_size,
                    remove_source=remove_source,
                    link_error=link_error,
                )
                return

            cls._verify_cas_object(target, expected_sha256, expected_size)
            cls._seal_and_sync_published_object(
                target,
                published_descriptor=published_source.fileno(),
            )
        finally:
            if not published_source.closed:
                published_source.close()
        if remove_source:
            cls._remove_source_after_publish(temp_path, target)
            target.chmod(stat.S_IREAD)
            cls._sync_existing_cas_object(target)

    @classmethod
    def _publish_via_complete_sibling(
        cls,
        temp_path: Path,
        target: Path,
        *,
        expected_sha256: str,
        expected_size: int,
        remove_source: bool,
        link_error: OSError,
    ) -> None:
        sibling_descriptor, sibling_name = tempfile.mkstemp(
            dir=target.parent,
            prefix=f".{target.name}.publish-",
        )
        sibling_path = Path(sibling_name)
        linked = False
        try:
            with os.fdopen(sibling_descriptor, "w+b") as sibling:
                with temp_path.open("rb") as source:
                    shutil.copyfileobj(source, sibling, length=1024 * 1024)
                sibling.flush()
                os.fsync(sibling.fileno())
                cls._verify_cas_object(
                    sibling_path, expected_sha256, expected_size
                )
                try:
                    os.link(sibling_path, target)
                    linked = True
                except FileExistsError:
                    cls._accept_existing_object(
                        temp_path,
                        target,
                        expected_sha256=expected_sha256,
                        expected_size=expected_size,
                        remove_source=remove_source,
                    )
                    return
                except OSError as publish_error:
                    raise RuntimeError(
                        "Content-addressed store requires atomic hard-link publication"
                    ) from publish_error

                cls._verify_cas_object(target, expected_sha256, expected_size)
                cls._seal_and_sync_published_object(
                    target,
                    published_descriptor=sibling.fileno(),
                )
            cls._remove_source_after_publish(sibling_path, target)
            linked = False
            if remove_source:
                cls._remove_source_after_publish(temp_path, target)
            target.chmod(stat.S_IREAD)
            cls._sync_existing_cas_object(target)
        except FileNotFoundError:
            # Stale-attempt cleanup may unlink a checkpoint before fallback
            # opens it. Never create a partial final target in that case.
            raise
        finally:
            if sibling_path.exists():
                if linked and target.exists():
                    cls._remove_source_after_publish(sibling_path, target)
                else:
                    sibling_path.unlink(missing_ok=True)
        if not target.exists():
            raise RuntimeError(
                "CAS fallback publication did not create its target"
            ) from link_error

    @classmethod
    def _accept_existing_object(
        cls,
        temp_path: Path,
        target: Path,
        *,
        expected_sha256: str,
        expected_size: int,
        remove_source: bool,
    ) -> None:
        cls._verify_cas_object(target, expected_sha256, expected_size)
        if remove_source:
            cls._remove_source_after_publish(temp_path, target)
        target.chmod(stat.S_IREAD)
        cls._sync_existing_cas_object(target)

    @classmethod
    def _sync_existing_cas_object(cls, target: Path) -> None:
        if os.name != "nt":
            with target.open("rb") as published:
                os.fsync(published.fileno())
        cls._sync_cas_directories(target)

    @staticmethod
    def _seal_and_sync_published_object(
        target: Path,
        *,
        published_descriptor: int,
    ) -> None:
        """Persist object bytes/mode and the CAS directory entries on POSIX."""
        # The descriptor was opened before the create-only link became visible,
        # so a concurrent loser sealing the target cannot revoke this handle.
        target.chmod(stat.S_IREAD)
        os.fsync(published_descriptor)
        ContentAddressedStore._sync_cas_directories(target)

    @staticmethod
    def _sync_cas_directories(target: Path) -> None:
        if os.name == "nt":
            return
        # target lives at root/objects/sha256/aa/bb/digest. Sync every
        # directory entry through the configured, pre-existing storage root.
        flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
        for directory in (
            target.parent,
            target.parent.parent,
            target.parent.parent.parent,
            target.parent.parent.parent.parent,
            target.parent.parent.parent.parent.parent,
        ):
            descriptor = os.open(directory, flags)
            try:
                os.fsync(descriptor)
            finally:
                os.close(descriptor)

    @staticmethod
    def _remove_source_after_publish(source: Path, target: Path) -> None:
        """Remove a private source alias without leaving a CAS winner writable."""
        try:
            source.unlink(missing_ok=True)
            return
        except PermissionError:
            pass
        same_object = False
        try:
            same_object = target.is_file() and os.path.samefile(source, target)
        except OSError:
            pass
        source.chmod(stat.S_IREAD | stat.S_IWRITE)
        try:
            source.unlink(missing_ok=True)
        finally:
            if same_object and target.exists():
                target.chmod(stat.S_IREAD)

    @staticmethod
    def _verify_cas_object(path: Path, expected_sha256: str, expected_size: int) -> None:
        if path.is_symlink() or not path.is_file():
            raise RuntimeError(f"Invalid content-addressed object: {path}")
        if path.stat().st_size != expected_size:
            raise RuntimeError(
                f"Content-addressed object size mismatch: {path}"
            )
        hasher = hashlib.sha256()
        with path.open("rb") as source:
            while chunk := source.read(4 * 1024 * 1024):
                hasher.update(chunk)
        if hasher.hexdigest() != expected_sha256:
            raise RuntimeError(
                f"Content-addressed object checksum mismatch: {path}"
            )

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
            try:
                checkpoint_path.unlink()
            except PermissionError:
                checkpoint_path.chmod(stat.S_IREAD | stat.S_IWRITE)
                checkpoint_path.unlink()
            if published_target.exists():
                published_target.chmod(stat.S_IREAD)
            os.replace(detached_path, checkpoint_path)
        finally:
            detached_path.unlink(missing_ok=True)
