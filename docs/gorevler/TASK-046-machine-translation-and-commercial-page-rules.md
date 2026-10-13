# TASK-046 — Two rules the web corpora need: machine-translated text and commercial/product pages

| Field | Value |
|---|---|
| Status | **IMPLEMENTED** — 2026-10-13; awaiting the owner's confirmation of the (provisional) targets and the judge rerun (blind file ready) |
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
- [x] Commercial rule measured the same way on both corpora. (2026-10-13: HQ 15.4 % / v5 34.3 % recall, 0 false drops on either corpus.)
- [ ] Judge rerun on 200 documents after the rules: junk share before/after with intervals.

## Owner actions

- Confirm the recall/false-drop targets above; judge ~20 anchor rows.

## Report

**Status: IMPLEMENTED** (2026-10-13) — code, tests, labelled measurement and the full-import
pass are done; the targets are still provisional, the judge rerun and the owner anchor are
owed. Full measurement: [var/olcum-2026-10-13/task-046/RAPOR.md](../../var/olcum-2026-10-13/task-046/RAPOR.md);
policy note: [docs/tr_web_v4_kalite_politikasi.md](../tr_web_v4_kalite_politikasi.md).

### What shipped

`tr-web-v4` = `tr-web-v3` (frozen, called as is) + `machine_translation` + `commercial_page`.
New modules `quality_v4.py`, `machine_translation.py`, `commercial_page.py`; `quality_filters.py`
gains the policy name and an optional `url` argument (read by v4 only); `clean_candidate.py`
reads `url` / `provenance.url` from a JSONL line under v4 and, in `--selection-list` mode, writes
**one `derlem.decision.v1` row per reason** (`decision_type=quality_rule`, `verdict=reject`,
`reason=machine_translation|commercial_page|<v3 reason>`, `judge=tr-web-v4@<sha12>` — the sha
of the six rule source files, LF-normalised; currently `tr-web-v4@bb0e396ee7b5`). The manifest
carries the same id in `quality_judge`. v1–v3 decision rows are unchanged.

- **`machine_translation`** = (URL signature ∧ (profile ≥ −4‰ ∨ sentence-initial "Bu," ∨
  Cyrillic residue)) ∨ profile ≥ 20‰ ∨ ("Bu," ∧ profile ≥ 10‰); profile only on ≥ 75 words.
  URL signature: host `tr.*`, a `tr` locale path segment / `?hl=tr`, or a foreign 2-letter ccTLD
  (generic-use ones and Wikimedia hosts exempt). Profile = (calque words − native connectives)
  per mille; both lists (29 + 20 words) were derived from the labelled rows by log-odds and
  filtered to grammatical items only — no topic words.
- **`commercial_page`** = ≥ 2 distinct families among price (decimal amount / currency symbol /
  `Fiyat:`), buy/call CTA, product-card fields, corporate "we" voice, sponsor label, shop
  breadcrumb, listing template (title trigram ≥ 5×) — or one strong family (price ≥ 2, CTA ≥ 2,
  spec ≥ 2, sponsor ≥ 1). Format first: it counts families, not genre words.

### Labelled rows (recall / false drops)

| | eye MT (107)¹ | jury MT (25) | union (119) | control MT (26)² | HQ `kalsin` (122) | v5 `kalsin` (103) |
|---|---:|---:|---:|---:|---:|---:|
| URL signature alone | 83.2 % | 44.0 % | 74.8 % | 80.8 % | 9.8 % | — |
| profile ≥ 20‰ | 17.8 % | 24.0 % | 17.6 % | 11.5 % | 0 | 1.0 % |
| "Bu," ∧ profile ≥ 10‰ | 13.1 % | 20.0 % | 14.3 % | 11.5 % | 0 | 0 |
| Cyrillic residue | 2.8 % | 4.0 % | 2.5 % | 3.8 % | 0 | 0 |
| **machine_translation** | **83.2 %** | **64.0 %** | **78.2 %** | **73.1 %** | **4.9 %** (6) | **1.0 %** (1) |

¹ eyeball flags exist only for the 269 URL-suspect candidates → URL recall there is an upper
bound. ² the profile lexicons were derived on the main sample; the control sample is held out.

**The provisional target (recall ≥ 80 % at ≤ 5 % false drops) is not fully met:** the false-drop
cap holds, recall is ≥ 80 % only on the (biased) eyeball set; on the unbiased sets it is 64 %
(jury) / 73 % (control). Relaxing the cap to 7.5 % gives control 81 %; at 10 %, 85 % (frontier in
the report). All six HQ false drops are localised corporate/agency pages (Microsoft/Deezer
support, motorsport.com, Sputnik, Tasnim) — professional translations. Rejected by measurement:
the literal-proper-noun dictionary (derived on the main sample it is 7 words and generalises to
1/26 control MT vs 5/174 non-MT), sentence-length regularity (AUC 0.50–0.59), English number
formats and "Bay/Sayın + name" (too rare).

**commercial_page:** HQ commercial junk 15.4 % (4/26), v5 commercial junk 34.3 % (12/35);
false drops 0/122 HQ `kalsin`, 0/103 v5 `kalsin`, 0/29 encyclopedia. The HQ commercial junk is
mostly prose promotion copy (book blurbs, company intros) with no sales format — out of reach of
a format rule.

**Whole v4 against the judges (labelled 200 + 200):** HQ junk 39.0 % → **31.4 %** (31 drops: 25
junk, 6 `kalsin`; in-sample for MT thresholds), v5 48.5 % → **44.3 %** (17 drops: 16 junk, 1
`kalsin`). v3 dropped 1 and 0.

### Full import, one pass (8,578,808 documents, 25.2 GB, every shard SHA-verified)

| | documents | bytes |
|---|---:|---:|
| machine_translation | 1,474,546 = **17.2 %** | **30.6 %** |
| commercial_page (pattern at pass time / final code³) | 2.54 % / ≈ 2.4 % | 8.1 % / ≈ 7.6 % |
| either (new v4 drops, final code³) | ≈ **18.4 %** | ≈ **33.7 %** (≈ 8.5 GB) |
| v4 total incl. v3 (210k sample) | 18.8 % | 34.9 % |

By dump year, machine translation: ≤ 2019 **9.5 %** of documents (17 % of bytes), 2020–21
**21.6 %** (40 %), ≥ 2022 **22.9 %** (35 %); commercial 1.7 / 2.7 / 3.4 %. This matches the
2026-10-03 eyeball estimate (MT ≈ 13.8 % of documents, ≈ 33 % of bytes, four times denser in new
dumps). ³ After the pass the `sponsor` pattern was fixed (it matched "sponsorluğunu" inside
news); the machine-translation rule did not change. The final commercial rate is measured on the
same 210,000-document sample with both patterns (2.52 % → 2.34 %) and scaled.

Eyeball check of the full import [eyeball, not a jury]: of 20 URL-path MT drops 15 are clear MT,
3 other junk (localised templates), 1 good, 1 unsure; of 20 content-only drops 10 MT, 6 SEO/LLM
text, 4 good Turkish (a Bible translation, a sports column, folk text, a tabloid item) — the
calque words are frequent in generated Turkish too.

### Regression, tests, control runs

- **v3 verdicts unchanged:** 0 differences on the 1,400 labelled texts and on 210,000 sampled
  documents of the full import (final code); `test_v4_keeps_every_v3_verdict_byte_for_byte`.
- Tests: `worker/tests/test_quality_v4.py` (73); whole non-database worker suite green.
- **Control runs: 30 mutations → 30 red** (11 machine-translation guards/thresholds, 10
  commercial, 5 v4 wiring incl. "v3 reasons dropped/reordered", 4 clean_candidate decision-row
  and URL wiring); untouched and restored trees green. Run on a scratch copy of the package —
  the source tree was not edited (`kontrol_kosulari.py`, `kontrol-kosulari.json`).

### Judge rerun and owner anchor (prepared, not run)

- `var/olcum-2026-10-13/task-046/juri-kor-200/` — 200 documents drawn uniformly (seed
  20261013) from the full import, blind (no source, URL, dump or verdict; whitespace normalised;
  shuffled), key in `ANAHTAR-acma.json`, instructions in `YONERGE.md`. One reading gives
  *before* (all 200), *after v3* and *after v4* (the kept subsets, 164 under v4) and the rules'
  hit rate (36 dropped: 32 MT, 4 commercial, 5 v3). Scoring: `puanla.py <verdicts>` (Wilson
  95 %; `emin degilim` counted as junk, plus a junk-only reading).
- `var/olcum-2026-10-13/task-046/kurucu-20.csv` — 20 hard rows (`id, metin_ilk_300,
  kural_hukmu, kurucu`; UTF-8, no BOM, LF) in six groups: MT drops a `kalsin` row, MT misses a
  jury MT row, content-only MT drops, commercial drops, commercial misses, encyclopedia/official
  text with one commercial family. Key: `kurucu-20-anahtar.json`.

### Still open

- Owner: confirm or change the targets (the frontier is in the report); read the 20 anchor rows.
- Judge rerun on `juri-kor-200` (TASK-047's jury path or the manual Sonnet strict reading).
- `clean_candidate` does not read an import manifest (it reads lines); a v4 derivation of the
  FineWeb2-HQ source needs the manifest/Parquet path (the URL is in the record) — separate work.
- Jury-only machine translation on Turkish domains (translated foreign news) stays below 65 %
  recall; content signals beyond the function-word profile were measured and did not separate.
