# TASK-020 — Rejection-report false-drop audit pack: stratified sheet (50 per reason) and byte-weighted scorer, no UI

| Field | Value |
|---|---|
| Status | **DRAFT** — from the 2026-09-19 plan ([plan_2026_09.md](../plan_2026_09.md), Faz 1); no new feature — may start when its dependencies are done |
| Kind | ops |
| Moratorium | allowed — a script and a document; no endpoint, no panel |
| Estimate | 1 day(s) |
| Depends on | — |
| Owner | (unassigned) |

## Goal

Give the shelf (or two office reviewers) a fixed-seed stratified sample of the 93,223-record rejection report and a scorer that turns their verdicts into a bytes-weighted false-drop rate per reason with a 95 % interval.

## Why

The shelf's one explicit ask (> 10 % of dropped bytes good text → talk). The 2026-09-17 slice showed whole encyclopedia articles dropped for a menu fragment; 55,677 lines were dropped by rules nobody audited. The result decides whether `tr-web-v2` is relaxed for v4/HF passes — never a v2 condition. The two-reviewer overlap also yields the first reviewer-agreement number (precondition for feature-list item 12, deferred).

## Scope

- `worker/src/derlem_worker/clean_candidate_audit.py`: from `…_v3.txt.rejections.jsonl` (SHA 2becaf9d…) draw min(50, stratum) per `reasons` stratum (12 quality reasons + near_duplicate + normalized_duplicate + language_not_turkish) with a fixed seed; CSV/markdown sheet with sha256, reasons, char_count, source_ordinal (to fetch the full line from the parent object), preview, `duplicate_of` partner preview, empty verdict column (`good` / `correct_drop` / `unsure`); seed + report SHA in the header.
- Scorer: refuses unknown verdicts; per-reason and overall false-drop share weighted by stratum bytes with binomial 95 % CI; writes `docs/atma_raporu_denetimi_v3.md`; optional agreement number when two reviewers mark the same 100 rows.
- Tests: stratum counts, seed determinism (identical sheet SHA), scorer reproduces a hand-computed rate on a synthetic sheet.

## Out of scope

- Audit UI (feature-list item 3).
- Any rule change to `tr-web-v2` (separate card after the number exists).
- Delaying v2 for the verdicts.
- Reviewer calibration beyond the free agreement number (feature-list item 12).

## Acceptance criteria

- [ ] Sheet row count = Σ min(50, stratum size); same seed → identical sheet SHA.
- [ ] After verdicts: per-reason table + overall bytes-weighted rate with interval, the three reasons with the highest false-drop share, comparison with 10 %.
- [ ] Owner decision on rule changes recorded; if > 10 %, a follow-up card exists before any re-derivation.

## Owner actions

- Hand the sheet to the shelf or assign two office reviewers (same 100 rows to both).
- Decide with the shelf whether any rule is relaxed for the next candidate.

## Report

(not started)
