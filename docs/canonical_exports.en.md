# Derlem Canonical Export Contract

**Version:** `derlem.export-manifest.v1`

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

Each line contains one document:

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

## TXT Output

The TXT artifact writes one UTF-8 line per document. Embedded `CRLF`, `CR`, and
`LF` characters are converted to a single space. TXT is a convenience format
for simple pretraining consumers; consumers that need lineage use JSONL.

## Determinism

The checksum contract is enforced by these rules:

1. Sources are sorted by `source_id`.
2. Documents retain their stable source-line order.
3. A document id hashes `source_sha256`, source ordinal, and text SHA256.
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

The Jobs view displays this progress. A Gardas clean-candidate export should be
started only after checking available disk space because it is a large disk
read/write operation.

## Permissions

- Start an export: `admin`, `data_manager`
- Download artifact and manifest: `admin`, `data_manager`, `consumer_team`
- Other roles can inspect release metadata but cannot download artifacts

## Next Extension

The current contract covers text corpora. A later canonical schema version will
add model-independent `messages`, `tools`, and `chosen/rejected` structures for
instruction, tool-call, preference, and conversation data. Target-model Jinja
or chat templates will remain outside the Derlem database.
