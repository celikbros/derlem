# TASK-023 — Licence notes for Turkish Hugging Face datasets in the TASK-011 format

| Field | Value |
|---|---|
| Status | **DRAFT** — from the 2026-09-19 plan ([plan_2026_09.md](../plan_2026_09.md), Faz 2); no new feature — may start when its dependencies are done |
| Kind | research |
| Moratorium | allowed — research |
| Estimate | 1 day(s) |
| Depends on | TASK-011 |
| Owner | (unassigned) |

## Goal

One evidence note per shortlisted Turkish dataset (Wikipedia, mC4/C4, 2–3 others such as OSCAR/HPLT/FineWeb-2 tr) so the same registry fields can hold them and the volume plan can rank them.

## Why

Owner decision #2: each dataset arrives with a documented licence. Card licences can be looser than the upstream content licence; the note records both and recommends on the stricter.

## Scope

- Per dataset `docs/haklar/hf-<dataset>.md`: dataset-card licence, upstream content licence, pinned revision/snapshot, redistribution/attribution/share-alike duties, Turkish subset bytes, recommended `rights_status`, and an 'already inside the parent?' flag (`wiki_oscar` was an mC4 + Wikipedia download).
- Summary table in TASK-013 ordered by expected net-new tokens per licence risk.

## Out of scope

- Downloading anything (TASK-024).
- Legal advice.

## Acceptance criteria

- [ ] ≥ 4 notes with licence id, evidence URL + retrieval date, pinned revision, Turkish bytes, recommended status and overlap flag.
- [ ] Summary table present in TASK-013.

## Owner actions

- Confirm the shortlist; decide whether share-alike and attribution-only terms are acceptable for the shelf's use.

## Report

(not started)
