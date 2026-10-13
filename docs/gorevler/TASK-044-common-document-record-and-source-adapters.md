# TASK-044 — Common document record (`derlem.document.v1`), decision record, Parquet shards, source adapters

| Field | Value |
|---|---|
| Status | **READY** — 2026-10-13, owner decision "yes to all three"; architecture in [veri_mimarisi_2026_10.md](../veri_mimarisi_2026_10.md) |
| Kind | feature (data model) |
| Moratorium | owner approval given 2026-10-13 |
| Estimate | 3 day(s) |
| Depends on | — |
| Owner | (unassigned) — opus; backfill of Faz-2 sources: sonnet |

## Goal

Every document from every source lands in **one** record shape with its provenance and signals,
stored as Parquet shards in the content-addressed store; every verdict about a document is a
row in a decision record keyed by `doc_id`; a source is described to the importer by a small
adapter file, not by code.

## Why

Each dataset has different columns (FineWeb2-HQ: 13; mevzuat: law number, type, gazette date;
instruction sets: messages or instruction/output). Today's intake reads only `text`/`id` from
JSONL and nothing from parquet, so metadata is lost at the door — exactly how Faz-2 lost its
URLs and source labels. The owner asked the direct question on 2026-10-13: how do we integrate
many datasets, measure their quality automatically, and derive new datasets from them. This card
is the data-model half of the answer; TASK-032 is the import half, TASK-047 the quality half.

## Scope

- **Schema `derlem.document.v1`** (pyarrow schema, versioned, documented in `docs/`): `doc_id`
  (sha256 of raw text bytes), `text` (never rewritten; paragraph breaks kept), `source_id`,
  `source_ordinal`, `provenance` (dataset, revision, file, row, external_id, url, crawl_date,
  dump), `language` (declared, detected, score), `signals` (map of scorer → value, e.g.
  `fineweb2-hq-quality`, `minhash_cluster_size`), `rights` (license_id, evidence_ref, scope),
  `extra` (JSON string of unmapped columns).
- **Schema `derlem.decision.v1`**: `doc_id`, `decision_type` (pii, duplicate, near_duplicate,
  quality_rule, language, rights_scope, held_out, jury, human_review), `verdict`, `reason`,
  `judge` (rule version / model+rubric id / user id), `run_id`, `decided_at`.
- **Shard writer/reader** in the worker: Parquet, zstd, ~100 k documents per shard, content
  addressed like any object; reader yields documents with optional column projection.
- **Adapter**: yaml contract (dataset, revision, config, split, format, columns_read,
  columns_skipped, map, extra, document_boundary) + validator (missing mapped column → refuse;
  empty text → counted and reported, never silently dropped). Adapters for: FineWeb2-HQ
  (parquet), a JSONL/TSV source, and `derlem.canonical-sample.v1` instruction sets.
- **Selection-list derivation**: `clean_candidate` gains a mode that writes a selection list
  (doc_ids + decision snapshot) instead of a text copy; `derive` materialises text only at export.
  Existing text-copy mode stays for v1–v5 reproducibility.
- **Backfill**: the Faz-2 parent and v5 re-expressed as document shards (provenance =
  source id + ordinal; no URL — there never was one) and v5 as a selection list over the parent.
- **Export**: jsonl envelope carries `provenance`, `language`, `signals`, `rights` per record;
  txt unchanged.
- Tests: schema round trip; adapter validation (missing column, empty text, unknown column →
  `extra`); shard determinism (same input → same shard SHA); selection-list export equals
  text-copy export byte for byte on the 100k slice; control runs for each guard.

## Out of scope

- The HTTP import itself (TASK-032).
- Tokenized export (TASK-033), licence registry enforcement (TASK-030).
- Storing per-document decisions in PostgreSQL (they stay in Parquet; only summaries and the
  200 sampled documents live in the DB).

## Acceptance criteria

- [ ] A FineWeb2-HQ row group, a mevzuat JSONL record and a canonical instruction sample all
      land as valid `derlem.document.v1` / canonical records through adapters, with nothing
      silently dropped (unmapped columns in `extra`).
- [ ] v5 reproduced as parent + selection list: materialised export SHA equals the v5 object SHA
      `9dc5d6f7…`.
- [ ] Disk: FineWeb2-HQ text+metadata as zstd Parquet measured against raw bytes (ratio in the card).
- [ ] Control runs: each new guard removed → a test goes red.

## Owner actions

- None until the schema doc is shown; then a one-line "ok" on the field list.

## Report

(not started)
