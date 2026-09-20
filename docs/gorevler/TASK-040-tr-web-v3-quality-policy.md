# TASK-040 — `tr-web-v3`: stop the quality filter from dropping good Turkish text

| Field | Value |
|---|---|
| Status | **IN PROGRESS** — scope approved by the owner 2026-09-20 ("onayladım"); phase 1 (per-family measurement) running |
| Kind | fix (derivation rules) |
| Moratorium | allowed — a measured defect in the pipeline that produces the v2 delivery; no product surface |
| Estimate | 1.5–2 day(s) work + ≈ 4.5 h machine |
| Depends on | TASK-020 (the measurement), TASK-039 (zlib determinism, folded in) |
| Owner | (unassigned) |

## Why

TASK-020's audit measured the false-drop rate of `tr-web-v2` on its own rejection report:

| Judge | Population estimate | 95 % interval |
|---|---|---|
| Shelf (706 rows, all strata) | 41.8 % | 35.9 – 47.9 |
| Owner (50 rows, same sheet) | 23.1 % | 5.4 – 61.3 (n_eff 6.2) |

The two disagree in one direction only — the shelf calls "good" what the owner calls
`correct_drop`/`unsure` in 11 of 18 rows, the reverse in 2 (agreement 66 %, kappa 0.36) — so
41.8 % is an upper bound and ~20–30 % is the honest reading. Either way the shelf's 10 %
threshold is exceeded 2–3×. In absolute terms: of ~880 M dropped characters, ~280–370 M are
good text (2.5–3.3 % of the v4 candidate), and the loss is concentrated in exactly the
document types the family's decision model needs — Resmî Gazete and ministry decisions,
municipal council minutes, MYK qualification documents, court/enforcement notices, and long
encyclopedia and science articles.

v4 is **not** frozen and the owner has **not** started the 200-sample review, so resetting now
costs no human time — only machine time. That is why the fix happens before the freeze.

## The four defects (shelf letter 2026-09-20, §3)

1. **Presence instead of proportion.** `encoding_corruption` drops a document for a single
   U+FFFD, usually a truncated byte at the very end (54 % wrong). `wiki_markup_residue` drops
   a sound article for a few `{{…}}` leftovers (37 % wrong). `navigation_boilerplate` drops for
   a long menu regardless of how much prose follows (82.6 % wrong, and the heaviest stratum —
   33.5 % of dropped characters).
2. **The tail takes the page.** Spam in a comment block at the end of a 67 k-character
   political interview drops the interview.
3. **Topic, not style.** `optics_spam_cluster` (62 % wrong) fires on "lens/kamera/zoom":
   phone-review journalism and Wikipedia articles on OPPO/Nokia. Same class of error in
   `dating_spam_cluster`, `commercial_keyword_stuffing`, partly `sexual_pharma_spam_cluster`.
   `adult_service_spam_cluster` is flawless (50/50) — the cluster idea is sound, four
   thresholds are not.
4. **Formulaic ≠ garbage.** `extreme_repetition` and `repeated_segments` treat administrative
   Turkish (council decisions, official gazette entries, technical sheets) as template spam,
   although each block carries unique content (parcel, date, decision number). A second
   pattern here is PDF/slide conversion that doubles every sentence — recoverable by line-level
   dedup, not a reason to drop.

## Scope

New policy version **`tr-web-v3`**; `tr-web-v1`/`v2` stay byte-for-byte as they are (v3/v4 are
frozen history and their manifests must stay reproducible).

1. **Body extraction, not text surgery.** A new pure function computes the *body* of a document
   (navigation header, menu runs, comment/footer block trimmed) and every rule is evaluated on
   the body, while the stored text stays the full original. Nothing is rewritten — no text is
   cleaned in place ([data_governance.md](../data_governance.md)).
2. **Proportion + position** for `encoding_corruption` (density and spread of U+FFFD and
   mojibake sequences; a single trailing replacement character is not a drop),
   `wiki_markup_residue` and `navigation_boilerplate` (how much prose survives the strip,
   absolute and as a share).
3. **Cluster thresholds:** each of `optics`, `dating`, `commercial_keyword_stuffing`,
   `sexual_pharma` requires more than one independent signal (keyword density on the body plus
   a structural signal: no paragraphs, no verbs, phone/price/CTA pattern, link density).
   `adult_service_spam_cluster` and multi-reason drops are **not touched** — measured correct.
4. **Repetition family:** repetition is measured on the deduplicated body (line-level dedup
   first), and a document whose repeated blocks each carry unique content (numbers, dates,
   identifiers) is not a repetition drop. The zlib-implementation dependence (TASK-039) is
   removed in the same pass; the manifest records the interpreter and zlib runtime version.
5. **Bar per number of signals:** a single-rule drop needs a stronger score than a document two
   rules agree on (the shelf measured multi-reason drops as almost always correct: 52/65).
6. **Verification, both directions.** (a) The 706 audited rows are re-run through `tr-web-v3`:
   how many of the `good` rows are now kept, how many `correct_drop` rows are now kept by
   mistake. (b) A fresh stratified sheet of **newly kept** lines (lines v2 dropped and v3 keeps)
   goes to the shelf and to the owner — relaxing rules must not admit garbage, and the owner's
   calibration is stricter than the shelf's. No rule ships on a reasoning; each one ships with
   the two counts.

## Out of scope

- The two missed garbage classes (machine-translated medical content farms, template
  dictionary pages) — real, but new detection work and not blocking v2; separate card.
- Re-deriving anything before the rule diff is measured and shown to the owner.
- Changing v3/v4 artifacts, the audit sheet, or the frozen policies.

## Then: v5

v5 must be derived **from the parent corpus** (`9826d58e…`), not from v3 — wrongly dropped
lines only exist upstream. Same pass as v3 plus the S2 scope list and the fastText drop list:
≈ 3.4 h + ≈ 25 min, then registration and gates (≈ 2 h). The 200-sample review then happens on
v5. Expected size: v4's 11.26 GB plus ~0.2–0.3 GB (estimate, from the measured false-drop
characters after the S2 filter).

## Acceptance criteria

- [ ] `tr-web-v3` exists; `tr-web-v1`/`v2` verdicts unchanged (existing tests green).
- [ ] Deterministic across interpreters: identical verdicts under the root `.venv` (3.14,
      zlib-ng) and `worker/.venv` (3.13, zlib); manifest carries both versions.
- [ ] Re-run of the 706 audited rows reported per reason: recovered `good`, newly admitted
      `correct_drop`.
- [ ] Newly-kept sheet judged by the shelf and spot-checked by the owner; false-keep rate
      reported with its interval before v5 is derived.
- [ ] Control runs: each new rule's guard removed → a test goes red.

## Owner actions

- Approve the scope (this card) before any code is written.
- Judge ~50 rows of the newly-kept sheet after the rule diff (the second calibration point).
- Decide on v5 derivation once the two counts are on the table.

## Report

(not started)
