# Resumable Large-File Ingest

> **UNMAINTAINED (2026-07-07):** This English translation is no longer
> updated and may be out of date. The Turkish original is authoritative.
> See [docs/v1-autopsy.md](v1-autopsy.md) / [diyet_yol_haritasi.md](diyet_yol_haritasi.md).

Derlem retains completed copy work for `ingest_local_file` and
`ingest_staged_file` jobs in a checkpoint bound to the job UUID. If a worker
stops or the job hits a retryable error, the same file is not written again from
byte zero.

## Safety Contract

- Checkpoint paths never come from user input. They are derived only from a
  validated job UUID as `var/storage/.tmp/ingest-<job-id>.part`.
- Before resuming, Derlem compares the entire checkpoint byte for byte with the
  source prefix of the same length.
- A checkpoint larger than the source, or one with a mismatching prefix, is
  deleted and the copy safely restarts from zero.
- Ingest fails if source size, modification time, or file identity changes while
  the operation is running; mixed content is never published.
- SHA256, UTF-8 validation, and line-count state are rebuilt by reading the
  checkpoint prefix. Hash objects and untrusted intermediate state are not
  serialized.
- A checkpoint already hard-linked to a content-addressed object is detached
  before appending bytes. An existing SHA256 object cannot be changed in place.

## Lifecycle

1. The first attempt writes 1 MiB blocks into the job checkpoint.
2. Approximately every 64 MiB, the worker flushes and `fsync`s the checkpoint,
   then persists progress in PostgreSQL.
3. Retryable failures retain the checkpoint.
4. A later attempt publishes `validating_checkpoint`, then `ingesting` progress.
5. The checkpoint is deleted after the object is published and the source
   transaction commits successfully.
6. A terminal failure removes the checkpoint. Browser staging files are removed
   only after successful ingest.

## Result and Audit Fields

The successful job result and `source.ingested` audit event include:

- `resumed_from_bytes`: verified byte offset where new copying began,
- `checkpoint_revalidated_bytes`: bytes revalidated during this attempt,
- `checkpoint_reset`: whether an invalid checkpoint forced a clean restart.

These are operational fields, not content identity. The canonical identity is
always the SHA256 of the published object.
