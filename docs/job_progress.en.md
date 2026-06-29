# Background Job Progress Contract

Derlem runs long operations through the PostgreSQL `background_jobs` queue.
Transient progress is stored in the running job's `result.progress` object
instead of a separate table.

## Covered Jobs

- `ingest_local_file` and `ingest_staged_file`
- `scan_pii`
- `index_document_fingerprints`
- `sample_documents` and `resample_documents`
- `export_release`

## Shape

```json
{
  "phase": "fingerprinting",
  "progress": {
    "input_bytes_processed": 5368709120,
    "input_bytes_total": 12884901888,
    "lines_read": 2480000,
    "documents_scanned": 2478000,
    "indexed_documents": 2394000,
    "skipped_oversized": 3,
    "skipped_too_short": 83997
  }
}
```

Fields may expand by job type. Byte and line counters form the common contract.
Fingerprinting adds indexed/skipped document counts, sampling adds eligible and
risk-candidate counts, and PII scanning adds the aggregate finding count.

## Phases

| Phase | Meaning |
|---|---|
| `validating_checkpoint` | Byte-validate a previous ingest checkpoint against the source prefix |
| `ingesting` | Validate and copy into immutable storage |
| `scanning_pii` | Scan basic PII patterns |
| `fingerprinting` | Build normalized document fingerprints |
| `matching_duplicates` | Compare generated fingerprints |
| `sampling` | Select representative and risk-quota samples |
| `publishing_samples` | Atomically publish the selected generation |
| `building` | Build a release export artifact |

## Persistence Policy

- Workers persist progress approximately every 64 MiB of input.
- Before ingest progress is persisted, the checkpoint is flushed and `fsync`ed;
  a retry resumes from the verified byte offset bound to the same job UUID.
- A separate PostgreSQL connection commits progress outside the long corpus
  transaction, making it visible while work continues.
- A retry clears stale `result` and `last_error` values.
- Successful completion replaces transient progress with the canonical result.
- The Jobs view refreshes silently every two seconds while active jobs exist.

Progress is operational visibility, not release evidence. Durable evidence is
the final job result, audit event, manifest, and object SHA256 chain.
