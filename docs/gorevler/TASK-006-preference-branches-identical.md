# TASK-006 — Canonical preference records accept identical chosen/rejected branches

| Field | Value |
|---|---|
| Status | **DONE** — 2026-09-12 (implemented by Claude at the owner's request) |
| Kind | fix |
| Moratorium | allowed (structural validation gap; half a day; no new behaviour) |
| Estimate | 0.5 day |
| Owner | (unassigned) |
| Verified against code | 2026-09-12 — `canonical.py:115-140` read by the owner's session |

## Goal

Reject a `preference` record whose `chosen` and `rejected` branches are identical after
sanitisation. Such a record carries zero preference signal, yet today it is exported
and counted in the frozen manifest's `record_type_counts` as a preference pair.

## Why

This is the cheapest real gate in the system and the first one that **compares two
fields** — every future multi-field type (translation pair, edit pair) needs the same
discipline. Doing it in `canonical.py` (not in a worker gate) is deliberate: a gate
can be bypassed by uploading a canonical JSONL file directly; the parser cannot.

## Current state (measured)

`worker/src/derlem_worker/canonical.py:119-139` validates that both branches exist,
are non-empty lists, and pass message validation. It never compares them:

```python
for branch in ("chosen", "rejected"):
    branch_messages = preference.get(branch)
    if not isinstance(branch_messages, list) or not branch_messages:
        raise CanonicalSampleError(f"preference_{branch}_required")
    combined, branch_texts = _validate_messages(context + branch_messages, tools)
    sanitized_branch = combined[len(context):]
    sanitized_preference[branch] = sanitized_branch
```

## Scope

1. After both branches are sanitised, compare `sanitized_preference["chosen"]` with
   `sanitized_preference["rejected"]` (structural equality of the message lists —
   role + content + reasoning as sanitised). Equal → raise
   `CanonicalSampleError("preference_branches_identical")`.
2. Compare the **sanitised** form, not the raw input, so that a difference living only
   in a `review_only` reasoning block (which sanitisation strips) is still caught as
   identical — the exported pair would be identical, and that is what matters.
3. Tests in `worker/tests/test_canonical.py`: identical branches → error; branches
   differing only in stripped reasoning → error; branches differing in one character →
   accepted.
4. Note in the Report whether any **existing** canonical fixture or stored sample
   trips the new rule (`data_samples/example_canonical_preferences.jsonl` and any
   canonical source in the DB). If one does, do not silently edit the fixture — report it.

## Out of scope

- Ties, "both bad", scores, annotator ids — those need a format decision
  (`docs/katki_gorev_tipleri_karar_notu.md` §2, §8.3), not this card.
- Near-duplicate branches (e.g. whitespace-only differences). Exact structural
  equality only; log the open question.

## Files

- `worker/src/derlem_worker/canonical.py`
- `worker/tests/test_canonical.py`

## Acceptance criteria

- [ ] `parse_canonical_sample` on a record with identical branches raises
      `CanonicalSampleError` with code `preference_branches_identical`.
- [ ] The three test cases above pass; the full `pytest worker/` stays green.
- [ ] Report states whether existing fixtures/sources trip the rule.

## Verification commands

```powershell
.\.venv\Scripts\python.exe -m pytest worker/tests/test_canonical.py -q
.\.venv\Scripts\python.exe -m pytest worker/ -q
```

## Risks / traps

- The stale packaged copy under `worker/build/lib/derlem_worker/` must not be edited;
  it is not what runs.
- Because export re-parses every record (`releases.py:746-760`), a stored record that
  trips this rule will **block that release at export**. That is the intended
  fail-closed behaviour — but the Report must say whether any frozen release's source
  would now fail a re-export.

## Report

**Done 2026-09-12.** `parse_canonical_sample` now raises
`CanonicalSampleError("preference_branches_identical")` when the two sanitised
branches carry the same training signal.

**One correction to the card's design, found by the tests.** "Compare the sanitised
form" was not enough: sanitisation pops `reasoning_content` for `review_only`/`hidden`
(`canonical.py:223`) but leaves the `reasoning_visibility` flag on the message, so two
branches differing only in private reasoning still compared as *different* — the
second test case failed on the first run. The comparison is therefore made on a
**projection** of each message to the fields the model actually sees or produces:
`role, name, content, reasoning_content (if it survived), tool_calls, tool_call_id`.
`message_id`, `reasoning_visibility` and `metadata` are record bookkeeping, not
signal, and are excluded (`_branch_signal`, `_BRANCH_SIGNAL_FIELDS`). Both
`test_canonical.py` and the packaged fixture agree with this.

**Verification run (owner's machine, 2026-09-12):**

- `pytest worker/tests/test_canonical.py` → 11 passed (3 new: identical → error;
  differs only in `review_only` reasoning → error; differs by one character → accepted)
- `pytest worker/tests` without DB → 214 passed, 9 skipped (unchanged skips)
- `pytest worker/tests` **with** `DERLEM_TEST_DATABASE_URL` → `derlem_ci_test`:
  **222 passed, 1 skipped** (only the Windows symlink privilege case) — the eight
  DB-backed tests, including `test_lineage_dedup_integration`, ran and passed
- `data_samples/example_canonical_preferences.jsonl` still passes
  `test_repository_examples_follow_the_runtime_contract`

**Existing data:** `SELECT count(*) FROM sources WHERE content_purpose='preference'`
on the working database → **0**, none in any release. The new rule blocks nothing
that exists today.

**Open question logged (out of scope):** near-identical branches (whitespace-only or
punctuation-only differences) still pass — exact structural equality on purpose. A
normalised comparison is a policy decision for the preference-type card.
