# TASK-028 — Language detection gate job with a stored per-source distribution; `detected_language` on sampled documents; mismatch risk reason

| Field | Value |
|---|---|
| Status | **DRAFT** — from the 2026-09-19 plan ([plan_2026_09.md](../plan_2026_09.md), Faz 3); needs the owner's approval before work starts |
| Kind | feature |
| Moratorium | **owner approval required** — owner ordering #1 |
| Estimate | 2 day(s) |
| Depends on | TASK-027, TASK-015 |
| Owner | (unassigned) |

## Goal

Detection becomes a stored fact per source (distribution) and per sampled document, with a declared/detected mismatch feeding sampling risk; the declared language is never overwritten.

## Why

Today language decisions enter the pipeline as an offline drop list. `documents` rows exist only for the 200 samples (`sample_jobs.py:200`), so per-document language at ingest is not a real capability; a per-source gate result is.

## Scope

- Job `detect_language` enqueued by the maintenance sweep for sources in `not_checked`: lines ≥ 200 chars, p ≥ 0.5 (v3 rule); result `{method, model_sha256, min_chars, min_p, distribution: {lang: lines}, sampled: bool}` on the source; resumable or sampled for very large sources.
- Migration: `documents.detected_language` (nullable) set for sampled documents; `language_mismatch` risk reason feeds sampling; source inspector shows the histogram.
- Detector unavailable → `method = 'unavailable'`, job succeeds with a warning counter.
- Tests with a 70 tr / 30 en fixture; control run red; runtime measured on the parent or the pre-drop 100k slice (not the v3 candidate, from which non-Turkish lines were already dropped).

## Out of scope

- Overwriting declared language.
- Blocking on mismatch.
- Per-language PII/quality rules.

## Acceptance criteria

- [ ] Fixture source → distribution `{tr: 70, en: 30}` stored and shown in the inspector; its sampled documents carry `detected_language`.
- [ ] On the pre-drop 100k slice the non-Turkish count for ≥ 200-char lines equals 30 / 82,239 within ±5 %; runtime written in the card.
- [ ] Worker suite green; control run red; CI green.

## Owner actions

- Approve; choose the interpreter route; confirm mismatch is a risk reason, not a block; apply migration; restart worker.

## Report

(not started)
