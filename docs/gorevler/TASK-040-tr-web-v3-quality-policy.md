# TASK-040 — `tr-web-v3`: stop the quality filter from dropping good Turkish text

| Field | Value |
|---|---|
| Status | **IN PROGRESS** — scope approved by the owner 2026-09-20 ("onayladım"); the three families are merged into `tr-web-v3` (code + tests in place); the newly-kept sheet was judged and the owner ruled "strict corpus" 2026-09-21, thresholds tightened accordingly; the strict set's own false-keep rate is owed |
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

- [x] `tr-web-v3` exists; `tr-web-v1`/`v2` verdicts unchanged (existing tests green).
- [x] Deterministic across interpreters: identical verdicts under the root `.venv` (3.14,
      zlib-ng) and `worker/.venv` (3.13, zlib); manifest carries both versions.
- [x] Re-run of the 706 audited rows reported per reason: recovered `good`, newly admitted
      `correct_drop`.
- [ ] Newly-kept sheet judged by the shelf and spot-checked by the owner; false-keep rate
      reported with its interval before v5 is derived.
- [x] Control runs: each new rule's guard removed → a test goes red (12 guards, 12 red;
      the strict pass adds 10 more guards, 10 more red — 2026-09-21).

## Owner actions

- Approve the scope (this card) before any code is written.
- Judge ~50 rows of the newly-kept sheet after the rule diff (the second calibration point).
- Decide on v5 derivation once the two counts are on the table.

## Owner decisions (2026-09-21)

**Policy: A — strict corpus.** "Şüpheliyi at. Daha az veri, daha temiz. Hacim açığı büyür."
The relaxation stays only where the evidence is strong; everything else returns to v2
strictness. Basis: the owner judged 50 newly-kept rows and called 47–49 of them junk (two,
a chemistry and a technical encyclopedia article, were corrected to "keep" after review);
independent model juries called 38–44 % of the same rows junk. The relaxation as shipped is
too permissive.

**Judge model: Sonnet.** Blind benchmark on the owner's 100 labelled rows (agreement /
Cohen kappa against the owner, sheet A = "was this drop wrong?"):

| Model | Sheet A agreement | kappa | Sheet B agreement |
|---|---|---|---|
| Haiku 4.5 | 26 % | 0.02 | 8 % |
| Sonnet | 68 % | 0.41 | 38 % |
| Opus | 72 % | 0.47 | 44 % |

Haiku is unusable here. Sonnet and Opus are within noise of each other and of the shelf
(0.36); Sonnet is cheaper, so bulk judging goes to Sonnet — as a **pre-screen**, never as
the deciding vote. Sheet B could not be scored: the owner's labels have almost no variance
(49/50 one class), which makes kappa meaningless, and two of those labels were wrong.

**What the benchmark really showed:** no judge — human or model — reproduces another
judge's bar. The owner's own bar moved between sheet A (9/50 "good") and sheet B (1/50
"keep"). This is a policy question wearing an empirical costume; hence the explicit
policy decision above instead of more measurement.

## Report

**Status: IN PROGRESS** — the merge is done, the newly-kept sheet was judged, and the owner's
"strict corpus" ruling of 2026-09-21 is in code with tests (see **Strict pass** below; the
numbers in the three sections that follow are the *pre-ruling* measurement and are kept as the
record of what the loose thresholds did). Full measurements:
[var/olcum-2026-09-20/task-040-birlestirme/RAPOR.md](../../var/olcum-2026-09-20/task-040-birlestirme/RAPOR.md)
(merge) and
[var/olcum-2026-09-21/task-040-siki/RAPOR.md](../../var/olcum-2026-09-21/task-040-siki/RAPOR.md)
(strict pass).

### What shipped

`quality_body.py` (new — `body()`, `body_span()`, `blocks()`, the strip/prose measures, with
the S1–S6 contract written on `body()` and tested), `quality_v3.py` (new — the three families'
thresholds, the structural signals, the pure-Python LZ77 estimate), `QUALITY_POLICY_TR_WEB_V3`
in `quality_filters.py` as a separate branch (v1/v2 code paths untouched, their tests green),
`--quality-policy tr-web-v3` and `interpreter_version` + `zlib_runtime_version` in the
clean-candidate manifest. Tests: 159 green across the four files (382 in the whole non-database
worker suite).

The policy asks v2's own triggers twice — once on the full text, once on the body — and each
family adds its second measure. For the ratio and cluster families that is a measurable
guarantee: v3 cannot drop a document v2 kept. The repetition family is deliberately not a
subset (`lz77 ≤ 260` vs `zlib ≤ 180`) — that is exactly what TASK-039 fixes.

### Both directions (556 quality-dropped rows of the audit sheet, real `body()`)

| Judge | recovered `good` | of good chars | leaked `correct_drop`/`unsure` | of dropped chars |
|---|---|---|---|---|
| Shelf | **129 / 187 (69.0 %)** | 52.6 % | **80 / 369 (21.7 %)** | 10.6 % |
| Owner | **7 / 7 (100 %)** | 100 % | **12 / 34 (35.3 %)** | 24.6 % |

By family (shelf): ratio 56/67 recovered, 21/83 leaked · clusters 73/96, 59/154 · repetition
0/24, 0/76. Strongest strata: `optics` 28/31, `encoding` 25/27, `dating` 17/17, `wiki` 14/18
with 1/32 leaked. `adult_service_spam_cluster` 0/61 freed (reason still fires 61/61),
`mixed_script_artifact` 0/6 freed. The owner's leak is concentrated in one stratum —
`encoding_corruption`, 7 of 8 — and the diagnosis from the ratio measurement holds: that
stratum's junk should have been dropped as commercial/SEO spam, not as corruption; no rule
catches it by name. v3 does not create that gap, it makes it visible.

**Multi-reason drops: 10 of 89 are now free (4 shelf-`good`, 6 junk).** Each family measured
0/89 on its own; the merge produces this because two families relax two different reasons. It
is a real cost and the newly-kept sheet must carry it as its own stratum.

### Three merge questions the card asked to re-measure with the real `body()`

- **Repetition family now measures on the full text, not the body.** On the body it recovers 2
  good rows and frees 9 junk ones (shelf), and on the owner's scale 0 recoveries against 1 leak.
  Head/tail trimming removes the document's unique part and can push the word count under the
  500/1 500 gates. Contract clause S6 was rejected by measurement for this family only.
- **The cluster family gained a full-text trigger.** Trimming can *raise* density; without the
  trigger one shelf-`good` row gained a new `commercial_keyword_stuffing` reason. Adding it
  costs nothing on the sheet (129/80 either way) and makes new cluster drops impossible.
- **The cluster family's 20 000-character body floor was dropped.** It compensated for the
  placeholder body; the real `body()` already refuses to trim short pages (S4).

### Regression, determinism, speed

- **Regression: 0.** The first 300 000 lines / 530 691 214 characters of the v4 candidate: v2
  drops 0 (right baseline), v3 drops 0 — no new drops.
- **Determinism:** 20 706 documents, identical decision-digest sha256 under the root `.venv`
  (3.14, zlib-ng) and `worker/.venv` (3.13, zlib). On TASK-039's seven boundary lines v2 flips
  7/7 between interpreters while v3 drops all seven on both. A test patches `zlib.compress` at
  both extremes: v2's verdict moves, v3's does not.
- **Speed:** v3 is **1.20×** slower than v2 (1 460 vs 1 758 documents/s); 13.57 GB works out at
  **1.44 h** against v2's 1.20 h. Pure-Python LZ77 is not the problem — it only runs when the
  unique-5-gram ratio is already under 600 ‰.

### Control runs

Twelve guards were removed one at a time and restored; all twelve turn a test red (table in the
report). Three came back untested on the first pass (the U+FFFD count bound, the wiki ratio, the
navigation ratio) because the fixtures were decided by a *different* threshold; documents that
actually bind each bound were built and the tests added.

### Suspended, in code, switched off, tested

- `FRAME_EXEMPTION_ENABLED = False` — the owner's ruling. Open, it recovers 17/24 on the shelf
  for 3 leaks but gives the owner 0 recoveries against 2 leaks and 50.8 % of the dropped
  characters. The test asserts the official-minutes document it was written for **is dropped**
  while off.
- `MOJIBAKE_BRANCH_ENABLED = False` — **new finding**. It was the only branch with no v2
  counterpart, so it could drop documents v2 kept, and the regression run caught it doing so:
  the pattern's `Â[ -¿]` arm matches Turkish circumflex Â ("el-ÂMİLÎ", "TABAKÂT") and dropped a
  sound theology article. It needs measuring on a corpus that actually contains mojibake.

### Strict pass (2026-09-21)

The owner ruled after seeing the newly-kept sheet: **"A) Strict corpus — drop the
suspicious. Less data, cleaner. The volume gap grows."** He judged 50 of the
newly-kept rows and called 48 garbage (correcting two — a Chloroform chemistry
entry and a XAML technical entry — to "keep" afterwards); independent model
juries called 38–44 % of the same 50 garbage. `tr-web-v3`'s exemptions were
therefore narrowed, with two numbers fixed in advance: **keep** the 7
quality-dropped documents the owner called `good` (7/7 today), and **re-drop at
least 85 %** of the 50 newly-kept rows he saw.

Both hold: **7/7 kept, 43/50 (86.0 %) re-dropped** — 43/48 (89.6 %) with
Chloroform and XAML counted as keeps, and both are kept. Leakage on the owner's
audit sheet fell from 12/34 to 4/34. What changed: the navigation and hashtag
exemptions are off, `encoding_corruption` is measured on the full text with a
single "one replacement character, in the tail, outside a word" exemption, the
wiki exemption needs prose volume + ratio + function-word ratio + no commercial
signal, the cluster family adds a 2.10× lexicon-density ceiling (R1 untouched),
and the "does v2 also fire on the body" gate is gone — body trimming is no
longer an exemption by itself. Thresholds were picked from a table, not by
intuition; the repetition family, LZ77 and the two suspended branches are
untouched. Full measurement, control runs and population effect:
[var/olcum-2026-09-21/task-040-siki/RAPOR.md](../../var/olcum-2026-09-21/task-040-siki/RAPOR.md).

### Still owed

The newly-kept sheet was produced and judged (criterion 4 — the owner's 50 rows are the
basis of the strict pass above), but it sampled the **loose** v3's newly-kept set. The strict
set is smaller and differently distributed: 4 888 records / 46.8 M characters against
25 505 / 286.7 M. Its false-keep rate at population scale is still unmeasured; what exists is
a lower bound from the owner's sheet (5 escapes in 48). Either a fresh stratified sheet comes
off the strict set, or the owner accepts the current reading — v5 should not be derived
before that is decided.
