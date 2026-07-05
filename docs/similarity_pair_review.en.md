# Similarity Pair Review

**Data model:** `000016_similarity_pair_reviews.sql`
**Importer:** `calibration-closest-pair-materialization-v1`

This workflow moves the closest natural document pairs from a
`derlem.similarity-calibration.v1` report into human review. A calibration
report does not change a threshold by itself; independent labels are required
for a purpose-specific policy decision.

## Immutability Boundary

- The calibration JSON is stored as a content-addressed object.
- Calibration runs and pair identities reject update, delete, and truncate.
- Full text is not stored in PostgreSQL. The database keeps the object SHA256,
  a preview of at most 500 characters, source identity, and source ordinal.
- Human decisions append to `similarity_pair_reviews`; they never mutate pairs.
- A reviewer can label a pair only once.
- Import revalidates source SHA256 values, ordinal documents, SimHash
  eligibility, and every reported Hamming distance.
- Reimporting the same report is idempotent.

## Labels

| Label | Meaning |
|---|---|
| `exact_duplicate` | Meaning and expression are effectively identical. |
| `near_duplicate` | The same information with a small edit or surface change. |
| `related` | Related topic or pattern, but a distinct training example. |
| `different` | Separate content. |
| `uncertain` | Domain knowledge is required; a reason is mandatory. |

Two or more independent reviews with one label produce `consensus`. Diverging
labels produce `disagreement`. One review counts as reviewed but not consensus.

Server-side blind review protects independence. A review-eligible user cannot
see the pair's review count, labels, reasons, consensus, or disagreement until
submitting their own label. Evidence becomes visible after submission. No label
is selected by default, and the UI advances to the next pending pair after a
successful decision.

## Gardas Import - Completed

Idempotent command that materializes the closest 100 pairs:

```powershell
cd "C:\CELIKBROS PROJECTS\derlem"
.\.venv\Scripts\python.exe -m derlem_worker.similarity_review_import `
  --report .\var\reports\similarity_calibration_pretrain_ebe29279.json
```

The command completed successfully on 2026-07-01. It materialized 178 unique
documents referenced by 100 pairs and streamed through 5,918,983 source lines
to reach the largest required ordinal. Result:

- `run_id`: `769836b7-f121-4d9d-b6cb-42f3f6ab490f`
- report SHA256: `365e67fa5bed3da7d670e53946542f5b6c77dab47fab4f7bcc45a75dadf0b3e1`
- pairs / unique documents: `100 / 178`
- initial review state: `0 / 100`

Running the same command again returns `already_imported` without duplicating
evidence. The run is listed as `pretrain` in the web application's
**Benzerlik** view.

## Authorization and API

- Only `admin`, `moderator`, and `expert_reviewer` can read runs, pairs, and
  full text or append decisions.
- Existing decisions are blinded for an eligible user until their own review.
- Other roles cannot access similarity endpoints.
- `GET /api/v1/similarity-calibrations`
- `GET /api/v1/similarity-calibrations/{id}/pairs`
- `GET /api/v1/similarity-pairs/{id}`
- `POST /api/v1/similarity-pairs/{id}/reviews`

Each decision emits `similarity.pair_reviewed`; each import emits
`similarity.calibration_imported` in the audit log.

## Smoke Evidence

The `Bulk Review Smoke 1782584401697` instruction calibration was imported
with three pairs. Admin and moderator independently labeled the first pair
`near_duplicate`. The API reported one reviewed pair, two independent reviews,
one consensus, and zero disagreements. Desktop and Pixel 7 Playwright flows
passed with no horizontal overflow or browser-console errors.
