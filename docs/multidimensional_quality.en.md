# Multidimensional Document Quality

**Active rubric:** `multidimensional-v1`

Derlem stores model-independent human quality labels rather than model- or
tokenizer-specific compatibility judgments. Every score uses `1` as the lowest
and `5` as the highest value.

## Dimensions

| Field | Meaning |
|---|---|
| `quality_score` | Overall training value |
| `language_quality_score` | Language correctness, naturalness, and readability |
| `coherence_score` | Internal meaning, context, and flow consistency |
| `information_density_score` | Density of useful information or task signal |
| `cleanliness_score` | Freedom from noise, malformed formatting, and meaningless residue |

The decision (`approved`, `rejected`, or `sensitive_review`) remains an
independent human label. Rejection and sensitive-review decisions require a
reason.

## Backward Compatibility

The migration never fabricates dimension scores for historical reviews:

- Existing records remain `overall-v1` with only `quality_score`.
- New records use `multidimensional-v1` and require all five scores.
- PostgreSQL rejects missing scores or values outside `1..5`.
- `document_reviews` remains append-only; rubric evidence cannot be edited.

## API

Single and bulk review payloads share the same quality fields:

```json
{
  "decision": "approved",
  "reason": null,
  "quality_score": 4,
  "language_quality_score": 5,
  "coherence_score": 4,
  "information_density_score": 3,
  "cleanliness_score": 5,
  "document_version": 1
}
```

Source summary endpoint:

```text
GET /api/v1/sources/{source_id}/document-quality-summary
```

The summary includes only `multidimensional-v1` reviews tied to current
versions in the active sample generation. Historical rubric records are
reported separately as `legacy_review_count` and never mixed into averages.

## Audit

Single and bulk review audit events include the rubric version, all five
scores, document version, and object SHA256 linkage. The evidence therefore
identifies the exact content version and sample generation that was scored.
