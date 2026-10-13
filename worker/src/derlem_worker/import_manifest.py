"""Alim manifesti (derlem.import-manifest.v1) ve onun belge gorunumu (TASK-032).

Bir HF alimi (hf_import.py) kaynagin nesnesi olarak tek bir JSON manifest
yayimlar: parca listesi (derlem.document.v1 Parquet), SHA'lari, satir sayilari,
kaynak dosyalar ve sabit surum. Parcalar nesne deposunda siradan nesnelerdir.

Kapilar (PII, parmak izi, ornekleme) nesneyi satir satir okur. Kaynak nesnesi
bir alim manifestiyse bu modul ayni ``(sira_no, satir, sinir_asimi)`` sozlesmesini
parcalardan uretir: her belge tek satirlik ``{"id": ..., "text": ...}`` JSON'u
olarak verilir -- satir okuyuculari bu bicimi zaten taniyor (JSONL ``text``
alani); belgenin icindeki paragraf sonlari JSON kacisiyla korunur, metin
degismez. Sira numarasi belge kaydinin ``source_ordinal``'idir.

Manifest tanima: dosya ``{"schema": "derlem.import-manifest.v1"`` ile baslar ve
boyutu sinirlidir; parcalar depoda SHA ile bulunur, boyut ve SHA256 her okumada
dogrulanir (tutmazsa okuma durur).
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re
from typing import Any, Callable, Iterator, Mapping

IMPORT_MANIFEST_SCHEMA = "derlem.import-manifest.v1"
IMPORT_MANIFEST_MEDIA_TYPE = "application/vnd.derlem.import-manifest+json"
SHARD_MEDIA_TYPE = "application/vnd.apache.parquet"
MAX_MANIFEST_BYTES = 64 * 1024 * 1024
_MANIFEST_PREFIX_RE = re.compile(rb'^\{\s*"schema"\s*:\s*"derlem\.import-manifest\.v1"')
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")

ByteProgressCallback = Callable[[int, int], None]


class ImportManifestError(ValueError):
    pass


def storage_key_for(sha256: str) -> str:
    return f"objects/sha256/{sha256[:2]}/{sha256[2:4]}/{sha256}"


def load_import_manifest(path: Path) -> dict[str, Any] | None:
    """Dosya bir alim manifestiyse ayristirilmis hali, degilse None."""
    try:
        size = path.stat().st_size
    except OSError:
        return None
    if size > MAX_MANIFEST_BYTES:
        return None
    with path.open("rb") as handle:
        head = handle.read(128)
        if not _MANIFEST_PREFIX_RE.match(head):
            return None
        payload = head + handle.read()
    try:
        value = json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ImportManifestError("import manifest is not valid JSON") from error
    validate_import_manifest(value)
    return value


def validate_import_manifest(value: Any) -> None:
    if not isinstance(value, dict) or value.get("schema") != IMPORT_MANIFEST_SCHEMA:
        raise ImportManifestError("not a derlem.import-manifest.v1 object")
    shards = value.get("shards")
    if not isinstance(shards, list):
        raise ImportManifestError("import manifest has no shard list")
    last_ordinal = 0
    for shard in shards:
        if not isinstance(shard, dict):
            raise ImportManifestError("shard entry must be an object")
        sha256 = shard.get("sha256")
        if not isinstance(sha256, str) or not _SHA256_RE.match(sha256):
            raise ImportManifestError("shard sha256 must be 64 lowercase hex characters")
        for key in ("byte_size", "row_count", "first_source_ordinal", "last_source_ordinal"):
            item = shard.get(key)
            if not isinstance(item, int) or isinstance(item, bool) or item < 0:
                raise ImportManifestError(f"shard {key} must be a non-negative integer")
        if shard["first_source_ordinal"] <= last_ordinal:
            raise ImportManifestError("shard ordinals must increase strictly")
        last_ordinal = shard["last_source_ordinal"]


def manifest_shard_paths(manifest: Mapping[str, Any], store_root: Path) -> list[tuple[dict[str, Any], Path]]:
    root = store_root.resolve()
    result = []
    for shard in manifest["shards"]:
        path = (root / storage_key_for(shard["sha256"])).resolve()
        path.relative_to(root)
        result.append((shard, path))
    return result


def verify_shard(path: Path, sha256: str, byte_size: int) -> None:
    try:
        actual_size = path.stat().st_size
    except OSError as error:
        raise ImportManifestError(f"shard {sha256} is missing from the store") from error
    if actual_size != byte_size:
        raise ImportManifestError(f"shard {sha256} size {actual_size} != manifest {byte_size}")
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(4 * 1024 * 1024):
            digest.update(chunk)
    if digest.hexdigest() != sha256:
        raise ImportManifestError(f"shard {sha256} content does not match its SHA256")


def iter_manifest_documents(
    manifest: Mapping[str, Any],
    store_root: Path,
    *,
    columns: tuple[str, ...] = ("source_ordinal", "text", "provenance"),
) -> Iterator[dict[str, Any]]:
    """Manifestteki parcalarin belgeleri, sira numarasi sirasinda; her parca dogrulanir."""
    from derlem_worker.document_record import read_documents

    last_ordinal = 0
    for shard, path in manifest_shard_paths(manifest, store_root):
        verify_shard(path, shard["sha256"], shard["byte_size"])
        rows = 0
        for document in read_documents(path, columns=list(columns)):
            ordinal = int(document["source_ordinal"])
            if ordinal <= last_ordinal:
                raise ImportManifestError(f"document order broken at ordinal {ordinal}")
            last_ordinal = ordinal
            rows += 1
            yield document
        if rows != shard["row_count"]:
            raise ImportManifestError(f"shard {shard['sha256']} has {rows} rows, manifest says {shard['row_count']}")


def document_line(document: Mapping[str, Any]) -> str:
    """Belgenin satir okuyuculari icin tek satirlik JSON bicimi (metin degismez)."""
    provenance = document.get("provenance") or {}
    external_id = provenance.get("external_id") if isinstance(provenance, Mapping) else None
    return json.dumps({"id": external_id, "text": document["text"]}, ensure_ascii=False, separators=(",", ":"))


def manifest_document_lines(
    manifest: Mapping[str, Any],
    store_root: Path,
    max_bytes: int,
    *,
    progress_callback: ByteProgressCallback | None = None,
    progress_interval_bytes: int = 64 * 1024 * 1024,
) -> Iterator[tuple[int, str | None, bool]]:
    """``sampling._bounded_lines`` sozlesmesi: (sira_no, satir | None, sinir_asimi).

    Sinir metnin UTF-8 bayti uzerinden uygulanir (ihracattaki parca yoluyla ayni).
    Ilerleme bayti islenen metin baytidir.
    """
    if progress_interval_bytes <= 0:
        raise ValueError("progress_interval_bytes must be positive")
    processed = 0
    ordinal = 0
    next_progress_at = progress_interval_bytes
    for document in iter_manifest_documents(manifest, store_root):
        ordinal = int(document["source_ordinal"])
        text_bytes = len(document["text"].encode("utf-8"))
        processed += text_bytes + 1
        if progress_callback is not None and processed >= next_progress_at:
            progress_callback(processed, ordinal)
            while next_progress_at <= processed:
                next_progress_at += progress_interval_bytes
        if text_bytes > max_bytes:
            yield ordinal, None, True
            continue
        yield ordinal, document_line(document), False
    if progress_callback is not None:
        progress_callback(processed, ordinal)


def manifest_text_units(manifest: Mapping[str, Any], store_root: Path) -> Iterator[bytes]:
    """PII taramasi icin: her belge metni (UTF-8) + satir sonu."""
    for document in iter_manifest_documents(manifest, store_root, columns=("source_ordinal", "text")):
        yield document["text"].encode("utf-8") + b"\n"


# --------------------------------------------------------------------------
# Temiz aday satiri (TASK-049)
# --------------------------------------------------------------------------

CANDIDATE_LINE_FORMAT = "derlem.candidate-line.v1"
"""Parcalardan turetilen adayin satir bicimi: belge basina tek satir, kompakt JSON,
sirali anahtarlar ``{"text": <metin>, "url": <provenance.url>}``, UTF-8 kacissiz
(``ensure_ascii=False``), LF ile biter.

- ``url``: ``tr-web-v4`` adresi okur. Adres satirda durursa satir okuyucusu
  (``clean_candidate._line_url``) ayni adresi gorur: parca okuyucusuyla satir
  okuyucusu ayni karari verir ve aday kendi basina yeniden suzulebilir.
- ``id`` (Common Crawl ``<urn:uuid:...>``) YOK: PII kapisi satirin tamamini tarar ve
  uuid'nin rakam gruplari telefon/kart desenine uyuyor (FineWeb2-HQ'nun ilk 30.000
  belgesinde 139 belge, %0,46 -- hepsi yanlis isabet). Kimlik secim listesinden
  bulunur: sira numarasi -> parca satiri -> ``provenance.external_id``.
- Belge icindeki paragraf sonlari JSON kacisiyla (``\\n``) korunur, metin degismez;
  satir okuyuculari (``sampling._document_from_line``) ``text`` alanini aynen verir.
- ``doc_id`` (secim listesi ve karar kaydi) bu satirin UTF-8 baytlarinin SHA256'sidir
  -- satir okuyucusunun kimligiyle ayni; ortak belge kaydinin ``doc_id``'si (metnin
  SHA'si) degildir. Held-out kurali da bu satirin baytlarina uygulanir: held-out
  dosyasinin her satiri kuralla yeniden dogrulanabilir."""


def candidate_line(document: Mapping[str, Any]) -> str:
    provenance = document.get("provenance") or {}
    if not isinstance(provenance, Mapping):
        provenance = {}
    return json.dumps(
        {"text": document["text"], "url": provenance.get("url")},
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )


def manifest_candidate_lines(
    manifest: Mapping[str, Any],
    store_root: Path,
    max_line_bytes: int,
    *,
    limit_documents: int | None = None,
    progress: dict[str, int] | None = None,
) -> Iterator[tuple[int, str | None, bool]]:
    """``sampling._bounded_lines`` sozlesmesi, aday satiriyla: (sira_no, satir | None, sinir_asimi).

    Sinir, satir okuyucusundaki gibi satirin LF dahil bayt sayisina uygulanir
    (``len(satir) + 1 > max_line_bytes``): ayni belgeler JSONL'e yazilip satir
    satir okununca ayni belgeler sinir asimi sayilir. Sira numarasi belge
    kaydinin ``source_ordinal``'idir (parca sirasinda kesintisiz artar). Her parca
    okunmadan once boyut ve SHA256 ile dogrulanir (``iter_manifest_documents``).
    ``progress`` verilirse ``documents`` ve ``shards_started`` sayaclari guncellenir.
    """
    if max_line_bytes <= 0:
        raise ValueError("max_line_bytes must be positive")
    if limit_documents is not None and limit_documents <= 0:
        raise ValueError("limit_documents must be positive")
    count = 0
    for document in iter_manifest_documents(
        manifest, store_root, columns=("source_ordinal", "text", "provenance")
    ):
        count += 1
        ordinal = int(document["source_ordinal"])
        if progress is not None:
            progress["documents"] = count
            progress["last_source_ordinal"] = ordinal
        line = candidate_line(document)
        if len(line.encode("utf-8")) + 1 > max_line_bytes:
            yield ordinal, None, True
        else:
            yield ordinal, line, False
        if limit_documents is not None and count >= limit_documents:
            return


def manifest_shards_covering(manifest: Mapping[str, Any], last_source_ordinal: int | None) -> list[dict[str, Any]]:
    """Bir kosunun okudugu parcalar (indeksleriyle); ``last_source_ordinal`` None ise hepsi."""
    covered = []
    for index, shard in enumerate(manifest["shards"]):
        if last_source_ordinal is not None and shard["first_source_ordinal"] > last_source_ordinal:
            break
        covered.append({
            "index": index,
            "sha256": shard["sha256"],
            "byte_size": shard["byte_size"],
            "row_count": shard["row_count"],
            "first_source_ordinal": shard["first_source_ordinal"],
            "last_source_ordinal": shard["last_source_ordinal"],
        })
    return covered
