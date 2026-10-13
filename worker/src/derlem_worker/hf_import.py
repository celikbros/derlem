"""HF veri seti alimi (TASK-032): sabit surum, uyarlayici, secici sutun okuma, devam.

Akis (docs/hf_ice_alim.md):

1. Uyarlayici yuklenir ve dogrulanir (adapters.py). ``revision`` 40 haneli commit
   SHA'si olmak zorundadir (dal adi sabit surum degildir).
2. Veri seti karti (README.md) sabit surumden okunur: lisans kimligi ve kartin
   SHA256'si manifeste girer; ``configs`` bolumunden config/split'in dosya
   kaliplari bulunur.
3. HF agac API'sinden sabit surumdeki dosya listesi (yol, boyut, LFS SHA256,
   xet hash) alinir ve ``import-manifest.draft.json``'a yazilir.
4. Parquet: her dosyanin altbilgisi (footer) HTTP Range ile okunur; yalniz
   uyarlayicinin okudugu sutunlarin parcalari satir grubu satir grubu Range ile
   cekilir. Atlanan sutunlarin (``embeddings``) bayt araliklari yasaktir: oraya
   dusen bir okuma isi durdurur (indirilmez). JSONL/TSV: dosyanin tamami indirilir,
   boyut + SHA (LFS SHA256 ya da git blob SHA1) dogrulanir.
5. Satirlar uyarlayicidan ``derlem.document.v1`` kaydina gecer; bir kaynak dosya =
   bir parca (``DocumentShardWriter.cut``). Parca depoya yayimlanir.
6. Her parca bittiginde defter (``ledger.jsonl``) atomik olarak yeniden yazilir:
   parca SHA256, satir sayisi, indirilen bayt, istek sayisi. Devam: defterde olan
   ve depoda/diskte SHA'si tutan parca atlanir; yarim dosya bastan alinir.
7. Sonda ``import-manifest.json`` (belirlenimci: zaman, sure, yerel yol yok)
   yazilir ve depoya yayimlanir; kaynagin nesnesi bu manifesttir.

HF_TOKEN yalniz ortam degiskeninden okunur ve yalniz hub alan adina gonderilir
(CDN yonlendirmesine gonderilmez). 429/5xx ve baglanti hatalari ustel beklemeyle
yeniden denenir (Retry-After varsa ona uyulur).
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field, replace
import fnmatch
import hashlib
import http.client
import io
import json
import os
from pathlib import Path
import re
import socket
import threading
import time
from typing import Any, Callable, Iterable, Mapping, Sequence
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, quote, urljoin, urlsplit
import urllib.request

import pyarrow as pa
import pyarrow.parquet as pq
import yaml

from derlem_worker.adapters import (
    Adapter,
    AdapterError,
    AdapterReport,
    adapt_file,
    adapt_rows,
    load_adapter,
    new_report,
)
from derlem_worker.document_record import (
    DEFAULT_ROW_GROUP_SIZE,
    DOCUMENT_SCHEMA_VERSION,
    SHARD_COMPRESSION,
    SHARD_COMPRESSION_LEVEL,
    SHARD_WRITER_PYARROW_VERSION,
    DocumentShardWriter,
    ParquetFileInfo,
    file_sha256,
    publish_parquet,
)
from derlem_worker.import_manifest import IMPORT_MANIFEST_SCHEMA, storage_key_for

DEFAULT_HUB_ENDPOINT = "https://huggingface.co"
DEFAULT_DATASETS_SERVER = "https://datasets-server.huggingface.co"
LEDGER_SCHEMA = "derlem.import-ledger.v1"
DRAFT_SCHEMA = "derlem.import-manifest-draft.v1"
USER_AGENT = "derlem-import/1.0 (+TASK-032)"
RETRY_STATUSES = frozenset({429, 500, 502, 503, 504})
REDIRECT_STATUSES = frozenset({301, 302, 303, 307, 308})
FORMAT_EXTENSIONS = {"parquet": (".parquet",), "jsonl": (".jsonl", ".json"), "tsv": (".tsv",)}
_COMMIT_RE = re.compile(r"^[0-9a-f]{40}$")
# Imzali CDN adresinin suresi dolmadan bu kadar once yeniden cozulur.
_URL_REFRESH_MARGIN_SECONDS = 120.0

ProgressCallback = Callable[[dict[str, Any]], None]


class HFImportError(RuntimeError):
    pass


# --------------------------------------------------------------------------
# HTTP: yeniden deneme, token yalniz hub'a, sayaclar
# --------------------------------------------------------------------------


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):  # noqa: ANN001
        return None


@dataclass
class HttpResponse:
    status: int
    headers: dict[str, str]
    body: bytes
    url: str


class HttpClient:
    """Kucuk HTTP istemcisi: yonlendirmeleri elle izler (token alan adi disina cikmaz),
    429/5xx ve baglanti hatalarini ustel beklemeyle yeniden dener, istek/bayt sayar."""

    def __init__(
        self,
        *,
        hub_endpoint: str = DEFAULT_HUB_ENDPOINT,
        timeout: float = 120.0,
        max_attempts: int = 7,
        backoff_base: float = 1.0,
        backoff_cap: float = 60.0,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        token = os.environ.get("HF_TOKEN", "").strip()
        self._token = token or None
        self.hub_netloc = urlsplit(hub_endpoint).netloc.lower()
        self.timeout = timeout
        self.max_attempts = max(1, max_attempts)
        self.backoff_base = backoff_base
        self.backoff_cap = backoff_cap
        self._sleep = sleep
        self._opener = urllib.request.build_opener(_NoRedirect)
        self._lock = threading.Lock()
        self.requests = 0
        self.bytes_received = 0
        self.retries = 0

    @property
    def authenticated(self) -> bool:
        return self._token is not None

    def _count(self, *, requests: int = 0, received: int = 0, retries: int = 0) -> None:
        with self._lock:
            self.requests += requests
            self.bytes_received += received
            self.retries += retries

    def _headers(self, url: str, extra: Mapping[str, str] | None) -> dict[str, str]:
        headers = {"User-Agent": USER_AGENT, "Accept-Encoding": "identity"}
        if self._token is not None and urlsplit(url).netloc.lower() == self.hub_netloc:
            headers["Authorization"] = f"Bearer {self._token}"
        if extra:
            headers.update(extra)
        return headers

    def _delay(self, attempt: int, retry_after: str | None) -> float:
        if retry_after:
            try:
                return min(self.backoff_cap, max(0.0, float(retry_after)))
            except ValueError:
                pass
        return min(self.backoff_cap, self.backoff_base * (2**attempt))

    def send(
        self,
        url: str,
        *,
        headers: Mapping[str, str] | None = None,
        range_request: bool = False,
        stream_to: Callable[[bytes], None] | None = None,
    ) -> HttpResponse:
        """Tek istek (yonlendirme izlenmez), gecici hatalarda yeniden denenir.

        ``range_request``: sunucu Range'i yok sayip 200 donerse govde OKUNMAZ
        (dosyanin tamamini, atlanan sutunlar dahil, indirmemek icin) ve hata verilir.
        """
        last_error: str | None = None
        for attempt in range(self.max_attempts):
            request = urllib.request.Request(url, headers=self._headers(url, headers))
            self._count(requests=1)
            retry_after = None
            try:
                response = self._opener.open(request, timeout=self.timeout)
            except HTTPError as error:
                status = error.code
                response_headers = {key.lower(): value for key, value in error.headers.items()}
                if status in RETRY_STATUSES:
                    error.close()
                    last_error = f"HTTP {status}"
                    retry_after = response_headers.get("retry-after")
                elif status in REDIRECT_STATUSES:
                    error.close()
                    return HttpResponse(status, response_headers, b"", url)
                else:
                    body = error.read(4096)
                    error.close()
                    return HttpResponse(status, response_headers, body, url)
            except (URLError, TimeoutError, socket.timeout, ConnectionError, http.client.HTTPException, OSError) as error:
                last_error = f"{type(error).__name__}: {error}"
            else:
                with response:
                    status = response.status
                    response_headers = {key.lower(): value for key, value in response.headers.items()}
                    if range_request and status == 200:
                        raise HFImportError(f"server ignored the Range header for {_redact(url)}; refusing a full download")
                    try:
                        if stream_to is not None:
                            received = 0
                            while chunk := response.read(1024 * 1024):
                                received += len(chunk)
                                self._count(received=len(chunk))
                                stream_to(chunk)
                            return HttpResponse(status, response_headers, b"", url)
                        body = response.read()
                    except (TimeoutError, socket.timeout, ConnectionError, http.client.HTTPException, OSError) as error:
                        last_error = f"{type(error).__name__}: {error}"
                        if stream_to is not None:
                            raise _StreamInterrupted(last_error) from error
                    else:
                        self._count(received=len(body))
                        return HttpResponse(status, response_headers, body, url)
            if attempt + 1 >= self.max_attempts:
                break
            self._count(retries=1)
            self._sleep(self._delay(attempt, retry_after))
        raise HFImportError(f"request failed after {self.max_attempts} attempts: {_redact(url)} ({last_error})")

    def get(self, url: str, *, headers: Mapping[str, str] | None = None, max_redirects: int = 5) -> HttpResponse:
        """Yonlendirmeleri izleyen GET; Authorization yalniz hub alan adina gider."""
        current = url
        for _ in range(max_redirects + 1):
            response = self.send(current, headers=headers)
            if response.status in REDIRECT_STATUSES:
                location = response.headers.get("location")
                if not location:
                    raise HFImportError(f"redirect without location: {_redact(current)}")
                current = urljoin(current, location)
                continue
            return response
        raise HFImportError(f"too many redirects: {_redact(url)}")


class _StreamInterrupted(HFImportError):
    pass


def _redact(url: str) -> str:
    parts = urlsplit(url)
    return f"{parts.scheme}://{parts.netloc}{parts.path}"


# --------------------------------------------------------------------------
# Hub: kart, agac, dosya cozumleme
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class RemoteFile:
    path: str
    size: int
    git_oid: str | None
    lfs_sha256: str | None
    xet_hash: str | None

    def to_dict(self) -> dict[str, Any]:
        return {
            "path": self.path,
            "size": self.size,
            "git_oid": self.git_oid,
            "lfs_sha256": self.lfs_sha256,
            "xet_hash": self.xet_hash,
        }


@dataclass
class ResolvedUrl:
    url: str
    expires_at: float | None


class HubClient:
    def __init__(self, http: HttpClient, *, hub_endpoint: str, dataset: str, revision: str) -> None:
        self.http = http
        self.hub = hub_endpoint.rstrip("/")
        self.dataset = dataset
        self.revision = revision

    def resolve_url(self, path: str) -> str:
        return f"{self.hub}/datasets/{self.dataset}/resolve/{self.revision}/{quote(path)}"

    def fetch_card(self) -> bytes | None:
        response = self.http.get(self.resolve_url("README.md"))
        if response.status == 404:
            return None
        if response.status != 200:
            raise HFImportError(f"dataset card fetch failed: HTTP {response.status}")
        return response.body

    def list_tree(self, prefix: str) -> list[RemoteFile]:
        url = f"{self.hub}/api/datasets/{self.dataset}/tree/{self.revision}"
        if prefix:
            url += "/" + quote(prefix)
        url += "?recursive=true&expand=false"
        files: list[RemoteFile] = []
        pages = 0
        while url:
            pages += 1
            if pages > 1000:
                raise HFImportError("tree listing does not terminate")
            response = self.http.get(url)
            if response.status != 200:
                raise HFImportError(f"tree listing failed: HTTP {response.status}")
            try:
                entries = json.loads(response.body.decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError) as error:
                raise HFImportError("tree listing is not JSON") from error
            if not isinstance(entries, list):
                raise HFImportError("tree listing is not a list")
            for entry in entries:
                if not isinstance(entry, dict) or entry.get("type") != "file":
                    continue
                lfs = entry.get("lfs") if isinstance(entry.get("lfs"), dict) else {}
                files.append(
                    RemoteFile(
                        path=str(entry["path"]),
                        size=int(entry["size"]),
                        git_oid=entry.get("oid"),
                        lfs_sha256=lfs.get("oid"),
                        xet_hash=entry.get("xetHash"),
                    )
                )
            url = _next_link(response.headers.get("link"), url)
        return files

    def resolve_file(self, remote: RemoteFile) -> ResolvedUrl:
        """Sabit surumdeki dosyanin indirme adresi; boyut, LFS SHA ve commit dogrulanir."""
        url = self.resolve_url(remote.path)
        response = self.http.send(url, headers={"Range": "bytes=0-0"}, range_request=True)
        commit = response.headers.get("x-repo-commit")
        if commit is not None and commit != self.revision:
            raise HFImportError(f"hub served commit {commit} for pinned revision {self.revision}")
        linked_size = response.headers.get("x-linked-size")
        if linked_size is not None and int(linked_size) != remote.size:
            raise HFImportError(f"{remote.path}: size {linked_size} != tree size {remote.size}")
        linked_etag = (response.headers.get("x-linked-etag") or "").strip('"').removeprefix("W/").strip('"')
        if linked_etag and remote.lfs_sha256 and linked_etag != remote.lfs_sha256:
            raise HFImportError(f"{remote.path}: etag {linked_etag} != LFS sha256 {remote.lfs_sha256}")
        if response.status in REDIRECT_STATUSES:
            location = response.headers.get("location")
            if not location:
                raise HFImportError(f"{remote.path}: redirect without location")
            target = urljoin(url, location)
            return ResolvedUrl(target, _expiry_from_url(target))
        if response.status != 206:
            raise HFImportError(f"{remote.path}: resolve failed: HTTP {response.status}")
        _check_content_range(response.headers, 0, 0, remote.size)
        return ResolvedUrl(url, None)


def _next_link(header: str | None, current: str) -> str | None:
    if not header:
        return None
    for part in header.split(","):
        match = re.match(r'\s*<([^>]+)>\s*;\s*rel="?next"?', part)
        if match:
            return urljoin(current, match.group(1))
    return None


def _expiry_from_url(url: str) -> float | None:
    query = parse_qs(urlsplit(url).query)
    for key in ("Expires", "X-Amz-Expires-At"):
        values = query.get(key)
        if values:
            try:
                return float(values[0])
            except ValueError:
                return None
    return None


def _check_content_range(headers: Mapping[str, str], start: int, end: int, total: int) -> None:
    value = headers.get("content-range", "")
    match = re.fullmatch(r"bytes (\d+)-(\d+)/(\d+|\*)", value.strip())
    if not match:
        raise HFImportError(f"missing or invalid Content-Range: {value!r}")
    if int(match.group(1)) != start or int(match.group(2)) != end:
        raise HFImportError(f"Content-Range {value!r} does not match the requested bytes {start}-{end}")
    if match.group(3) != "*" and int(match.group(3)) != total:
        raise HFImportError(f"remote file size changed: Content-Range total {match.group(3)} != {total}")


def parse_card(card: bytes | None) -> dict[str, Any]:
    if card is None:
        return {}
    text = card.decode("utf-8", errors="replace")
    if not text.startswith("---"):
        return {}
    end = text.find("\n---", 3)
    if end < 0:
        return {}
    try:
        value = yaml.safe_load(text[3:end])
    except yaml.YAMLError:
        return {}
    return value if isinstance(value, dict) else {}


def data_file_patterns(card_meta: Mapping[str, Any], config: str | None, split: str | None) -> list[str] | None:
    """Kartin ``configs`` bolumunden config/split icin dosya kaliplari; yoksa None."""
    configs = card_meta.get("configs")
    if not isinstance(configs, list):
        return None
    wanted = config or "default"
    for entry in configs:
        if not isinstance(entry, dict) or entry.get("config_name") != wanted:
            continue
        data_files = entry.get("data_files")
        if isinstance(data_files, str):
            return [data_files]
        if isinstance(data_files, list):
            patterns: list[str] = []
            for item in data_files:
                if isinstance(item, str):
                    patterns.append(item)
                elif isinstance(item, dict) and (split is None or item.get("split") == split):
                    path = item.get("path")
                    patterns.extend([path] if isinstance(path, str) else [p for p in path or [] if isinstance(p, str)])
            return patterns or None
    return None


def _pattern_prefix(pattern: str) -> str:
    parts = []
    for part in pattern.split("/"):
        if any(ch in part for ch in "*?["):
            break
        parts.append(part)
    if parts and parts == pattern.split("/"):
        parts = parts[:-1]
    return "/".join(parts)


def select_files(
    hub: HubClient,
    adapter: Adapter,
    card_meta: Mapping[str, Any],
    only_files: Sequence[str] | None,
) -> tuple[list[RemoteFile], list[str]]:
    patterns = data_file_patterns(card_meta, adapter.config, adapter.split)
    if patterns is None:
        patterns = [f"{adapter.config}/**" if adapter.config else "**"]
    prefixes = sorted({_pattern_prefix(pattern) for pattern in patterns})
    # Ic ice onekler tek listelemeyle kapsanir.
    roots = [p for p in prefixes if not any(p != q and (q == "" or p.startswith(q + "/")) for q in prefixes)]
    extensions = FORMAT_EXTENSIONS[adapter.format]
    seen: dict[str, RemoteFile] = {}
    for root in roots:
        for remote in hub.list_tree(root):
            if not remote.path.lower().endswith(extensions):
                continue
            if any(fnmatch.fnmatchcase(remote.path, pattern) for pattern in patterns):
                seen[remote.path] = remote
    files = [seen[path] for path in sorted(seen)]
    if only_files is not None:
        wanted = list(dict.fromkeys(only_files))
        missing = [path for path in wanted if path not in seen]
        if missing:
            raise HFImportError(f"requested files are not in the pinned revision's data files: {missing}")
        files = [remote for remote in files if remote.path in set(wanted)]
    if not files:
        raise HFImportError(f"no {adapter.format} data files matched {patterns} at revision {adapter.revision}")
    return files, patterns


def datasets_server_rows(http: HttpClient, base: str | None, adapter: Adapter) -> dict[str, Any]:
    """Bilgi amacli capraz kontrol (datasets-server ana dali izler; manifeste girmez)."""
    if not base:
        return {"status": "skipped"}
    url = f"{base.rstrip('/')}/size?dataset={quote(adapter.dataset, safe='')}"
    if adapter.config:
        url += f"&config={quote(adapter.config, safe='')}"
    try:
        response = http.get(url)
        if response.status != 200:
            return {"status": "unavailable", "http_status": response.status}
        value = json.loads(response.body.decode("utf-8"))
        for split in value.get("size", {}).get("splits", []):
            if adapter.split is None or split.get("split") == adapter.split:
                return {
                    "status": "ok",
                    "num_rows": split.get("num_rows"),
                    "num_bytes_parquet_files": split.get("num_bytes_parquet_files"),
                    "partial": value.get("partial"),
                }
        return {"status": "split_not_listed"}
    except (HFImportError, ValueError, KeyError, AttributeError) as error:
        return {"status": "error", "error": str(error)[:200]}


# --------------------------------------------------------------------------
# Range ile okunan uzak dosya (pyarrow icin)
# --------------------------------------------------------------------------


@dataclass
class FileTransferStats:
    requests: int = 0
    bytes: int = 0
    ranges: list[tuple[int, int]] = field(default_factory=list)
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)

    def add(self, start: int, length: int) -> None:
        with self._lock:
            self.requests += 1
            self.bytes += length
            self.ranges.append((start, length))


class RemoteRangeFile(io.RawIOBase):
    """Salt okunur, aranabilir uzak dosya; her ag okumasi tek HTTP Range istegi.

    ``forbidden``: atlanan sutun parcalarinin [bas, son) araliklari. Bunlarla kesisen
    bir ag okumasi istek gonderilmeden HFImportError verir: atlanan sutunun tek
    bayti indirilmez. ``prefetch`` ile cekilen bloklar onbellekten servis edilir.
    """

    def __init__(
        self,
        http: HttpClient,
        resolver: Callable[[bool], ResolvedUrl],
        size: int,
        stats: FileTransferStats,
    ) -> None:
        super().__init__()
        self.http = http
        self._resolver = resolver
        self.size = size
        self.stats = stats
        self.pos = 0
        self.forbidden: list[tuple[int, int]] = []
        self._blocks: list[tuple[int, bytes]] = []

    def readable(self) -> bool:
        return True

    def seekable(self) -> bool:
        return True

    def tell(self) -> int:
        return self.pos

    def seek(self, offset: int, whence: int = io.SEEK_SET) -> int:
        if whence == io.SEEK_SET:
            self.pos = offset
        elif whence == io.SEEK_CUR:
            self.pos += offset
        else:
            self.pos = self.size + offset
        return self.pos

    def _fetch(self, start: int, end_exclusive: int) -> bytes:
        for low, high in self.forbidden:
            if start < high and low < end_exclusive:
                raise HFImportError(
                    f"read {start}-{end_exclusive} overlaps a skipped column chunk {low}-{high}; refusing to download it"
                )
        last = end_exclusive - 1
        refreshed = False
        while True:
            resolved = self._resolver(refreshed)
            response = self.http.send(resolved.url, headers={"Range": f"bytes={start}-{last}"}, range_request=True)
            if response.status in (401, 403, 410) and not refreshed:
                # Imzali CDN adresinin suresi dolmus olabilir: bir kez yeniden coz.
                refreshed = True
                continue
            if response.status != 206:
                raise HFImportError(f"range read failed: HTTP {response.status}")
            _check_content_range(response.headers, start, last, self.size)
            if len(response.body) != end_exclusive - start:
                raise HFImportError(f"short range read: {len(response.body)} of {end_exclusive - start} bytes")
            self.stats.add(start, len(response.body))
            return response.body

    def prefetch(self, ranges: Iterable[tuple[int, int]]) -> None:
        self._blocks = [(start, self._fetch(start, end)) for start, end in ranges]

    def clear(self) -> None:
        self._blocks = []

    def read(self, n: int = -1) -> bytes:
        if n is None or n < 0:
            n = self.size - self.pos
        n = min(n, self.size - self.pos)
        if n <= 0:
            return b""
        start, end = self.pos, self.pos + n
        for block_start, block in self._blocks:
            if block_start <= start and end <= block_start + len(block):
                data = block[start - block_start : end - block_start]
                break
        else:
            data = self._fetch(start, end)
        self.pos = end
        return data

    def readinto(self, buffer) -> int:  # noqa: ANN001
        data = self.read(len(buffer))
        buffer[: len(data)] = data
        return len(data)


def read_remote_metadata(reader: RemoteRangeFile) -> pq.FileMetaData:
    """Parquet altbilgisi tam iki Range istegiyle: son 8 bayt (uzunluk + PAR1), sonra altbilgi.

    pyarrow'un kendi okumasi dosyanin son 64 KB'sini ister; kucuk dosyalarda bu
    atlanan sutunlarin baytlarini da kapsardi. Burada yalniz altbilgi cekilir.
    """
    if reader.size < 12:
        raise HFImportError("remote file is too small to be parquet")
    tail = reader._fetch(reader.size - 8, reader.size)
    if tail[4:] != b"PAR1":
        raise HFImportError("remote file is not parquet (missing PAR1 footer magic)")
    length = int.from_bytes(tail[:4], "little")
    if length <= 0 or length > reader.size - 12:
        raise HFImportError("invalid parquet footer length")
    footer = reader._fetch(reader.size - 8 - length, reader.size - 8)
    return pq.read_metadata(pa.BufferReader(b"PAR1" + footer + tail))


def _chunk_range(column) -> tuple[int, int]:  # noqa: ANN001
    start = column.data_page_offset
    if column.has_dictionary_page and column.dictionary_page_offset is not None and 0 < column.dictionary_page_offset < start:
        start = column.dictionary_page_offset
    return start, start + column.total_compressed_size


def _top_level(column) -> str:  # noqa: ANN001
    return column.path_in_schema.split(".")[0]


def column_chunk_ranges(metadata: pq.FileMetaData, row_group: int, names: set[str]) -> list[tuple[int, int]]:
    group = metadata.row_group(row_group)
    return sorted(
        _chunk_range(group.column(index))
        for index in range(group.num_columns)
        if _top_level(group.column(index)) in names
    )


def coalesce(ranges: Sequence[tuple[int, int]], forbidden: Sequence[tuple[int, int]]) -> list[tuple[int, int]]:
    """Bitisik/ust uste araliklari birlestirir; aradaki bosluk yasak bayt icerirse birlestirmez."""
    merged: list[tuple[int, int]] = []
    for start, end in sorted(ranges):
        if merged:
            last_start, last_end = merged[-1]
            if start <= last_end:
                merged[-1] = (last_start, max(last_end, end))
                continue
            gap_forbidden = any(low < start and last_end < high for low, high in forbidden)
            if start - last_end <= 4096 and not gap_forbidden:
                merged[-1] = (last_start, max(last_end, end))
                continue
        merged.append((start, end))
    return merged


# --------------------------------------------------------------------------
# Defter (ledger) ve manifest
# --------------------------------------------------------------------------


def _canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _write_atomic(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(f".{path.name}.{os.getpid()}.{threading.get_ident()}.tmp")
    with temp.open("wb") as handle:
        handle.write(data)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temp, path)


class Ledger:
    """JSONL defter: ilk satir baslik (alim kimligi), sonra dosya basina bir satir.

    Her guncellemede dosyanin tamami gecici dosyaya yazilip yerine konur (atomik):
    yarim satir kalmaz.
    """

    def __init__(self, path: Path, header: dict[str, Any]) -> None:
        self.path = path
        self.header = header
        self.entries: dict[int, dict[str, Any]] = {}
        if path.exists():
            lines = [line for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
            if lines:
                existing = json.loads(lines[0])
                if existing.get("identity") != header.get("identity"):
                    raise HFImportError(
                        f"ledger {path} belongs to a different import (dataset/revision/adapter/files differ); "
                        "use a fresh work directory"
                    )
                for line in lines[1:]:
                    entry = json.loads(line)
                    self.entries[int(entry["file_index"])] = entry
        self._flush()

    def _flush(self) -> None:
        lines = [_canonical_json(self.header)]
        lines.extend(_canonical_json(self.entries[index]) for index in sorted(self.entries))
        _write_atomic(self.path, ("\n".join(lines) + "\n").encode("utf-8"))

    def put(self, entry: dict[str, Any]) -> None:
        self.entries[int(entry["file_index"])] = entry
        self._flush()

    def drop(self, index: int) -> None:
        if self.entries.pop(index, None) is not None:
            self._flush()


def merge_reports(adapter: Adapter, reports: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    merged = new_report(adapter).to_dict()
    for report in reports:
        merged["files"].extend(report["files"])
        for key in ("records_seen", "documents", "blank_lines", "empty_text", "oversized", "invalid_records"):
            merged[key] += report[key]
        for key in ("empty_text_ordinals", "oversized_ordinals", "invalid_samples"):
            merged[key] = (merged[key] + list(report[key]))[:100]
        for key in ("skipped_columns", "unlisted_columns"):
            merged[key] = sorted(set(merged[key]) | set(report[key]))
        for name, count in report["missing_signal_values"].items():
            merged["missing_signal_values"][name] = merged["missing_signal_values"].get(name, 0) + count
    merged["missing_signal_values"] = dict(sorted(merged["missing_signal_values"].items()))
    merged["ok"] = merged["invalid_records"] == 0
    return merged


def column_classes(adapter: Adapter) -> Callable[[str], str]:
    text_column = adapter.text_column
    skipped = set(adapter.columns_skipped)

    def classify(name: str) -> str:
        if name == text_column:
            return "text"
        if name in skipped:
            return "skipped"
        return "metadata"

    return classify


def build_manifest(
    *,
    adapter: Adapter,
    files: Sequence[RemoteFile],
    entries: Sequence[Mapping[str, Any]],
    card_sha256: str | None,
    licence_id: str | None,
    patterns: Sequence[str],
    max_row_groups: int | None,
) -> dict[str, Any]:
    """Belirlenimci manifest: ayni surum + uyarlayici + parametre -> ayni bayt."""
    classify = column_classes(adapter)
    bytes_by_class = {"text": 0, "metadata": 0, "skipped": 0}
    source_files = []
    shards = []
    for remote, entry in zip(files, entries):
        for name, size in entry["column_bytes"].items():
            bytes_by_class[classify(name)] += size
        source_files.append({
            **remote.to_dict(),
            "num_rows": entry["num_rows"],
            "row_groups": entry["row_groups"],
            "row_groups_read": entry["row_groups_read"],
            "records_seen": entry["records_seen"],
            "column_bytes": dict(sorted(entry["column_bytes"].items())),
        })
        shard = entry.get("shard")
        if shard is not None:
            shards.append({
                "file": remote.path,
                "sha256": shard["sha256"],
                "byte_size": shard["byte_size"],
                "row_count": shard["row_count"],
                "row_groups": shard["row_groups"],
                "first_source_ordinal": shard["first_source_ordinal"],
                "last_source_ordinal": shard["last_source_ordinal"],
                "text_utf8_bytes": shard["text_utf8_bytes"],
            })
    report = merge_reports(adapter, [entry["report"] for entry in entries])
    return {
        "schema": IMPORT_MANIFEST_SCHEMA,
        "dataset": adapter.dataset,
        "revision": adapter.revision,
        "config": adapter.config,
        "split": adapter.split,
        "format": adapter.format,
        "data_file_patterns": list(patterns),
        "max_row_groups_per_file": max_row_groups,
        "adapter": {
            **adapter.to_dict(),
            "columns_read": list(adapter.columns_read),
            "columns_skipped": list(adapter.columns_skipped),
        },
        "document_schema": DOCUMENT_SCHEMA_VERSION,
        "shard_writer": {
            "pyarrow": SHARD_WRITER_PYARROW_VERSION,
            "compression": SHARD_COMPRESSION,
            "compression_level": SHARD_COMPRESSION_LEVEL,
            "one_shard_per_source_file": True,
        },
        "licence": {"id": licence_id, "card_path": "README.md", "card_sha256": card_sha256},
        "totals": {
            "source_files": len(source_files),
            "source_bytes": sum(remote.size for remote in files),
            "shards": len(shards),
            "shard_bytes": sum(shard["byte_size"] for shard in shards),
            "records_seen": report["records_seen"],
            "documents": report["documents"],
            "empty_text": report["empty_text"],
            "invalid_records": report["invalid_records"],
            "text_utf8_bytes": sum(shard["text_utf8_bytes"] for shard in shards),
            "bytes_by_column_class": bytes_by_class,
        },
        "source_files": source_files,
        "shards": shards,
        "adapter_report": report,
    }


def manifest_bytes(manifest: Mapping[str, Any]) -> bytes:
    # "schema" ilk anahtar kalir (tanima onekine bakilir); sira kod sabittir.
    return (json.dumps(manifest, ensure_ascii=False, indent=1) + "\n").encode("utf-8")


def lineage_summary(manifest: Mapping[str, Any], manifest_sha256: str, *, lineage_note: str | None = None) -> str:
    """Kaynak kaydinin lineage_ref'i: manifestin kisa ozeti (tek satir JSON)."""
    totals = manifest["totals"]
    summary = {
        "kind": "hf_dataset",
        "manifest_sha256": manifest_sha256,
        "dataset": manifest["dataset"],
        "revision": manifest["revision"],
        "config": manifest["config"],
        "split": manifest["split"],
        "columns_read": manifest["adapter"]["columns_read"],
        "columns_skipped": manifest["adapter"]["columns_skipped"],
        "adapter_sha256": manifest["adapter"]["sha256"],
        "records_seen": totals["records_seen"],
        "documents": totals["documents"],
        "shards": totals["shards"],
        "bytes_by_column_class": totals["bytes_by_column_class"],
        "licence_id": manifest["licence"]["id"],
        "card_sha256": manifest["licence"]["card_sha256"],
    }
    if lineage_note:
        summary["note"] = lineage_note
    return _canonical_json(summary)


# --------------------------------------------------------------------------
# Is
# --------------------------------------------------------------------------


@dataclass
class ImportResult:
    work_dir: Path
    manifest: dict[str, Any]
    manifest_path: Path
    manifest_sha256: str
    manifest_byte_size: int
    manifest_storage_key: str | None
    shards: list[dict[str, Any]]
    files_skipped_by_resume: int
    cross_check: dict[str, Any]
    run_stats: dict[str, Any]

    def lineage_ref(self, lineage_note: str | None = None) -> str:
        return lineage_summary(self.manifest, self.manifest_sha256, lineage_note=lineage_note)


@dataclass
class _RunCounters:
    started: float
    files_total: int
    files_done: int = 0
    files_skipped: int = 0
    shards_done: int = 0
    rows: int = 0
    bytes_downloaded: int = 0
    bytes_planned: int = 0
    last_emit: float = 0.0


def import_hf_dataset(
    adapter_path: Path,
    work_dir: Path,
    *,
    store=None,  # noqa: ANN001 - ContentAddressedStore | None
    hub_endpoint: str | None = None,
    datasets_server: str | None = DEFAULT_DATASETS_SERVER,
    only_files: Sequence[str] | None = None,
    max_row_groups: int | None = None,
    connections: int = 1,
    keep_local_shards: bool = True,
    progress_callback: ProgressCallback | None = None,
    progress_interval_seconds: float = 2.0,
    http: HttpClient | None = None,
    rows_per_row_group: int = DEFAULT_ROW_GROUP_SIZE,
) -> ImportResult:
    """Uyarlayicinin tanimladigi HF veri setini sabit surumden alir (bkz. modul belgesi).

    ``store`` verilirse parcalar ve manifest depoya yayimlanir; verilmezse (kuru
    kosu) parcalar ``work_dir/shards`` altinda kalir. ``only_files`` /
    ``max_row_groups`` kuru kosu icindir ve manifestte yazilidir.
    """
    hub_endpoint = (hub_endpoint or os.environ.get("HF_ENDPOINT") or DEFAULT_HUB_ENDPOINT).rstrip("/")
    if connections < 1 or connections > 8:
        raise ValueError("connections must be between 1 and 8")
    if max_row_groups is not None and max_row_groups < 1:
        raise ValueError("max_row_groups must be positive")
    adapter = load_adapter(adapter_path)
    if adapter.target != DOCUMENT_SCHEMA_VERSION:
        raise HFImportError("import_hf_dataset writes derlem.document.v1; canonical-sample adapters are not supported yet")
    if not _COMMIT_RE.match(adapter.revision):
        raise HFImportError(f"adapter revision must be a 40-hex commit SHA (pinned), got {adapter.revision!r}")
    if max_row_groups is not None and adapter.format != "parquet":
        raise HFImportError("max_row_groups applies to parquet sources only")

    http = http or HttpClient(hub_endpoint=hub_endpoint)
    hub = HubClient(http, hub_endpoint=hub_endpoint, dataset=adapter.dataset, revision=adapter.revision)
    started = time.monotonic()
    requests_before, bytes_before = http.requests, http.bytes_received

    card = hub.fetch_card()
    card_meta = parse_card(card)
    card_sha256 = hashlib.sha256(card).hexdigest() if card is not None else None
    licence = card_meta.get("license")
    licence_id = licence if isinstance(licence, str) else (",".join(map(str, licence)) if isinstance(licence, list) else None)
    files, patterns = select_files(hub, adapter, card_meta, only_files)
    cross_check = datasets_server_rows(http, datasets_server, adapter)

    work_dir = work_dir.resolve()
    shards_dir = work_dir / "shards"
    shards_dir.mkdir(parents=True, exist_ok=True)
    for leftover in list(shards_dir.glob("*.tmp")) + list(shards_dir.glob("tmp-*.parquet")):
        leftover.unlink(missing_ok=True)

    identity = {
        "dataset": adapter.dataset,
        "revision": adapter.revision,
        "config": adapter.config,
        "split": adapter.split,
        "adapter_sha256": adapter.sha256,
        "document_schema": DOCUMENT_SCHEMA_VERSION,
        "shard_writer_pyarrow": SHARD_WRITER_PYARROW_VERSION,
        "max_row_groups_per_file": max_row_groups,
        "card_sha256": card_sha256,
        "files": [remote.to_dict() for remote in files],
        "publish": store is not None,
    }
    draft = {
        "schema": DRAFT_SCHEMA,
        "identity": identity,
        "data_file_patterns": patterns,
        "licence_id": licence_id,
        "datasets_server": cross_check,
    }
    _write_atomic(work_dir / "import-manifest.draft.json", (json.dumps(draft, ensure_ascii=False, indent=1) + "\n").encode("utf-8"))
    ledger = Ledger(work_dir / "ledger.jsonl", {"kind": "header", "schema": LEDGER_SCHEMA, "identity": identity})

    counters = _RunCounters(started=started, files_total=len(files))

    def emit(event: str, force: bool = False, **extra: Any) -> None:
        if progress_callback is None:
            return
        now = time.monotonic()
        if not force and now - counters.last_emit < progress_interval_seconds:
            return
        counters.last_emit = now
        elapsed = max(now - counters.started, 1e-9)
        downloaded = http.bytes_received - bytes_before
        progress_callback({
            "event": event,
            "files_done": counters.files_done,
            "files_total": counters.files_total,
            "files_skipped_by_resume": counters.files_skipped,
            "shards_done": counters.shards_done,
            "rows_read": counters.rows,
            "bytes_downloaded": downloaded,
            "mb_downloaded": round(downloaded / 1e6, 1),
            "mb_per_s": round(downloaded / 1e6 / elapsed, 2),
            "requests": http.requests - requests_before,
            "retries": http.retries,
            **extra,
        })

    next_ordinal = 1
    entries: list[dict[str, Any]] = []
    for index, remote in enumerate(files):
        entry = ledger.entries.get(index)
        if entry is not None and _entry_is_complete(entry, remote, store, shards_dir):
            counters.files_skipped += 1
            counters.files_done += 1
            if entry.get("shard") is not None:
                counters.shards_done += 1
            next_ordinal += int(entry["records_seen"])
            entries.append(entry)
            emit("file_skipped", force=True, file=remote.path)
            continue
        if entry is not None:
            ledger.drop(index)
        file_started = time.monotonic()
        if adapter.format == "parquet":
            entry = _import_parquet_file(
                adapter, hub, http, remote, index, next_ordinal, shards_dir,
                max_row_groups=max_row_groups, connections=connections,
                rows_per_row_group=rows_per_row_group, counters=counters, emit=emit,
            )
        else:
            entry = _import_whole_file(
                adapter, hub, http, remote, index, next_ordinal, shards_dir,
                rows_per_row_group=rows_per_row_group, counters=counters,
            )
        entry["seconds"] = round(time.monotonic() - file_started, 3)
        shard = entry.get("shard")
        if shard is not None:
            local = shards_dir / shard["local_name"]
            if store is not None:
                info = ParquetFileInfo(
                    path=str(local), sha256=shard["sha256"], byte_size=shard["byte_size"],
                    row_count=shard["row_count"], row_groups=shard["row_groups"],
                    first_source_ordinal=shard["first_source_ordinal"],
                    last_source_ordinal=shard["last_source_ordinal"],
                )
                stored = publish_parquet(store, info)
                shard["storage_key"] = stored.storage_key
                if not keep_local_shards:
                    local.unlink(missing_ok=True)
            counters.shards_done += 1
        ledger.put(entry)
        counters.files_done += 1
        next_ordinal += int(entry["records_seen"])
        entries.append(entry)
        emit("file_done", force=True, file=remote.path, shard_sha256=(shard or {}).get("sha256"))

    manifest = build_manifest(
        adapter=adapter, files=files, entries=entries, card_sha256=card_sha256,
        licence_id=licence_id, patterns=patterns, max_row_groups=max_row_groups,
    )
    payload = manifest_bytes(manifest)
    manifest_sha256 = hashlib.sha256(payload).hexdigest()
    manifest_path = work_dir / "import-manifest.json"
    _write_atomic(manifest_path, payload)
    storage_key = None
    if store is not None:
        stored = store.ingest_bytes(payload)
        if stored.sha256 != manifest_sha256:
            raise HFImportError("published manifest does not match the written manifest")
        storage_key = stored.storage_key
    elapsed = time.monotonic() - started
    downloaded = http.bytes_received - bytes_before
    run_stats = {
        "seconds": round(elapsed, 3),
        "requests": http.requests - requests_before,
        "retries": http.retries,
        "bytes_downloaded": downloaded,
        "mb_per_s": round(downloaded / 1e6 / max(elapsed, 1e-9), 3),
        "connections": connections,
        "authenticated": http.authenticated,
    }
    emit("done", force=True)
    return ImportResult(
        work_dir=work_dir,
        manifest=manifest,
        manifest_path=manifest_path,
        manifest_sha256=manifest_sha256,
        manifest_byte_size=len(payload),
        manifest_storage_key=storage_key,
        shards=[entry["shard"] for entry in entries if entry.get("shard") is not None],
        files_skipped_by_resume=counters.files_skipped,
        cross_check=cross_check,
        run_stats=run_stats,
    )


def _entry_is_complete(entry: Mapping[str, Any], remote: RemoteFile, store, shards_dir: Path) -> bool:  # noqa: ANN001
    if entry.get("path") != remote.path or entry.get("size") != remote.size or entry.get("lfs_sha256") != remote.lfs_sha256:
        return False
    shard = entry.get("shard")
    if shard is None:
        return int(entry.get("documents", -1)) == 0
    if store is not None:
        candidate = store.root / storage_key_for(shard["sha256"])
    else:
        candidate = shards_dir / shard["local_name"]
    try:
        if candidate.stat().st_size != shard["byte_size"]:
            return False
    except OSError:
        return False
    digest, _ = file_sha256(candidate)
    return digest == shard["sha256"]


def _shard_entry(info: ParquetFileInfo, final_path: Path, text_bytes: int) -> dict[str, Any]:
    return {
        "local_name": final_path.name,
        "sha256": info.sha256,
        "byte_size": info.byte_size,
        "row_count": info.row_count,
        "row_groups": info.row_groups,
        "first_source_ordinal": info.first_source_ordinal,
        "last_source_ordinal": info.last_source_ordinal,
        "text_utf8_bytes": text_bytes,
    }


def _write_file_shard(
    records: Iterable[Mapping[str, Any]],
    shards_dir: Path,
    index: int,
    *,
    rows_hint: int,
    rows_per_row_group: int,
) -> tuple[dict[str, Any] | None, int]:
    """Bir kaynak dosyanin belgeleri -> tek parca (dosya sinirinda cut). Hata: yarim dosya silinir."""
    writer = DocumentShardWriter(
        shards_dir,
        rows_per_shard=max(1, rows_hint) + 1,
        row_group_size=rows_per_row_group,
        prefix=f"tmp-{index:05d}",
    )
    text_bytes = 0
    documents = 0
    try:
        for record in records:
            writer.add(record)
            text_bytes += len(record["text"].encode("utf-8"))
            documents += 1
        writer.cut()
    except BaseException:
        writer.abort()
        for info in writer.shards:
            Path(info.path).unlink(missing_ok=True)
        raise
    if not writer.shards:
        return None, 0
    if len(writer.shards) != 1:
        raise HFImportError("one source file must produce exactly one shard")
    info = writer.shards[0]
    final_path = shards_dir / f"shard-{index:05d}.parquet"
    os.replace(info.path, final_path)
    info = replace(info, path=str(final_path))
    return _shard_entry(info, final_path, text_bytes), documents


def _base_entry(remote: RemoteFile, index: int, first_ordinal: int) -> dict[str, Any]:
    return {
        "kind": "file",
        "file_index": index,
        "path": remote.path,
        "size": remote.size,
        "lfs_sha256": remote.lfs_sha256,
        "xet_hash": remote.xet_hash,
        "first_ordinal": first_ordinal,
    }


def _import_parquet_file(
    adapter: Adapter,
    hub: HubClient,
    http: HttpClient,
    remote: RemoteFile,
    index: int,
    first_ordinal: int,
    shards_dir: Path,
    *,
    max_row_groups: int | None,
    connections: int,
    rows_per_row_group: int,
    counters: _RunCounters,
    emit: Callable[..., None],
) -> dict[str, Any]:
    stats = FileTransferStats()
    url_lock = threading.Lock()
    resolved: list[ResolvedUrl] = []

    def resolver(force: bool) -> ResolvedUrl:
        with url_lock:
            now = time.time()
            stale = (
                not resolved
                or force
                or (resolved[0].expires_at is not None and resolved[0].expires_at - now < _URL_REFRESH_MARGIN_SECONDS)
            )
            if stale:
                fresh = hub.resolve_file(remote)
                resolved[:] = [fresh]
            return resolved[0]

    footer_reader = RemoteRangeFile(http, resolver, remote.size, stats)
    metadata = read_remote_metadata(footer_reader)
    footer_requests, footer_bytes = stats.requests, stats.bytes
    names = metadata.schema.to_arrow_schema().names
    plan = adapter.plan_columns(names)  # eksik sutun -> AdapterError, alim baslamaz
    read_set = set(plan.read)
    skipped_set = set(plan.skipped)

    num_groups = metadata.num_row_groups
    groups = list(range(num_groups if max_row_groups is None else min(num_groups, max_row_groups)))
    forbidden: list[tuple[int, int]] = []
    column_bytes: dict[str, int] = {}
    for group in range(num_groups):
        meta = metadata.row_group(group)
        for column_index in range(meta.num_columns):
            column = meta.column(column_index)
            top = _top_level(column)
            if top in skipped_set:
                forbidden.append(_chunk_range(column))
            if group in groups or max_row_groups is None:
                column_bytes[top] = column_bytes.get(top, 0) + column.total_compressed_size
    forbidden.sort()
    planned = sum(size for name, size in column_bytes.items() if name in read_set)
    counters.bytes_planned += planned

    offsets = []
    total = 0
    for group in range(num_groups):
        offsets.append(total)
        total += metadata.row_group(group).num_rows

    local = threading.local()

    def read_group(group: int) -> pa.Table:
        reader = getattr(local, "reader", None)
        if reader is None:
            reader = RemoteRangeFile(http, resolver, remote.size, stats)
            reader.forbidden = forbidden
            local.reader = reader
            local.parquet = pq.ParquetFile(pa.PythonFile(reader, mode="r"), metadata=metadata, pre_buffer=False)
        ranges = coalesce(column_chunk_ranges(metadata, group, read_set), forbidden)
        reader.prefetch(ranges)
        try:
            return local.parquet.read_row_group(group, columns=list(plan.read))
        finally:
            reader.clear()

    report = new_report(adapter)
    report.files.append(remote.path)
    records_seen = 0

    def rows():
        nonlocal records_seen
        with ThreadPoolExecutor(max_workers=connections, thread_name_prefix="hf-range") as pool:
            window = max(2, connections * 2)
            pending: dict[int, Any] = {}
            position = 0
            try:
                while position < len(groups):
                    while len(pending) < window and position + len(pending) < len(groups):
                        group = groups[position + len(pending)]
                        pending[group] = pool.submit(read_group, group)
                    group = groups[position]
                    table = pending.pop(group).result()
                    position += 1
                    base = offsets[group]
                    for offset, row in enumerate(table.to_pylist()):
                        records_seen += 1
                        yield base + offset, row
                    counters.rows += table.num_rows
                    emit("row_group", file=remote.path, row_group=group)
            finally:
                for future in pending.values():
                    future.cancel()

    total_rows = sum(metadata.row_group(group).num_rows for group in groups)
    documents = adapt_rows(
        adapter, rows(), plan=plan, report=report, file_label=remote.path, first_ordinal=first_ordinal
    )
    shard, written = _write_file_shard(
        documents, shards_dir, index, rows_hint=total_rows, rows_per_row_group=rows_per_row_group
    )
    if written != report.documents:
        raise HFImportError("document count mismatch between adapter and shard writer")
    if records_seen != total_rows:
        raise HFImportError(f"{remote.path}: read {records_seen} rows, footer says {total_rows}")
    for low, high in forbidden:
        for start, length in stats.ranges:
            if start < high and low < start + length:
                raise HFImportError(f"{remote.path}: skipped column bytes were downloaded ({start}+{length})")
    counters.bytes_downloaded += stats.bytes
    return {
        **_base_entry(remote, index, first_ordinal),
        "num_rows": metadata.num_rows,
        "row_groups": num_groups,
        "row_groups_read": len(groups),
        "records_seen": records_seen,
        "documents": report.documents,
        "column_bytes": dict(sorted(column_bytes.items())),
        "bytes_planned": planned,
        "bytes_downloaded": stats.bytes,
        "requests": stats.requests,
        "footer": {"requests": footer_requests, "bytes": footer_bytes},
        "skipped_bytes_downloaded": 0,
        "shard": shard,
        "report": report.to_dict(),
    }


def _import_whole_file(
    adapter: Adapter,
    hub: HubClient,
    http: HttpClient,
    remote: RemoteFile,
    index: int,
    first_ordinal: int,
    shards_dir: Path,
    *,
    rows_per_row_group: int,
    counters: _RunCounters,
) -> dict[str, Any]:
    """JSONL/TSV: dosyanin tamami indirilir, boyut + SHA dogrulanir, sonra ayni sozlesme."""
    raw_dir = shards_dir.parent / "raw"
    raw_dir.mkdir(parents=True, exist_ok=True)
    target = raw_dir / f"file-{index:05d}{Path(remote.path).suffix}"
    temp = target.with_name(target.name + ".part")
    attempts = 3
    received = 0
    sha256 = hashlib.sha256()
    sha1 = hashlib.sha1()
    for attempt in range(attempts):
        resolved = hub.resolve_file(remote)
        sha256 = hashlib.sha256()
        # git blob kimligi: sha1("blob <boyut>\0" + icerik) -- LFS olmayan kucuk dosyalar.
        sha1 = hashlib.sha1(f"blob {remote.size}\0".encode("ascii"))
        received = 0
        try:
            with temp.open("wb") as handle:
                def sink(chunk: bytes) -> None:
                    nonlocal received
                    received += len(chunk)
                    if received > remote.size:
                        raise HFImportError(f"{remote.path}: more bytes than the tree size {remote.size}")
                    sha256.update(chunk)
                    sha1.update(chunk)
                    handle.write(chunk)

                current = resolved.url
                for _ in range(6):
                    response = http.send(current, stream_to=sink)
                    if response.status in REDIRECT_STATUSES and response.headers.get("location"):
                        current = urljoin(current, response.headers["location"])
                        continue
                    break
                if response.status != 200:
                    raise HFImportError(f"{remote.path}: download failed: HTTP {response.status}")
                handle.flush()
                os.fsync(handle.fileno())
        except _StreamInterrupted:
            if attempt + 1 >= attempts:
                raise
            continue
        if received == remote.size:
            break
        if attempt + 1 >= attempts:
            raise HFImportError(f"{remote.path}: downloaded {received} bytes, expected {remote.size}")
    if remote.lfs_sha256 is not None:
        if sha256.hexdigest() != remote.lfs_sha256:
            temp.unlink(missing_ok=True)
            raise HFImportError(f"{remote.path}: sha256 does not match the LFS pointer")
    elif remote.git_oid is not None and sha1.hexdigest() != remote.git_oid:
        temp.unlink(missing_ok=True)
        raise HFImportError(f"{remote.path}: git blob sha1 does not match the tree")
    os.replace(temp, target)
    counters.bytes_downloaded += received
    report = new_report(adapter)
    try:
        documents = adapt_file(adapter, target, report=report, first_ordinal=first_ordinal, file_label=remote.path)
        shard, _written = _write_file_shard(
            documents, shards_dir, index, rows_hint=1_000_000_000, rows_per_row_group=rows_per_row_group
        )
    finally:
        target.unlink(missing_ok=True)
    counters.rows += report.records_seen
    return {
        **_base_entry(remote, index, first_ordinal),
        "num_rows": report.records_seen,
        "row_groups": None,
        "row_groups_read": None,
        "records_seen": report.records_seen,
        "documents": report.documents,
        "column_bytes": {},
        "bytes_planned": remote.size,
        "bytes_downloaded": received,
        "requests": None,
        "sha256": sha256.hexdigest(),
        "shard": shard,
        "report": report.to_dict(),
    }
