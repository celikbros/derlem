# Derlem Canonical Export Contract

> **UNMAINTAINED (2026-07-07):** This English translation is no longer
> updated and may be out of date. The Turkish original is authoritative.
> See [docs/v1-autopsy.md](v1-autopsy.md) / [diyet_yol_haritasi.md](diyet_yol_haritasi.md).

**Version:** `derlem.export-manifest.v2`

**Status:** Working MVP

**Formats:** JSONL, TXT

## Purpose

Derlem does not store data in a GLM, DeepSeek, Kimi, or other model-specific
chat template. A frozen release is converted into a model-independent canonical
artifact. Tokenizer and LLM teams adapt that artifact through their own training
pipeline.

This boundary means that a newly released model does not require Derlem data to
be reviewed again. Only the consumer-side adapter changes.

## JSONL Record

Each line contains one text, conversation, or preference record. Plain text
keeps the backward-compatible document shape:

```json
{
  "id": "stable-document-id",
  "metadata": {
    "content_purpose": "pretrain",
    "document_sha256": "...",
    "domain": "general",
    "external_id": null,
    "language": "tr",
    "license": "internal",
    "source_id": "...",
    "source_ordinal": 42,
    "source_sha256": "..."
  },
  "text": "Document text"
}
```

Keys are serialized in sorted compact JSON. UTF-8 characters are preserved and
every record ends with `LF`.

Structured records use a `derlem.canonical-export-record.v1` envelope that
carries the source `derlem.canonical-sample.v1` sample unchanged. `messages`,
`tools`, tool calls, multimodal content parts, and preference `chosen/rejected`
branches are not rendered through a model template. Source SHA256 and line
position are attached under the envelope's `lineage` field.

## TXT Output

The TXT artifact writes one UTF-8 line per document. Embedded `CRLF`, `CR`, and
`LF` characters are converted to a single space. TXT is a convenience format
for simple pretraining consumers; consumers that need lineage use JSONL.
Conversation and preference records hard-fail a TXT export.

## Determinism

The checksum contract is enforced by these rules:

1. Sources are sorted by `source_id`.
2. Documents retain their stable source-line order.
3. A record id hashes `source_sha256`, source ordinal, and exported canonical
   payload SHA256.
4. JSON keys are sorted and serialized without variable whitespace.
5. The export manifest uses the frozen release timestamp and release-manifest
   checksum, never the current execution time.

## Storage and Audit

The artifact and export manifest are published to the content-addressed object
store. Once a `release_exports` row becomes `ready`, a PostgreSQL trigger blocks
updates and deletes. Append-only audit records:

- `release.export_queued`
- `release.export_ready`
- `release.export_failed`

## API

```text
POST /api/v1/releases/{release_id}/exports
GET  /api/v1/releases/{release_id}/exports/{format}/artifact
GET  /api/v1/releases/{release_id}/exports/{format}/manifest
```

POST body:

```json
{"format":"jsonl"}
```

Only a frozen release can be exported. An existing ready or active export for
the same release and format returns `409 release_export_conflict`.

## Large-Corpus Behavior

The worker streams records to a temporary file instead of buffering the corpus
in memory. Every 50,000 records it persists these counters in the job result:

- `input_bytes_processed`
- `records_written`
- `sources_completed`
- `source_count`
- `output_bytes_written`
- `estimated_tokens`

The Jobs view displays this progress. A Gardas clean-candidate export should be
started only after checking available disk space because it is a large disk
read/write operation.

## Token Estimate

The manifest `token_estimate` is not tokenizer output. Without selecting a
model or tokenizer, Derlem aggregates semantic Unicode code points, UTF-8 bytes,
and whitespace units. `unicode-codepoint-range-v1` reports:

- lower bound: `max(whitespace_units, ceil(codepoints / 6))`
- point estimate: `max(lower_bound, ceil(codepoints / 4))`
- upper bound: `max(point_estimate, ceil(codepoints / 2))`

This deliberately broad range is for capacity planning. The training team runs
the exact count with its target tokenizer downstream; Derlem records do not need
new approval.

## Permissions

- Start an export: `admin`, `data_manager`
- Download artifact and manifest: `admin`, `data_manager`, `consumer_team`
- Release metadata: `admin`, `data_manager`, `consumer_team`; consumers see
  frozen releases only
- Other roles cannot access release metadata or artifacts

## Canonical Structured Record

The active schema is `schemas/conversation_sample.schema.json`, with ingest-ready
examples in `data_samples/example_canonical_conversations.jsonl` and
`data_samples/example_canonical_preferences.jsonl`. Model names,
`model_compatibility`, chat templates, special tokens, and rendered prompts are
not accepted by this schema. They are downstream artifacts owned by the LLM or
tokenizer team.
The structured export envelope is independently validated by
`schemas/canonical_export_record.schema.json`.
