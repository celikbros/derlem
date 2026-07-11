# Release Mixture Report

> **UNMAINTAINED (2026-07-07):** This English translation is no longer
> updated and may be out of date. The Turkish original is authoritative.
> See [docs/v1-autopsy.md](v1-autopsy.md) / [diyet_yol_haritasi.md](diyet_yol_haritasi.md).

**Active schema:** `derlem.mixture-report.v2`

The mixture report describes a frozen release's source composition without
selecting a model or tokenizer. It is built deterministically from release-source
snapshot metadata during freeze and stored under `gate_results.mixture_report`
in the frozen manifest.

`v2` adds a `quality` sample snapshot without changing the `v1` source
distribution. Previously frozen `v1` manifests remain immutable and readable.

## Dimensions

The report aggregates:

- `language`
- `domain`
- `source_type`
- `license`
- `rights_status`

Each value includes source count, byte size, and line/record count. Empty
metadata values are grouped as `unknown`.

## Share Unit

Shares use integer basis points instead of floating-point percentages:

- `10000 bps` = `100%`
- `2500 bps` = `25%`
- `1 bps` = `0.01%`

The calculation is deterministic. The UI prefers `byte_share_bps`; when byte
size is zero it falls back to `source_share_bps`.

## Totals

`totals` includes:

- `source_count`
- `byte_size`
- `line_count`
- `missing_byte_size_count`
- `missing_line_count`

Missing byte or line metadata is never hidden. It is counted explicitly and
contributes zero to weighted totals.

## Quality Sample

The active `quality` contract is `derlem.quality-mixture.v2`. Its unit is the current
document version in each release source's active sample generation. Only
documents carrying a `multidimensional-v1` review enter the quality distribution.

Five dimensions are reported independently:

- `overall`
- `language`
- `coherence`
- `information_density`
- `cleanliness`

Each dimension contains its score sum, integer `average_score_milli`, and three bands:

- `low`: 1-2
- `medium`: 3
- `high`: 4-5

Each band includes a document count and `document_share_bps`. The denominator is
the set of sampled documents with valid multidimensional scores.

Coverage evidence is explicit:

- `sample_document_count`
- `scored_document_count`
- `coverage_bps`
- `legacy_document_count`
- `missing_review_document_count`
- `coverage_status`: `complete`, `partial`, or `unavailable`

Ordered sample generations, document versions, object SHA256 values, review
identities, approval decisions, rubric, and scores are fixed without raw text
in `review_snapshot_sha256` using `ordered-sample-review-json-sha256-v2`. The freeze commit
transaction rebuilds the same snapshot under source locks and blocks on a mismatch.

`derlem.quality-mixture.v1` snapshots created during the local pilot remain
readable; they are never rewritten or upgraded in place.

## Boundary

The freeze mixture report describes source snapshots. Text, conversation, and
preference counts inside a JSONL export live in the export manifest's
`record_type_counts`. Token shares depend on the target tokenizer and are not
part of this report; exact tokenizer mixture analysis belongs downstream.

Quality bands do not claim that every corpus document was scored. They describe
the explicitly reported human-review sample. Any corpus-level inference must
consider the sampling method and coverage.

## Immutability

Sources are sorted by `source_id`, groups by value, and quality documents by
`source_id` plus `document_id`. The report contains no execution timestamp. The
same source metadata and sample/review snapshot produces the same mixture JSON
and manifest checksum chain.
