# TASK-020 — Rejection-report false-drop audit pack: stratified sheet (50 per reason) and byte-weighted scorer, no UI

| Field | Value |
|---|---|
| Status | **IN PROGRESS** — 2026-09-19: script, tests, sheet (706 rows) and skeleton document done; verdicts pending (from the 2026-09-19 plan, [plan_2026_09.md](../plan_2026_09.md), Faz 1) |
| Kind | ops |
| Moratorium | allowed — a script and a document; no endpoint, no panel |
| Estimate | 1 day(s) |
| Depends on | — |
| Owner | (unassigned) |

## Goal

Give the shelf (or two office reviewers) a fixed-seed stratified sample of the 93,223-record rejection report and a scorer that turns their verdicts into a bytes-weighted false-drop rate per reason with a 95 % interval.

## Why

The shelf's one explicit ask (> 10 % of dropped bytes good text → talk). The 2026-09-17 slice showed whole encyclopedia articles dropped for a menu fragment; 55,677 lines were dropped by rules nobody audited. The result decides whether `tr-web-v2` is relaxed for v4/HF passes — never a v2 condition. The two-reviewer overlap also yields the first reviewer-agreement number (precondition for feature-list item 12, deferred).

## Scope

- `worker/src/derlem_worker/clean_candidate_audit.py`: from `…_v3.txt.rejections.jsonl` (SHA 2becaf9d…) draw min(50, stratum) per `reasons` stratum (12 quality reasons + near_duplicate + normalized_duplicate + language_not_turkish) with a fixed seed; CSV/markdown sheet with sha256, reasons, char_count, source_ordinal (to fetch the full line from the parent object), preview, `duplicate_of` partner preview, empty verdict column (`good` / `correct_drop` / `unsure`); seed + report SHA in the header.
- Scorer: refuses unknown verdicts; per-reason and overall false-drop share weighted by stratum bytes with binomial 95 % CI; writes `docs/atma_raporu_denetimi_v3.md`; optional agreement number when two reviewers mark the same 100 rows.
- Tests: stratum counts, seed determinism (identical sheet SHA), scorer reproduces a hand-computed rate on a synthetic sheet.

## Out of scope

- Audit UI (feature-list item 3).
- Any rule change to `tr-web-v2` (separate card after the number exists).
- Delaying v2 for the verdicts.
- Reviewer calibration beyond the free agreement number (feature-list item 12).

## Acceptance criteria

- [x] Sheet row count = Σ min(50, stratum size); same seed → identical sheet SHA. (706 = 14 × 50 + 6; tested on synthetic reports and measured on the real one; Python 3.13 and 3.14 draw the same rows.)
- [ ] After verdicts: per-reason table + overall bytes-weighted rate with interval, the three reasons with the highest false-drop share, comparison with 10 %. (Scorer built and tested; waiting for a filled sheet.)
- [ ] Owner decision on rule changes recorded; if > 10 %, a follow-up card exists before any re-derivation.

## Owner actions

- Hand the sheet to the shelf or assign two office reviewers (same 100 rows to both).
- Decide with the shelf whether any rule is relaxed for the next candidate.

## Sonuç (2026-09-22)

Sayfa model rafı tarafından dolduruldu (706/706), sonra **düzeltildi**: ilk turda kopya
tabakalarındaki 100 satırın eşi pakette yoktu (`duplicate_of` sha256 değil satır numarası
tutuyor), hüküm yalnız metin kalitesine göre verilmişti. Eşlerin tam metni gönderilince
`near_duplicate` içindeki 26 "iyi"nin **24'ü gerçekten kopya** çıktı.

| Ölçüm | Oran | %95 aralık |
|---|---|---|
| v1 (eşler görülemeden) | %41,8 | %35,9 – %47,9 |
| **v2 (eşler görüldü) — geçerli sayı** | **%32,9** | %27,5 – %38,9 |
| Kurucunun 50 satırıyla (ayrı ölçüm) | %23,1 | %5,4 – %61,3 (n_eff 6,2) |

Değerlendirici uyumu (kurucu ↔ raf, 50 satır): %66, Cohen kappa 0,35 — ayrışmalar tek yönlü,
raf daha cömert. Eşik (%10) her okumada fena hâlde aşıldı; karar **TASK-040** oldu ve
uygulandı. Ters yön ölçümü (kural gevşetmesi çöp aldı mı) aynı kartın altında yapıldı:
**%33,2**, oradan **TASK-041** ve **TASK-042** doğdu.

Kanıt dosyaları: `docs/mektuplar/2026-09-21-denetim-sayfasi-dolu-v2.csv` (rafın düzeltilmiş
hükümleri), `var/olcum-2026-09-19/atma-denetimi-v3/denetim-sayfasi-dolu-kurucu.csv`
(kurucunun 50 hükmü), ölçüm `docs/atma_raporu_denetimi_v3.md`.

## Report

### 2026-09-19 — sheet drawn, scorer ready, verdicts pending

**Built**

- `worker/src/derlem_worker/clean_candidate_audit.py` — `sheet` and `score` subcommands; reads the rejection report only, never writes under `var/derived`.
  - Stratum = the **first (primary) reason** in the record's `reasons` list (the list order is fixed by `quality_filters._REASON_ORDER`, so the assignment is deterministic); the `reasons` column keeps all reasons. 15 strata: the 12 quality reasons + `near_duplicate`, `normalized_duplicate`, `language_not_turkish`.
  - Selection: per stratum, records are ordered by `sha256(f"{seed}:{sha256}:{source_ordinal}")` and the first min(50, stratum) are taken — independent of Python's RNG (3.13 and 3.14 draw identical rows). Default seed `20260919`.
  - Sheet CSV (UTF-8 with BOM, `# ` header lines: version, seed, sheet size, report path, report SHA256, record count, generation date, stratum rule, per-stratum record and `char_count` totals) + Markdown twin. Columns: `sha256, reasons, char_count, source_ordinal, preview, duplicate_of, duplicate_of_preview, verdict`. `duplicate_of_preview` is filled only when the partner ordinal itself appears in the report (1 of 100 duplicate rows; the kept partner is by construction not a rejection).
  - Scorer: refuses unknown verdicts (allowed `good` / `correct_drop` / `unsure`, case- and space-insensitive; empty = not judged) and empty sheets; per-reason rate `good/(good+correct_drop)` with Wilson 95 % CI; overall rate weighted by stratum `char_count` totals from the full report (the report carries no byte size), interval = Wilson at the Kish effective n; contribution `w_s·p_s` and the top three; comparison with 10 %; secondary char-weighted-within-stratum rate; optional `--second` sheet → percent agreement + Cohen kappa. Writes `docs/atma_raporu_denetimi_v3.md` (or `--out`).
- `worker/tests/test_clean_candidate_audit.py` — 10 tests: stratum counts = Σ min(50, size), seed determinism (identical CSV SHA, different seed differs), CSV round trip with provenance header, hand-computed rate (0,8·2/3 + 0,2·1/4 = 58,33 %) and interval reproduced, Wilson reference values, unknown verdict refused (library and CLI, no document written), empty sheet refused, verdict normalisation + agreement/kappa, CLI end to end. Run: `.venv/Scripts/python.exe -m pytest worker/tests/test_clean_candidate_audit.py worker/tests/test_clean_candidate.py -q` → 25 passed (10 + 15). Note: `worker/.venv` (Python 3.13, uv) has no pytest; the root `.venv` (3.14) is the documented test runner.
- `docs/atma_raporu_denetimi_v3.md` — skeleton: how the sheet was drawn, how to fill verdicts, how to run the scorer, method; the scorer overwrites it with the tables.

**Measured (real sheet)**

- Report: `…_clean_candidate_v3.txt.rejections.jsonl`, SHA256 `2becaf9d…8dd778`, 93,223 records, 879,565,845 chars in total; 10,793 records carry more than one reason.
- Sheet: `var/olcum-2026-09-19/atma-denetimi-v3/gardash_faz2_tr_dedup_20260621_06ac330e_clean_candidate_v3_audit_sheet_seed20260919.csv` (+ `.md`), seed 20260919, **706 rows** = 14 × 50 + 6 (`mixed_script_artifact` has only 6 primary-reason records; the manifest's 7 includes one where it is a secondary reason). CSV SHA256 `fac0e207927ea48be6b7be0f9835d38584f3eecb0088432ef082466783144b1e` (a redraw changes only the `generated_at` header line).
- Stratum weights (share of report chars): `navigation_boilerplate` 33.5 %, `wiki_markup_residue` 18.2 %, `near_duplicate` 18.1 %, `encoding_corruption` 7.6 %, `repeated_segments` 5.6 %, `extreme_repetition` 5.1 %, `commercial_keyword_stuffing` 4.0 %, `dating_spam_cluster` 3.4 %, others < 2 % each (`normalized_duplicate` 0.003 %, `language_not_turkish` 0.08 %).

**Not done / next**

- Verdicts: hand the CSV to the shelf or two office reviewers (same rows to both); then run `score`, which fills the document and answers the 10 % question.
- Owner decision and, if > 10 %, a follow-up card.
