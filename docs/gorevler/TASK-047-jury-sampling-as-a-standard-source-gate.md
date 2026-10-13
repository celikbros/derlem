# TASK-047 — Jury sampling as a standard source gate: four quality numbers on every source card

| Field | Value |
|---|---|
| Status | **MEASURED** — 2026-10-13: jury run done on FineWeb2-HQ (junk 46.5 % [39.7–53.4], test-retest κ 0.91) and the parent corpus (48.0 % [41.2–54.9], κ 0.84); the manual 2026-10-04 number for FineWeb2-HQ (43 %) is inside the interval. Pending: `--apply-db` (owner runs it; blocked for the agent), owner anchor sheet (20 rows), budget approval + API key for in-job judging. Implemented 2026-10-13; requested 2026-10-13 |
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

- [x] FineWeb2-HQ re-measured through the sampler + rubric: **46.5 % [39.7–53.4]** (strict
      cop-only 44.0 %), manual 2026-10-04 value 43 % is inside the interval. v5 no longer exists
      (purged 2026-10-13, TASK-043); its parent, the Faz-2 corpus, measured **48.0 % [41.2–54.9]**
      (manual v5 value 53 % [43–63] on 100 docs overlaps). Test-retest κ 0.91 / 0.84 (binary 0.92 /
      0.86), in line with the 0.88–0.92 measured in TASK-040.
- [ ] Source card shows the four numbers; comparison view lists all pretrain sources — code and
      web done; the numbers reach the cards when the owner runs `score … --apply-db` (the agent's
      database write was blocked).
- [ ] Cost per 200-document run measured — not yet: the verdicts came from Claude Code sessions
      (8 sonnet readers, 2 passes, 4 × 100 rows), not from the in-job API path; the per-run and
      daily caps are implemented and tested, the API path waits for `ANTHROPIC_API_KEY` and the
      owner's budget approval.

## Owner actions

- Approve the model call budget per run and per day.

## Report

**2026-10-13 — jury run and scoring (Fable + 8 sonnet readers).** The mixed 400-row blind file
(`var/olcum-2026-10-13/task-047/karma-400/juri-kor.jsonl`, 200 FineWeb2-HQ + 200 parent corpus,
shuffled) was read in two independent passes by four sonnet sessions each (100 rows per session,
rubric `juri-siki-v1@50e993d6` only; answer key forbidden). Pass 1: 211 kalsın / 183 çöp / 6 emin
değilim; pass 2: 209 / 183 / 8. `jury split` → per-run verdict files, `jury score … --retest` →
`kalite-sayilari.json` + `kararlar.parquet` (400 decision rows per run: pass + retest).

| | FineWeb2-HQ `tur_Latn` (n=200 of 8,578,808) | Faz-2 parent (n=200 of 6,027,965) |
|---|---:|---:|
| Jury junk (çöp + emin değilim) | **46.5 %** [39.7–53.4] | **48.0 %** [41.2–54.9] |
| Strict (çöp only) | 44.0 % [37.3–50.9] | 47.5 % [40.7–54.4] |
| Test-retest κ (3-class / binary) | 0.91 / 0.92 | 0.84 / 0.86 |
| Rule drop (`tr-web-v3`) | 0.5 % (1/200) | 1.5 % (3/200) |
| PII hit | 0.5 % (1/200) | 3.5 % (7/200) |
| Top junk reasons | makine-çevirisi **42**, seo-ticari 25, diğer 6, liste-katalog 5, menü-spot 5 | diğer 23, seo-ticari 21, menü-spot 20, liste-katalog 17, forum-yığını 8, makine-çevirisi 3 |
| Rule × jury | rule kept 92 of the 93 jury-junk docs | rule kept 95 of 96; 2 of 3 rule drops were jury-keep |

Reading: the two corpora are equally dirty by this rubric, but for different reasons — FineWeb2-HQ's
junk is machine translation (42 of 93 junk verdicts, 21 % of all documents) and commercial pages;
the parent's is menu piles, lists, forums and commercial pages. `tr-web-v3` sees almost none of it on
either (TASK-046 is the answer). Decisions: `fineweb2-hq-200/kararlar.parquet` sha `dbd80df9…`,
`ana-korpus-200/kararlar.parquet` sha `78e7f5ef…`. Owner anchor: `fineweb2-hq-200/kurucu-20.md` (20
hard rows: undecided, pass-disagreement, rule-conflict). The numbers are **not yet on the cards**:
the agent's `--apply-db` was blocked; the owner runs the two `score … --apply-db` commands.

**Status: IMPLEMENTED — waiting for the jury run and the owner's budget approval.** Design and
usage: [docs/hakem_orneklemesi.md](../hakem_orneklemesi.md).

### What shipped

- `derlem_worker/jury.py` — uniform deterministic sampler (`jury-uniform-sha256-v1`: key =
  sha256(method, seed, doc_id) for shard sources, sha256(method, seed, line number) for txt/jsonl;
  bottom-n; exact-copy texts taken once), blind file (`no`, `metin`, `kesildi`, `char_count`
  only, whitespace collapsed, guard on write), answer key, budget ledger, judge call through the
  distillation provider registry (key from the worker env only, rubric as cached system prompt,
  no model fallback), `derlem.decision.v1` rows (`decision_type=jury`, reason `genre/junk_reason`,
  retest pass as `run_id/retest`), quality numbers, mixed blind file for one-session judging, CLI
  (`sample`, `judge`, `score --verdicts [--retest] [--apply-db]`, `anchor`, `anchor-score`,
  `mix`, `split`).
- `derlem_worker/jury_scoring.py` — Wilson, Cohen kappa (binary and 3-class), verdict file
  reader, anchor sheet (14–30 hard rows) writer/reader: `puanla.py` as a module.
- `rubrics/juri-siki-v1.md` — judge id `sonnet+juri-siki-v1@50e993d6`. **The exact prompt used on
  2026-10-04 was never stored in the repo**; v1 is reconstructed from the owner's 14-row sheet
  (question, "strict corpus" criterion) and the verdict files' vocabulary. Reproducing 43 % / 53 %
  is therefore also the test of the reconstruction.
- Job `jury_sample` (`jobs/jury_jobs.py`, routed in `worker.py`; budget/judge errors are
  permanent failures). Numbers land in `sources.source_metadata.quality_numbers` — no migration,
  no Go change (the API already returns `source_metadata`). Artifacts (blind file, key, run
  record, verdicts, decisions Parquet) go to the object store and `storage_objects`.
- Web: "Kalite sayıları" section on the source card (four numbers with Wilson intervals,
  measurement record) and a collapsible pretrain comparison table under the source list. Human
  reject rate is computed live from the source row (TASK-048 formula).

### Budget (owner to approve)

Per run 450 calls / 3.0 M tokens, per day 1,000 calls / 6.0 M tokens (env
`DERLEM_JURY_MAX_*`). Pre-flight refuses a plan that does not fit before any call; every call is
reserved in a durable daily ledger (`var/state/jury-budget/`, fsync + atomic replace) before it
is made; the per-run counter is keyed to the job, so a retry cannot pay twice. Estimated cost of
a 200-document run with retest (Sonnet 5.5, table `anthropic-2026-10-06`): **≈ $1.6–2.8**;
measured cost owed by the first real run.

### Real run without the judge (2026-10-13, seed 20261013, n = 200, direct call, no DB writes)

| Source | Population | Time | PII hit | Rule drop (`tr-web-v3`) | Blind SHA |
|---|---:|---:|---|---|---|
| FineWeb2-HQ `ba80dc1c` | 8,578,808 docs / 105 shards | 61 s | 1/200 = 0.5 % [0.1–2.8] | 1/200 = 0.5 % [0.1–2.8] | `627f520f…` |
| Main corpus `06ac330e` (13.57 GB txt) | 6,027,965 lines (3 oversized) | 26 s | 7/200 = 3.5 % [1.7–7.0] | 3/200 = 1.5 % [0.5–4.3] | `2891e26f…` |

Files: `var/olcum-2026-10-13/task-047/{fineweb2-hq-200,ana-korpus-200}/` and a 400-row mixed
file `karma-400/` (both sources in one blind file, as on 2026-10-04). A second sampling of the
main corpus produced the byte-identical blind file. v5 was purged (TASK-043), so the comparison
source is the main corpus — the parent v5 was derived from, i.e. **before** the quality filter;
the manual 2026-10-04 reading was v5 53 % / FineWeb2-HQ 43 % junk, so the main corpus is expected
to read at or above v5, not equal to it.

### Tests and control runs

`test_jury.py` 24 tests, `test_jury_job_integration.py` 4 tests (run against `derlem_ci_test`,
isolated schema): deterministic sampling (same seed → same doc_ids, independent of shard
layout), blind-file leak check, rubric SHA pinned, decision rows written, numbers on the card,
budget pre-flight and durable daily cap stop the job, retry cannot pay twice, missing key →
`judge_unavailable`. Control runs: 15 guards removed one at a time, 15 tests red, all green after
restore (`var/olcum-2026-10-13/task-047/kontrol.txt`, script `kontrol.py`).

### Open

- Jury verdicts for the two blind files (owner, separate session) → `score`, then acceptance
  criterion 1; owner anchor sheet via `anchor`.
- Owner approves the per-run/per-day caps; `ANTHROPIC_API_KEY` in the worker env enables the
  in-job judge; first real run records measured cost.
- No API endpoint/button to enqueue `jury_sample` yet (SQL in the doc); no Playwright test for
  the card section.
