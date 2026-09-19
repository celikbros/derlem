# TASK-026 — Quality-filter language honesty: `tr-web-*` policies write `not_evaluated` for non-Turkish sources

| Field | Value |
|---|---|
| Status | **DONE** — 2026-09-19; from the 2026-09-19 plan ([plan_2026_09.md](../plan_2026_09.md), Faz 3); no new feature |
| Kind | fix |
| Moratorium | allowed — same defect class as TASK-005 |
| Estimate | 0.5 day(s) |
| Depends on | — |
| Owner | (unassigned) |

## Goal

The offline clean-candidate derivation never applies Turkish lexicon rules to a source whose declared language is not Turkish; it records `not_evaluated` instead.

## Why

`tr-web-v1/v2` are Turkish-only; applying them to another language produces a verdict on nothing. This is a guard in the derivation script (release quality rows come from `document_reviews`), not release gate reporting — labelled honestly.

## Scope

- `quality_filters.py`: `supported_languages = {'tr'}` on `tr-web-v1/v2`.
- `clean_candidate.py`: source language outside the set → manifest `quality_filter_status: not_evaluated`, 0 quality drops.
- Tests + control run; temiz_aday_v3.md note.

## Out of scope

- New quality rules.
- Language detection (TASK-028).

## Acceptance criteria

- [x] `clean_candidate --quality-policy tr-web-v2` on a `language = en` source writes `not_evaluated` and drops 0 lines for quality; `tr` behaviour unchanged (existing tests green).
- [x] Control run with the guard removed → new test red.

## Owner actions

- None.

## Report

Done 2026-09-19. No quality rule changed; the guard sits in the derivation script only.

**Code**

- `worker/src/derlem_worker/quality_filters.py`: `QUALITY_POLICY_SUPPORTED_LANGUAGES`
  (`tr-web-v1` and `tr-web-v2` → `{"tr"}`; `none` has no restriction), three status
  constants (`applied`, `applied_language_unknown`, `not_evaluated`) and
  `quality_filter_status(policy, language)`. The language tag is normalised with the
  PII scanner's `normalize_language_tag` (`tr-TR` → `tr`), same convention as TASK-005.
- `worker/src/derlem_worker/clean_candidate.py`: `load_source` now selects
  `sources.language`; `derive_clean_candidate` computes the status from the source's
  declared language and, when it is `not_evaluated`, runs the line loop with policy
  `none` (0 quality drops, empty rejections file). New manifest field
  `quality_filter_status` (dataclass default `None`, appended last — every existing
  field, `quality_filter_version`, `algorithm_version` and the `_v2`/`_v3` file-name
  suffix are untouched, so old manifests and readers stay valid).

**Decisions**

- `--input-path` runs have no source row and therefore no language: the policy applies
  exactly as before and the manifest records `applied_language_unknown` rather than a
  bare `applied`. Policy `none` leaves the field `null`.
- `quality_filter_version` keeps recording the *requested* policy in the
  `not_evaluated` case, so a reader can see which policy was declined and why.

**Tests** (`worker/tests/test_quality_filters.py`, `worker/tests/test_clean_candidate.py`)

- 8 new: supported-language table; status for `tr`/`tr-TR`/` TR `/`en`/`en-US`/`None`/`""`
  on both policies; `none` policy → `None`; unknown policy → `ValueError`; derivation on
  an `en` source → `not_evaluated`, 0 quality drops, spam line kept, manifest keeps
  `tr-web-v2`; `tr` and `tr-TR` sources → `applied`, same drops and reasons as before;
  `--input-path` (no source) → `applied_language_unknown`, policy applied; no policy →
  status `null`.
- Run: `PYTHONPATH=worker/src PYTHONIOENCODING=utf-8 .venv/Scripts/python.exe -m pytest
  worker/tests/test_quality_filters.py worker/tests/test_clean_candidate.py -q` →
  **42 passed** (34 before the task + 8). Note: `worker/.venv` (Python 3.13) has neither
  `pytest` nor `pip`, so the repo-root `.venv` documented in CONTRIBUTING.md was used;
  it imports `worker/src` directly (confirmed via `derlem_worker.clean_candidate.__file__`).

**Control run** — guard removed on disk by replacing the line
`effective_quality_policy = (QUALITY_POLICY_NONE if quality_status == QUALITY_FILTER_STATUS_NOT_EVALUATED else quality_policy)`
with `effective_quality_policy = quality_policy`, same pytest command as above:
`1 failed, 41 passed` — the failure is
`test_tr_web_policy_is_not_evaluated_for_non_turkish_source` (the `en` source's spam
line was dropped: `Right contains one more item: '#etiket0 …'`). Guard restored →
`42 passed`.

**Docs**: `docs/temiz_aday_v3.md`, new section "Dil dürüstlüğü (TASK-026)".

**Open**: the language guard reads the declared `sources.language` only; mixed-language
or mislabelled sources are TASK-028's business. The long-running v3 derivation that was
in flight on 2026-09-19 loaded the pre-change module and is unaffected; its manifest will
not carry `quality_filter_status` (source is `tr`, so it would have read `applied`).
