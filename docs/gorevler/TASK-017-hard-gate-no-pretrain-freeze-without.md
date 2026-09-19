# TASK-017 — Hard gate: no `pretrain` freeze without a registered eval/holdout reference source

| Field | Value |
|---|---|
| Status | **DRAFT** — from the 2026-09-19 plan ([plan_2026_09.md](../plan_2026_09.md), Faz 1); no new feature — may start when its dependencies are done |
| Kind | fix |
| Moratorium | allowed — enforces a written governance rule (2026-09-17) |
| Estimate | 0.5 day(s) |
| Depends on | — |
| Owner | (unassigned) |

## Goal

Make `QueueFreeze` refuse a `pretrain` freeze when no eval/holdout reference exists, so decontamination can never return `not_applicable` on a frozen pretrain release.

## Why

data_governance.md says the rule is process-only ('kodda sert kapı değildir'). v2 is the first pretrain freeze ever; the held-out source exists, so the gate cannot block it. It lands before the freeze because TASK-018's Go half calls `Releases.Create` and `QueueFreeze` on the `_test` DB with a pretrain draft — the exact path this gate touches — so the gate is exercised once on a pretrain draft before the real run.

## Scope

- `internal/repository/releases.go` `QueueFreeze` (line 495): for `content_purpose = pretrain` return `GateError{eval_reference_missing}` (422) unless a source with purpose in (eval, holdout), `object_sha256` present and `duplicate_status <> 'duplicate'` exists — the same selection `release_jobs.py` uses for references.
- Purpose-scoped: instruction/preference releases unaffected (7 frozen instruction releases exist).
- Integration test on the `_test` DB (TASK-007 harness, pattern of `releases_contract_integration_test.go`): pretrain draft without reference → 422; with the held-out → queued; control run with the check removed → red.
- data_governance.md: replace the process-only note with 'sert kapı (TASK-017, commit SHA)'.

## Out of scope

- Making the approximate decontamination report a hard gate (uncalibrated).
- Any migration.

## Acceptance criteria

- [ ] `go test ./internal/repository/... -count=1` green with the new test; control run red recorded.
- [ ] `POST /releases/{id}/freeze` on a pretrain draft with 0 eval/holdout sources → 422 `eval_reference_missing`; with the held-out present → freeze queued.
- [ ] Governance sentence updated; CI green.

## Owner actions

- Restart the API after merge.

## Report

(not started)
