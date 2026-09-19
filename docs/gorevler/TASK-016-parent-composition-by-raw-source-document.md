# TASK-016 — Parent composition by raw source, document-boundary measurement, and the v2 rights contingency table

| Field | Value |
|---|---|
| Status | **DONE** — 2026-09-19: containment, exclusive attribution, length and bytes-per-scenario measured (below); decision is TASK-011's. Was: DRAFT — from the 2026-09-19 plan ([plan_2026_09.md](../plan_2026_09.md), Faz 1); no new feature — may start when its dependencies are done |
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

### Exclusive attribution by lines (measured 2026-09-19, 1,260 s)

Parent unique lines found in **exactly one** raw source:

| Raw source | Exclusive lines | Share of parent lines |
|---|---|---|
| `tr_corpus` | 1,501,077 | 24.90 % |
| `wiki_oscar` | 44,820 | 0.74 % |
| `celik_gold` | 44,328 | 0.74 % |
| `tdk` | 20,848 | 0.35 % |
| `academic` | 41 | 0.00 % |
| `trt` | 4 | 0.00 % |
| `ttk` | 1 | 0.00 % |

Most frequent source combinations: `celik_gold+wiki_oscar` 4,207,949 · `tr_corpus` alone
1,501,077 · `celik_gold+ttk` 84,693 · `celik_gold+tdk` 77,724 · `celik_gold+academic` 45,167.
So **`celik_gold` is a merge, not an independent source**: 99 % of its documents also exist in
another raw file; only 44,328 lines are its own. **`tr_corpus` is the opposite**: fully
exclusive, unknown provenance. Dropping both leaves 1,545,405 parent lines (25.64 %) uncovered.

Length per raw source (characters): `wiki_oscar` mean 2,737 (0.9 % < 120), `celik_gold`
2,647, `trt` 2,552, `academic` 1,278, `ttk` 1,180, **`tr_corpus` 278 (39.0 % < 120)**,
**`tdk` 85 (77.2 % < 120)** — the short fragments the 100k slice found come from these two.

Line shares mislead here (sources differ tenfold in line length); bytes per scenario are
measured in the next pass.

### Bytes per rights scenario (measured 2026-09-19, 1,066 s)

Parent: 6,027,968 lines, 13,569,773,056 bytes. A parent line is kept in a scenario if its
normalised text is found in at least one allowed raw source (and in no TRT document, from S1 on).

| Scenario | Allowed raw sources | Kept bytes | Share |
|---|---|---|---|
| S0 — today's v3 input | all seven | 13,569,773,056 | 100.00 % |
| S1 — drop TRT (terms forbid copying) | all but `trt` | 13,569,220,927 | 100.00 % |
| S2 — drop unknown provenance too | `wiki_oscar`, `ttk`, `academic`, `tdk` | 12,847,009,148 | 94.67 % |
| S3 — S2 minus `ttk` (CC BY-NC; commercial target) | `wiki_oscar`, `academic`, `tdk` | 12,737,682,394 | 93.87 % |
| S4 — S3 minus `tdk` (no licence statement) | `wiki_oscar`, `academic` | 12,728,760,928 | 93.80 % |
| **S5 — only the documented-licence source** | `wiki_oscar` | **12,665,606,700** | **93.34 %** |

Byte shares by exclusive source: `tr_corpus` only 456,043,593 (3.36 %), `celik_gold` only
266,168,186 (1.96 %), `wiki_oscar` only 270,542,687 (1.99 %), `tdk` only 558,206; lines found
in any TRT document 552,129 bytes; nothing unattributed (0 bytes).

**`wiki_oscar` provenance verified from content** (every 50th record, 85,075 records): each
record carries `source`; values are `mc4` (77,087, 90.6 %) and `wikipedia` (7,988, 9.4 %) only;
no URLs. So its terms are the documented ones: mC4 ODC-BY + Common Crawl terms, Wikipedia
CC BY-SA 3.0 + GFDL.

**Reading:** the rights problem is 6.66 % of the bytes. The unknown-provenance files are
either a merge of the others (`celik_gold`: 1.96 % own) or short fragments (`tr_corpus`:
3.36 % of bytes, 24.9 % of lines, mean 278 chars). S5 keeps 93.34 % and needs only the
documented licence terms to be accepted.

Earlier plan note — per-source **exclusive** attribution — parent lines found in exactly one raw
source, and the count of parent lines not covered by any source other than
`celik_gold`/`tr_corpus`. If that count is ~0, the two unknown-provenance files add no
unique text and their rights question falls away. Length distribution per raw source is
measured in the same pass (document-boundary question).
