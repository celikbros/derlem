# Controlled Document Resampling

> **UNMAINTAINED (2026-07-07):** This English translation is no longer
> updated and may be out of date. The Turkish original is authoritative.
> See [docs/v1-autopsy.md](v1-autopsy.md) / [diyet_yol_haritasi.md](diyet_yol_haritasi.md).

**Job type:** `resample_documents`

**Permission:** `admin` only

## Why Generations?

A sample list is evidence used by a quality decision. Deleting the old 200
documents and replacing them would make the reviewed input ambiguous. Derlem
therefore stores every sample list as a numbered generation.

- `document_sample_generations` records source SHA256, method, status, count,
  job, and time.
- `document_sample_memberships` records every selected document, ordinal,
  object SHA256, and risk snapshot for that generation.
- `documents.is_active` identifies the generation currently shown to reviewers.

## Hard Gates

Resampling is blocked when the source is not sampled, a resample is active, an
active sample was edited, any sample review exists, source approval has begun,
or the active sample list is missing. Both the API and worker publish
transaction verify these rules.

## Two-Phase Publication

The old generation remains active during the potentially long corpus scan.
After all new sample objects are ready, one transaction:

1. Marks the previous generation `superseded`.
2. Deactivates previous document rows.
3. Inserts or safely reactivates the new selection.
4. Writes the new generation and every membership snapshot.
5. Updates source generation, method, count, and status.

If the transaction fails, the old generation remains unchanged. After all job
retries fail, the source returns from `resampling` to `sampled`.

## API

```text
POST /api/v1/sources/{source_id}/documents/resample
GET  /api/v1/sources/{source_id}/document-sample-generations
```

The queue response is `202` with a job id. Progress is read from
`GET /jobs?source_id=...` and the source sampling status.

## Gardas Operation

The Gardas clean candidate is roughly 13 GB, so resampling is a long disk scan.
After queueing, progress is followed in worker logs and the Jobs view instead
of continuous interactive polling. On success, generation 1 is archived,
generation 2 is active, and the method is `risk-stratified-sha256-v1`.
