# TASK-034 — Distillation cost estimate + approval gate + hard caps (calls/tokens, durable daily counter) + model-id validation

| Field | Value |
|---|---|
| Status | **DRAFT** — from the 2026-09-19 plan ([plan_2026_09.md](../plan_2026_09.md), Faz 5); needs the owner's approval before work starts |
| Kind | feature |
| Moratorium | **owner approval required** — owner ordering #3 |
| Estimate | 2 day(s) |
| Depends on | TASK-019 |
| Owner | (unassigned) |

## Goal

No paid provider call happens without an estimate the requester saw, a cap the job cannot exceed, and a model id known to be valid.

## Why

distilasyon.md lists cost quota/estimate/approval as mandatory before production use; a retry today can repeat paid calls and a mistyped model id fails after the budget is reserved. Hard limits are in calls/tokens because price tables go stale; the currency figure is an estimate with its table version recorded (explicit owner decision).

## Scope

- `POST /sources/{id}/distill`: estimate = count × (prompt tokens + max_tokens) × configured dated rate; response carries it; `confirm_estimate: true` required above the owner's threshold; 422 `distill_budget_exceeded` (both numbers) before any `background_jobs` row when estimate > `max_cost` (bounded by a server-side ceiling) or calls > `DISTILL_MAX_CALLS_PER_RUN` / `_PER_DAY`.
- Job: running totals in the result, hard stop at the cap with terminal state `budget_exhausted`; daily counter in the DB; manifest records planned vs actual calls/tokens and the price-table version.
- Model id validated per provider (model list where offered, else allowlist in `PROVIDERS`) → 422 `model_id_unknown` before enqueue.
- Echo-provider tests; control run. Interim control until merged: no real provider keys in the worker env.

## Out of scope

- Settings page; new distillation kinds (b)/(d).
- Per-prompt checkpoint (TASK-035).

## Acceptance criteria

- [ ] Echo run `count = 10`, `max_calls = 4` → exactly 4 provider calls, state `budget_exhausted`, manifest `actual_calls = 4`.
- [ ] Request over cap → 422 with the estimate and no job row; model `nope` → 422 before any job; allowlisted id passes.
- [ ] Running spend visible in the Jobs view counters; CI green.

## Owner actions

- Approve; set env caps and the `max_cost` ceiling; supply the dated price table as configuration; set the approval threshold.

## Report

(not started)
