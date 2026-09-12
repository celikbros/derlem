# TASK-008 — Integration tests leaked schemas into the working database

| Field | Value |
|---|---|
| Status | **DONE** — 2026-09-13, implemented by Claude at the owner's request, including the one-time cleanup of the working database (owner's go-ahead, backup first) |
| Kind | fix (test infrastructure + one-time cleanup) |
| Moratorium | allowed |
| Estimate | 0.5 day |
| Owner | (unassigned) |
| Verified against code | 2026-09-13 — schema names, timestamps, cleanup order and the full `CASCADE` blast radius measured in the owner's session |

## Goal

1. Remove the two leaked test schemas from the **working** database.
2. Make the leak impossible to repeat unnoticed: tests refuse non-`_test` databases,
   and schemas left behind by an interrupted run are swept on the next run.

## Why

Two schemas sat in the production database `derlem` (removed 2026-09-13, see Report):

```
derlem_claim_test_1787335360053578500          created 2026-08-21 18:02:40 UTC
derlem_claim_resume_test_1787335642024510000   created 2026-08-21 18:07:22 UTC
```

They were full copies of the migrated schema (every table, every trigger). Harmless in
themselves, but:

- They meant someone ran the integration suite with `DERLEM_TEST_DATABASE_URL` pointed
  at the **working database**. Nothing stopped it. The same run could have dropped
  `pgcrypto` from `public` (the race fixed in 2026-09) or, with a different bug,
  touched real tables.
- They are the class of leftover that caused the pgcrypto race: an isolated schema
  that changes `search_path`, then disappears with `CASCADE`.
- They made every schema-agnostic query ambiguous. Measured 2026-09-12: asking
  `information_schema.columns` for `release_exports` returned every column **three
  times**, one per schema.

## Current state (measured)

Both schemas came from Go tests in `internal/repository/`:

- `document_claims_integration_test.go` — `fmt.Sprintf("derlem_claim_test_%d", time.Now().UnixNano())`
- `document_claim_resume_integration_test.go` — `"derlem_claim_resume_test_%d"`

Cleanup is registered and correct in the happy path:

```go
t.Cleanup(func() {
    cleanupCtx, cleanupCancel := context.WithTimeout(context.Background(), 30*time.Second)
    defer cleanupCancel()
    if _, err := adminPool.Exec(cleanupCtx, "DROP SCHEMA "+schemaIdentifier+" CASCADE"); err != nil {
        t.Errorf("drop test schema: %v", err)
    }
})
```

**Corrected 2026-09-13.** The first version of this card said the drop "can time out"
because it must wait for the 1,000 concurrent callers' locks. That is contradicted by
the code: `t.Cleanup` runs last-in-first-out, and the isolated pool's `pool.Close` is
registered *after* the drop, so it runs *before* it — the pool's connections are gone
when `DROP SCHEMA` executes. The realistic leak path is the process being killed
(Ctrl+C, IDE stop, `go test -timeout`), for example while `pgxpool.Close` waits for
connections still held by running callers; the cleanup then never runs at all. Nothing
inside the cleanup can fix that — a sweep on the *next* run can.

There was no guard on the database name anywhere in the test helpers — fixed by TASK-007.

## Scope

1. **One-time cleanup of the working database** — done 2026-09-13 with the owner's
   go-ahead, after measuring the blast radius and taking a backup (Report).
2. ~~Database-name guard~~ — **landed in TASK-007**
   (`internal/testdb.RequireScratchDatabase`, `worker/tests/conftest.py`).
3. **Sweeper** — implemented, see Report.
4. ~~Cleanup robustness: `pg_terminate_backend` + 2-minute drop timeout~~ — **dropped.**
   It targeted the lock-wait hypothesis corrected above; the kill path is covered by (3).

## Out of scope

- Any change to what the tests test.

## Files

- `internal/testdb/testdb.go`, `internal/testdb/testdb_test.go`
- `internal/database/testmain_test.go`, `internal/httpapi/testmain_test.go`,
  `internal/repository/testmain_test.go` (new)
- `worker/tests/conftest.py`, `worker/tests/test_schema_sweeper_integration.py` (new)
- `worker/tests/test_queue_integration.py`, `test_lineage_dedup_integration.py`,
  `test_pii_gate_integration.py` (schema names now carry their creation time)

## Acceptance criteria

- [x] `SELECT nspname FROM pg_namespace WHERE nspname LIKE 'derlem%test%'` on the working
      database returns **0 rows** — measured after the cleanup: `0`.
- [x] `information_schema.columns` for `release_exports` returns each column once —
      measured after the cleanup: 17 rows for 17 distinct columns.
- [x] Pointing `DERLEM_TEST_DATABASE_URL` at a non-`_test` database is refused before
      connecting — TASK-007.
- [x] An old test schema is swept and a fresh one is kept — Go and worker tests.
- [x] A test schema holding an extension is never dropped — Go test.
- [x] A killed run's leftover is gone after the next run — by design of the sweep; shown
      with a deliberately old-named schema, which is the state a killed run leaves
      (see gaps).

## Verification commands

```powershell
.\scripts\test.ps1
```

## Report

**Done 2026-09-13.**

**Design — each rule chosen so the sweeper cannot hurt a live run or the database:**

- **Age comes from the name, never from a guess.** Go schemas were already
  `derlem_<label>_test_<unixnano>`. Worker schemas were `…_test_<uuid>` (no time); they
  now come from an `isolated_schema_name` fixture:
  `derlem_<label>_test_<time_ns>_<8 hex>`. `SchemaCreatedAt` parses only names matching
  `^derlem_[a-z0-9_]+_test_([0-9]{19})(?:_[0-9a-f]{8})?$`. Old uuid-only names never
  match — their age cannot be proven, so they are never swept.
- **Only provably old schemas are dropped**: default threshold one hour. The full Go
  suite takes ~70 s and the worker suite ~20 s, so a concurrent run's live schema is
  never touched.
- **A schema holding an extension is never dropped** — it is reported instead.
  `DROP SCHEMA … CASCADE` removes the extension from the whole database; that is exactly
  how the 2026-09 pgcrypto race broke parallel migrations.
- **Scratch databases only**: `SweepLeakedSchemas` calls `RequireScratchDatabase` first;
  the worker sweeper raises before connecting.
- **Where it runs**: a `TestMain` in each Go package with database-backed tests
  (`database`, `httpapi`, `repository`) calls `testdb.SweepBeforeTests()`; the worker
  runs the same sweep in `pytest_sessionstart`. A sweep failure prints to stderr and never
  fails the run — housekeeping must not become a new source of red.

**Concurrency — designed, then measured.** `go test ./...` runs packages in parallel and
every `TestMain` sweeps with the one-hour threshold. The sweeper tests' "old" schema is
therefore named 11 minutes old and swept with a 10-minute threshold: old enough for the
test, too young for any concurrent sweeper. The Go and worker suites were then run
**simultaneously** against the same scratch database to exercise exactly that — both green.

**Verification run (owner's machine, 2026-09-13):**

- `go build ./...`, `go vet ./...` clean
- `internal/testdb`: 6 PASS, including
  `TestSchemaCreatedAtParsesOnlyTimestampedTestSchemas` (the real leaked name parses to
  `2026-08-21T18:02:40Z`; `public`, `pg_catalog`, an old uuid-style worker name, a short
  number and an injection-looking suffix are all rejected),
  `TestSweepLeakedSchemasDropsOnlyProvablyOldSchemas`, and
  `TestSweepLeakedSchemasNeverDropsASchemaHoldingAnExtension` (citext installed into an
  11-minute-old schema: reported as skipped, schema still exists)
- full `go test -count=1 ./...`: every package `ok`, with the three `TestMain` sweeps
- worker: the sweeper test plus the three re-named fixtures → 16 passed; full suite with
  the database → **243 passed, 1 skipped** (pre-existing Windows symlink case)
- CI for the preceding commit `4360e6c`: all three jobs green
- scratch database `derlem_ci_test` held 0 leaked schemas before and after

**Working-database cleanup — blast radius measured before anything was dropped.**
`DROP SCHEMA … CASCADE` also drops everything that depends on the dropped objects, so
every `pg_depend` row referencing an object in the two schemas was resolved with
`pg_identify_object` (read-only) and classified:

| Dependent objects not named inside the two schemas | Count | What they are |
|---|---|---|
| schema-less, identity names a leaked schema | 1704 | triggers and column defaults **on leaked tables** (`pg_identify_object` reports no schema for these kinds) |
| `pg_toast` | 76 | the leaked tables' own TOAST tables (`deptype = i`); owners outside the leaked schemas: **0** |
| **truly outside** | **0** | — |

Also measured: extensions inside the schemas **0** (`pgcrypto` lives in `public`);
foreign keys from outside **0**. Size: 158 relations each, 3.2 MB and 2.0 MB.

This replaced the card's original verification query (`pg_depend … deptype = 'n'`),
which looked at a subset only. Two broader first attempts reported 76 and then 1780
"outside" dependents — both artefacts of how TOAST tables, triggers and defaults are
catalogued, resolved by the classification above. No action was taken on the strength
of those intermediate numbers.

**Cleanup performed 2026-09-13, with the owner's go-ahead.** One chained command, so the
drop could not run unless every check before it held:

1. target database confirmed as `derlem`
2. schema-only backup `var/backups/leaked_test_schemas_2026-09-13.sql` — 561,958 bytes,
   exactly one `CREATE SCHEMA` line per schema, 80 `CREATE TABLE` lines (local file,
   outside git)
3. `DROP SCHEMA "<exact name>" CASCADE` for each schema. PostgreSQL reported 74 cascaded
   objects per schema, and every one it listed was a table or function inside the
   schema being dropped — consistent with the measured blast radius (triggers, defaults
   and TOAST tables go with their tables and are not listed separately)
4. afterwards: test schemas remaining **0**; `release_exports` **17 column rows for 17
   distinct columns** (previously tripled); `pgcrypto` still in `public`; `public.sources`
   still 12 rows

The same session also applied migration `000027` (TASK-005) to the working database.

The commands, for the record (PowerShell, repo root):

```powershell
$db = ((Get-Content .env | Select-String '^DATABASE_URL=').Line -split '=', 2)[1]
$bin = "C:\Program Files\PostgreSQL\18\bin"
New-Item -ItemType Directory -Force var\backups | Out-Null

# 1. schema-only copy first (cheap insurance)
& "$bin\pg_dump.exe" --schema-only `
  -n derlem_claim_test_1787335360053578500 `
  -n derlem_claim_resume_test_1787335642024510000 `
  -f var\backups\leaked_test_schemas_2026-09-13.sql $db

# 2. drop by exact name -- never with a wildcard
& "$bin\psql.exe" $db -v ON_ERROR_STOP=1 `
  -c 'DROP SCHEMA "derlem_claim_test_1787335360053578500" CASCADE;' `
  -c 'DROP SCHEMA "derlem_claim_resume_test_1787335642024510000" CASCADE;'

# 3. verify: expect 0 rows
& "$bin\psql.exe" $db -c "SELECT nspname FROM pg_namespace WHERE nspname LIKE 'derlem%test%';"
```

**Honest gaps:**

- The kill path was not reproduced with an actual kill (`go test -timeout` mid-run). The
  sweeper's handling is demonstrated with a deliberately old-named schema — the same
  state a killed run leaves behind.
- The extension guard is covered by its test's opposite-outcome assertions (reported as
  skipped *and* still present) but was not mutation-controlled.
- The worker sweeper has no extension test of its own; it shares the rule and query shape
  with the Go sweeper, which has one.
- Worker schemas created before 2026-09-13 (uuid-only names) can never be swept
  automatically; the scratch database currently holds none.