# TASK-031 — Licence mixture in the release report, `intended_use` on releases, freeze gate on incompatible terms

| Field | Value |
|---|---|
| Status | **DRAFT** — from the 2026-09-19 plan ([plan_2026_09.md](../plan_2026_09.md), Faz 4); needs the owner's approval before work starts |
| Kind | feature |
| Moratorium | **owner approval required** |
| Estimate | 1.5 day(s) |
| Depends on | TASK-030, TASK-019 |
| Owner | (unassigned) |

## Goal

Each release states its intended use, its report shows byte share per licence and flag, and freeze refuses an owner-declared incompatible mixture.

## Why

Makes the datasheet and the legal story mechanical for every future release; needed once a share-alike (Wikipedia) source is in the mix.

## Scope

- Release draft gains `intended_use` (values set by the owner, e.g. `internal-training`, `commercial-model`).
- Mixture report: byte/document share per `license_id` and per flag; frozen manifest snapshots the table.
- `QueueFreeze`: 422 `license_mixture_incompatible` naming the pair when the declared incompatibility is present or any flag is `unknown`.
- Tests on the scratch DB; control run; release_mixture_report.md updated.

## Out of scope

- Modelling law beyond the owner's table.

## Acceptance criteria

- [ ] Scratch release with one CC-BY-SA source: `share_alike` share > 0, freeze passes for `internal-training`; with a `commercial_use = forbidden` source and `intended_use = commercial-model` → 422.
- [ ] Frozen manifest carries the mixture table with shares summing to 100 %.

## Owner actions

- Approve; define `intended_use` values and refused pairs.

## Report

(not started)
