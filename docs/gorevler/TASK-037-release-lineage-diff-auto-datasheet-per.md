# TASK-037 — Release lineage diff + auto datasheet per frozen release

| Field | Value |
|---|---|
| Status | **DRAFT** — from the 2026-09-19 plan ([plan_2026_09.md](../plan_2026_09.md), Faz 5); needs the owner's approval before work starts |
| Kind | feature |
| Moratorium | **owner approval required** — feature-list items 7 and 8; only once a second frozen pretrain release exists |
| Estimate | 2 day(s) |
| Depends on | TASK-031, TASK-036 |
| Owner | (unassigned) |

## Goal

For any two releases, what was added/removed/kept; for any frozen release, an immutable datasheet whose numbers equal the manifest.

## Why

The model's 'what is new' and the legal 'what is in it' questions need it once there is more than one release; until then the delivery letter and manifest carry the content.

## Scope

- Diff by `document_sha256` (family-aware): added/removed/kept, byte and token deltas, per-source and per-licence change; stored as an object linked from the newer release.
- Datasheet (markdown object): sources with SHAs and licences, gate results, licence and language mixture, decontamination results, tokenizer counts, `known_issues` filled by the owner at draft time; `GET /releases/{id}/datasheet`.
- Tests on fixture releases.

## Out of scope

- Editing frozen manifests.
- Consumer download resume / consumer API keys (feature-list item 11 — deferred in the plan's what-not-to-do until a consumer outside the LAN exists).

## Acceptance criteria

- [ ] `GET /releases/{id}/datasheet` returns markdown whose numbers equal the manifest's; diff of v2 vs v2 = 0 added / 0 removed.
- [ ] First real datasheet attached to a delivery follow-up letter after owner review.

## Owner actions

- Approve when a second release exists; review the first datasheet text.

## Report

(not started)
