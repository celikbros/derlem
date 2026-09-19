# TASK-016 — Parent composition by raw source, document-boundary measurement, and the v2 rights contingency table

| Field | Value |
|---|---|
| Status | **DRAFT** — from the 2026-09-19 plan ([plan_2026_09.md](../plan_2026_09.md), Faz 1); no new feature — may start when its dependencies are done |
| Kind | research |
| Moratorium | allowed — measurement, no product surface |
| Estimate | 1.5 day(s) |
| Depends on | — |
| Owner | (unassigned) |

## Goal

Know what share of the parent corpus (13,569,773,056 bytes, 6,027,968 lines) and of the v3 candidate comes from each of the seven raw files, how document boundaries look per source, and what each rights scenario (A/B/C) costs — before the owner's second review session.

## Why

The rights decision is otherwise all-or-nothing: the parent is one merged file and the source-labelled `gardash_tr_dedup.jsonl` was deleted. A per-source share prices a `blocked` decision; per-source fragment shares feed the boundary policy (TASK-022) and the volume plan (TASK-013). The 2026-09-17 letter measured only a global 11.84 % of lines < 120 chars.

## Scope

- Scratch script (not product): hash every document of the seven raw files under `var/raw-derlem/ham-derlem/` and every parent line — exact line bytes first, then `normalized-document-sha256-v1`; map parent lines → raw source; report line and byte share per source in the parent and in the v3 candidate (via the rejection report's `source_ordinal` and the held-out rule); unmatched share as a number; runtime measured.
- Optional determinism check: fetch `scripts/rebuild_faz2_corpus.py` from `celikbros/Gardash`, fix paths, compare per-source counts with `per_source.in`; divergence reported, not hidden.
- Per raw source: length p10/p50/p90, fragment share (< 120 chars, no terminal punctuation), 'title + body' share, whether the raw JSONL keeps document structure the flat parent lost.
- Contingency table appended to TASK-011: per scenario (A cleared inputs only / B whole parent under the owner's memo / C defer) input bytes, tokens at 5.405 bytes/token (labelled estimate), derivation hours from 3.4 h / 13.57 GB, whether the 200-sample review survives.
- Write `docs/parent_bilesimi_ve_belge_sinirlari.md`.

## Out of scope

- Registering any raw file (TASK-010b).
- Any re-derivation of the corpus.
- Rights recommendations (TASK-011).

## Acceptance criteria

- [ ] Table with 7 rows + 'unmatched' whose byte shares sum to 100 % of the parent; unmatched share stated; runtime written.
- [ ] Per-source fragment share and percentiles; per source a yes/no on boundary-preserving re-derivation from the raw file.
- [ ] Contingency table with three scenarios present in TASK-011 before the owner's decision date ('TASK-011 (decision)' depends on this card).

## Owner actions

- None (read-only on the archive; hash sets ~200 MB in memory, no temp disk).

## Report

(not started)
