# Release Near-Duplicate Report

> **UNMAINTAINED (2026-07-07):** This English translation is no longer
> updated and may be out of date. The Turkish original is authoritative.
> See [docs/v1-autopsy.md](v1-autopsy.md) / [diyet_yol_haritasi.md](diyet_yol_haritasi.md).

Before freezing a release, Derlem scans its documents for approximate
similarity both within each source and across sources. The result is bound to
the frozen manifest and API snapshot under `gate_results.near_duplicate_report`.

## Contract

- Schema: `derlem.release-near-dedup-report.v1`
- Method: `normalized-word-3gram-simhash64-v1-hamming3-bands4x16-v1`
- Policy: report-only; detected pairs do not block freeze by themselves.
- Scope: every release purpose (`pretrain`, `instruction`, `preference`, `eval`,
  `holdout`, and `post_training`).
- Persistence: no raw text; only source SHA256 identity, line ordinal, relation,
  Hamming distance, and estimated similarity.

## Method

1. Plain text and common JSONL `text/content/body` fields become canonical document text.
2. For `derlem.canonical-sample.v1` conversation/preference records, messages,
   tools, and exportable semantic text replace the JSON envelope.
3. Documents with at least five tokens produce a word 3-gram 64-bit SimHash.
4. Each signature is split into four 16-bit bands in a temporary SQLite index.
5. A new document is compared with earlier documents sharing at least one band.
6. Every unique pair with Hamming distance at most 3 is reported.

Distributing three changed bits across four bands necessarily leaves at least
one band unchanged. Therefore, unless the candidate bound overflows, the band
index does not miss pairs whose Hamming distance is 3 or lower. The usual
limits of SimHash as a representation of textual similarity still apply.

## Fields

- `document_count`: non-empty documents scanned.
- `indexed_document_count`: documents signed because they contain at least five tokens.
- `potential_pair_count`: unique pairs within the Hamming threshold.
- `within_source_pair_count`: pairs within one source.
- `cross_source_pair_count`: pairs spanning different sources.
- `candidate_overflow_document_count`: documents exceeding the 5,000-candidate bound.
- `sample_pairs`: up to 20 sample pairs without raw text.

`status=reported` means the scan completed within its bounded contract.
`status=inconclusive` means at least one document exceeded the candidate bound,
so the report must not be treated as complete.

## Interpretation

Distance 0 means an identical SimHash signature; it does not by itself prove
byte or text equality. Positive pairs are never deleted automatically. A data
manager reviews sample pairs and source context before making a separate dedup
decision. The threshold is neither raised nor converted into a hard gate before
calibration on real Derlem corpora.
Use the [SimHash Calibration Report](similarity_calibration.en.md) for the
calibration method and long Gardas command.
