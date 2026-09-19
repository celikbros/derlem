# TASK-033 — Tokenizer-true counting with a registered tokenizer artifact (estimate kept; exact count added when configured)

| Field | Value |
|---|---|
| Status | **DRAFT** — from the 2026-09-19 plan ([plan_2026_09.md](../plan_2026_09.md), Faz 4); needs the owner's approval before work starts |
| Kind | feature |
| Moratorium | **owner approval required** — scoped deviation from canonical_exports.md for measurement only |
| Estimate | 1.5 day(s) |
| Depends on | TASK-019 |
| Owner | (unassigned) |

## Goal

Export and clean-candidate manifests carry `token_count_exact` with the tokenizer's id and SHA256 next to the existing codepoint estimate.

## Why

Both sides of the ~0.4 B token gap are 5.405 bytes/token conversions; a 10 % error is 0.2 B tokens. No tokenizer is named anywhere in the repo ('v3.8' is the gardash corpus release), so the shelf must send one.

## Scope

- Tokenizer artifact registered in the object store via config (never UI); counting streams the artifact; determinism test with a tiny fixture tokenizer; verify the dependency installs on Windows/3.14 before promising.
- Manifests: `token_count_exact`, `tokenizer_id`, `tokenizer_sha256`; `token_estimate` unchanged; manifest without a configured tokenizer still validates.
- Run on the v2 export; record exact vs estimate; recompute the TASK-013 gap.

## Out of scope

- Changing the export contract or the estimate field.
- Any model-specific export format.

## Acceptance criteria

- [ ] v2 export manifest shows the three fields; the shelf confirms the count for the same artifact SHA by letter.
- [ ] Manifest without tokenizer still validates; TASK-013 gap recomputed with the estimate error recorded.

## Owner actions

- Ask the shelf for the tokenizer file/id + SHA256 by letter; approve the scoped deviation.

## Report

(not started)
