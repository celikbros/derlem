# TASK-049 — Clean candidate from document shards: FineWeb2-HQ → first `tr-web-v4` pretrain candidate

| Field | Value |
|---|---|
| Status | **READY** — 2026-10-13 (owner: "yes to all", FineWeb2-HQ imported, TASK-046 measured) |
| Kind | feature (derivation path) |
| Moratorium | owner approval given 2026-10-13 (delivery path for the first real candidate) |
| Estimate | 2 day(s) |
| Depends on | TASK-032 (import, DONE), TASK-044 (selection list, DONE), TASK-046 (`tr-web-v4`, MEASURED), TASK-048 (threshold, DONE) |
| Owner | (unassigned) — opus |

## Why

The FineWeb2-HQ import (`ba80dc1c…`, 8,578,808 documents, 105 `derlem.document.v1` shards) is a
raw source: PII-flagged (phone 108,729, e-mail 59,701, card 4,612, IBAN 326, TCKN 115), quarantined
by design. `clean_candidate` only reads line sources (txt/jsonl), so the raw source cannot become a
candidate, cannot be reviewed and cannot be frozen. The jury says 47 % junk before rules and 39 %
after `tr-web-v4`; the rules exist, the path from shards to a candidate does not.

## Scope

- `clean_candidate` accepts an **import-manifest source** (`derlem.import-manifest.v1` → shards via
  `import_manifest.py`): iterates documents in shard order (`source_ordinal` = shard index + row),
  reuses the same decision code path as the line reader: PII (the existing per-document PII
  decision; findings → `pii` decision, reject), `tr-web-v4` quality rules (`url` from
  `provenance.url`), exact duplicate by `doc_id`, near-duplicate SimHash (Hamming ≤ 3, same policy
  as v5), held-out rule `afacan-held-out-v1`, oversized/empty; writes the **selection list**
  (`derlem.selection.v1`) + decision rows (`derlem.decision.v1`, judge `tr-web-v4@<sha>`) + manifest
  with `quality_judge`, source manifest SHA, policy ids, interpreter/zlib (as v5's manifest does).
- `selection.materialize` works from shards (text per `doc_id`/ordinal), producing the candidate
  **text object** (one document per line, `\n` inside documents escaped exactly as the Faz-2 line
  format does — check `releases.py`/`canonical_exports.md` for the line contract) and the held-out
  object; both deterministic (same input → same SHA, two runs).
- Registration: the candidate and held-out are registered the way v5 was (derived source with
  `derived_from_source_id`, `lineage_ref` = derivation manifest, `content_purpose` pretrain /
  holdout, rights inherited from the parent's note) — follow the v5 registration script/notes
  (`docs/temiz_aday_v3.md`, `var/olcum-2026-09-21/v5/` if still present, `hak_kanit_paketi`); the
  existing gates (PII, dedup, sampling, 200-sample review with the 10 % threshold) then run on the
  candidate through the normal path. **Registration writes the DB: the agent prepares the command,
  the owner or Fable runs it.**
- Measurement on a 200 k-document slice first (time, drop rates per decision type, SHA stability),
  then the full-run command + estimate; the **full run is launched only after the owner picks the
  MT target pair (A: 5 % cap / B: 7.5 % cap, TASK-046)** — the thresholds are a policy constant.
- Tests: shard reader = line reader on the same documents (byte-identical selection + decisions for
  a fixture with PII/dup/near-dup/oversized/empty/MT/commercial cases); determinism; materialize
  from shards = text copy; control runs for each guard.

## Out of scope

- Freezing a `document_shards` source directly (the candidate is a text object; the existing
  freeze/export path applies). Tokenized export (TASK-033). Jury in-job judging (TASK-047 API path).

## Acceptance criteria

- [ ] `clean_candidate --selection-list` runs on the FineWeb2-HQ import manifest; decisions per
      type counted; manifest reproducible (two runs → same selection-list and decisions SHA).
- [ ] Materialized candidate text object + held-out object, SHAs recorded; a second materialize
      gives the same SHAs.
- [ ] 200 k slice measured (time per 100 k docs, drop rates); full-run estimate written.
- [ ] Registration command prepared; after the owner runs it the candidate shows on the source
      list with gates running.

## Owner actions

- Pick the MT target pair (A/B, TASK-046) before the full run.
- Run the registration command when it is handed over (database write).

## Report

(not started)
