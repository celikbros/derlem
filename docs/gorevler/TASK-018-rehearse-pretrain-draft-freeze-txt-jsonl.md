# TASK-018 — Rehearse pretrain draft → freeze → txt/jsonl export on the `_test` database with the 100k slice (Go half: draft + QueueFreeze; Python half: freeze + export jobs in-process)

| Field | Value |
|---|---|
| Status | **DRAFT** — from the 2026-09-19 plan ([plan_2026_09.md](../plan_2026_09.md), Faz 1); no new feature — may start when its dependencies are done |
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

- [ ] Go half: draft created through the repository with `contract_snapshot_status = present`; `QueueFreeze` inserts a `freeze_release` job row; no-holdout case → 422 `eval_reference_missing`; fixture committed.
- [ ] Python half: scratch release `frozen`; `gate_results.exact_decontamination.compared_document_count = 43`, matches 0; approximate gate `reported`; two `release_exports` rows `ready`; recomputed SHA256 equals manifest for both.
- [ ] Measured MB/s and extrapolated hours written in TASK-019; both halves green in CI.

## Owner actions

- Explicit OK to run both halves inside the existing Go and pytest harnesses against `derlem_ci_test` (no service is started).

## Report

(not started)
