# TASK-044 — Common document record (`derlem.document.v1`), decision record, Parquet shards, source adapters

| Field | Value |
|---|---|
| Status | **DONE** — 2026-10-13 (implemented, measured, control runs 20/20); schema field list awaits the owner's one-line "ok" ([belge_kaydi_v1.md](../belge_kaydi_v1.md)); was READY 2026-10-13, owner decision "yes to all three" |
| Kind | feature (data model) |
| Moratorium | owner approval given 2026-10-13 |
| Estimate | 3 day(s) |
| Depends on | — |
| Owner | (unassigned) — opus; backfill of Faz-2 sources: sonnet |

## Goal

Every document from every source lands in **one** record shape with its provenance and signals,
stored as Parquet shards in the content-addressed store; every verdict about a document is a
row in a decision record keyed by `doc_id`; a source is described to the importer by a small
adapter file, not by code.

## Why

Each dataset has different columns (FineWeb2-HQ: 13; mevzuat: law number, type, gazette date;
instruction sets: messages or instruction/output). Today's intake reads only `text`/`id` from
JSONL and nothing from parquet, so metadata is lost at the door — exactly how Faz-2 lost its
URLs and source labels. The owner asked the direct question on 2026-10-13: how do we integrate
many datasets, measure their quality automatically, and derive new datasets from them. This card
is the data-model half of the answer; TASK-032 is the import half, TASK-047 the quality half.

## Scope

- **Schema `derlem.document.v1`** (pyarrow schema, versioned, documented in `docs/`): `doc_id`
  (sha256 of raw text bytes), `text` (never rewritten; paragraph breaks kept), `source_id`,
  `source_ordinal`, `provenance` (dataset, revision, file, row, external_id, url, crawl_date,
  dump), `language` (declared, detected, score), `signals` (map of scorer → value, e.g.
  `fineweb2-hq-quality`, `minhash_cluster_size`), `rights` (license_id, evidence_ref, scope),
  `extra` (JSON string of unmapped columns).
- **Schema `derlem.decision.v1`**: `doc_id`, `decision_type` (pii, duplicate, near_duplicate,
  quality_rule, language, rights_scope, held_out, jury, human_review), `verdict`, `reason`,
  `judge` (rule version / model+rubric id / user id), `run_id`, `decided_at`.
- **Shard writer/reader** in the worker: Parquet, zstd, ~100 k documents per shard, content
  addressed like any object; reader yields documents with optional column projection.
- **Adapter**: yaml contract (dataset, revision, config, split, format, columns_read,
  columns_skipped, map, extra, document_boundary) + validator (missing mapped column → refuse;
  empty text → counted and reported, never silently dropped). Adapters for: FineWeb2-HQ
  (parquet), a JSONL/TSV source, and `derlem.canonical-sample.v1` instruction sets.
- **Selection-list derivation**: `clean_candidate` gains a mode that writes a selection list
  (doc_ids + decision snapshot) instead of a text copy; `derive` materialises text only at export.
  Existing text-copy mode stays for v1–v5 reproducibility.
- **Backfill**: the Faz-2 parent and v5 re-expressed as document shards (provenance =
  source id + ordinal; no URL — there never was one) and v5 as a selection list over the parent.
- **Export**: jsonl envelope carries `provenance`, `language`, `signals`, `rights` per record;
  txt unchanged.
- Tests: schema round trip; adapter validation (missing column, empty text, unknown column →
  `extra`); shard determinism (same input → same shard SHA); selection-list export equals
  text-copy export byte for byte on the 100k slice; control runs for each guard.

## Out of scope

- The HTTP import itself (TASK-032).
- Tokenized export (TASK-033), licence registry enforcement (TASK-030).
- Storing per-document decisions in PostgreSQL (they stay in Parquet; only summaries and the
  200 sampled documents live in the DB).

## Acceptance criteria

- [x] A FineWeb2-HQ row group, a mevzuat JSONL record and a canonical instruction sample all
      land as valid `derlem.document.v1` / canonical records through adapters, with nothing
      silently dropped (unmapped columns in `extra`). *(FineWeb2-HQ: real 1,000-row sample + test
      fixture with `embeddings`; mevzuat: test fixture in JSONL and TSV — the real mevzuat adapter
      waits for its licence note, TASK-032; canonical: `data_samples/` file, byte-for-byte.)*
- [x] v5 reproduced as parent + selection list: materialised export SHA equals the v5 object SHA
      `9dc5d6f7…` *(full corpus, hash only; held-out `de48eabb…` too)*.
- [x] Disk: FineWeb2-HQ text+metadata as zstd Parquet measured against raw bytes (ratio in the card).
- [x] Control runs: each new guard removed → a test goes red *(20/20)*.

## Owner actions

- None until the schema doc is shown; then a one-line "ok" on the field list.

## Report

**2026-10-13 — done (opus).** Schema doc: [belge_kaydi_v1.md](../belge_kaydi_v1.md); export contract:
[canonical_exports.md](../canonical_exports.md) ("Belge ustverisi"). Measurements and scripts:
`var/olcum-2026-10-13/task-044/` (`olc.py`, `kontrol.py`, `olcum-*.json`, `kontrol-kosulari.txt`,
`v5-secim/`, `secim-100k/`).

**What exists now**

- `worker/src/derlem_worker/document_record.py` — pyarrow schemas `derlem.document.v1`,
  `derlem.decision.v1`, `derlem.selection.v1`; validators; deterministic Parquet writer
  (`ParquetRowWriter`, `DocumentShardWriter` ~100 k docs/shard, 10 k-row row groups, `cut()` for
  file boundaries, temp file + rename), reader with column projection, `publish_parquet` → the
  object store's binary content-addressed path (`ingest_raw_file`).
- `worker/src/derlem_worker/adapters.py` + `adapters/{epfml-fineweb2-hq,faz2-raw-jsonl,derlem-canonical-sample}.yaml`
  — yaml contract, static + data validation, parquet/jsonl/tsv readers, canonical passthrough,
  `line_source_documents` (Faz-2 backfill: provenance = source + line number, no URL),
  `AdapterReport` (`records_seen = documents + empty_text + invalid (+ oversized)`).
- `clean_candidate --selection-list` (same decision code path as the text copy; output end is a
  hash-only sink + `SelectionRecorder`) and `python -m derlem_worker.selection materialize | from-text-copy`.
  Text-copy mode unchanged: existing 24 clean-candidate tests green; pre-TASK-044 code on the 100k
  slice gives the same SHA as the new code (below).
- `releases.py`: jsonl text records gain `provenance`, `language`, `signals`, `rights`; null for
  line sources (removing them gives the pre-TASK-044 bytes — golden SHA in the test); real values for
  `document_shards` sources; `doc_id` ≠ sha256(text) blocks the export. TXT byte-identical.
- Dependencies: `pyarrow==25.0.1` (exact pin — the writer version is in the shard bytes; 26.0.0 was
  4 days old, not taken) and `pyyaml>=6.0.3,<7` in `worker/pyproject.toml` + `uv.lock`; installed
  with `uv sync` (worker/.venv, 3.13.15) and `uv pip install` (root .venv, 3.14.6). cp314 wheels exist
  for both; no problem on 3.14.

**Tests** (root .venv, Python 3.14.6, `DERLEM_SKIP_DB_TESTS=1` — DB untouched): full worker suite
**442 passed, 20 skipped** (19 DB-backed, skipped on purpose; 1 opt-in 100k-slice test, run by the
measurement script instead). New: `test_document_record.py` 13, `test_adapters.py` 23 (12 of them the
static-validation table), `test_clean_candidate.py` +7, `test_releases.py` +4. worker/.venv has no
pytest (dev extra not installed; not installed by this card) — on 3.13.15 the shard writer was run by
the measurement script, not by pytest.

**Control runs** (`kontrol.py`, 3.14.6): 20 guards removed one at a time → the named test red →
restored → green, file SHA restored: **20/20** (`kontrol-kosulari.txt`): missing mapped column
(parquet and JSONL), empty text counted, unlisted column → extra, static `text` mapped, read-but-unused
column, doc_id = sha256(text), empty text not a document, decision type/verdict enum, pyarrow pin,
volatile footer field (timestamp injected → determinism tests red), ordinal order, selection mode
writes no text, PII decision recorded, materialize: doc_id per line / output SHA / selection-list SHA,
from-text-copy subsequence, export null fields, export doc_id gate.

**Measurements (100k slice `dilim-100k_v3.txt`: 202,923,864 B, 99,007 lines, sha `51df1672…`)**

| | Result |
|---|---|
| Parquet/zstd-9 shard | 70,516,336 B = **34.75 % of raw bytes**; write 17.0 s (11.9 MB/s, 5,810 docs/s, incl. sha256 + validation) |
| zstd-3 / zstd-19 | 38.6 % at 31.1 MB/s / 31.9 % at 1.4 MB/s → level 9 kept |
| Read | all columns 1.72 s (118 MB/s raw-equivalent, 57 k docs/s); `text` only 1.18 s; `doc_id`+ordinal 0.086 s (1.16 M docs/s) |
| Round trip | 99,007 / 99,007 texts identical to the slice lines |
| Determinism | shard sha `2d7a6278…` — same on 3.14.6 and 3.13.15, two runs each; footer keys only `ARROW:schema`, `derlem.schema`; `created_by` = `parquet-cpp-arrow version 25.0.1` |
| Full parent estimate (13,569,773,056 B, 6,027,968 lines) — **not run** | ≈ 4.7 GB Parquet, 61 shards, write ≈ 19 min, full read ≈ 2 min, doc_id scan ≈ 6 s |
| Selection list = text copy (v5 options on the slice) | text copy `e69dd953…` (191,889,947 B, 73,230 lines) **= materialised output, byte for byte**; selection + decisions = 1.9 % of the text copy; materialise 2.4 s |
| Text copy unchanged | pre-TASK-044 `clean_candidate.py`, same slice and options: `e69dd953…` — identical (`onceki-kod-metin-kopya.json`) |
| **v5 as parent + selection list (full corpus, hash only)** | materialised **`9dc5d6f7…aefd33` = v5**, held-out `de48eabb…` = v5; 4,327,374 + 1,651 rows; selection list 160,110,427 B (1.40 % of v5's 11.46 GB); build 171 s, materialise 121 s; 3 oversized parent lines listed by ordinal |
| FineWeb2-HQ (1,000-row sample, 12 columns) | 1,000/1,000 documents, 923 with `\n`, texts and paragraph breaks identical; shard = **31.2 % of raw text+metadata** (34.0 % of uncompressed 12-column Parquet); full set ≈ 27.2 GB → **≈ 9.2 GB** (design estimate was 12–15 GB) |

The 100k slice is a v3 output, so on it the v5 options only exercise the drop list (25,777 lines:
25,776 `rights_scope`, 1 `language`); PII, quality, duplicate, near-duplicate, held-out, blank and
oversized decisions are covered by the synthetic test, and the full v5 proof covers the real mix.

**Deviations from the card / for the owner's "ok"**

1. `derlem.decision.v1` has one extra nullable column, `source_ordinal`: an exact-duplicate text
   occurs twice in a source with different verdicts (kept once, rejected as duplicate), so `doc_id`
   alone is ambiguous.
2. Two extra decision types, `oversized` and `empty_text` (the text-copy path's mechanical drops);
   verdicts are `pass / reject / held_out / flag`.
3. `source_id` is nullable in documents so that shard SHAs do not depend on the registration
   (TASK-032's "two runs → identical shard SHAs").
4. Re-exporting a release as JSONL now gives a different SHA than before (4 null fields per record);
   TXT is identical. Ready exports are immutable and are not regenerated.

**Open**

- Owner: one-line "ok" on the field list (above).
- `releases.py` does not read a selection list directly; `materialize` produces the text object.
- The real mevzuat adapter (licence note) and the HF import itself: TASK-032. Decision summaries in
  PostgreSQL: next card. `from-text-copy` carries no decision snapshot (old runs' decisions live in
  their rejection reports).
- FineWeb2-HQ ratio measured on 1,000 docs; the first real import measures it on 100 k-doc shards.
