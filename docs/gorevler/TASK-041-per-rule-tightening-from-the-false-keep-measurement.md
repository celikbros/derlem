# TASK-041 — Per-rule tightening of `tr-web-v3` from the measured false-keep rate

| Field | Value |
|---|---|
| Status | **READY (measured, not implemented)** — 2026-09-22; deliberately deferred until v5 is frozen |
| Kind | fix (derivation rules) |
| Moratorium | allowed — same defect class as TASK-040 |
| Estimate | 1 day |
| Depends on | TASK-040 (measurement), delivery of v5 |
| Owner | (unassigned) |

## Why

TASK-040's reverse audit measured what the relaxed rules newly admit. The strict set's
false-keep rate is **33.2 %** (shelf's 293-row sheet, stratum character-weighted, Wilson 95 %
[26.5–41.5] by our scorer, [26.1–40.3] by theirs; `unsure` counted as garbage). The owner's
14-row anchor agreed with the shelf on 13 of 14 rows, the single disagreement being the shelf
keeping a sponsored phone review the owner called garbage — so 33.2 % is, if anything, low.

Under the agreed threshold (a rule whose newly-kept characters are > 20 % garbage is tightened;
at least 30 judged rows required for samples, not for full censuses), **7 of 8 rules fail**.

Not urgent: the whole strict newly-kept population is 0.41 % of v5 and the garbage it adds is
0.14 % of v5 — which is why this card waits for the freeze instead of restarting the candidate
cycle.

## Measured rates (2026-09-21, shelf sheet, our independent scoring)

| Rule | newly kept | judged | garbage (docs) | garbage (chars) | weight | verdict |
|---|---:|---:|---:|---:|---:|---|
| `wiki_markup_residue` | 1,923 | 50 | 28.0 % | 29.1 % | 50.9 % | tighten |
| `commercial_keyword_stuffing` | 401 | 50 | 54.0 % | 55.1 % | 18.2 % | tighten |
| `dating_spam_cluster` | 624 | 50 | 24.0 % | 24.4 % | 19.1 % | tighten |
| `encoding_corruption` | 1,847 | 50 | 24.0 % | 16.4 % | 8.2 % | tighten — interval straddles 20 %, needs more rows |
| `sexual_pharma_spam_cluster` | 48 | 48 (census) | 79.2 % | 72.1 % | 2.5 % | tighten |
| `optics_spam_cluster` | 18 | 18 (census) | 27.8 % | 25.6 % | 0.4 % | tighten |
| `multi_reason` | 11 | 11 (census) | 63.6 % | 53.8 % | 0.4 % | tighten |
| `extreme_repetition` | 16 | 16 (census) | 93.8 % | 93.3 % | 0.2 % | tighten |

Value is concentrated: `wiki_markup_residue` and `commercial_keyword_stuffing` carry **69 %**
of the weight. The four census strata together are 3.5 % — tightening them is right, but the
gain is symbolic (tightening `extreme_repetition`, 93.8 % garbage, moves the overall rate by
0.1 point).

## Scope

- Re-tighten the seven rules; each change ships with the two counts on the owner's and the
  shelf's labelled rows (recovered good / newly admitted garbage), as in TASK-040.
- **Format first, genre second** (corrected 2026-09-24). An earlier draft of this card read
  the owner's 14-row anchor as "encyclopedia stays, sponsored review goes". The shelf found the
  counter-example in the same 14 rows: the Mehmet Ağar biography is a genuine encyclopedic
  article and the owner marked it **garbage** — every apostrophe in it is a backtick, so it
  teaches a wrong Turkish orthographic rule. Commercial product and review pages were 3/3
  garbage; encyclopedia articles were 1 keep / 1 garbage. Genre is a signal, never a verdict:
  the format gates (prose share, systematic character corruption, sponsor/CTA pattern) run
  first. Sponsor and affiliate markers ("Sponsorlu Bağlantılar", price tables, spec lists,
  buy-now calls to action) remain a usable structural signal for `optics` and `commercial`.
- **Which shelf verdicts to trust.** Use the shelf's sub-agent verdicts (13/14 on the owner's
  anchor). The shelf's own main session scored 3/9 on the same anchor and is the most lenient
  of the three judges; its 64-row blind sample must not drive any rule change (the shelf's own
  instruction, 2026-09-22).
- `wiki_markup_residue` needs a **Wikipedia namespace filter** first (shelf 2026-09-21 §6.1):
  user talk pages, revision-diff pages and discussion archives pass the prose counter because
  they are many short sentences; what they lack is a single body. Cheaper than any threshold
  change and it removes most of that stratum's garbage.
- Draw **+150 rows** for `wiki_markup_residue` (it carries half the weight on a 2.6 % sample;
  the overall interval is plus/minus 7.1 points because of it) and **+150** for
  `encoding_corruption` (its interval straddles the threshold).

## Out of scope

- Re-deriving v5 (frozen history once the release exists).
- The missed-garbage classes and the two new rule candidates — TASK-042.
- Any change before v5 is delivered.

## Acceptance criteria

- [ ] Each of the seven rules either tightened with its two counts, or explicitly left with a
      written reason.
- [ ] New sheets for `wiki_markup_residue` and `encoding_corruption` judged; overall interval
      reported with the widened samples.
- [ ] `adult_service_spam_cluster`, multi-reason drops and the v1/v2 policies unchanged.
- [ ] Control runs: each new guard removed causes a test to go red.

## Owner actions

- Judge a small anchor slice of the new sheets. The 14-row format worked: 13/14 agreement on
  deliberately hard rows, about 20 minutes of reading.

## Report

(measurement only — implementation deferred to after the v5 delivery)
