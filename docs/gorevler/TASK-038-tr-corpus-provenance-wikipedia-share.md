# TASK-038 — `tr_corpus` provenance: how much of it is Wikipedia paragraphs

| Field | Value |
|---|---|
| Status | **IN PROGRESS** — 2026-09-19, opened on the owner's "önerilerin ok" |
| Kind | research |
| Moratorium | allowed — measurement, no product surface |
| Estimate | 0.5 day(s) |
| Depends on | TASK-016, TASK-022 (findings) |
| Owner | (unassigned) |

## Goal

Measure what share of `tr_corpus.txt` (1,502,165 lines, 457,814,564 bytes, S2: `unknown`,
dropped from v4) is text that also appears inside Wikipedia records of `wiki_oscar`
(`source = wikipedia`, CC BY-SA 3.0 + GFDL, already `cleared` non-commercial).

## Why

TASK-011 recorded `tr_corpus` as "collector not found". Two later findings contradict that:
the archived `celik_ai-kod/.../download_tr_corpus.py` reads an existing `tr_corpus.txt` and
expands it with Wikipedia (`20220301.tr` / `20231101.tr`) paragraphs; TASK-022 found 366 of
the first 500 `tr_corpus` lines to be substrings of `wiki_oscar` records. If most of
`tr_corpus` is Wikipedia text, its rights question largely falls away. It does **not** change
v4 (those lines are dropped; the same text is already kept as whole articles in `wiki_oscar`),
so this is evidence for TASK-011, not a re-derivation trigger.

## Scope

- Read-only scan of `var/raw-derlem/ham-derlem/tr_corpus.txt` and `wiki_oscar_corpus.jsonl`.
- Per `tr_corpus` line (whitespace-collapsed, casefolded): contained in some Wikipedia record /
  in some mC4 record / neither; line and byte shares; length distribution per class; 20 examples
  of "neither"; runtime.
- Result section appended to TASK-011's evidence packet (`docs/hak_kanit_paketi_2026_09.md`).

## Out of scope

- Changing `rights_status` of `tr_corpus` (owner decision after the number).
- Any re-derivation.

## Acceptance criteria

- [ ] Shares (lines, bytes) for wikipedia / mc4 / neither, summing to 100 %; method and runtime written.
- [ ] Recommendation line for the owner (keep `unknown`, or treat the Wikipedia share as covered).

## Report

(in progress)
