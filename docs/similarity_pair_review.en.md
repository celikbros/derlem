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

## Gardas Import

After generating the calibration report, materialize the closest 100 pairs:

```powershell
cd "C:\CELIK- DERLEM"
.\.venv\Scripts\python.exe -m derlem_worker.similarity_review_import `
  --report .\var\reports\similarity_calibration_pretrain_ebe29279.json
```

The command stores only referenced documents, but it must stream through the
source to reach their ordinals. It can take time for Gardas and reports progress
every 100,000 lines. The resulting `run_id` appears automatically in the web
application's **Benzerlik** view.

## Authorization and API

- Every authenticated user can read runs, pairs, and reviews.
- `admin`, `moderator`, and `expert_reviewer` can append decisions.
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
