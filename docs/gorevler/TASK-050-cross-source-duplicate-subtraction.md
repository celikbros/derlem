# TASK-050 — Cross-source duplicate subtraction: remove documents already held by unrelated sources from a candidate, without re-deriving

| Field | Value |
|---|---|
| Status | **READY** — 2026-10-14 |
| Kind | fix (derivation step) |
| Moratorium | allowed — the first real candidate is blocked at the dedup gate |
| Estimate | 1 day |
| Depends on | TASK-049 (DONE) |
| Owner | (unassigned) — opus |

## Why

The FineWeb2-HQ `tr-web-v4` (B) candidate `b255c3d8-9e3e-48db-8f0b-3f9bfe1ece06` (6,602,551
documents, object `a502b9dd…`) was quarantined by the normalized-document dedup gate on
2026-10-14: 1,149 of its documents (0.017 %) also exist in unrelated sources — the Faz-2 parent
corpus `gardash_faz2_tr_dedup_20260621` (1,149), `faz2_ham_tr_corpus_20260918` (865),
`faz2_ham_wiki_oscar_20260919` (289), `faz2_ham_ttk_20260918` (2). Both corpora come from Common
Crawl, so the same pages appear in both. The gate is right ("Soy Ailesi Tekrar Sayılmaz" in
`data_governance.md`: unrelated sources count) and stays as it is. The candidate must not carry
the overlap; the first-registered source keeps the document.

Re-running the full derivation with a drop list costs ~3 hours (signal tables were deleted after
the run). The selection list makes a cheaper, exact path possible: subtract.

## Scope

- **Drop list from the database (SELECT only):** candidate documents (`document_fingerprints`
  rows of `b255c3d8…`, `source_ordinal` = candidate line number) whose `normalized_sha256` exists
  in any source outside the candidate's lineage family (same family logic as the gate:
  `derived_from_source_id` + `source_lineage_inputs`, ancestors, siblings, descendants). Write it
  as `derlem.decision.v1` rows (`decision_type=duplicate`, `verdict=reject`, reason
  `cross_source_normalized_duplicate`, judge `normalized-document-sha256-v1`, plus the other
  source ids in the reason/extra) with a SHA in the manifest.
- **Subtract:** `python -m derlem_worker.selection subtract --manifest <selection manifest>
  --drop <decisions parquet> --out <new prefix>` → new selection list (train rows minus the drops,
  held-out partition unchanged), decisions = old decisions + drop rows, new manifest whose
  `parent` is unchanged and which records the subtraction (input selection SHA, drop SHA, count).
  Map candidate line ordinal → selection row → parent ordinal exactly; refuse if any mapping is
  ambiguous or a drop is not in the train partition.
- **Materialize** the new candidate from the shards (existing path); two runs, same SHA; the new
  candidate equals the old candidate file with exactly those lines removed (verify by streaming
  both).
- **Self-check before registering:** normalize every remaining line with the gate's own function
  and confirm 0 hits against the other sources' `normalized_sha256` set (SELECT).
- **Registration (prepared, run by Fable through the API):** extend `var/olcum-2026-10-13/task-049/kayit.py`
  or add a sibling that registers the new candidate (`…_trweb4B_xdedup_20261014`, pretrain,
  derived from `ba80dc1c…`, 10 % threshold before ingest). The existing held-out `ffde0f72…` stays
  (unique, sampled). **Purge plan** (dry-run only) for the quarantined `b255c3d8…` in
  `deploy/purge_plans/` — the owner runs `--execute`.
- Tests on a fixture: subtract = re-derive with the drop list (byte-identical selection, decisions,
  materialized text); held-out untouched; ambiguous / out-of-partition drops refused; control runs.

## Out of scope

- Changing the dedup gate. Re-deriving. Purging the Faz-2 sources (owner keeps them).

## Acceptance criteria

- [ ] New candidate: 6,602,551 − n documents, n = drop count (≈1,149), SHA recorded, two
      materializations identical, line-by-line equal to the old file minus the drops.
- [ ] Self-check: 0 normalized overlaps with unrelated sources.
- [ ] Registration and purge-plan dry run ready; after registration the dedup gate returns `unique`.

## Owner actions

- Run the purge `--execute` for the old quarantined candidate when handed over.

## Report

(not started)
