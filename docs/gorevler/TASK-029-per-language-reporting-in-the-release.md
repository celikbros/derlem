# TASK-029 — Per-language reporting in the release mixture report (bytes by detected distribution; PII/quality coverage per language)

| Field | Value |
|---|---|
| Status | **DRAFT** — from the 2026-09-19 plan ([plan_2026_09.md](../plan_2026_09.md), Faz 3); needs the owner's approval before work starts |
| Kind | feature |
| Moratorium | **owner approval required** — owner ordering #1 (reporting only) |
| Estimate | 1 day(s) |
| Depends on | TASK-028, TASK-025 |
| Owner | (unassigned) |

## Goal

The mixture report shows, per language, bytes/lines and which gates could evaluate that language.

## Why

Completes the cheap multilingual foundation; freeze stays blocked by `not_evaluated` (TASK-005), the report makes the reason visible per language.

## Scope

- Mixture report groups by each source's detected distribution (fallback: declared `language`); per language: PII coverage (`clear` vs `not_evaluated`, basic-tr-v2 Turkish-only), quality-filter coverage.
- release_mixture_report.md updated; tests with the mixed fixture on the scratch DB.

## Out of scope

- New rules; UI beyond the existing report view.

## Acceptance criteria

- [ ] Scratch release with the mixed fixture: report shows `en` bytes and `pii_not_evaluated_lines = 30`; language shares sum to release totals; tests green.

## Owner actions

- Approve.

## Report

(not started)
