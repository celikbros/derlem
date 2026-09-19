# TASK-024 — Overlap pilot: one pinned Turkish Wikipedia slice through the existing local-file intake, net-new share measured

| Field | Value |
|---|---|
| Status | **DRAFT** — from the 2026-09-19 plan ([plan_2026_09.md](../plan_2026_09.md), Faz 2); needs the owner's approval before work starts |
| Kind | research |
| Moratorium | allowed as research through existing code — **owner approval** for the download and disk |
| Estimate | 1 day(s) |
| Depends on | TASK-023, TASK-022 |
| Owner | (unassigned) |

## Goal

Measure how much of a Turkish Wikipedia slice is net-new against the parent family before any importer is built.

## Why

The parent already holds Wikipedia via `wiki_oscar`; near-dup rates were 45× higher on the full corpus than in the slice, so paper estimates under-count. A one-day pilot beats a three-day importer that imports duplicates.

## Scope

- Download one pinned slice (a few hundred MB) outside the app into `IMPORT_ROOT`; convert record → one document per line without splitting any record; register via the admin local-file intake with `content_purpose = pretrain`, `rights_status = unknown`, `lineage_ref` → the licence note; let the gates run.
- Read the normalized-dedup result (external duplicates against the family vs unique); net-new bytes and token estimate into TASK-013 and the dataset note; ingest/PII/fingerprint durations recorded.

## Out of scope

- New code.
- Any release containing the pilot source.

## Acceptance criteria

- [ ] Registered source with `normalized_dedup_status` result and `external_duplicate_count`; net-new share = 1 − duplicates/documents written as a number.
- [ ] Job durations for the slice recorded (feeds TASK-021 and TASK-032 sizing).

## Owner actions

- Approve the download, disk use and registration.

## Report

(not started)
