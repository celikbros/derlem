# Release Mixture Report

**Schema:** `derlem.mixture-report.v1`

The mixture report describes a frozen release's source composition without
selecting a model or tokenizer. It is built deterministically from release-source
snapshot metadata during freeze and stored under `gate_results.mixture_report`
in the frozen manifest.

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

## Boundary

The freeze mixture report describes source snapshots. Text, conversation, and
preference counts inside a JSONL export live in the export manifest's
`record_type_counts`. Token shares depend on the target tokenizer and are not
part of this report; exact tokenizer mixture analysis belongs downstream.

## Immutability

Sources are sorted by `source_id`, and groups by value. The report contains no
execution timestamp. The same frozen source snapshot produces the same mixture
JSON and manifest checksum chain.
