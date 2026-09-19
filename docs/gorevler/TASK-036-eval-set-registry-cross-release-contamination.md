# TASK-036 — Eval-set registry + cross-release contamination re-check report

| Field | Value |
|---|---|
| Status | **DRAFT** — from the 2026-09-19 plan ([plan_2026_09.md](../plan_2026_09.md), Faz 5); needs the owner's approval before work starts |
| Kind | feature |
| Moratorium | **owner approval required** — feature-list item 9; after v2 and after the first external eval set exists |
| Estimate | 2 day(s) |
| Depends on | TASK-017, TASK-019 |
| Owner | (unassigned) |

## Goal

Every registered eval/holdout set is checked against every frozen release, at freeze and retroactively when a new set arrives, with results in the manifest or a separate report object.

## Why

The shelf wrote that task evals come as separate `eval` sources; today contamination is checked only against our own held-out split.

## Scope

- Registry view over sources with purpose eval/holdout (version, SHA, registered date).
- At freeze: exact + approximate decontamination against every registered set; per-set results in the manifest.
- Maintenance job: when a new eval set is registered, re-check all frozen releases and write a separate report object (frozen manifests never change).
- Tests with two eval sources; control run; eval text never appears in reports.

## Out of scope

- Making the approximate result a hard gate.

## Acceptance criteria

- [ ] Freeze manifest lists every eval/holdout source with match counts; registering a new set after a freeze produces a report object naming affected releases and counts; approximate cost measured on first run.

## Owner actions

- Approve; carry afacan's task eval sets as `eval` sources.

## Report

(not started)
