# TASK-048 — Pretrain review gate: threshold instead of zero tolerance; rejected samples become a drop list; the measured rate goes on the release card

| Field | Value |
|---|---|
| Status | **IMPLEMENTED — threshold decided: 10 %** (owner, 2026-10-13: "yüzde 10 iyi ise bence de ok"); committed 3743403 + b5f0ba1; migration 000030 applies on the next API start (owner: "tamam"); the value is written per source with `PUT /api/v1/sources/{id}/pretrain-review-threshold` before that source's first review |
| Kind | fix (release gate) |
| Moratorium | allowed — the gate as written makes any web corpus unfreezable |
| Estimate | 1 day |
| Depends on | — |
| Owner | (unassigned) — opus |

## Why

`approvalGateReasons` (`internal/repository/reviews.go`) approves a source only when all 200
sampled documents are approved and the flagged count is 0. One rejection locks the source, and
an unapproved source cannot enter a release. That rule is right for contribution data (every
record is trained on individually) and wrong for a 4-million-document web corpus: the 200-sample
review does not clean the corpus, it **measures** it. Measured junk rates under the owner's strict
rubric are 39–53 % for both candidates; zero rejections in 200 is impossible, so the owner's two
review sessions would end at a closed gate.

## Scope

- For `content_purpose = pretrain`: the gate passes when `(rejected + sensitive) / sampled ≤
  threshold`; `document_sample_review_incomplete` stays for unreviewed samples. Contribution and
  instruction purposes keep zero tolerance.
- Rejected and sensitive sampled documents are written as a drop list (decision rows,
  `human_review`) and excluded from the frozen release; the measured rate, the threshold and the
  reviewer go into the release manifest and the model card line.
- Threshold is a release-level constant recorded in the manifest, set **before** the review
  starts (the shelf's rule: set the bar before measuring). Owner's current proposal: **10 %**.
- Web: the source card shows rate vs. threshold instead of "200/200".
- Tests: 10 % passes at 20/200, fails at 21/200; instruction sources unchanged; drop list
  applied at freeze (rehearsal on the 100k slice, TASK-018 harness); control runs.

## Out of scope

- Changing the human sampler or the 200 size.
- Jury verdicts as a gate input (TASK-047 reports them; they do not decide).

## Acceptance criteria

- [x] Threshold set by the owner (**10 %**, 2026-10-13); written per source before its first
      review (first target: the FineWeb2-HQ `tur_Latn` import, TASK-032).
- [ ] Freeze of a source with k ≤ threshold rejections succeeds and excludes exactly those k
      documents; manifest shows rate, threshold, reviewer.
- [x] Instruction/contribution behaviour byte-for-byte unchanged (existing tests green).

## Owner actions

- ~~Set the threshold~~ — done 2026-10-13: **10 %**. Start the API once so migration 000030 applies.

## Report

**2026-10-13 — implemented; the threshold value is the only open item.** No value is written
anywhere in code: with the column NULL every pretrain source keeps the old zero-tolerance rule.
The proposal (10 %) appears only in tests and here.

### Design: where the threshold lives

On the **source row**: `sources.pretrain_review_reject_threshold numeric(5,2)` (percent, 0–100,
two decimals, NULL = zero tolerance), migration `000030_pretrain_review_threshold.sql`.

- Why not the release: the gate that blocks today is **source approval**
  (`approvalGateReasons`), which runs before any release exists, and a release is created only
  from already-approved sources. A release-level value would be set after the measurement it is
  supposed to bound — the opposite of "set the bar before measuring".
- The lock is in two places: `Sources.SetPretrainReviewThreshold` (Go) refuses once any review
  trace exists (`reviewed_document_count > 0`, a `document_reviews` row, a source `reviews` row,
  or a review claim), and the DB trigger `sources_lock_pretrain_review_threshold` refuses the same
  UPDATE (also clearing to NULL). CHECK: only `content_purpose = 'pretrain'`, 0–100.
- "Release-level constant": the freeze recomputes and **blocks** when the threshold sources of one
  release carry different values (`review_threshold_not_release_constant`); the manifest records
  the single value at release level and per source.
- Setting it: `PUT /api/v1/sources/{id}/pretrain-review-threshold`
  `{"pretrain_review_reject_threshold": 10}` (or `null`), **admin only**, audited
  (`source.pretrain_review_threshold_set`). Route lives in its own file
  (`internal/httpapi/review_threshold_handlers.go`, `reviewThresholdRoutes`), registered by
  `server.go` with the same fail-closed role policy.

### Gate (one formula, three places)

`flagged_document_count` in Derlem already counts `rejected + sensitive_review`. For
`content_purpose = pretrain` with a threshold:

```
sampled > 0 AND reviewed = sampled AND (
  (approved = sampled AND flagged = 0)                                   -- old rule
  OR (approved + flagged = sampled AND flagged * 10000 <= threshold_bps * sampled))
```

Integer comparison (basis points), no float rounding. Go `documentSampleReviewReasons`
(`internal/repository/review_threshold.go`), DB `source_document_review_gate_passes` (000030),
worker `human_review.review_gate_passes`. Unreviewed samples → `document_sample_review_incomplete`
(unchanged); rate above threshold → new reason `review_reject_rate_above_threshold`, with
`GateError.Detail` = "measured reject rate 10.50% (21 rejected or flagged of 200 sampled) >
threshold 10.00%" (in `Error()`; the HTTP body of `POST /sources/{id}/reviews` still carries the
reason code only — its handler is in `source_handlers.go`, which was off-limits during TASK-032).
`contribution` / `instruction` / `eval` / `holdout`, and pretrain without a threshold, follow the
old branch byte for byte.

Zero-tolerance was also enforced in five more places; each now calls the same predicate:
`Releases.Create` review-evidence CTE (rejected/flagged campaign reviews count as coverage only
in threshold mode), `Releases.QueueFreeze` eligibility, DB `validate_release_source_contract_snapshot`,
`validate_release_source_snapshot_fresh` and `validate_release_review_evidence` (000030 copies the
three 000024 bodies verbatim and changes only those predicates — diff checked), and the worker
(`_release_source_is_current`, commit-time eligibility SQL, `validate_release_contract_evidence`).

### Freeze: drop list, decisions, manifest

`worker/src/derlem_worker/human_review.py`, wired into `_freeze_release_with_verified_objects`:

- For every threshold pretrain source the freeze reads the sampled documents' current reviews,
  checks every sample is reviewed, rejected+flagged equals the source counter and the rate ≤
  threshold, then finds each rejected/flagged sample's text in the verified source snapshot at its
  `source_ordinal` (`doc_id = sha256(document text)`, the same text the export hashes). Missing
  text, an empty or oversized line → freeze blocked.
- A second pass counts **every** occurrence of those texts; all are dropped
  (`extra_occurrence_count` in the manifest says how many were duplicates).
- Decision rows `derlem.decision.v1`: `decision_type=human_review`, verdict `reject`
  (`rejected`) / `flag` (`sensitive_review`), `judge` = reviewer user id, `run_id` = release id,
  `decided_at` = freeze start, `source_ordinal` null (the verdict belongs to the text),
  `reason = document_review=<decision>;sample_ordinal=<n>`. One Parquet file per source, stored
  in the CAS (`application/vnd.apache.parquet`, `storage_objects` row in the freeze transaction).
- Rejected/flagged samples leave the quality mixture (the mixture describes what ships).
  The commit-time recheck blocks if the drop set changed (`human_review_changed`).
- Manifest (`derlem.release-manifest.v2`, additive keys only when a threshold source exists — an
  instruction manifest is byte-identical): per source `sources[].human_review` and release-level
  `human_review` = `{sampled, approved, rejected, flagged, rate_bps, rate_pct, threshold_bps,
  threshold_pct, reviewer_ids, excluded_doc_id_count, excluded_line_count,
  extra_occurrence_count, excluded_doc_ids_sha256, decisions{sha256, byte_size, row_count},
  model_card_line}`; `gate_results.document_review_gate` gains `mode, rate_pct, threshold_pct,
  excluded_*`. `excluded_doc_ids_sha256` = SHA-256 of the sorted unique doc_ids, one per line
  with LF (`sorted-unique-doc-id-lf-sha256-v1`).
- **Model card line.** There is no model card template in `docs/` yet (TASK-037 datasheet is
  future work); the line is generated into the manifest (`human_review.model_card_line`):
  "Human sample review: 18 rejected + 2 flagged of 200 sampled documents = 10.00% (threshold
  10.00%, set before review; 1 reviewer(s)); 20 reviewed texts dropped from the release (21 lines,
  every occurrence)."
- Export (txt/jsonl) of a pretrain release loads the frozen manifest and each decision file from
  the CAS (SHA-verified), checks the doc_id list against `excluded_doc_ids_sha256`, skips those
  documents, and blocks unless the skipped count equals `excluded_line_count`. Export manifest:
  per source `human_review_excluded_record_count` and `human_review_decisions_sha256` (only for
  sources with a drop list).

### Web

`web/lib/review-gate.ts` (same formula). Source list "next step": threshold pretrain sources show
"Ret oranı %x / eşik %y" instead of "Örnek 200/200" (danger above threshold, "Onaylı · …" after
approval); the inspector's approval checklist and "Örnek inceleme" line use the same gate, so the
approve button opens at rate ≤ threshold. Sources without a threshold: unchanged.

### Tests

| Suite | Before | After |
|---|---|---|
| Go `go test ./...` (`DERLEM_SKIP_DB_TESTS=1`) | 322 pass, 39 skip | 365 pass, 41 skip (this task: 34 pass + 1 DB skip; the other new skip is TASK-032's) |
| Python `pytest worker/tests` | 442 pass, 20 skip | 492 pass, 20 skip (this task: `test_human_review.py` 29 pass; the rest is TASK-032 work in the same tree) |

Go: 10 % passes at 20/200, fails at 21/200; 10.50 % passes and 10.49 % fails at 21/200; NULL →
old reason; instruction/contribution/eval/holdout ignore a threshold; unreviewed sample stays
closed; detail text carries 10.50 % and 10.00 %; threshold change reasons (locked after review,
pretrain only, 0–100, two decimals); route admin-only and not duplicated; existing
`TestApprovalGateReasons` untouched and green. DB integration
`TestPretrainReviewThresholdLocksOnceReviewStarts` (lock in API and trigger, CHECK constraint,
SQL gate table) is written but **skipped here** (no `_test` database in this session).
Python: gate table; k rejected texts dropped exactly, every occurrence (4 lines for 3 texts);
decision file schema/verdicts/judge/run_id and determinism; tampered doc-id SHA rejected;
txt and jsonl outputs equal the independently filtered full export, byte for byte; empty drop
list = unchanged bytes; manifest unchanged without `human_review`; freeze evidence accepts
rejected samples only under a threshold.

SQL: 000030 and every changed query (Go and worker) parse with libpg_query (pglast 8.5,
`parse_sql` + `parse_plpgsql` for the three plpgsql bodies). Not executed against PostgreSQL.

**Control runs** (`var/olcum-2026-10-13/task-048/control_runs.py`, output `control_out.txt`):
each guard removed → target test red → restored → green: G1 rate check, G2 pretrain-only, G3
review-started lock, G4 reviewed=sampled, P1 export exclusion, P2 every-occurrence pass, P3
decision file ↔ manifest SHA, P4 rejected evidence only under threshold, P5 drop-list rate check,
P6 worker gate formula, P7 quality-mixture filter — 11/11 OK.

**Rehearsal on the 100k slice (DB-less)** (`var/olcum-2026-10-13/task-048/rehearsal_100k.py`,
`rehearsal_out.json`): `dilim-100k_v3.txt` (`51df1672…668b54`), 200 samples at ordinals
1, 496, 991, …; ordinals 1, 496, 991 counted as rejected, threshold 10 % → rate 1.50 %, 3 doc_ids,
3 lines, 0 extra occurrences; drop list 2.2 s.

| Export | Full | With drop list | Independent filter of full |
|---|---|---|---|
| txt | `51df1672…668b54`, 99,007 records (= TASK-018) | `c8b35714…bd450a`, 99,004 records, 2,067 bytes fewer | `c8b35714…bd450a` ✓ |
| jsonl | `59135401…f572a`, 99,007 records | `4b8d084e…eaf82`, 99,004 records | `4b8d084e…eaf82` ✓ |

(The jsonl full SHA differs from TASK-018's `b7c0dd2e…` because TASK-044 added the null
provenance/language/rights/signals fields.) The DB freeze → export path itself (TASK-018 harness)
was not run: it needs the `_test` database.

### Not done / follow-ups

- Migration 000030 is **not applied**. The API applies pending migrations at startup, so the next
  API start applies it; owner approval first.
- `POST /sources/{id}/reviews` 422 body: add `GateError.Detail` to the message once TASK-032 has
  released `source_handlers.go` (one line).
- Run `TestPretrainReviewThresholdLocksOnceReviewStarts` and the TASK-018 rehearsal on the
  `_test` database.
