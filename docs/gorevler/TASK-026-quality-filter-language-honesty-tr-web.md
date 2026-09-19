# TASK-026 — Quality-filter language honesty: `tr-web-*` policies write `not_evaluated` for non-Turkish sources

| Field | Value |
|---|---|
| Status | **DRAFT** — from the 2026-09-19 plan ([plan_2026_09.md](../plan_2026_09.md), Faz 3); no new feature — may start when its dependencies are done |
| Kind | fix |
| Moratorium | allowed — same defect class as TASK-005 |
| Estimate | 0.5 day(s) |
| Depends on | — |
| Owner | (unassigned) |

## Goal

The offline clean-candidate derivation never applies Turkish lexicon rules to a source whose declared language is not Turkish; it records `not_evaluated` instead.

## Why

`tr-web-v1/v2` are Turkish-only; applying them to another language produces a verdict on nothing. This is a guard in the derivation script (release quality rows come from `document_reviews`), not release gate reporting — labelled honestly.

## Scope

- `quality_filters.py`: `supported_languages = {'tr'}` on `tr-web-v1/v2`.
- `clean_candidate.py`: source language outside the set → manifest `quality_filter_status: not_evaluated`, 0 quality drops.
- Tests + control run; temiz_aday_v3.md note.

## Out of scope

- New quality rules.
- Language detection (TASK-028).

## Acceptance criteria

- [ ] `clean_candidate --quality-policy tr-web-v2` on a `language = en` source writes `not_evaluated` and drops 0 lines for quality; `tr` behaviour unchanged (existing tests green).
- [ ] Control run with the guard removed → new test red.

## Owner actions

- None.

## Report

(not started)
