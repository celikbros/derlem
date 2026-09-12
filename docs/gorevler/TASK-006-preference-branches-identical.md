# TASK-006 — Canonical preference records accept identical chosen/rejected branches

| Field | Value |
|---|---|
| Status | READY |
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

_(to be filled on completion)_
