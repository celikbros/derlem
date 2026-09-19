# TASK-016 — Parent composition by raw source, document-boundary measurement, and the v2 rights contingency table

| Field | Value |
|---|---|
| Status | **IN PROGRESS** — 2026-09-19: containment measured (below); exclusive attribution + length distribution running. Was: DRAFT — from the 2026-09-19 plan ([plan_2026_09.md](../plan_2026_09.md), Faz 1); no new feature — may start when its dependencies are done |
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

### Containment (measured 2026-09-19, 1,235 s)

Method: every line of the parent (`9826d58e…`, 6,027,968 lines → 6,027,720 unique after
whitespace-collapse + casefold normalisation, BLAKE2b-128) was indexed; every document of
each raw file (`text`/`content`/`body` field of JSONL, or the raw line) was normalised the
same way and looked up.

| Raw source | Documents | Found in parent | Share |
|---|---|---|---|
| `celik_gold` | 4,460,931 | 4,460,931 | 100.0 % |
| `wiki_oscar` | 4,253,739 | 4,253,739 | 100.0 % |
| `tr_corpus` | 1,502,165 | 1,502,165 | 100.0 % |
| `tdk` | 118,455 | 118,455 | 100.0 % |
| `ttk` | 84,789 | 84,789 | 100.0 % |
| `academic` | 45,208 | 45,208 | 100.0 % |
| `trt` | 388 | 388 | 100.0 % |

Parent lines matched by at least one raw source: **6,027,720 / 6,027,720 (100.00 %)**,
unmatched 0 — the seven files are the complete input, nothing else went in. Raw documents
sum to 10,465,675 (= `documents_in` of the Faz-2 manifest) against 6,027,720 unique parent
lines, so the raw sources overlap heavily with each other; `celik_gold` alone (4.46 M docs,
13.0 GB) is near the size of the whole parent and is likely a merge of the others.

Next (running): per-source **exclusive** attribution — parent lines found in exactly one raw
source, and the count of parent lines not covered by any source other than
`celik_gold`/`tr_corpus`. If that count is ~0, the two unknown-provenance files add no
unique text and their rights question falls away. Length distribution per raw source is
measured in the same pass (document-boundary question).
