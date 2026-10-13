# TASK-032 — In-app `import_hf_dataset` job: pinned revision, adapter-driven columns, selective parquet read, shard-resumable — FineWeb2-HQ first

| Field | Value |
|---|---|
| Status | **DONE** — 2026-10-13 20:13: full FineWeb2-HQ `tur_Latn` import through the job queue (owner "ok"): 105 shards, 8,578,808 documents, 27.67 GB downloaded, 0 `embeddings` bytes, 9.11 GB in the store, 1 h 46 min; PII scan and exact-duplicate gates queued automatically (running at time of writing). Was REVIEW (dry run), READY (rewritten 2026-10-13), DRAFT (Wikipedia-tr first) |
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

- [x] Two runs of the same revision + adapter → identical shard SHA256s and manifest (dry run: 1, 4
      and 8 connections → `e449bdce…` / `6ee3a6b9…`); resume after an injected failure at shard N
      completes with identical output (test). The full run was done once; the first shard's SHA was
      not compared against the dry run because the dry run did not publish.
- [x] No `embeddings` bytes downloaded: full run 27,668,653,910 B downloaded vs 79,654,592,152 B
      skipped; no request touched a skipped column range (guarded in code and tests).
- [x] Every record keeps `url`, `date`, `dump`, `language_score`, `quality_score`,
      `minhash_cluster_size`; paragraph breaks preserved (101 datasets-server rows compared byte for
      byte in the dry run).
- [x] Source registered (`ba80dc1c…`, `raw_ingested`), numbers in the card, disk before/after
      recorded. Gates: `scan_pii` running, `check_exact_duplicate` queued — results go to the
      source card when they finish (not "green" yet at the time of this report).

## Owner actions

- Decide backup scope for the raw import (recommendation: outside — reproducible from
  revision + adapter + manifest).
- Set `HF_TOKEN` in the worker env only if the dataset turns out to need it (it is public).

## Report

**2026-10-13 20:13 — full run done (Fable, through the API).** Owner's "ok" at 18:2x; job queued
18:27, succeeded 20:13 (6,377 s, 4 connections, 4.34 MB/s, 17,579 requests, 0 retries, no token).
8,578,808 records seen = 8,578,808 documents, 0 empty; downloaded 27.67 GB (text 25.28 GB, metadata
2.35 GB), `embeddings` 79.65 GB never requested. 105 shards = **9,110,440,606 B** in the store
(32.9 % of downloaded; estimate was 9.1 GB), manifest `d28fe0d1…` (115,846 B) is the source object;
`license` read from the card = `odc-by`, `rights_status` stays `unknown` until the owner reads
[hf-fineweb2-hq.md](../haklar/hf-fineweb2-hq.md). Store 26 GB → 34 GB, working dir 352 KB at the end.
The 10 % review threshold (TASK-048) was written on the source during the import (HTTP 200). Numbers
table: [hf_ice_alim.md §6.1](../hf_ice_alim.md). Script: `var/olcum-2026-10-13/task-032/tam_kosu.py`
(login → import → watch → threshold; state in `tam-kosu-durum.json`, log in `tam-kosu.log`).

Correction to an earlier note: migrations are **not** applied at API start; `go run ./cmd/migrate`
was run before the import so that the threshold column existed.

**2026-10-13 — implemented, tested, dry-run measured (opus).** How it works, ledger, resume, manifest,
commands: [hf_ice_alim.md](../hf_ice_alim.md). Measurements and scripts: `var/olcum-2026-10-13/task-032/`
(`kuru_kosu.py`; `rg1/`, `file-c1/`, `file-c4/`, `file-c8/` each with `sonuc.json`, `ledger.jsonl`,
manifests and the shard; `kontrol-kosulari.json`). Nothing was published to the store, the database was
not touched, no service was started.

**What exists now**

- `worker/src/derlem_worker/hf_import.py` — `import_hf_dataset(adapter_path, work_dir, *, store, …)`:
  pinned revision (40-hex commit required; `X-Repo-Commit`, size and LFS SHA checked on resolve), card
  licence + card SHA, file list from the tree API (paged) via the card's `configs` patterns, draft
  manifest. Parquet: footer in exactly 2 Range requests; row groups read column-chunk-exact (coalesced,
  never across a skipped chunk; a read touching `columns_skipped` bytes is refused before it is sent; a
  server ignoring Range is refused without reading the body); 1–8 parallel connections, ordered writes.
  JSONL/TSV: whole-file download with size + SHA256 / git-blob-SHA1 check. One source file = one
  `derlem.document.v1` shard (`DocumentShardWriter.cut()`), published with `publish_parquet`. Atomic JSONL
  ledger (shard SHA, rows, downloaded bytes, requests); resume skips ledger shards whose SHA verifies,
  half files restart. Deterministic `import-manifest.json`, published as the source object. 429/5xx and
  connection errors retried with exponential backoff (honours `Retry-After`). `HF_TOKEN` from the
  environment only, sent to the hub host only (never to the CDN redirect).
- `worker/src/derlem_worker/import_manifest.py` — manifest recognition/validation and a shard-backed
  document view. `sampling.source_document_lines`, `PIIScanner.scan_file(store_root=…)`, the fingerprint
  gate and the sampling job read manifest sources from the shards (each shard size + SHA verified;
  documents reach the line readers as one-line `{"id","text"}` JSON — text unchanged, ordinal =
  `source_ordinal`). Exact-duplicate gate unchanged (object SHA). Release freeze/export **refuse** manifest
  sources (`document_shards_source_not_supported`) instead of reading manifest lines as documents.
- `worker/src/derlem_worker/jobs/hf_import_jobs.py` + `worker.py` dispatch: job `import_hf_dataset`
  (adapter re-validated under `IMPORT_ROOT`/`ADAPTERS_ROOT`; work dir `IMPORT_ROOT/hf-import/<source_id>`;
  progress every 5 s and per file). Completion in one transaction: shard + manifest `storage_objects`,
  `sources.object_sha256` = manifest, `lineage_ref` = manifest summary, `license` = card licence (replaces
  the `hf-card:pending` placeholder), `raw_ingested`, `scan_pii` + `check_exact_duplicate` queued. Worker
  config: `ADAPTERS_ROOT`, `HF_IMPORT_CONNECTIONS` (default 4, max 8).
- API `POST /api/v1/sources/import-hf` (admin only, `DisallowUnknownFields`): `adapter_path`,
  `content_purpose`, `rights_status`, `license_evidence_ref` (`docs/haklar/…`), `lineage_note`, optional
  `name`/`language`/`domain`; source + job + audit in one transaction; 409 while an import with the same
  adapter is active. Progress via the existing `GET /api/v1/jobs?source_id=<id>` (`result.progress`:
  files/shards/bytes/MB/s). Go config `ADAPTERS_ROOT` (`Server.WithAdaptersRoot`).
- **No migration needed:** `source_type` is free text, `lineage_ref` is text, the shard list lives in the
  manifest object, job types are free text.

**Tests** (`DERLEM_SKIP_DB_TESTS=1`, DB untouched): `worker/tests/test_hf_import.py`, 21 tests, no network
(local hub + separate CDN `http.server` with Range and a range log; fixture parquet with `embeddings` in the
middle): pinned + deterministic (1 vs 3 connections → same shard SHAs and manifest bytes); token on hub only;
metadata + `\n` preserved; empty text counted; no request touches the embeddings chunks and ledger bytes =
logged bytes; resume after injected failure at shard 2 → identical output, only the third file fetched;
half-read file restarted, no partial shard left; tampered shard re-imported; foreign ledger refused; store
publish + resume + gates (sampling, PII) reading the manifest; missing mapped column → `AdapterError`;
429/503 retried; retries bounded; backoff schedule; Range-ignoring server refused; unpinned revision
refused; dry-run subset; jsonl path (download + SHA) and SHA mismatch; adapter path roots; release guard.
Go: `hf_import_handlers_test.go` (admin-only, path roots incl. `..`/outside/non-yaml, validation, unknown
field → 400) green; `internal/repository/hf_import_integration_test.go` (source + job + audit atomically,
409 on a second active import, no orphan source) **written, not run** (needs `DERLEM_TEST_DATABASE_URL`).

**Control runs** (`kontrol-kosulari.json`): each guard removed → its test red → restored → green, 16/16:
coalesce never bridges a skipped chunk; reader + post-check forbidden ranges; exact footer read (pyarrow's
own 64 KB tail read would fetch embeddings in small files); resume skip; resume SHA check; half-file abort;
foreign ledger; 429/5xx retry; token host check; pinned revision; Range-ignored refusal; jsonl SHA;
sampling and PII manifest dispatch; release freeze guard; adapter path roots. Go: path-root check and
evidence-ref prefix removed → red → restored → green.

**Dry run (real network; `tur_Latn/000_00000.parquet`, 1,068,500,812 B, 84,773 rows, 85 row groups)**

| Run | Requests (file) | Downloaded | Share of file | Time | MB/s | Shard |
|---|---:|---:|---:|---:|---:|---|
| first row group, 1 conn | 4 (2 footer + 2) | 5,422,715 | 0.51 % | 4.0 s | 1.36 | 1,649,858 B |
| whole file, 1 conn | 172 (2 + 2×85) | 270,825,687 | **25.35 %** | 155 s | **1.74** | 90,623,172 B `e449bdce…` |
| whole file, 4 conn | 172 | 270,825,687 | 25.35 % | 41.7 s | **6.49** | same SHA, same manifest `6ee3a6b9…` |
| whole file, 8 conn | 172 | 270,825,687 | 25.35 % | 23.2 s | **11.68** | same SHA, same manifest |

- **No embeddings bytes:** downloaded = the 12 read columns' chunk sizes from the footer (270,491,207) +
  footer (334,480), zero extra; embeddings 797,675,121 B (74.65 %) never requested (also enforced in code).
- 84,773/84,773 documents, 0 empty. The 101 rows of the 2026-10-03 datasets-server sample that fall in
  file 0 match byte-for-byte (text, 1,251 `\n`, `url`, `dump`, `id`, signals). Shard = 33.5 % of downloaded.
- 1.9 MB/s was a per-connection CDN limit: 4 connections 3.7×, 8 connections 6.7×, 0 retries, no 429. Hub
  resolve is 1 request per file (hub "resolvers" limit 3,000 / 5 min).

**Full run (105 files) — not run; command and estimate** (scaled from one file): `POST
/api/v1/sources/import-hf` with `{"adapter_path":"epfml-fineweb2-hq.yaml","content_purpose":"pretrain",
"rights_status":"unknown","license_evidence_ref":"docs/haklar/hf-fineweb2-hq.md","name":"FineWeb2-HQ
tur_Latn","language":"tr","domain":"web"}` (rights → `cleared` after the owner's §8 decision). ≈ 27.2 GB
download, ≈ 17,470 Range requests + 105 resolves, 105 shards ≈ 9.1 GB in the store, 8,578,808 records;
≈ 4.3 h at 1 connection, **≈ 70 min at 4** (worker default), ≈ 39 min at 8. Disk during the run: store
shards + at most one local shard (~90 MB) and its temp copy; nothing raw lands on disk. `df` on 2026-10-13:
C: 192 GB free (the 57 GB figure above is older).

**Open**

- Release freeze/export for shard sources (freeze near-dup/decontamination need a shard reader;
  `release_jobs` must pass `document_shards` from the manifest) — fail-closed until then.
- DB-backed end-to-end test of the worker completion transaction; the Go repository test was not run here.
- Canonical-sample (instruction-set) adapters and compressed JSONL are not supported by this job.
- Left for the full run: gates green on the real source, ingest minutes, disk during/after, net-new share
  against the family-excluded corpus.
