# TASK-022 — Document-boundary policy note (fragments vs whole documents) for new intake and any re-derivation

| Field | Value |
|---|---|
| Status | **IN PROGRESS** — 2026-09-19: policy note written ([belge_sinirlari_politikasi.md](../belge_sinirlari_politikasi.md)); owner decision line pending; shelf question drafted for the next letter. Was: DRAFT — from the 2026-09-19 plan ([plan_2026_09.md](../plan_2026_09.md), Faz 2); no new feature — may start when its dependencies are done |
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

- [x] Policy doc exists with a dated owner decision line and the shelf's answer (or 'not answered yet'). — 2026-09-19: decision line present as "(karar bekliyor …)", shelf answer "henüz sorulmadı".
- [ ] TASK-032 cites the policy in its scope.

## Owner actions

- Decide (a)/(b)/(c) and date it; recommended: (a) yes, (c) yes, (b) later.

## Report

### 2026-09-19 — policy note written, decision pending

Deliverable: [belge_sinirlari_politikasi.md](../belge_sinirlari_politikasi.md). Read-only
inspection of the raw archive and the archived collector code changed the premise of this
card:

- **The boundaries were lost at collection, not at the Faz-2 merge.** Every raw JSONL
  record has only `text` + `source`; no title/body/paragraph/article-id field in any of
  the six files. Paragraph breaks are absent from the text too (`wiki_oscar` 10 of the
  first 100,000 records contain `\n`, `celik_gold` 38 of 100,000, `ttk`/`academic`/`tdk`/`trt`
  0 of 2,000): the collector's `clean_and_normalize` did `re.sub(r'\s+', ' ', text)`. The
  Faz-2 merge kept the record boundary (TASK-016 containment 100 %, one raw record = one
  parent line); it lost only the source label.
- Per source: `wiki_oscar` = one article/page per record (boundary kept, paragraphs gone);
  `ttk` = one `<p>` paragraph per record (article boundary gone, no article id);
  `academic` = one OAI abstract, "Title . Abstract" in one string (6.0 % title-only in the
  first 20,000); `tdk` = one definition or example sentence (mean 85 chars, 77.2 % < 120);
  `tr_corpus.txt` = paragraphs of the same Wikipedia articles (366 of the first 500 lines are
  substrings of `wiki_oscar`'s first 200 records) — the parent carried those articles twice,
  whole and paragraph-split; S2 removes `tr_corpus`.
- So option (b) (re-derive Faz-2 from raw JSONL with boundaries) gains **zero** boundaries;
  it would be a v5 with one review reset (~2 Claude days, ~5 machine hours) for a source
  label S2 already reconstructs by hash. Real boundaries only come from re-downloading the
  upstream datasets — that is TASK-032, not (b).
- Today's intake already accepts `.jsonl` with a `text` field and keeps `\n` inside it
  (`sampling.py` 304–308); JSONL export keeps it, txt export joins to a single space
  (`releases.py` 838). Option (a) therefore costs 0 extra days and 0 resets; the rule is in
  the note's §4 and TASK-032's scope now cites it. TASK-024's pilot should write JSONL, not
  txt, or the breaks are lost at intake.
- Estimate for v4 after S2 (not measured): lines < 120 chars ≈ 3 % of lines, < 0.2 % of bytes
  (parent: 11.84 % / 0.44 %; ≈ 586,000 of the ≈ 713,000 short lines were `tr_corpus`).
- Cost lines: (a) 0 days / 0 resets; (b) ≈ 2 days + ≈ 5 machine hours / 1 reset, becomes v5,
  no boundary gain; (c) 0 days / 0 resets.
- Owner decision line left as "(karar bekliyor — öneri: (a) evet, (c) evet, (b) sonra)";
  shelf question drafted as a paste-ready paragraph (note §6), not yet sent.

Not done: the owner's dated decision; the shelf's answer; `docs/gorevler/README.md` not
edited. Nothing under `var/` was modified.
