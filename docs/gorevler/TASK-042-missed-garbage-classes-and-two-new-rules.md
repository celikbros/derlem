# TASK-042 — Garbage classes no rule catches, and two new rule candidates

| Field | Value |
|---|---|
| Status | **DRAFT** — 2026-09-22, from the shelf's two audits |
| Kind | feature (detection rules) |
| Moratorium | allowed once v5 is delivered — a filter defect, not a product surface |
| Estimate | 1.5 day |
| Depends on | TASK-041 |
| Owner | (unassigned) |

## Why

Both audits found garbage that **no rule names**. It is caught today only by accident (a
medical content farm falling into `sexual_pharma_spam_cluster`) or not at all. The
`encoding_corruption` stratum is the clearest case: its garbage is not bad because of encoding,
it is SEO spam — the encoding rule was removing it for the wrong reason, and tightening that
rule will not keep removing it. Two independent agents reached this diagnosis separately; the
owner's verdicts agree.

## Classes (shelf letters 2026-09-20 §4 and 2026-09-21 §6)

1. **Machine-translated content farms** (Russian or English into Turkish): ampicillin dosage,
   prostate, thrush, varicocele. Fluent-looking, wrong at the meaning level. Signature: brand
   names translated literally — "Çarpıcı" (Strikingly), "Sabit İletişim" (Constant Contact),
   "Kare Alan" (Squarespace), "Hayalet" (Ghost).
2. **Template dictionary pages** — "X nedir ne demek" pages with a slot-filled template.
3. **Auto-multiplied templates**: neighbourhood × service (timber, sofa cleaning, pest
   control), product × city, daily horoscope. Nearly all of `extreme_repetition`'s garbage.
4. **Sound body, injected page**: a real article with escort keywords in the title or Russian
   link spam in the tail. The shelf's rule of thumb — *if the text has to be trimmed to be
   saved, it is garbage* — and the owner applied the same line in the 14-row anchor (a
   translated science article with injected escort keywords: garbage).
5. **Wikipedia non-article namespaces**: user talk pages, revision diffs, discussion archives.
   The fix is a namespace filter, not a threshold (see TASK-041).

## Two new rule candidates (measured, small)

- **Apostrophe corruption.** Turkish separates a proper noun from its suffix with an
  apostrophe; on some pages this is systematically a backtick instead. It teaches a wrong
  Turkish orthographic rule. The shelf measured 3 of 293 documents (at least 5 corrupted
  occurrences and more corrupted than correct). Rare but cheap to detect. **Supported by the
  owner's anchor:** the Mehmet Ağar biography was marked garbage and this is its only defect.
- **Cross-domain duplicate translation farms.** Six pairs of near-identical text entering from
  different domains; dedup missed them because of small differences. This inflates the strict
  population in `sexual_pharma`.

## Scope

- One rule per class where the signal is structural, never topical (the whole TASK-040 lesson);
  each ships with its two counts.
- Namespace filter for Wikipedia-sourced documents.
- Carry `body()` into the near-duplicate path: the shelf's 7 false duplicate matches all share
  the "short body, template tail" signature, and all seven would have been prevented by
  comparing bodies rather than whole pages.

## Out of scope

- Topic-based filters.
- Anything before v5 is delivered.

## Acceptance criteria

- [ ] Each new rule ships with recovered and admitted counts on the labelled rows.
- [ ] The near-duplicate path measured with and without `body()`; false-match count reported.
- [ ] No regression: the lines v5 keeps are not newly dropped (300k-line regression as in TASK-040).

## Report

(not started)
