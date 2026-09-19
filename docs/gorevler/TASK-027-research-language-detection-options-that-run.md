# TASK-027 — Research: language detection options that run in the Python 3.14 worker, measured against the fastText baseline

| Field | Value |
|---|---|
| Status | **DONE** — 2026-09-19. Measured on the 82,239 long lines; table with 4 running options + baseline; recommendation: subprocess bridge (`DERLEM_LID_PYTHON`, model SHA pinned, 2,000-char window). From the 2026-09-19 plan ([plan_2026_09.md](../plan_2026_09.md), Faz 3) |
| Kind | research |
| Moratorium | allowed — measurement |
| Estimate | 0.5 day(s) |
| Depends on | — |
| Owner | (unassigned) |

## Goal

A measured recommendation for how the worker detects language, given that the official fastText package does not build on the project's Python 3.14.

## Why

Lingua had 64 % false positives; fastText lid.176.ftz measured 30 flagged / 82,239 long lines in 23 s on 3.13. The gate job (TASK-028) must not rest on an assumption.

## Scope

- On the same 82,239 long lines of the 100k slice: (a) does `fasttext-predict` install on 3.14 today; (b) a pure-Python reader for `lid.176.ftz`; (c) a subprocess bridge to a configured 3.13 interpreter (`DERLEM_LID_PYTHON`) with model SHA pinned (8f3472cf…).
- Table: install status, time, flagged count, share of flagged lines that are Turkish (Turkish-letter density ≥ 1 %); one recommendation; honest fallback 'unavailable' when no detector runs.

## Out of scope

- Any pipeline change.

## Acceptance criteria

- [x] Table with ≥ 2 options plus the baseline; a written recommendation with reason; model SHA recorded as the method-id component. (Report below: baseline + 4 options that were run, 2 cited; SHA256 `8f3472cfe8738a7b6099e8e999c3cbfae0dcd15696aac7d7738a8039db603e83`.)

## Owner actions

- None required. Recommendation **accepted** 2026-09-19 (kurucu, 2026-09-19 gece: "önerilerin ok"): TASK-028 (still approval-gated) builds on the subprocess bridge (`DERLEM_LID_PYTHON`, SHA-pinned, `unavailable` fallback) with the window-carrying method id.

## Report

Measured 2026-09-19 on `var/olcum-2026-09-17/dilim-100k.txt` (100,000 lines; **82,239 lines
≥ 200 chars**, 196,177,180 chars, 25.8 M whitespace tokens). A 3-hour derivation was running on
the machine throughout (CPU 25–56 %), so absolute times are 1.5–1.7× the 2026-09-18 figures;
the ratios between options are what count. Scripts and per-run outputs (JSON summary + every
flagged line) are in `var/olcum-2026-09-17/task-027-lid/` (`var/` is gitignored, like the
earlier measurement files there).

### Model, interpreters, and one method finding

- **Model** `lid.176.ftz`, 938,013 bytes, **SHA256
  `8f3472cfe8738a7b6099e8e999c3cbfae0dcd15696aac7d7738a8039db603e83`** (verified today; this is
  the method-id component). Header (`ftz_header.py`, stdlib): fastText v12, dim 16, char
  n-grams minn 2 / maxn 4, bucket 2,000,000, dictionary 7,235 words + 176 labels, pruneidx
  42,765 entries, input matrix product-quantised (50,000 rows × 16, 8 sub-quantisers of 2 dims,
  256 centroids each, plus a norm quantiser), output matrix dense 176 × 16.
- **Interpreters.** `worker/.venv` is **Python 3.13.15** (uv 0.12.3, created 2026-08-21;
  `requires-python >= 3.12`). The repo-root `.venv` is **3.14.6** (the documented test runner).
  So "the worker's 3.14" is the root venv / the direction of travel, not the worker's runtime
  venv as it exists today. Nothing was installed into either; every install below went into a
  throwaway venv under the session scratchpad.
- **Method finding.** The 2026-09-18 baseline (30 flagged) and the production drop list
  (1,501 records) predicted on the **first 2,000 characters** of each line, not the full line.
  Reproduced exactly: with a 2,000-char window today's run flags the same 30 lines; the line at
  source ordinal 217038 (drop list `hu 0.6962`, sample list `hu 0.696`) gives `hu 0.696` only at
  2,000 chars and `tr 0.701` on its full 6,644 chars. The full line flags **33** (4 new, 1 gone;
  all five are 3.5k–16k-char mixed-language lines). The docs state only "≥ 200 chars, p ≥ 0.5";
  the window is part of the method and must be written into the method-id (below).

### Table

Rule everywhere: line ≥ 200 chars, detector says not `tr` with p ≥ 0.5 → flagged. "Turkish" =
Turkish-specific letters (çğıöşüÇĞİÖŞÜ) ≥ 1 % of the line's letters (`str.isalpha`), computed
on the full line.

| Option | Install status (2026-09-19) | Time, 82,239 lines | Flagged | Flagged that are Turkish (density ≥ 1 %) |
|---|---|---|---|---|
| **Baseline**: `fasttext-predict` 0.9.2.4 in-process, Python 3.13.15 throwaway venv, window 2,000 chars | cp313 wheel on PyPI; installs | **36.0 s** (rerun 34.9 s); load 0.03 s | **30** (0.036 %) | 10 (33 %) — same 30 lines as 2026-09-18 |
| Baseline on the **full line** (no window) | same | 40.1 s | 33 (0.040 %) | 13 (39 %) |
| (a) `fasttext-predict` 0.9.2.4 on **Python 3.14.6** | **fails**: no cp314 wheel on PyPI (`--only-binary` finds none for 0.9.2.1–0.9.2.4); pip builds the sdist and stops at `error: Microsoft Visual C++ 14.0 or greater is required` (no MSVC on this machine) | — | — | — |
| (a′) `fasttext-wheel` 0.9.2 and `fasttext` (official) on 3.14.6 | **fail**, identical error (no cp314 wheels, sdist needs MSVC). Side note: `fasttext-wheel` 0.9.2 with numpy 2.5 raises `ValueError` in `predict` (`np.array(copy=False)`), so even on 3.12 it is not a drop-in | — | — | — |
| (a″) `fasttext-predict` in a throwaway venv created from `worker/.venv`'s own interpreter (3.13.15) | installs (cp313 wheel), imports | = baseline | 30 | 10 |
| (b) pure-Python reader for `lid.176.ftz` | **not built; nothing on PyPI does it.** `fasttextlt` 0.2.0 (pure Python + numpy) raises `NotImplementedError("Supervised fastText models are not supported")` and does not read quantised matrices; `fasttext-langdetect` 1.1.1 is a wrapper that `Requires-Dist: fasttext-predict`; `compress-fasttext` needs gensim (no supervised/quantised); `pyfasttext`, `fasttext-numpy2(-wheel)` are the same C++ extension (need a compiler). Estimate for building one: dictionary + pruneidx + PQ de-quantisation ≈ 250 lines with numpy (feasible); the hot loop is the subword hashing (FNV-1a with `int8` cast over UTF-8 bytes, n = 2..4). Measured that loop in pure Python on 1,000 long lines (`ngram_bench.py`): **6.4 ms/line → ≈ 17 min for the slice, hashing alone**, i.e. 25–30× the C++ path; ≈ 17 h for the 6.0 M-line corpus vs ~25 min. Equivalence to the C++ predictions would also have to be proven line by line | ≈ 17 min (hashing only, extrapolated) | — | — |
| **(c) subprocess bridge**: parent = stdlib-only Python **3.14.6**, child = `DERLEM_LID_PYTHON` (3.13 venv with `fasttext-predict`), child verifies the model SHA against the pinned value before loading, one line in → `lang\tp` out; window 2,000 | **runs** on 3.14 today; nothing to install on the 3.14 side | **39.4 s** incl. child start 0.1–0.2 s (one outlier 67 s at 56 % system load); full line 40.6 s vs 40.1 s in-process | **30** — byte-identical set to the baseline (also 33 = 33 on full line) | 10 |
| (c) with `DERLEM_LID_PYTHON` unset / not a file / SHA mismatch / `import fasttext` fails | exits 1, prints `unavailable: …` — no decision is produced | 0.1 s | — | — |
| (d) `lingua-language-detector` 2.2.0 (not re-run; 2026-09-18 measurement) | installs on 3.14 | 323 s | 121 (0.147 %) | 77 (**64 %**) — footballer biographies as "Tagalog 1.0" |
| `langdetect` 1.0.9 (not re-run; 2026-09-18) | installs on 3.14 | 291 s | 84 (0.102 %) | not measured |

### Recommendation

**Use the subprocess bridge (c) as the worker's language-detection contract**, with the model
SHA pinned and the 2,000-char window fixed. Reason: it is the only option that runs from the
3.14 side today, it reproduces the production decisions exactly (30/30 and 33/33 in every run),
its cost is ≈ +5–13 % on 82,239 lines (0.5–4.5 s, child start 0.1–0.2 s), it needs no compiler
and no change to any venv's packages, and it fails **loudly** (`unavailable`, exit 1) instead of
silently defaulting. The pure-Python reader is not worth building (25–30× slower, ~17 h per
corpus, unproven equivalence); lingua and langdetect are 8–9× slower and lingua flags Turkish
text 64 % of the time. When the worker's own interpreter can import `fasttext` (as
`worker/.venv` 3.13.15 could, if the wheel were added — a dependency change, out of scope here),
the same contract holds by pointing `DERLEM_LID_PYTHON` at that interpreter; the decision path
and the method-id do not change.

Method-id for the gate (TASK-028):
`fasttext-lid.176.ftz@8f3472cfe8738a7b6099e8e999c3cbfae0dcd15696aac7d7738a8039db603e83;window=2000;min_chars=200;p>=0.5;flag=lang!=tr`.
The window value is load-bearing: full-line prediction moves 5 decisions on 82,239 lines
(+4 / −1) relative to the production drop list.

**Honest fallback.** If `DERLEM_LID_PYTHON` is unset, not a file, the child cannot import
`fasttext`, or the model's SHA256 differs from the pinned value, the detector reports
**`unavailable`**: no line is dropped for language, no line is labelled Turkish, and the manifest
records `language: unavailable` with the reason. Never fall back to lingua or langdetect
silently.

Bridge protocol as measured (`lid_bridge.py` / `lid_child.py`, both stdlib on the parent side):
child argv `MODEL PINNED_SHA256`; child's first stdout line is `OK <sha256>` or `ERR <reason>`
(exit 2 on SHA mismatch, 3 on import failure); then one UTF-8 line in (newlines stripped,
window applied by the parent) → one `lang<TAB>p` line out; parent feeds stdin from a thread and
counts results against inputs, refusing the run if the counts differ.
