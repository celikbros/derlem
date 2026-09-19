# TASK-022 — Document-boundary policy note (fragments vs whole documents) for new intake and any re-derivation

| Field | Value |
|---|---|
| Status | **DRAFT** — from the 2026-09-19 plan ([plan_2026_09.md](../plan_2026_09.md), Faz 2); no new feature — may start when its dependencies are done |
| Kind | research |
| Moratorium | allowed — a decision note (feature-list item 2 reduced to policy; corpus merge deferred) |
| Estimate | 0.5 day(s) |
| Depends on | TASK-016 |
| Owner | (unassigned) |

## Goal

A written, dated policy on how new sources carry document boundaries and whether Faz-2 is ever re-derived with boundaries, before any Hugging Face intake.

## Why

The parent lost boundaries (title + body lines, Wikipedia sentence fragments); flattening later is free, un-flattening impossible. The shelf kept short lines on 2026-09-18 as dense data; revisit only with a number from them.

## Scope

- `docs/belge_sinirlari_politikasi.md`: TASK-016 findings per source; how txt (newlines → space) and jsonl carry boundaries today (canonical_exports.md); options (a) whole records with paragraph breaks preserved in JSONL, joined only at txt export; (b) re-derive Faz-2 from raw JSONL once rights allow; (c) v3 stays the v2 delivery; cost of each in days and review resets; the HF intake rule 'one record = one document, never split'.
- One question to the shelf in the next letter: does packing prefer whole documents or are fragments fine?

## Out of scope

- Changing the v3 candidate.
- Merging fragments in the existing corpus (deferred; open decision #1).
- Implementing the intake (TASK-032).

## Acceptance criteria

- [ ] Policy doc exists with a dated owner decision line and the shelf's answer (or 'not answered yet').
- [ ] TASK-032 cites the policy in its scope.

## Owner actions

- Decide (a)/(b)/(c) and date it; recommended: (a) yes, (c) yes, (b) later.

## Report

(not started)
