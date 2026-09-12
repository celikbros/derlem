# TASK-005 — PII scanner reports "clear" on languages it cannot inspect

| Field | Value |
|---|---|
| Status | **DONE** — 2026-09-13 (implemented by Claude at the owner's request). **Deploy step pending:** `go run ./cmd/migrate` on the working database (see Report) |
| Kind | fix |
| Moratorium | allowed (an unearned "clear" stamp is the 0e5c7c5 failure class; this closes it) |
| Estimate | 1–2 days |
| Owner | (unassigned) |
| Verified against code | 2026-09-12 — `pii.py:15-56` and `release_jobs.py:680` read by the owner's session |

## Goal

A source whose language the PII scanner does not support must come out of `scan_pii`
as **`not_evaluated`**, not `clear` — and `not_evaluated` must block freeze exactly
as `flagged` does.

## Why

The scanner is Turkish-only and says so in its own version string, but its verdict
does not. For a Kurdish, Arabic, English or French source every counter is zero, the
status is `clear`, the freeze gate accepts it, and the frozen manifest carries a
"PII clean" claim that was never earned. The output is **byte-identical** to a
genuinely clean Turkish scan; the only trace is `scanner_version`, and nothing gates on
it.

The project's stated direction is multilingual (translation pairs, TR↔KU, TR↔AR).
The first non-Turkish source to be frozen will carry a false clean stamp into an
immutable manifest. Fix it before that happens, independent of any task-type decision.

## Current state (measured)

`worker/src/derlem_worker/pii.py`:

```python
TCKN_PATTERN  = r"(?<!\d)\d{11}(?!\d)"                 # Turkish national id
IBAN_PATTERN  = r"...TR(?:[ ]?\d){24}..."               # Turkish IBAN only
PHONE_PATTERN = r"...(?:\+?90...)?0?5\d{2}..."          # Turkish mobile only
CARD_PATTERN  = ...                                      # language-agnostic
PII_KEYS = ("tckn", "iban", "email", "phone", "payment_card")

class PIIReport:
    scanner_version: str
    findings: dict[str, int]
    @property
    def status(self) -> str:
        return "flagged" if any(self.findings.values()) else "clear"   # :28-29

class PIIScanner:
    version = "basic-tr-v1"                                             # :33
```

`worker/src/derlem_worker/jobs/release_jobs.py:680` — the freeze gate:

```sql
source.pii_status <> 'clear' OR ...
```

So the gate already blocks anything that is not literally `clear`. A new status value
therefore blocks freeze **without touching the gate** — provided the DB accepts it.

## Scope

1. `PIIReport` gains an explicit `status` derived from three inputs: findings, the
   scanner's supported-language set, and the source language. Rule:
   `flagged` if any finding; else `clear` if language ∈ supported; else
   `not_evaluated`. Supported set for `basic-tr-v1` is `{"tr"}` — declare it on the
   scanner class, next to `version`.
2. The `scan_pii` job passes the source language to the scanner. Find where the job
   loads the source (`worker/src/derlem_worker/jobs/gate_jobs.py`) and confirm
   `sources.language` is available there; if the job only has the file path, extend the
   SELECT.
3. Check the DB constraint on `sources.pii_status` (grep the migrations for
   `pii_status`). If it is a CHECK list, a **new migration `000027_…`** adds
   `not_evaluated`. Existing migrations are checksum-locked (`migrate.go:67`) — never
   edit one.
4. The **language-agnostic** patterns (`email`, `payment_card`) still run on every
   source and can still produce `flagged`. `not_evaluated` means "the language-specific
   detectors did not apply", not "nothing was looked at". Record that distinction in the
   scanner's docstring.
5. Surface it: wherever the web shows `pii_status` (source inspector / sources list),
   `not_evaluated` needs a label — Turkish copy: "Değerlendirilmedi (dil desteklenmiyor)".
   Do not colour it green.
6. Tests: a `ku`/`ar`/`en` fixture yields `not_evaluated`; a `tr` fixture with no
   findings yields `clear`; an `en` fixture containing an e-mail yields `flagged`.
   A freeze attempt on a `not_evaluated` source is refused — extend the existing freeze
   gate test rather than writing a new harness.

## Out of scope

- Per-language PII detectors (Kurdish/Arabic phone or id formats). That is real work
  and a separate card; this card only stops the false stamp.
- Re-scanning already-scanned sources. But: **list** every existing source whose
  `language <> 'tr'` and `pii_status = 'clear'` in the Report — they carry the false
  stamp today. (Measured 2026-09-12: the two largest sources are `gardash_faz2_tr_*`,
  Turkish — so the immediate exposure is probably zero, but verify with a query.)

## Files

- `worker/src/derlem_worker/pii.py`
- `worker/src/derlem_worker/jobs/gate_jobs.py`
- `internal/database/migrations/000027_*.sql` (only if a CHECK list exists)
- `worker/tests/test_pii*.py`, freeze-gate test in `worker/tests/`
- web: the component(s) rendering `pii_status`

## Acceptance criteria

- [ ] `SELECT id, language, pii_status FROM sources WHERE language <> 'tr'` after a
      fresh `scan_pii` on a non-Turkish fixture shows `not_evaluated`.
- [ ] Freezing a release that includes that source fails with the same error class as
      a `flagged` source.
- [ ] A Turkish source's result is unchanged (`clear` / `flagged` as before).
- [ ] `pytest worker/` green; if a migration was added, `go run ./cmd/migrate` applies
      cleanly on `derlem_ci_test` and the Go migration tests pass.
- [ ] Report lists the sources that currently hold a false `clear` (may be empty).

## Verification commands

```powershell
.\.venv\Scripts\python.exe -m pytest worker/ -q
go test ./internal/database/
```

## Risks / traps

- `not_evaluated` is already used elsewhere (`releases.py:440`, decontamination). Reuse
  the exact spelling; do not invent `unevaluated` / `skipped`.
- If `sources.language` is nullable or free-text, decide the rule for unknown language:
  treat it as unsupported (`not_evaluated`). Never default unknown to `tr`.
- Do **not** weaken the freeze gate to let `not_evaluated` through "for now". The
  entire point is that the stamp is not earned.

## Report

**Done 2026-09-13.** The scanner no longer issues a clean stamp for a language it
cannot inspect.

Implemented:

- **`pii.py`**: `scan_file(path, *, language, …)` — `language` is required with no
  default (defaulting unknown to `tr` would reintroduce the lie).
  `normalize_language_tag` takes the primary subtag, lowercased (`tr-TR` → `tr`).
  `PIIReport` gains `language` and `language_evaluated`; `status` is `flagged` on any
  finding, else `clear` only when the language is supported, else `not_evaluated`.
  `supported_languages = {"tr"}` is declared on the scanner. Version
  `basic-tr-v1` → `basic-tr-v2`.
- **`gate_jobs.py`**: `_scan_pii` reads `sources.language` and passes it.
  `_complete_pii_scan`: only `clear` lowers risk (`unknown` → `low`) and advances
  approval to `auto_checked` / `sampled_for_review`; `not_evaluated` does neither.
  Language is recorded in `audit_events.details` and the job `result`.
- **`000027_pii_not_evaluated.sql`**: `sources_pii_status_check` and
  `pii_scans_status_check` re-created with `not_evaluated`. Constraint names were read
  from the live database before writing, not assumed.
- **Web**: `web/lib/pii.ts` (`piiStatusText`); the sources list, inspector detail and
  corpus metric show "değerlendirilmedi — dil desteklenmiyor" in amber, never green;
  next-step label "PII: dil desteklenmiyor".
- **e2e**: `upload.spec.ts` expects `basic-tr-v2` (a fresh upload is scanned by v2).
  `catalog.spec.ts` is **deliberately unchanged** — it inspects a pre-existing source
  whose historical scan row stays `basic-tr-v1`; re-scans are only queued for
  `not_scanned` sources.
- **`schemas/source_dataset.schema.json`**: enum corrected to the database's actual set
  plus the new value. It listed `warning` / `blocked` (never valid in the DB) and lacked
  `flagged`. Its only consumer is a mention in a planning doc; there is no validator.

Two deviations from the card, both found while reading the code:

1. **Approval must not advance.** The card only said "`not_evaluated` blocks freeze".
   `_complete_pii_scan`'s CASE would have moved a `not_evaluated` source to
   `auto_checked` / `sampled_for_review` — into the human review queue, for a source
   that can never be frozen. Closed with an explicit `status = 'clear'` condition on the
   advance branch. The exact- and normalized-dedup CASEs already required
   `pii_status = 'clear'`.
2. **Scanner version bumped.** Not asked for. The release contract pins PII by its
   `data_policy_versions` row (key / version / sha), not by the scanner string —
   `basic-tr` appears only in `pii.py` and two e2e specs — so no frozen manifest is
   affected. It keeps v1 "clear" verdicts distinguishable from v2 verdicts in
   `pii_scans`, whose uniqueness includes the version.

**Verification run (owner's machine, 2026-09-13):**

- `go build ./...`, `go vet ./...` clean; web `typecheck`, `lint`, `build` clean
- Go against `derlem_ci_test`: `TestPIINotEvaluatedMigrationIsInChain` PASS;
  `TestPIINotEvaluatedIsAcceptedAndJunkStillRejectedOnPostgres` PASS — in a fully
  migrated schema both constraint definitions contain `not_evaluated`,
  `UPDATE … 'not_evaluated'` is accepted and `'evaluated_somehow'` is rejected with
  SQLSTATE 23514; `TestMigrateAppliesAllMigrationsAndIsIdempotent` PASS with 000027 in
  the chain; full `go test ./...` all `ok`
- Worker: `test_pii.py` + new `test_pii_gate_integration.py` → 24 passed; full suite
  with the database → **241 passed, 1 skipped** (pre-existing Windows symlink case)
- The integration test drives the real `_scan_pii` → `_complete_pii_scan` path with the
  language read from the source row: `tr` / `tr-TR` → clear / low / auto_checked;
  `en` / `ku` / `multi` → not_evaluated / unknown / raw_ingested; `en` containing an
  e-mail → flagged / high / quarantined; audit details and job result carry status and
  language.

**Control run — the tests must fail against the bug.** In-process,
`PIIScanner.supported_languages` was patched to claim every language, which is exactly
v1's behaviour (no finding → clear). The same tests: **9 failed, 15 passed** — the six
unsupported-language unit cases and the three `not_evaluated` integration cases. No file
was changed for the control.

**Existing data:** the working database has 12 sources, all `language = 'tr'`
(10 clear, 1 flagged, 1 not_scanned). Sources carrying a false clean stamp today:
**0**. `pii_scans` history: 11 rows, all `basic-tr-v1`.

**Deploy step — owner.** The working database is at migration `000026`, and only
`cmd/migrate` applies migrations (the API does not at startup). Run
`go run ./cmd/migrate` **before** starting a worker on this code. Until then, scanning a
non-Turkish source fails its job with a CHECK violation — fail-closed, nothing is
mis-stamped, but noisy. All current sources are Turkish, so nothing breaks today.

**Honest gaps:**

- Freeze refusal of a `not_evaluated` source is not exercised end to end. The four
  freeze gates (`releases.go:534`, the `000024` freeze check, `release_jobs.py:680`,
  `triage.py:210`) were read and are unchanged `<> 'clear'` conditions; an end-to-end
  test needs the ~150-line approved-source fixture in `releases_contract_integration_test.go`.
- The approval guard is covered by the integration test's assertions but was not
  mutation-controlled itself (the control patched the scanner, not the SQL).
- Open design question: a source already advanced under v1 that is re-scanned and comes
  back `not_evaluated` keeps its approval — there is no "PII pending" approval state to
  demote to. Unreachable with today's data (no non-Turkish sources).
- Per-language detectors (Kurdish / Arabic IDs, phones, IBANs) remain out of scope.
  Every non-Turkish source now stops honestly at the PII gate until they exist.
