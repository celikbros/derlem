# TASK-025 — Language on contributions and language-partitioned bundles

| Field | Value |
|---|---|
| Status | **DRAFT** — from the 2026-09-19 plan ([plan_2026_09.md](../plan_2026_09.md), Faz 3); needs the owner's approval before work starts |
| Kind | feature |
| Moratorium | **owner approval required** — owner ordering #1 (multilingual foundation) |
| Estimate | 1.5 day(s) |
| Depends on | TASK-002 S7 + TASK-009 |
| Owner | (unassigned) |

## Goal

Every contribution carries its own language into the canonical record; bundles never mix languages.

## Why

Contributions have no language field today; everything created before this is silently `tr`, and back-filling human data later is guesswork.

## Scope

- Migration `000030`: `contributions.language text NOT NULL DEFAULT 'tr'` with the same CHECK as `sources.language` (000001:72); Go registry validates the tag.
- Form: language select with help text (TASK-009 pattern; catalog test enforces help exists).
- `Bundle` partitions by task_type + language, refuses mixing (422 naming the field); bundled source `language` and each canonical record's `metadata.language` come from the contribution.
- Regenerate Go↔web catalog JSON and Go↔Python bundle fixture; drift tests; export gate test asserts language survives `build_release_export`; control run: drop the partition → mixed test red.

## Out of scope

- Per-language PII/quality rules.
- Phase B contribution types.
- UI i18n.

## Acceptance criteria

- [ ] Two `qa_pair` contributions `tr` and `en` bundle into two sources whose `language` differs; every canonical line's `metadata.language` equals its contribution's (fixture test on both sides).
- [ ] `TestContributionCatalogExplainsEveryField` green; jsonl export shows per-record `metadata.language`; CI green.

## Owner actions

- Approve; apply migration 000030 to the working DB; restart API.

## Report

(not started)
