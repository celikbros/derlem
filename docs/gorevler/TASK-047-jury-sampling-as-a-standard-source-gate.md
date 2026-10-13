# TASK-047 — Jury sampling as a standard source gate: four quality numbers on every source card

| Field | Value |
|---|---|
| Status | **READY** — 2026-10-13, owner: "I need to check each dataset's quality automatically" |
| Kind | feature (quality pipeline) |
| Moratorium | owner approval given 2026-10-13 |
| Estimate | 2 day(s) |
| Depends on | TASK-044 (decision record) |
| Owner | (unassigned) — pipeline: opus; judging: sonnet |

## Why

The FineWeb2-HQ vs. v5 comparison (2026-10-04) was done by hand: sample, blind file, jury agent,
score script. It answered the owner's question in a day and it should be a button. Every new
dataset gets the same four numbers so sources can be compared and the owner only reads a small
anchor.

## Scope

- Worker job `jury_sample(source_id, n=200, seed)`: draw uniformly from the source's document
  shards (not risk-weighted — that is the human review's sampler), normalise whitespace so
  format does not leak the source, write a blind file, run the judge, write `jury` decision rows
  (`verdict`, `genre`, `junk_reason`, `judge="sonnet+siki-v1"`), store the rubric id and its
  SHA; a second judge pass on the same rows gives test-retest agreement.
- The rubric is a versioned file in the repo (the strict rubric measured in TASK-040: owner
  agreement kappa 0.49; test-retest 0.88–0.92). Changing it bumps the judge id.
- Judge calls go through the worker's existing model-call path (API key via env only; cost cap
  from TASK-034's design — a per-run cap and a durable daily counter are required before this
  runs unattended).
- Source card shows **four numbers**: PII hit rate, rule drop rate, jury junk rate (with
  interval), human reject rate (when reviewed). Comparison view across sources.
- Owner anchor: a 14–30 row "hard rows" sheet per source (the shelf's format), agreement
  reported as kappa against the jury.
- Tests: deterministic sampling, blind-file leak check (no source-identifying fields), rubric SHA
  pinning, decision rows written; control runs.

## Out of scope

- Replacing the human 200-sample review (the contract gate stays human).
- Using the jury to drop documents directly — jury rows inform rules and selection lists, they
  are not a filter by themselves until the owner says so.

## Acceptance criteria

- [ ] FineWeb2-HQ and v5 re-measured through the job reproduce the manual 2026-10-04 numbers
      within their intervals (43 % / 53 %).
- [ ] Source card shows the four numbers; comparison view lists all pretrain sources.
- [ ] Cost per 200-document run measured and written; daily cap enforced.

## Owner actions

- Approve the model call budget per run and per day.

## Report

(not started)
