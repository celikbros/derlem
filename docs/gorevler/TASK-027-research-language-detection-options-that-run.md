# TASK-027 — Research: language detection options that run in the Python 3.14 worker, measured against the fastText baseline

| Field | Value |
|---|---|
| Status | **DRAFT** — from the 2026-09-19 plan ([plan_2026_09.md](../plan_2026_09.md), Faz 3); no new feature — may start when its dependencies are done |
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

- [ ] Table with ≥ 2 options plus the baseline; a written recommendation with reason; model SHA recorded as the method-id component.

## Owner actions

- None.

## Report

(not started)
