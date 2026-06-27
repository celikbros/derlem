# Derlem Risk-Based Sampling Contract

**Algorithm:** `risk-stratified-sha256-v1`

**Status:** Active for new `sample_documents` jobs

## Purpose

The sampler helps human reviewers see both representative documents and likely
problem cases without loading full corpus text into PostgreSQL. It assigns
review priority, not a final quality decision.

## Selection Strategy

The default sample size is 200 and the source is scanned once with bounded line
reads:

1. Up to half of the sample budget is reserved for high-risk documents.
2. Every eligible document also enters a deterministic SHA256-seeded reservoir.
3. After risk candidates are selected, remaining slots are filled from the
   representative reservoir without duplicate ordinals.
4. The final sample is sorted by source ordinal.

When few risky documents exist, the risk quota is not filled artificially;
representative samples use the remaining capacity.

## Risk Rules

| Reason | Condition | Score |
| --- | --- | ---: |
| `short_text` | Fewer than 24 characters | 1 |
| `long_text` | More than 4,000 characters | 2 |
| `control_characters` | Non-whitespace control or format character | 3 |
| `high_symbol_ratio` | At least 40 characters and over 35% symbols | 2 |
| `repeated_character_run` | Same character repeated at least 8 times | 2 |
| `low_lexical_diversity` | At least 20 words and under 25% unique | 2 |
| `identifier_pattern` | Email, TR IBAN shape, or 11-digit candidate | 3 |
| `malformed_json` | Starts with `{` but cannot be parsed | 2 |
| `missing_text_field` | JSON object lacks `text/content/body` | 2 |

The total score is capped at 10. `identifier_pattern` is review priority, not a
PII verdict; the separate PII gate still applies checksum and scanner rules.

## Persisted Metadata

Each selected document stores `sampling_method`, `risk_score`, and
`risk_reasons`. Job results contain only document counts and reason counters;
matched text, email addresses, numbers, and identifiers are never written to
job results or audit details.

Editing a document clears its old risk score because it no longer describes the
new text. The immutable review context retains the risk snapshot seen when the
review decision was made.

## Determinism

The same immutable source SHA256, algorithm version, sample size, and document
order produce the same selection. Risk ties use
`SHA256(source_sha256:ordinal)` and never depend on execution time or global
random state.

## Existing Sources

The migration preserves old samples with `risk_score=0` and an empty reason
list. It does not silently replace reviewed data. The existing 200 Gardas clean
candidate reservoir samples will be replaced through a separate audited,
controlled resampling operation before review begins.

## Limits

- These heuristics are not a language model and do not decide semantic quality.
- Cross-source domain and source-type mixture belongs at release level.
- Near-duplicate and evaluation decontamination remain separate gates.
- A risk score never automatically approves or rejects a document.
