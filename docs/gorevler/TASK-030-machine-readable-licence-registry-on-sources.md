# TASK-030 — Machine-readable licence registry on sources with a code-enforced derivation rule

| Field | Value |
|---|---|
| Status | **DRAFT** — from the 2026-09-19 plan ([plan_2026_09.md](../plan_2026_09.md), Faz 4); needs the owner's approval before work starts |
| Kind | feature |
| Moratorium | **owner approval required** — feature-list item 5; lands before the first HF dataset is registered |
| Estimate | 2 day(s) |
| Depends on | TASK-011 (decision), TASK-023 |
| Owner | (unassigned) |

## Goal

Every source carries a licence id and flags as data; a derived source can never be more permissive than its least permissive input.

## Why

A source registered without machine-readable terms is how this month's rights research became necessary; HF datasets arrive with explicit licences that must be captured as data, not prose. The vocabulary must also be able to express the v2 rights decision (path B: `owner-risk-accepted` with explicit flags) so the later mixture gate does not reject the v3 state as `unknown`.

## Scope

- Migration: `license_id` (CHECK against the Go vocabulary: CC-BY-4.0, CC-BY-SA-4.0, ODC-BY-1.0, site-terms, own-production, owner-risk-accepted, unknown…), `attribution_required`, `share_alike`, `commercial_use` (allowed/forbidden/unknown), `evidence_sha256`; free-text `license` kept for display; `rights_status` stays the decision field; API 422 `license_id_unknown`.
- Derivation rule in code across `derived_from_source_id` + `source_lineage_inputs`; backfill `unknown` everywhere except synthetic (own-production) and path-B sources (explicit flags from the owner's memo); owner-approved flags for the raw sources, parent, v3 candidate from the TASK-011 notes and the chosen path.
- Tests: migration, validation, derivation rule; control run.

## Out of scope

- Mixture gate (TASK-031).
- Legal decisions about the vocabulary.

## Acceptance criteria

- [ ] `PATCH /sources/{id}` with `license_id: CC-BY-SA-4.0` stores flags; unknown id → 422.
- [ ] Deriving from an input with `commercial_use = forbidden` cannot yield `allowed` (test; control run red).
- [ ] 7/7 raw sources, the parent and the v3 candidate carry flags consistent with TASK-011 and the chosen path; every source row has a `license_id`; the v3 candidate's flags equal the least permissive of its seven inputs (query recorded).

## Owner actions

- Approve; decide the vocabulary (including what flags `owner-risk-accepted` carries under the memo); apply migration; approve the flag updates per row.

## Report

(not started)
