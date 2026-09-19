# TASK-019 — v2 release: draft → freeze → txt + jsonl export → delivery letter with SHAs; post-export backup

| Field | Value |
|---|---|
| Status | **DRAFT** — from the 2026-09-19 plan ([plan_2026_09.md](../plan_2026_09.md), Faz 1); no new feature — may start when its dependencies are done |
| Kind | delivery |
| Moratorium | allowed — this is Faz 0 (real deliveries 0 → 1) |
| Estimate | 1.5 day(s) |
| Depends on | TASK-012, TASK-011 (decision), TASK-017, TASK-018, TASK-010a |
| Owner | (unassigned) |

## Goal

Freeze the first real `pretrain` release from clean candidate v3, export both formats, and hand the shelf a letter with the export SHA256 (the model-card number), release manifest SHA256, numeric decontamination results and measured durations.

## Why

This is the reason the project exists; everything in later phases is conditional on having done it once.

## Scope

- Create the pretrain draft with source 0820b63b…; verify contract snapshot + implementation bundle SHA; queue freeze; watch progress counters; one fix cycle budgeted (moratorium-allowed fix with test + control run).
- Queue txt and jsonl exports; record `input_bytes_processed`, durations, artifact SHA256s, record counts, `token_estimate` (`unicode-codepoint-range-v1`, labelled estimate); verify one artifact end to end via API download (TASK-003 path).
- Letter `docs/mektuplar/<date>-derlem-raf-v2-teslim.md`: export SHA, release manifest SHA, held-out SHA, gate results (compared 2,239 / matches 0 / approximate reported), durations, rights basis (path A/B/C from 'TASK-011 (decision)' + evidence ref; under B the memo is named), known defects (short-line fragments; false-drop audit 'pending' — not a number), the responsibility-signature sentence (diyet Faz 3), reading order from letter 2026-09-17 §2.
- Second encrypted backup after the exports; update diyet_yol_haritasi.md Faz 0; close TASK-012 and README rows.

## Out of scope

- Any re-derivation or rule change to the candidate.
- Waiting for the audit verdicts (TASK-020).
- Tokenizer-true counts (TASK-033).

## Acceptance criteria

- [ ] `releases` row `status = frozen`, `contract_snapshot_status = present`; `gate_results.exact_decontamination.compared_document_count = 2239`, matches 0; approximate `status = reported`.
- [ ] Two `release_exports` rows `ready`; `sha256sum` of each downloaded artifact equals the manifest value.
- [ ] Letter committed with all SHAs and durations as numbers; post-export backup manifest lists the frozen manifest and both artifacts; diyet Faz 0 shows delivery count 1.

## Owner actions

- Check free disk (≥ ~30 GB) before export; approve each working-DB action (draft, attach, freeze, two exports) or perform them in the UI; keep API + worker running.
- Give the go for the post-export backup; hand-carry the letter (and the 36 MB rejection report if the shelf wants it).

## Report

(not started)
