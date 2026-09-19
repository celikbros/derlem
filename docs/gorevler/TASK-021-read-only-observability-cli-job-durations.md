# TASK-021 — Read-only observability CLI: job durations, queue depth, review throughput from existing columns (read-only session enforced in code)

| Field | Value |
|---|---|
| Status | **DRAFT** — from the 2026-09-19 plan ([plan_2026_09.md](../plan_2026_09.md), Faz 2); needs the owner's approval before work starts |
| Kind | ops |
| Moratorium | **owner approval required** — feature-list item 4 (owner leaning to accept); CLI only, no endpoint or panel |
| Estimate | 1 day(s) |
| Depends on | TASK-015 |
| Owner | (unassigned) |

## Goal

A command that prints p50/p95/max run time and queue wait per job type, queue depth, failures, sweep runs and review decisions per hour per reviewer, from existing tables, with no schema change and a session that cannot write.

## Why

'İnceleme hızı ölçülmedi' and unmeasured freeze/export durations appear in two letters; the sweep bug was found by accident. Phase 4 sizing and the office team's review capacity need these numbers. No read-only DB role exists in the repo (`deploy/`, ofis_kurulumu.md, backup_restore.md checked), so the script enforces read-only itself instead of assuming one.

## Scope

- `python -m derlem_worker.reports.throughput --since 7d`: `background_jobs` (`created_at`, `locked_at`, `completed_at`, 000001:134-140) → run time and queue wait percentiles per `job_type`, queued/running counts, oldest queued age, failed jobs with `last_error` head; `document_reviews` (`reviewer_id`, `created_at`, 000007) → decisions per hour per reviewer per day; open claims from `document_review_claims`; sweep log lines from TASK-015.
- Read-only guarantee: the connection runs `SET default_transaction_read_only = on` before any query; unit test asserts an INSERT through the report's session raises `cannot execute INSERT in a read-only transaction`.
- Markdown to stdout and `var/reports/ops_<ts>.md` (inside backup scope); unit test with seeded rows asserts percentile arithmetic; docs/job_progress.md.
- Run once on the working DB with the existing worker credentials (owner-approved single run); paste the baseline (v3 ingest, fingerprint, sampling, the 200-review speed) into the card.

## Out of scope

- JSON endpoint, panel, dashboard.
- Schema changes.
- Creating a `derlem_readonly` DB role (cluster-level; a separate owner decision via psql if the office team needs it later).

## Acceptance criteria

- [ ] Command exits 0 on the working DB in a read-only session; every job_type seen in the window listed with counts and p50/p95; numbers equal a hand-written SQL check for one run (recorded).
- [ ] Read-only test green (INSERT refused through the report session).
- [ ] Review throughput section shows the v2 review sessions' documents/hour (cross-checks TASK-012); unit tests green; CI green.

## Owner actions

- Approve as feature-list item 4; confirm CLI-only.
- Approve one read-only run on the working DB with the existing credentials; optionally decide whether a dedicated read-only role should be created later (not required).

## Report

(not started)
