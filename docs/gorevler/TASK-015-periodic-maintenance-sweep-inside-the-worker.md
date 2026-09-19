# TASK-015 — Periodic maintenance sweep inside the worker loop (TASK-014 follow-up)

| Field | Value |
|---|---|
| Status | **IN REVIEW** — 2026-09-19: implemented; waiting for the owner to restart the worker. Was: DRAFT — from the 2026-09-19 plan ([plan_2026_09.md](../plan_2026_09.md), Faz 1); no new feature — may start when its dependencies are done |
| Kind | fix |
| Moratorium | allowed — a gate that silently waits for a restart blocks the approved v2 path |
| Estimate | 0.5 day(s) |
| Depends on | TASK-014 |
| Owner | (unassigned) |

## Goal

Run `enqueue_maintenance_jobs()` periodically from `run_forever` so a source reset or late registration is picked up without a worker restart.

## Why

Found 2026-09-19 (TASK-014 step 5): the sweep runs once in `main.py` before the loop; a `not_checked` reset made after start-up is never enqueued. Every later registration (overlap pilot, raw files, HF datasets) passes through the same gates. Not a freeze prerequisite: freeze/export jobs are inserted by the API.

## Scope

- `worker/src/derlem_worker/jobs/worker.py`: call the sweep from `run_forever` when `MAINTENANCE_SWEEP_SECONDS` (config, default 300) has elapsed; keep the start-up call in `main.py`.
- The sweep enqueues only `check_exact_duplicate`, `index_document_fingerprints`, `sample_documents` (worker.py:37-118); it is idempotent (`ON CONFLICT DO NOTHING`, NOT EXISTS on queued/running).
- Unit test with an injected clock: below the interval not called again; past it exactly once more. Control run: revert the loop call → red; paste output.
- One log line per sweep with the three counts (read by TASK-021).
- Docs: job_progress.md note; TASK-014 report pointer.

## Out of scope

- Any change to what the sweep enqueues.
- Endpoint or UI for the sweep.

## Acceptance criteria

- [ ] `python -m pytest worker/tests -q` green incl. the interval test. Measured 2026-09-19 before this card: 271 collected, 270 passed + 1 skipped (TASK-014 report). After this card: 272 collected, 271 passed + 1 skipped. Control run documented red.
- [ ] On the running stack after an owner-approved reset of a test source's `normalized_dedup_status` to `not_checked`, an `index_document_fingerprints` row appears in `background_jobs` within 2 × interval without a restart (read-only query).
- [ ] CI green on the closing commit.

## Owner actions

- Restart the worker after the commit is on main.

## Report

**Done 2026-09-19.** `Config.maintenance_sweep_seconds` (`MAINTENANCE_SWEEP_INTERVAL`, default `5m`);
`Worker.maybe_sweep_maintenance(now)` runs `enqueue_maintenance_jobs()` when the interval has
elapsed (first periodic sweep one interval after start; the start-up sweep in `main.py` stays);
`run_forever` calls it on every loop turn with `time.monotonic()`. A sweep failure is logged
(`maintenance_sweep_failed`) and does not stop the loop. Configs that predate the field
(tests use `SimpleNamespace`) fall back to 300 s.

Tests (`worker/tests/test_maintenance_sweep.py`, fake clock): once per interval not per poll;
failure does not stop the loop; default interval. Full worker suite: 273 passed, 1 skipped.
Control run: making the sweep ignore the interval turns all three tests red.

Owner action pending: restart the worker after this is on main.
