# TASK-014 — Normalized dedup quarantines a source's own lineage family

| Field | Value |
|---|---|
| Status | **IN REVIEW** — 2026-09-19. Code, migration and tests done; migration `000029` must be applied to the working database (owner approval per action), the worker restarted, and the parent's inputs declared. |
| Kind | fix (gate correctness) + small schema addition |
| Moratorium | allowed — a gate that quarantines correct sources blocks the approved v2 path |
| Owner | (unassigned) |
| Found | 2026-09-19 while registering the v3 clean candidate (TASK-012) |

## Problem (measured)

The normalized-dedup gate (`index_document_fingerprints`, `gate_jobs.py`) counts a
document as an external duplicate when the same fingerprint exists in **any other
source except the source's ancestors** (`derived_from_source_id` chain). Two lineage
shapes it cannot see:

1. **Siblings.** v1 candidate (`f63352dd…`) and v3 candidate (`0820b63b…`) are both
   derived from the parent `06ac330e…`. Their documents are the same by construction.
   v3 is not v1's ancestor, so v1's 5.9 M fingerprints count as external duplicates →
   v3 would be **quarantined**. Same for the held-out source (`a043125e…`).
2. **Multi-parent inputs.** The parent was built from seven raw files; the model has
   one `derived_from_source_id`, so the five raw sources registered under TASK-010
   (`faz2_ham_*`) have no recorded relation to the parent. Their fingerprints also
   count against every candidate. (They themselves were quarantined for the mirror
   reason — expected for archival inputs, but the direction candidate ← raw is a bug.)

## Fix

- **Migration `000029_source_lineage_inputs.sql`**: `source_lineage_inputs(source_id,
  input_source_id)` — multi-parent inputs. Bookkeeping, not ledgered; self-reference
  rejected by a CHECK; an input referenced by a derivation cannot be deleted.
- **Gate**: exclusion set = the source's **lineage family** — its ancestors and inputs
  (transitively), every other source that shares any of them, and its own descendants.
  Unrelated sources are counted exactly as before. `lineage_excluded_source_ids` in the
  job result now lists the family.
- **API**: `lineage_input_source_ids` on create and update (nil on update = untouched,
  `[]` = clear); canonical UUIDs, deduplicated, sorted; unknown input → 422
  `derived_source_not_found`, self → 422 `self_lineage`. Read back on every source.
  Web shows "Girdi kaynakları" in the inspector (no form editing yet).

## Verification (2026-09-19)

- `go test ./...` on the scratch database: every package `ok`, including
  `TestSourceLineageInputsRoundTrip` (repository) and the two migration tests.
- Worker: 270 passed, 1 skipped; `test_normalized_dedup_excludes_lineage_family_but_not_unrelated_sources`
  covers ancestors (unchanged assertions), a sibling, a declared input and an unrelated source.
- Control run: reverting the family clause to ancestors-only (mutation in a copy) turns the
  sibling case red.

## Rollout (owner actions, in order)

1. ~~Apply `000029` to the working database~~ — **done 2026-09-19 07:16** (`go run ./cmd/migrate`,
   owner approval; `schema_migrations` head is `000029_source_lineage_inputs.sql`).
2. ~~Restart the API and the worker~~ — **done by the owner 2026-09-19 10:43.** Before the
   restart the old worker had already run the gate on both new sources: the v3 candidate
   was quarantined with **5,807,521** "external duplicates" (every fingerprinted document)
   and the held-out with **2,226** — the measured shape of the bug.
3. ~~Declare the parent's inputs~~ — **done 2026-09-19** (API PATCH, parent version 5 → 6,
   five `faz2_ham_*` sources; `celik_gold` and `wiki_oscar` to be added once registered).
4. ~~Reset~~ — **done 2026-09-19** with the owner's approval: `normalized_dedup_status` →
   `not_checked`, counts → 0, `approval_status` → `auto_checked`, `risk_level` → `low`
   for both sources, each with a `source.normalized_dedup_reset` audit event carrying the
   before/after state and the reason. The worker re-enqueues the gate on its own.
5. **Found while waiting:** the worker's maintenance sweep (`enqueue_maintenance_jobs`,
   which enqueues exact-dup / fingerprint / sampling jobs for sources in `not_checked`
   states) runs **only once at worker start-up** (`main.py`), not in the loop. A reset
   done after a restart therefore never gets picked up. With the owner's approval the
   sweep was invoked once from the worker's own code (no hand-written SQL). Follow-up:
   run the sweep periodically in `run_forever` (small change; separate card).
6. **Gate re-run (2026-09-19): both sources `unique`, 0 external duplicates,
   `approval_status = auto_checked`** — the same 5.8 M documents that the old query had
   counted as 5,807,521 duplicates. Next: sampling, then the owner's 200-sample review.
