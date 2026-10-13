# TASK-046 — Two rules the web corpora need: machine-translated text and commercial/product pages

| Field | Value |
|---|---|
| Status | **READY** — 2026-10-13, owner: "yes, after the import, before the freeze" |
| Kind | fix (quality rules) |
| Moratorium | allowed — measured filter gap |
| Estimate | 1.5 day(s) |
| Depends on | TASK-032 (the imported data to measure on); supersedes classes 1 and 3 of TASK-042 |
| Owner | (unassigned) — opus |

## Why

Blind, mixed, same-judge reading of 100 + 100 documents (2026-10-04): FineWeb2-HQ 43 % junk,
v5 53 % junk. The junk differs — and **our rules see almost none of it on FineWeb2-HQ**
(`tr-web-v3` drops 0.6 % of its documents where the judge calls ~40 % junk).

| Junk cause (mixed reading) | FineWeb2-HQ | v5 |
|---|---:|---:|
| Machine translation | **12** | 1 |
| SEO / commercial / product | 12 | **18** |
| Menu / headline pile | 1 | 12 |
| Adult / betting | 1 | 7 |

Machine translation is at least 8–14 % of FineWeb2-HQ documents and **16–33 % of its bytes**
(long documents, concentrated in 2020+ dumps); the dataset's own `quality_score` does not
separate it (median 0.19 for translated vs. 0.10 for the rest). The thirteen eyeball-flagged
translation documents that reached the jury were called junk by the jury 13/13 — two independent
methods agree.

## Scope

- **`machine_translation`** rule, structural not topical, measured on the 1,200-document
  FineWeb2-HQ sample (`var/olcum-2026-10-03/fineweb2-hq/`, eyeball flags + jury verdicts as
  labels) and on the full import once TASK-032 lands. Candidate signals, each measured alone and
  combined: URL signature (host starts with `tr.`, path contains `/tr/`, non-Turkish TLD with
  Turkish text) — only available because the common record carries `url`; literal-translated
  proper nouns (brand/surname dictionary hits: "Düşük" for Low, "Hayalet" for Ghost…);
  function-word profile drift and Cyrillic residue (TASK-040 signals); sentence-length and
  punctuation regularity typical of MT. Report recovered/admitted counts on labelled rows as in
  TASK-040; owner anchor of ~20 rows.
- **`commercial_page`** rule: product/price/buy signals, sponsor and affiliate markers, spec
  tables, listing templates (neighbourhood × service) — the owner's measured line is
  "encyclopedia stays, sponsored review goes" with format first (TASK-041).
- Both ship as `tr-web-v4` (v3 verdicts frozen), with decision rows in the new decision record
  (TASK-044) rather than only the rejection report.
- Control runs; regression on the lines v5 keeps and on the FineWeb2-HQ sample's `kalsin` rows.

## Out of scope

- Topic filters. Re-deriving v5.
- Template dictionary pages and Wikipedia namespace filter (remaining TASK-042 items).

## Acceptance criteria

- [ ] On the labelled FineWeb2-HQ rows: machine-translation recall ≥ 80 % at ≤ 5 % false drops
      among `kalsin` rows (targets to be confirmed by the owner before tuning).
- [ ] Commercial rule measured the same way on both corpora.
- [ ] Judge rerun on 200 documents after the rules: junk share before/after with intervals.

## Owner actions

- Confirm the recall/false-drop targets above; judge ~20 anchor rows.

## Report

(not started)
