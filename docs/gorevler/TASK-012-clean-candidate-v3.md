# TASK-012 — Clean candidate v3: quality v2, held-out split, near-dedup, rejection report

| Field | Value |
|---|---|
| Status | **IN PROGRESS** — 2026-09-18. Code, tests and the 100k end-to-end run are done; production run in progress (owner: "time is yours"). |
| Kind | feature (data pipeline), inside the TASK-002-era exception: it produces the frozen v2 input |
| Moratorium | allowed by owner decision 2026-09-18 |
| Owner | (unassigned) |
| Trigger | Shelf letter 2026-09-17 (measurement reply) + owner decisions 2026-09-18 |

## Goal

Replace the unfiltered clean candidate (`clean-candidate-v1`, 2026-07-25) with a
candidate that (1) passed the quality filter, (2) has encoding corruption and wiki markup
removed, (3) has near-duplicates removed, (4) carries its own held-out split so the
decontamination gate produces a number instead of `not_applicable`, and (5) ships a
rejection report the shelf can audit for false positives.

## Decisions this implements (owner, 2026-09-18)

- Short lines are **kept** (shelf §1: 0.44 % of bytes, dictionary/Wikipedia fragments are dense data).
- `tr-web-v1` stays as is; two exact rules added as `tr-web-v2` (`U+FFFD`, wiki markup).
- Near-duplicates (Hamming ≤ 3) are **removed** in the same pass, not only reported.
- Held-out: the shelf's hash rule (`afacan-held-out-v1`) replaces "afacan sends a file".
- Language rule: **applied** with fastText `lid.176` (≥ 200 chars, p ≥ 0.5) as a drop list computed
  outside the project venv (Python 3.13); lingua was rejected after measurement (64 % false positives).

## Done

- `quality_filters.py`: `tr-web-v2`; `_REASON_ORDER` gains `encoding_corruption`,
  `wiki_markup_residue`. v1 unchanged (tests assert it).
- `clean_candidate.py`: `clean-candidate-v3` — `--held-out-rule`, `--held-out-path`,
  `--near-dedup`; shared dedup registry across both streams; in-memory SimHash index on
  `array('Q')`/`array('I')` (≈ 140 MB for 5.9 M lines); rejection record v2 (sha256,
  reasons, char_count, preview, duplicate_of); atomic outputs. Dedup registry keys are
  32-byte digests instead of 64-char hex strings (less memory than v1).
- Docs: [temiz_aday_v3.md](../temiz_aday_v3.md) (pipeline, report format, production command).
- Tests: 4 new in `test_quality_filters.py`, 4 new in `test_clean_candidate.py`; full
  worker suite 269 passed, 1 skipped (Windows symlink case).
- Control runs (copies of the tree): removing the shared registry for held-out lines →
  `test_v3_dedup_is_shared_across_streams_so_held_out_never_leaks` red; disabling
  near-dup lookup → `test_v3_near_dedup_drops_close_variant_and_reports_partner` red.
  (A first mutation that only disabled the *lookup* for held-out lines survived — it did
  not model "separate registries"; the second mutation did.)
- End to end on the seeded 100k sample: 249 s; 99,007 kept / 43 held-out / 937 quality /
  13 near-dup; candidate-overflow 0; numbers match the standalone measurement
  (231 `U+FFFD`, 353 markup).
- Held-out rule reproduced independently on the current candidate: **2,275 docs /
  5,084,138 bytes**, identical to the shelf's count.

- `--drop-list` / `--drop-list-method` / `--drop-list-reason`: external decisions enter the
  pass by line SHA256; the list's own SHA256 and entry count go into the manifest. Test added
  (listed line removed with `details`, unlisted kept, malformed list refused).
- First production run (no language rule) was stopped after ~25 min by owner decision and its
  temp files removed; restarted with the drop list.

## Open

1. **Production run** on `gardash_faz2_tr_dedup_20260621` (13.57 GB, 6,027,968 lines):
   ~4 h estimate, dominated by SimHash. Owner picks the time. Note: the input is the
   *parent* (`9826d58e…`), not the v1 candidate — PII removal reruns as part of the pass.
2. Register both outputs as sources through the API (owner starts API + worker):
   `pretrain` candidate (`derived_from` parent) and `holdout`; rights `unknown`.
3. Then sampling → 200-sample review (owner, two sessions) → draft release → freeze
   (decontamination gate now numeric) → exports → delivery letter with SHA256.
4. Hand the rejection report to the shelf for the false-positive audit.
