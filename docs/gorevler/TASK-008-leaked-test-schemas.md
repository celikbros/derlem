# TASK-008 — Integration tests leaked schemas into the working database

| Field | Value |
|---|---|
| Status | READY |
| Kind | fix (test infrastructure + one-time cleanup) |
| Moratorium | allowed |
| Estimate | 0.5 day |
| Owner | (unassigned) |
| Verified against code | 2026-09-12 — schema names, timestamps and cleanup code read in the owner's session |

## Goal

1. Remove the two leaked test schemas from the **working** database.
2. Make the leak impossible to repeat: tests refuse non-`_test` databases, and an
   interrupted run cannot leave a schema behind unnoticed.

## Why

Two schemas sit in the production database `derlem` today:

```
derlem_claim_test_1787335360053578500          created 2026-08-21 18:02:40 UTC
derlem_claim_resume_test_1787335642024510000   created 2026-08-21 18:07:22 UTC
```

They are full copies of the migrated schema (every table, every trigger). Harmless in
themselves, but:

- They mean someone ran the integration suite with `DERLEM_TEST_DATABASE_URL` pointed
  at the **working database**. Nothing stopped it. The same run could have dropped
  `pgcrypto` from `public` (the race fixed in 2026-09) or, with a different bug,
  touched real tables.
- They are the class of leftover that caused the pgcrypto race: an isolated schema
  that changes `search_path`, then disappears with `CASCADE`.
- They make every schema-agnostic query ambiguous. Measured 2026-09-12: asking
  `information_schema.columns` for `release_exports` returned every column **three
  times**, one per schema.

## Current state (measured)

Both schemas come from Go tests in `internal/repository/`:

- `document_claims_integration_test.go:34` — `fmt.Sprintf("derlem_claim_test_%d", time.Now().UnixNano())`
- `document_claim_resume_integration_test.go:219` — `"derlem_claim_resume_test_%d"`

Cleanup is registered and correct in the happy path (`document_claims_integration_test.go:47-53`):

```go
t.Cleanup(func() {
    cleanupCtx, cleanupCancel := context.WithTimeout(context.Background(), 30*time.Second)
    defer cleanupCancel()
    if _, err := adminPool.Exec(cleanupCtx, "DROP SCHEMA "+schemaIdentifier+" CASCADE"); err != nil {
        t.Errorf("drop test schema: %v", err)
    }
})
```

It does not run when the process is killed (Ctrl+C, IDE stop, `go test -timeout`
kill), and it can time out: the claims test drives **1,000 concurrent callers**
through a 16-connection pool (`:60-63`); a `DROP SCHEMA … CASCADE` that must wait for
those connections to release locks can exceed 30 s, log `t.Errorf`, and leave the
schema. Either path matches the two timestamps: 4 min 42 s apart, both tests, one
session.

There is **no guard** on the database name anywhere in the test helpers.

## Scope

1. **One-time cleanup**, done by hand, verified first:

   ```sql
   -- must return ONLY the two names above; anything else → stop and report
   SELECT nspname FROM pg_namespace WHERE nspname LIKE 'derlem_%_test_%';
   -- confirm nothing outside the schema references them (expected: 0)
   SELECT count(*) FROM pg_depend d JOIN pg_namespace n ON n.oid = d.refobjid
    WHERE n.nspname LIKE 'derlem_%_test_%' AND d.deptype = 'n';
   DROP SCHEMA "derlem_claim_test_1787335360053578500" CASCADE;
   DROP SCHEMA "derlem_claim_resume_test_1787335642024510000" CASCADE;
   ```
   Take a `pg_dump --schema-only` of the two schemas first and attach the file names
   to the Report — cheap insurance.

2. **Database-name guard** (shared with TASK-007 item 5 — implement once, in the
   shared helper): every DB-backed test parses `DERLEM_TEST_DATABASE_URL` and
   `t.Fatal`s unless the database name ends in `_test`. The worker's `conftest.py`
   does the same with `pytest.exit`.

3. **Leak visibility.** A sweeper at the start of each DB-backed test package
   (`TestMain`): list schemas matching `derlem_%_test_%` older than one hour, log them
   loudly, and drop them. Because of (2) this only ever runs inside a `_test` database,
   so dropping is safe. This turns "leaked forever" into "leaked until the next run".

4. **Cleanup robustness.** Raise the drop timeout to 2 minutes and, before the DROP,
   terminate the isolated pool's own backends
   (`SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE application_name = …`)
   — set `application_name` on the isolated pool config to the schema name so this is
   precise. Keep `t.Errorf` on failure; the sweeper in (3) is the backstop.

## Out of scope

- Any change to what the tests test.
- The worker's own schema naming (`derlem_worker_test_<uuid>`, already isolated and
  dropped in a `finally`); only the sweeper pattern applies there, via `conftest.py`.

## Files

- shared Go test helper (same one TASK-007 introduces — coordinate; whoever lands
  first creates it)
- `internal/repository/document_claims_integration_test.go`,
  `document_claim_resume_integration_test.go` (application_name + timeout)
- `worker/tests/conftest.py`
- manual SQL, recorded in the Report

## Acceptance criteria

- [ ] `SELECT nspname FROM pg_namespace WHERE nspname LIKE 'derlem_%_test_%'` on the
      working database returns **0 rows**.
- [ ] `information_schema.columns` for `release_exports` returns each column **once**.
- [ ] Pointing `DERLEM_TEST_DATABASE_URL` at `…/derlem` (no `_test`) makes
      `go test ./internal/repository/` fail immediately with a message naming the rule;
      same for `pytest worker/tests`.
- [ ] Create a schema `derlem_claim_test_1` by hand in `derlem_ci_test`, run the suite:
      it is logged and dropped by the sweeper.
- [ ] Kill the claims test mid-run (`-timeout 5s`), rerun: the leaked schema is gone
      after the rerun.

## Verification commands

```powershell
# working DB must be clean
psql "$env:DATABASE_URL" -c "SELECT nspname FROM pg_namespace WHERE nspname LIKE 'derlem_%_test_%';"
# guard
$env:DERLEM_TEST_DATABASE_URL = "postgres://.../derlem?sslmode=disable"; go test ./internal/repository/ -run Claims
```

## Risks / traps

- **Do not run the cleanup SQL with a wildcard.** Name the two schemas explicitly; the
  `LIKE` query is for verification only.
- The sweeper must never run outside a `_test` database — it depends on the guard in
  (2) being in place first. Implement (2) before (3).
- `pg_terminate_backend` needs the test role to own those backends or be superuser;
  check the role used in `DERLEM_TEST_DATABASE_URL` and fall back to the longer timeout
  if it is not permitted.

## Report

_(to be filled on completion)_
