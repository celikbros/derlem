# TASK-048 — Pretrain review gate: threshold instead of zero tolerance; rejected samples become a drop list; the measured rate goes on the release card

| Field | Value |
|---|---|
| Status | **DRAFT — owner decision needed** (threshold value) — 2026-10-13 |
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

- [ ] Threshold set by the owner and written before any pretrain review starts.
- [ ] Freeze of a source with k ≤ threshold rejections succeeds and excludes exactly those k
      documents; manifest shows rate, threshold, reviewer.
- [ ] Instruction/contribution behaviour byte-for-byte unchanged (existing tests green).

## Owner actions

- **Set the threshold** (proposal 10 %). Without it the next candidate cannot be reviewed.

## Report

(not started)
