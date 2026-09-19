# TASK-018 — Rehearse pretrain draft → freeze → txt/jsonl export on the `_test` database with the 100k slice (Go half: draft + QueueFreeze; Python half: freeze + export jobs in-process)

| Field | Value |
|---|---|
| Status | **DONE (in working tree, not yet committed)** — 2026-09-19: both halves green on `derlem_ci_test`; freeze 326 s, txt 30.5 MB/s, jsonl 22.8 MB/s, SHAs match; no freeze/export defect found. Commit of the two tests + fixture left to the owner (this session had no commit permission). Earlier: Was: DRAFT — from the 2026-09-19 plan ([plan_2026_09.md](../plan_2026_09.md), Faz 1); no new feature — may start when its dependencies are done |
| Kind | delivery |
| Moratorium | allowed — Faz 0 support; no working-DB change, no service start |
| Estimate | 2 day(s) |
| Depends on | TASK-017 |
| Owner | (unassigned) |

## Goal

Run the never-tried `pretrain` freeze and export path end to end on `derlem_ci_test` with the 100k slice (99,007 lines candidate, 43 held-out) and measure it, so the 12 GB run does not discover the first defect on delivery day.

## Why

Letter 2026-09-17 §1: the pretrain draft/freeze flow 'denenmedi (ölçülmedi)'; all frozen releases are instruction; no Python test drives `freeze_release`/`export_release` on a real DB. The contract snapshot is written only by the Go `Releases.Create` (releases.go:30) and the TASK-017 gate lives in Go `QueueFreeze` (line 495) — neither is callable from pytest — so the rehearsal has a Go half and a Python half joined by a fixture. A defect on the 11.9 GB run costs a day of owner waiting and a new letter.

## Scope

- Go half — `internal/repository/pretrain_rehearsal_integration_test.go` (TASK-007 harness, `internal/testdb`): seed the slice as a `pretrain` source and its held-out as `holdout` with objects in a temp store; seed sampling (200 documents), 200 approving `document_reviews` by a second seeded user (creator cannot approve), rights `cleared` + evidence ref (scratch DB only); create the draft through `Releases.Create` → assert `contract_snapshot_status = present` and implementation bundle SHA; call `QueueFreeze` → assert a `freeze_release` job row; sibling case without the holdout → 422 `eval_reference_missing` (TASK-017). Export the resulting `releases`, `release_sources`, `release_source_contract_snapshots` and `contract_spec_artifacts` rows as a JSON fixture under `worker/tests/fixtures/pretrain_rehearsal/` (Go↔Python shared-fixture pattern from TASK-002).
- Python half — `worker/tests/test_pretrain_rehearsal_integration.py` (`_test` DB, in-process via `Worker.run_once()` like `test_queue_integration.py`): load the same slice sources and the Go-produced fixture rows; the worker's `_freeze_release_with_verified_objects` re-verifies the snapshot SHA, so a fabricated snapshot would fail here; run `freeze_release` then `export_release` for txt and jsonl; assert gate results and artifact SHAs.
- Honest statement in the card: the two halves run in separate processes joined by the fixture; no single process drives API + worker. A drift test fails the Python half when the fixture's snapshot no longer verifies against the current contract schema.
- Record compared/matched counts, approximate status, freeze wall-clock, export MB/s, recomputed artifact SHA vs manifest; extrapolate to 11.9 GB as a labelled estimate in TASK-019.
- Any defect → its own fix commit with test + control run before Phase 1 continues.

## Out of scope

- Touching the working database.
- Starting the API/worker as services.
- Freezing anything real.

## Acceptance criteria

- [x] Go half: draft created through the repository with `contract_snapshot_status = present`; `QueueFreeze` inserts a `freeze_release` job row; no-holdout case → 422 `eval_reference_missing`; fixture generated at `worker/tests/fixtures/pretrain_rehearsal/slice100k.fixture.json` (392 KB, in the working tree; commit is the owner's).
- [x] Python half: scratch release `frozen`; exact decontamination 43 reference documents compared, 0 matches (the code writes this as `gate_results.decontamination.reference_document_count` / `match_count`, not `exact_decontamination.compared_document_count` — see Report); approximate gate `reported`; two `release_exports` rows `ready`; recomputed SHA256 equals the manifest for both.
- [x] Measured MB/s and extrapolated hours written in TASK-019 ("Rehearsal numbers (TASK-018)"). CI: the two DB drift tests run everywhere; the slice-dependent tests (Go rehearsal, Python freeze/export) skip **explicitly with a reason** on a machine without the 203 MB slice — they are green locally, not exercised in CI (see "Honest statement").

## Owner actions

- Explicit OK to run both halves inside the existing Go and pytest harnesses against `derlem_ci_test` (no service is started). — given 2026-09-19; used as described below.
- Commit the two test files + fixture (this session did not commit).

## Report

**Done 2026-09-19** on `derlem_ci_test` only (isolated schemas, dropped afterwards; the working
database `derlem` was not opened; no API/worker service started). Slice used: the existing
`var/olcum-2026-09-17/dilim-100k_v3.txt` (99,007 lines, 202,923,864 bytes, SHA256
`51df1672…668b54`) and `dilim-100k_v3_heldout.txt` (43 lines, 84,579 bytes, SHA256
`44338c01…79df01`) — the files were read, not re-derived.

### Go half — `internal/repository/pretrain_rehearsal_integration_test.go`

`go test ./internal/repository/ -run TestPretrainRehearsal -v` (TASK-007 harness; the scratch
address comes from `DERLEM_TEST_DATABASE_URL`, derived from `.env` by `scripts/test.ps1`).
PASS in 3.6–4.2 s. It copies both files into a temp CAS store (`objects/sha256/aa/bb/<sha>`,
the worker layout), seeds a `pretrain` source (rights `cleared`, license evidence ref set,
PII clear, unique, sampled 200/200/200/0), 200 documents chosen at a fixed stride
(ordinals 1, 496, 991, …; object = SHA-256 of the line text as the sampler does), 200
memberships, one campaign, and 200 `approved` reviews by a **second** seeded user. Then:

- Sibling draft **before** any holdout exists: `Releases.Create` → `present`; `QueueFreeze` →
  `GateError{eval_reference_missing}`, and `count(*) FROM background_jobs WHERE job_type =
  'freeze_release'` stays 0 (TASK-017 hard gate).
- Holdout source (43 lines, purpose `holdout`) inserted; main draft `Releases.Create` →
  `contract_snapshot_status = present`, `contract_bundle` artifact re-verifies
  (`sha256 = contract_spec_artifact_sha256(canonical_bytes)`), 64-hex implementation bundle
  SHA; `QueueFreeze` → one `freeze_release` job row, `queued`, payload carries the release id
  and the snapshot SHA.
- Fixture: `to_jsonb(row)` of 13 tables (users, storage_objects, sources, sample generation,
  documents, memberships, the two `contract_bundle` artifacts, campaign, reviews, releases,
  release_sources, release_source_contract_snapshots, the freeze job) in FK order. Golden
  pattern from TASK-002: `DERLEM_UPDATE_GOLDEN=1` rewrites it; otherwise the test compares the
  41 registry-derived snapshot columns (profile/rubric/protocol/policy/purpose-contract/export
  SHAs, implementation bundle SHA, sample pins) and the slice identity against the committed
  file and fails with "contract registry drifted … regenerate". Identities (UUIDs,
  membership root, which hashes document ids) are excluded because they change per run.

### Python half — `worker/tests/test_pretrain_rehearsal_integration.py`

Run from the repo root with `PYTHONPATH=worker/src PYTHONIOENCODING=utf-8` and the root
`.venv\Scripts\python.exe` (the one `scripts/test.ps1` uses; `worker/.venv` has no pytest):
`python -m pytest worker/tests/test_pretrain_rehearsal_integration.py -v -s` → **3 passed in
352 s**. The test applies the real `internal/database/migrations/*.sql` to an isolated
`derlem_pretrain_rehearsal_test_<ns>_<hex>` schema (0.5–1.4 s; pgcrypto pre-created in
`public` like the Go helper), ingests both files into the worker's own CAS store (keys and
SHAs equal the Go rows), loads the fixture with `jsonb_populate_record` in FK order — the
`releases` row goes in as `pending` and is flipped to `present` afterwards so the DB trigger
**re-derives the bundle SHA and compares it with the fixture's** — then drives
`Worker.run_once()` in-process three times: freeze, txt export, jsonl export (the export rows
and jobs are inserted the way `Releases.QueueExport` does, since Go is not callable here).

Measured (run 2; run 1 was within a few seconds before a test-only assertion bug on a UUID
vs string comparison, fixed):

| Step | Wall-clock | Throughput | Result |
|---|---|---|---|
| fixture load (~800 rows, all triggers) | 1.5 s | — | release `present`, SHAs equal the fixture |
| **freeze_release** (verified-object copy + near-dup SimHash + exact + approximate decontamination + manifest) | **326.3 s** | 0.62 MB/s of input | release `frozen`; manifest SHA `19d6d93c…ea91f` |
| **export_release txt** | **6.65 s** | **30.5 MB/s** (202.9 MB in = 202.9 MB out) | `ready`, 99,007 records, artifact SHA `51df1672…668b54` = manifest |
| **export_release jsonl** | **8.91 s** | **22.8 MB/s** in, 27.7 MB/s out (247.0 MB) | `ready`, 99,007 records, artifact SHA `b7c0dd2e…e4246` = manifest |

Gate results as written by the worker: `decontamination` = `passed`, method
`document-text-sha256-v1`, `reference_source_count 1`, `reference_document_count 43`,
`reference_unique_document_count 43`, `release_document_count 99007`, `match_count 0`;
`approximate_decontamination` = `reported`, `potential_match_count 0`, 98,628 indexed,
379 skipped as too short; `near_duplicate_report` = `reported`, 0 pairs; `contract_snapshot` =
`passed`, `review_document_count 200`; storage integrity 1 source object + 1 reference object.
Both export manifests carry `token_estimate` `unicode-codepoint-range-v1`: 46,597,661
(bounds 31,065,108 – 93,195,322) — a labelled estimate, not a tokenizer count. Recomputed
SHA-256 of each stored artifact equals both the `release_exports.object_sha256` column and
the export manifest's `export.sha256`. Note: the txt artifact is byte-identical to the source
object (same SHA) because the candidate is already one LF-terminated line per document; that
is the contract working as documented, not a shortcut.

Freeze phase timing (coarse, from job progress polled every 15 s in run 1): claim → first
`release_near_dedup` progress ≈ 85 s (two verified-object snapshot copies + setup); near-dup
scan ≈ 175 s; exact + approximate decontamination + commit ≈ 55 s.

Drift tests (run everywhere, no slice needed): a fixture whose child snapshot
`implementation_bundle_sha256` is off by one hex digit is rejected on insert by
`release_source_contract_snapshots_validate` ("does not match purpose contract"); a fixture
whose release-level `contract_snapshot_sha256` is stale is rejected at the pending → present
transition ("does not match child snapshots"). Together with the Go compare mode this is
the drift protection the card asked for.

Comparison run on the same database: `worker/tests/test_queue_integration.py` 7 passed in
4.9 s; full `go test ./internal/repository/` ok in 46 s (rehearsal test included). No test
schema was left behind on `derlem_ci_test`.

### Honest statement

The two halves run in **separate processes** joined by the fixture; no single process
drives API + worker. The fixture rows are exactly what Go wrote; Python does not fabricate
any contract value, and a fabricated one is caught by the database itself. The slice text
(203 MB) is **not** in git: both slice-dependent tests look in `var/olcum-2026-09-17` or
`DERLEM_PRETRAIN_SLICE_DIR` and skip **with a printed reason** when it is absent, so CI is
green but only the drift tests are exercised there; a full CI rehearsal would need the slice
as a CI artifact (not done, out of the moratorium). If the slice is present but its SHA
differs from the fixture, the Python half fails, not skips.

### Defects found

None in the freeze/export path. Two documentation-level mismatches to carry forward:

1. This card and TASK-019 name the gate `gate_results.exact_decontamination.compared_document_count`;
   the worker writes `gate_results.decontamination.reference_document_count` /
   `reference_unique_document_count` / `match_count` (`worker/src/derlem_worker/releases.py`,
   `DecontaminationResult.to_dict`). The tests assert the real keys; TASK-019's acceptance line
   should read the real keys when the letter is written.
2. `max_document_bytes` defaults to 256 KiB (`worker/src/derlem_worker/config.py`); a single
   longer line makes `exact_decontamination` raise `document_too_large` and block the freeze.
   The slice's longest line is 159,267 bytes; the full v3 candidate's longest line was not
   checked here — TASK-019 should check it (or set `MAX_DOCUMENT_BYTES`) before queueing.

Not changed: `clean_candidate.py`, `quality_filters.py`, anything under `var/derived`,
`var/import`, `docs/gorevler/README.md`.
