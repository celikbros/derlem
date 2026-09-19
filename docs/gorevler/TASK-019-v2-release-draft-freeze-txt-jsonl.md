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

## Rehearsal numbers (TASK-018)

Measured 2026-09-19 on `derlem_ci_test` with the 100k slice (99,007 lines, 202.9 MB; 43-line
held-out) driven in-process through the real worker code (`Worker.run_once()`), same machine
that will run the real job. **Extrapolation is linear in bytes (×58.6 for 11,896,793,726 B)
and is a labelled estimate, not a measurement**; the near-duplicate SimHash index and the
approximate-decontamination candidate lookups grow with document count and may be worse
than linear at 5.8 M documents, so treat the freeze figure as a lower bound.

| Step | Measured (202.9 MB) | Throughput | Extrapolated (11.9 GB) |
|---|---|---|---|
| freeze_release (verify copies + near-dup + exact + approximate decontamination) | 326 s | 0.62 MB/s | ≈ 19,100 s ≈ **5.3 h** (lower bound) |
| export_release txt | 6.65 s | 30.5 MB/s | ≈ 390 s ≈ **6.5 min** |
| export_release jsonl | 8.91 s | 22.8 MB/s in (27.7 MB/s out, output ≈ 1.22 × input) | ≈ 520 s ≈ **8.7 min**, artifact ≈ 14.5 GB |

Gate values seen on the slice (the keys the worker actually writes):
`gate_results.decontamination.reference_document_count = 43`, `match_count = 0`, status
`passed`; `approximate_decontamination.status = reported`, `potential_match_count = 0`;
`near_duplicate_report.status = reported`. For the real run the reference is the 2,239-line
v3 held-out, so expect `reference_document_count = 2239` (this card's acceptance line says
`exact_decontamination.compared_document_count`; that key does not exist — read
`decontamination.reference_document_count`).

Disk: each of the three jobs first copies the source object into a verified temp snapshot
under the store's `.tmp` (≈ 11.9 GB, deleted when the job ends) and the exports add ≈ 11.9 GB
(txt; on this input the txt artifact is byte-identical to the source) and ≈ 14.5 GB (jsonl).
The ≥ 30 GB free-disk check above is consistent with that; ~40 GB is the comfortable figure.

Before queueing: the worker's `MAX_DOCUMENT_BYTES` default is 256 KiB; one longer line blocks
the freeze with `document_too_large`. The slice's longest line is 159,267 B; check the full
candidate's longest line (or raise the limit) first. — Checked 2026-09-20 from the v3 manifest: `clean_candidate` ran with `max_document_bytes = 262144` and dropped 3 oversized lines, so no v3 line (and therefore no v4 line, v4 ⊂ v3) exceeds the worker limit. Nothing to raise.

## Owner actions

- Check free disk (≥ ~30 GB) before export; approve each working-DB action (draft, attach, freeze, two exports) or perform them in the UI; keep API + worker running.
- Give the go for the post-export backup; hand-carry the letter (and the 36 MB rejection report if the shelf wants it).

## Report

(not started)
