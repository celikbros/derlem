# TASK-032 — In-app `import_hf_dataset` job: pinned revision, adapter-driven columns, selective parquet read, shard-resumable — FineWeb2-HQ first

| Field | Value |
|---|---|
| Status | **READY** — rewritten 2026-10-13 after the owner's "yes to all three" (download without embeddings, build the architecture with this import, write the two rules after); was DRAFT (Wikipedia-tr first) |
| Kind | feature |
| Moratorium | owner approval given 2026-10-13 (`docs/veri_mimarisi_2026_10.md`); HF token via env only |
| Estimate | 3 day(s) |
| Depends on | TASK-044 (common document record + adapter); licence note `docs/haklar/hf-fineweb2-hq.md` (done) |
| Owner | (unassigned) — opus |

## Goal

Import a pinned Hugging Face dataset revision as a registered Derlem source: adapter-defined
columns, **only the columns we need** (no `embeddings`), one record = one document with paragraph
breaks preserved, per-shard SHA with resume, a production manifest, then the standard gates.

## Why

The owner chose FineWeb2-HQ `tur_Latn` as the base of the next corpus (decision B, 2026-09-29;
measured 2026-10-04 in [fineweb2_hq_degerlendirmesi_2026_10.md](../fineweb2_hq_degerlendirmesi_2026_10.md)).
Full download is 107.3 GB of which 74.7 % is a 768-dim embedding column we do not use; selective
column reading over HTTP Range was tried on one file and works (two requests per row group,
byte-exact). Text + metadata ≈ 27.3 GB; disk has 57 GB. Today's intake would also drop every
metadata column — the Faz-2 loss repeated.

## Scope

- Worker job `import_hf_dataset(adapter_path)`: the adapter yaml (TASK-044) names dataset,
  revision, config, split, columns to read, column map, skipped columns, boundary rule.
- Parquet path: list files at the pinned revision (HF tree API, sizes + SHA/etag), read each
  file's footer, then read only the mapped columns row-group by row-group over HTTP Range
  (pyarrow); write common-record Parquet shards (TASK-044 schema) straight into `IMPORT_ROOT`,
  one shard per source file; per-shard SHA256 and row count in a progress ledger; **resume** skips
  shards whose SHA matches the ledger. No full-file download ever.
- JSONL/CSV/TSV path for small datasets (mevzuat, instruction sets): same adapter contract,
  whole-file download with size + SHA check.
- Registration via the existing intake: source with `lineage_ref` = manifest (dataset, revision,
  config, split, columns, record count, bytes per column class, licence id, card snapshot SHA),
  `rights_status` and `license_evidence_ref` from the licence note; gates follow automatically.
- Production manifest written next to the shards; two runs of the same revision + adapter must
  produce identical shard SHAs (determinism test with a local fixture dataset served from a
  temp HTTP server — no network in tests).
- Progress counters like exports (shards done / total, bytes, MB/s); API endpoint
  `POST /api/v1/sources/import-hf` (admin only, `DisallowUnknownFields`), minimal form later.
- Dry run: one row group first (measured), then one file, then all 105.
- Measured in the card: bytes downloaded vs. full size, documents, download minutes and MB/s
  (single vs. parallel connections — the 1.9 MB/s single-connection figure must be beaten or
  explained), ingest minutes, gate results, net-new share against the family-excluded corpus.

## Out of scope

- The two new quality rules (TASK-046) — they run on the imported data, they do not gate the import.
- mC4-tr remainder, FineWeb-2 (non-HQ): separate go/no-go after this run is measured.
- Tokenized export (TASK-033).

## Acceptance criteria

- [ ] Two runs of the same revision + adapter → identical shard SHA256s and manifest; resume after
      an injected failure at shard N completes with identical output.
- [ ] No `embeddings` bytes downloaded (ledger shows per-file bytes ≈ 25 % of file size).
- [ ] Every record keeps `url`, `date`, `dump`, `language_score`, `quality_score`,
      `minhash_cluster_size` in the common record; paragraph breaks preserved (`\n` count per
      document equals the source's).
- [ ] Source registered, gates green, measured numbers in the card; disk usage during and after
      the run recorded.

## Owner actions

- Decide backup scope for the raw import (recommendation: outside — reproducible from
  revision + adapter + manifest).
- Set `HF_TOKEN` in the worker env only if the dataset turns out to need it (it is public).

## Report

(not started)
