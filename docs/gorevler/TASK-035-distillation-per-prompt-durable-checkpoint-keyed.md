# TASK-035 — Distillation per-prompt durable checkpoint keyed by request hash

| Field | Value |
|---|---|
| Status | **DRAFT** — from the 2026-09-19 plan ([plan_2026_09.md](../plan_2026_09.md), Faz 5); needs the owner's approval before work starts |
| Kind | feature |
| Moratorium | **owner approval required** — owner ordering #3 |
| Estimate | 2 day(s) |
| Depends on | TASK-034 |
| Owner | (unassigned) |

## Goal

A distillation job interrupted after k of n prompts resumes with exactly n−k further paid calls and produces the same final source.

## Why

Without it every worker crash can double a paid run; distilasyon.md lists it as mandatory before production use.

## Scope

- Checkpoint rows (job_id, request_hash, prompt_index, response object SHA, tokens) written after each successful call inside the existing lease/parent-child model; on retry skip completed indices; changed request (different hash) discards the checkpoint; final source assembled from checkpointed outputs; idempotency key per prompt where the provider supports it (best effort).
- Tests: injected failure after k prompts → rerun makes n−k calls for k ∈ {0, 3, n}; control run red; manifest lists attempts and resumed-from index.

## Out of scope

- Provider-side guarantees beyond best-effort keys.

## Acceptance criteria

- [ ] Echo run interrupted after k prompts resumes with exactly n−k further calls and an identical final manifest SHA; a changed request triggers a full rerun.

## Owner actions

- Approve; apply migration; restart worker.

## Report

(not started)
