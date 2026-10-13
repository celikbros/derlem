# TASK-043 — Retire-and-purge mechanism for superseded candidate objects

| Field | Value |
|---|---|
| Status | **DONE** — 2026-10-13 17:26 (owner ran `--execute`): 16 sources, 7 smoke releases, 20.3 M rows deleted; 1,608 objects / 47.48 GB quarantined outside the repo; store now 214 objects = 214 DB rows, no orphans; record in `deploy/purged_objects.jsonl` + `audit_events` (`sources_purged`). Opened DRAFT 2026-09-22 |
| Kind | ops (storage lifecycle) |
| Moratorium | allowed — housekeeping, no product surface |
| Estimate | 0.5 day (actual ~1 day: scope grew, see below) |
| Depends on | — |
| Owner | (unassigned) |

## Scope change (owner decision, 2026-10-13)

The design below ("retire" with a review row, rows stay, only bytes go) is **superseded**.
On 2026-10-13 the owner said *"her çöpü yok et, taze ve doğru başlangıç"* and explicitly
said yes to cleaning the database. New design:

- **Rows are deleted too**, not only bytes: the dead sources and trial releases go together
  with every dependent row (documents, versions, reviews — including the three early
  reviews on v1 —, sample generations, PII scans, fingerprints, lineage inputs, similarity
  rows, jobs, release sources/exports).
- The record is kept elsewhere: one `audit_events` row (action `sources_purged`, actor = the
  approver named in the plan), `row_change_events` (every deleted row is captured as a
  `DELETE` by the existing triggers), and the deletion log `deploy/purged_objects.jsonl`
  (replaces the planned `deploy/retired_objects.txt`).
- Object files are **moved to a quarantine directory**, not deleted.
- Scope widened from v1/v3/v4 + held-outs to: v1, v3, v4, **v5**, held-out v1–v3, nine
  June–July smoke sources and seven frozen trial `instruction` releases.
- A frozen release may be deleted, but only when the plan lists it explicitly with
  `status: frozen` (this replaces "never delete anything referenced by a frozen release").

The original text is kept below for history.

## Why

Three superseded clean candidates hold about 35 GB in the content-addressed store: v1
(`ebe29279…`, 12.85 GB), v3 (`83dcac77…`, 11.9 GB), v4 (`23bfcdcf…`, 11.26 GB), plus their
held-out objects. None is referenced by any frozen release (every frozen release today is
`instruction` purpose). The owner asked for them to be deleted (2026-09-21, "gereksiz olan her
şeyi sil"), and there is currently **no correct way to do it**:

- Deleting the objects leaves `sources` rows pointing at missing files, which the restore
  drill's chain check reports as data loss.
- `deploy/known_lost_objects.txt` is the wrong instrument: its own rule says a line there means
  *accepting permanent data loss after recovery is exhausted*. Using it for deliberate cleanup
  would make the drill meaningless — "every missing object is a problem" is its current
  behaviour and that is the point.
- Deleting the `sources` rows requires deleting sampled documents, sample generations and
  reviews first (RESTRICT foreign keys), which destroys audit history — including the owner's
  three early document reviews on v1.

The cheap win was already taken: hard-linking the six raw-source objects to their archive
copies recovered 13.47 GB on 2026-09-21. That trick does not apply here, because the
candidates exist only in the store.

## Scope

- A `retired` lifecycle for a source, recorded through the product's own review path (decision
  `rejected` with a reason), so retirement is audited rather than surgical.
- Object purge for retired sources: the file is removed and `deploy/retired_objects.txt`
  records sha256, source id, reason, and the manifest that reproduces the artifact.
- Chain check (`deploy/scripts/derlem_restore_drill.py`) treats a retired source's missing
  object as intentional, and still fails on any other missing object.
- A written rule in [backup_restore.md](../backup_restore.md): what may be retired (never an
  object referenced by a frozen release; never a raw source that is the only copy) and what
  retirement costs (re-derivation time, stated per candidate from its manifest).
- Then retire the v1, v3 and v4 candidates and their held-outs — about 35 GB. All are
  reproducible from their manifests; note honestly that only runs from `tr-web-v3` onward
  record the interpreter and zlib version, so v1/v2-era candidates are reproducible in
  principle but not byte-guaranteed on a different interpreter.

## Out of scope

- Deleting anything referenced by a frozen release.
- Deleting raw sources or the parent corpus.
- Changing the immutability rule for objects still in use.

## Acceptance criteria

- [x] Retirement appears in the audit trail — as an `audit_events` row (`sources_purged`,
      2026-10-13 17:26 Europe/Istanbul), not a review row (scope changed by the owner: rows are
      deleted, so a review row could not survive).
- [x] Drill passes with purged objects absent and still fails on an unlisted missing object
      (permanent test `test_sha_removed_from_the_list_turns_the_drill_red`).
- [x] v1, v3, v4 **and v5** candidates, three held-outs, nine smoke sources and seven smoke
      releases purged; 47,480,123,757 B moved to quarantine (disk frees when the owner deletes
      the folder). The backup mirror still carries the July objects (v1 + smoke); pruning the
      mirror is a separate owner decision (`backup_restore.md`, deliberate-deletion rule).

## Owner actions

- Confirm the three candidates are retirable. v1 carries three of the owner's own document
  reviews; those rows stay, only the bytes go.

## Report

**2026-10-13 17:26 — executed by the owner** (the agent-blocked run; the owner ran the exact
command). First run: 16 sources + 7 releases + 20,308,352 rows deleted in one transaction, 1,608
objects moved to `C:\CELIKBROS PROJECTS\derlem-cop-2026-10-13-nesneler`, `deploy/purged_objects.jsonl`
1,608 lines (sum 47,480,123,757 B), one `sources_purged` audit row. The first attempt had been
refused because the candidates' local manifests had been quarantined early (restored, then
re-quarantined after the run; `manifest_sha256` is in the log). A second `--execute` by the owner
was refused ("plan kaynağı veritabanında yok") and overwrote `execute.txt`, so the execute report
file shows the refusal; the log and the audit row are the record. After: 11 sources, 0 releases,
214 objects on disk = 214 `storage_objects` rows, 0 orphans, `var/storage` 26 GB (was 57 GB).

2026-10-13 — implemented (dry-run only at that point).

**What was built**

- `worker/src/derlem_worker/purge_sources.py` — `python -m derlem_worker.purge_sources --plan <json|yaml>`.
  `--dry-run` (default) computes everything in a `REPEATABLE READ READ ONLY` transaction and
  rolls back. `--execute --quarantine-dir D` applies the same computation in one transaction:
  explicit `DELETE … WHERE <plan set>` per table in FK order (no reliance on CASCADE), then
  `storage_objects`, then one `audit_events` row; files are moved with `os.replace` to
  `D/sha256/aa/bb/<sha>` before COMMIT (moved back if COMMIT fails); then
  `deploy/purged_objects.jsonl` is appended (sorted by sha256).
- Safety, all enforced before anything is written: every plan id must exist **and** match its
  name (releases: name, version and status; a frozen release must be written as `frozen`);
  `keep_sources` must exist and their objects can never enter the purge set; a generic,
  catalog-driven check refuses the plan if any row outside the plan references a row to be
  deleted (including CASCADE / SET NULL edges); open (queued/running) jobs of planned
  sources refuse it; a similarity calibration run is never split; an object is kept if any
  surviving row references it through a FK column, a job/source/release JSON, or a kept
  source's lineage text. The list of FK columns into `storage_objects` is checked against
  the live catalog, so a future migration that adds one stops the tool instead of being
  missed.
- Guard triggers (append-only / frozen protections) are disabled **by name, inside the
  transaction only, only on tables that lose rows**, re-enabled before COMMIT and verified.
  FK constraints and `row_change_events` capture stay on. Deleting `storage_objects` rows
  runs a FK check per row against `document_fingerprints.source_sha256`, which has no index
  (32 M rows → full scan per row); the tool builds a temporary index inside the transaction
  and drops it before COMMIT. **No migration was written or needed.**
- `deploy/scripts/derlem_restore_drill.py`: `load_purged()` reads `deploy/purged_objects.jsonl`;
  a listed object missing from a backup taken **before** its `purged_at` counts as
  intentional (`purged_objects_hit`); an unlisted missing object, a listed object still in a
  **post-purge** catalog, and an unlisted missing frozen manifest stay failures. A malformed
  log line stops the drill. Report gains `purged_objects_declared` / `purged_objects_hit`.
- Plan: `deploy/purge_plans/2026-10-13-taze-baslangic.json` (16 sources, 7 releases, 11
  `keep_sources`, manifest paths for the seven candidates/held-outs).
- Rule written in [backup_restore.md › Kasıtlı silme kuralı](../backup_restore.md).

**Live dry-run (2026-10-13, READ ONLY, rolled back)** — full output
`var/olcum-2026-10-13/task-043/dry-run.txt`. 0 problems. 16 sources, 7 frozen releases,
20,308,352 rows in total, of which 20,301,064 are `document_fingerprints`; 1,733 documents,
1,733 versions, 1,853 sample memberships, 10 document reviews, 92 jobs, 103 similarity
pairs; **1,608 objects / 47,480,123,757 B (47.48 GB) to move, all files present**. Two
objects stay because surviving rows reference them: `20ec9446…` (Derlem Ornek Katki Verisi,
shared with Browser Upload Smoke) and `9826d58e…` (the parent corpus, named in v1's metadata
and jobs). The 47.48 GB is larger than the card's original 35 GB because v5 (11.46 GB) is
now in scope.

**Tests** — `worker/tests/test_purge_sources_integration.py` (10, on an isolated schema built
from the real migrations in the `_test` database: 3 sources one of which shares its object,
1 frozen release) and `worker/tests/test_restore_drill_purged.py` (5). Dry-run changes
nothing (every table hashed before/after, triggers, files); execute deletes the plan, keeps
the shared object and the out-of-plan source intact, moves files, writes the log and the
audit row, leaves no trigger disabled and no temporary index, and the append-only guard on
`storage_objects` works again afterwards; unknown id / wrong name / unknown release /
unacknowledged frozen status → nothing changes; a reference from outside the plan (derived
child, release) → nothing changes. Control runs (guard removed → red → restored, files
byte-identical afterwards): K1 surviving-FK-reference check off → 1 red; K1b whole keep
decision off → 2 red (execute refused by the `keep_sources` assertion); K2 outside-reference
check off → 2 red; K3 name match off → 1 red; K4 drill purged pardon off → 2 red. The drill's
"remove one SHA from the list → red" control is a permanent test
(`test_sha_removed_from_the_list_turns_the_drill_red`).

**Execute (owner)** — stop API and worker first (the transaction takes table locks and
`lock_timeout` is 15 s), then from the repo root:

```powershell
.\.venv\Scripts\python.exe -m derlem_worker.purge_sources `
  --plan deploy\purge_plans\2026-10-13-taze-baslangic.json `
  --execute --quarantine-dir var\purge-quarantine\2026-10-13 `
  --report var\olcum-2026-10-13\task-043\execute.txt
```

Expected duration is not measured: deleting 20.3 M fingerprint rows plus building the
temporary index over the 32 M-row table should be minutes, not hours, but it has not been
run on live data.

**Open**

- Acceptance "freed bytes measured" waits for execute (bytes move to quarantine; disk is
  freed only when the owner deletes the quarantine directory — a separate decision).
- Acceptance "backup mirror no longer carries them": not done. The mirror is incremental
  and never deletes; pruning it is a separate decision. The drill change keeps a pre-purge
  backup green either way.
- Kept raw sources' normalized-dedup counters (e.g. `faz2_ham_tr_corpus` duplicate source
  count 3) were computed while the candidates' fingerprints existed and become stale; the
  purge does not touch kept rows by rule. Re-run normalized dedup on them if the numbers
  matter.
- `var/derived/*.manifest.json` is the only recipe for the purged candidates and is not in
  the backup.
- First acceptance criterion ("retirement appears as a review row") is replaced by the
  `sources_purged` audit row under the new design.
