# SimHash Calibration Report

**Schema:** `derlem.similarity-calibration.v1`

This tool produces SimHash threshold evidence for a content purpose and real
corpus sample without automatically changing the release policy. JSON and
Markdown reports never contain raw document text.

## Measurements

- A deterministic bottom-k document sample from content-addressed sources.
- Sample token-length distribution: `5-7`, `8-15`, `16-31`, and `32+`.
- Hamming distance for four controlled token perturbations:
  - drop the middle token,
  - replace the middle token,
  - swap the two middle tokens,
  - drop the middle 10 percent span.
- Distance distribution for every natural pair in the corpus sample.
- Source SHA256 and ordinal identities for the closest natural pairs, without text.
- Synthetic recall and corpus-pair rates for thresholds `0..10`.
- Thresholds for which the 4x16 release LSH index has a complete candidate guarantee when the candidate bound does not overflow.

The sampler selects the K smallest SHA256 priorities derived from
`source_sha256 + ordinal`. Source order cannot change the result, and memory is
bounded by sample size. The default and maximum sample sizes are 1,000 and
2,000 documents.

## Decision Boundary

The report deliberately returns `human_labels_required`. Synthetic perturbation
recall and natural corpus-pair rates are not labeled precision. A purpose-specific
threshold is not activated until humans label the natural `closest_pairs` as
same, near, or different.

The active release policy remains:

- `policy_id`: `universal-report-only-h3-4x16-v1`
- threshold: Hamming `3`
- mode: `report_only`
- purpose status: `pending_labeled_calibration`

## Small Smoke Result

All three documents in the `Bulk Review Smoke` instruction source contain six
tokens. Controlled-variant recall was `0%` at both Hamming thresholds 3 and 10.
This tiny result is insufficient for a policy change, but it exposes instability
of 64-bit SimHash on short instruction documents.

## Long Gardas Scan

This command streams all 5,922,891 documents in the
`gardash_faz2_tr_dedup_20260621_clean_candidate_20260625` source. It may take a
long time and should be run in the user's terminal without assistant-side polling:

```powershell
cd "C:\CELIK- DERLEM"
.\.venv\Scripts\python.exe -m derlem_worker.similarity_calibration `
  --source-id f63352dd-fdd1-4e4b-a8d2-b167b3c856cf `
  --sample-size 1000 `
  --threshold-max 10 `
  --closest-pair-limit 100 `
  --output-dir .\var\reports `
  --force
```

Progress is written to stderr every 100,000 documents. On completion, stdout
returns the JSON and Markdown paths.

## Gardas Result - 2026-06-30

- Source object: `ebe292793d87ec067076bbb86f39801e6ed5fae18761dfcfa3506c4503c0d989`
- JSON report SHA256: `365e67fa5bed3da7d670e53946542f5b6c77dab47fab4f7bcc45a75dadf0b3e1`
- Scanned / eligible documents: `5,922,891 / 5,900,610`
- Sampled documents / natural pairs / synthetic variants: `1,000 / 499,500 / 3,998`
- Token min / p50 / p90 / max: `5 / 132 / 603 / 6,329`
- Hamming 3 synthetic recall: `32.69%`; natural pairs: `0`
- Hamming 10 synthetic recall: `80.22%`; natural pairs: `0`
- Closest natural distance: `15`; median natural-pair distance: `32`
- There were `5` natural pairs at distance 15 and `165` at distance 18 or lower.

The length buckets show that one universal threshold is not appropriate.
Hamming 3 recall for `5-7`, `8-15`, `16-31`, and `32+` tokens was `0%`, `0%`,
`0.26%`, and `40.71%`; Hamming 10 recall was `0%`, `3.26%`, `39.32%`, and
`94.89%`. The 4x16 LSH index is candidate-complete only through Hamming 3, so
this report does not activate threshold 10. Short documents need a non-SimHash
method, and the closest natural pairs still require human labels.

See [Similarity Pair Review](similarity_pair_review.en.md) for the import command
and human-review workflow.

## Local File Experiment

A direct file requires both its content SHA256 and purpose. The CLI hashes the
file and stops when the supplied SHA256 does not match:

```powershell
.\.venv\Scripts\python.exe -m derlem_worker.similarity_calibration `
  --input-path .\data\sample.jsonl `
  --source-sha256 <64_HEX_SHA256> `
  --content-purpose instruction `
  --sample-size 500
```
