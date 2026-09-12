# TASK-005 — PII scanner reports "clear" on languages it cannot inspect

| Field | Value |
|---|---|
| Status | READY |
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

_(to be filled on completion)_
