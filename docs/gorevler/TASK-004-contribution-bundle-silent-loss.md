# TASK-004 — Contribution bundling silently loses data and mislabels purpose

| Field | Value |
|---|---|
| Status | **DONE** — 2026-09-12 (implemented by Claude at the owner's request) |
| Kind | fix |
| Moratorium | allowed (closes silent data loss; no new behaviour, no new endpoint, no migration) |
| Estimate | 1 day |
| Owner | (unassigned) |
| Verified against code | 2026-09-12 — every line below was read by the owner's session, not by a summariser |

## Goal

Make the contribution → source bundling step **fail loudly or preserve**, never drop
silently. Three defects, all in `internal/repository/contributions.go`:

1. `contentPurposeForTaskType` has an unguarded fallthrough to `pretrain`.
2. `free_text` contributions discard `prompt` at bundle time even though the API
   accepted and stored it.
3. Per-contribution `domain` is never read at bundle time; a single bundle-level
   domain is stamped on the source instead.

## Why

Every future contribution type (see `docs/katki_gorev_tipleri_karar_notu.md`) will
inherit this code path. Defect 1 in particular is a trap: add a new `task_type` to the
DB CHECK, forget this function, and the bundle becomes a **permanently** `pretrain`
source (`sources.content_purpose` is immutable by trigger, `000001_initial.sql`), whose
preference/instruction records are then rejected at export — blocking the whole
release. Defects 2 and 3 are the "stamped as stored, actually dropped" class the owner
is alert to: the API returns 201, the row is in the DB, the data is not in the bundle,
and no human can see the loss at any stage.

## Current state (measured)

`internal/repository/contributions.go`:

```go
// :189-195 — free_text uses Body only; Prompt is ignored unless qa_pair
text := item.Body
if taskType == "qa_pair" {
    text = "Soru: " + item.Prompt + "\n\nCevap: " + item.Body
}
// :196 — the bundle line is a two-key map; nothing else can be carried
encoder.Encode(map[string]string{"id": item.ID, "text": text})

// :203-208 — unguarded default
func contentPurposeForTaskType(taskType string) string {
    if taskType == "qa_pair" {
        return "instruction"
    }
    return "pretrain"
}

// :222 — Bundle reads three columns; domain is not one of them
SELECT id::text, prompt, body FROM contributions
WHERE status = 'submitted' AND task_type = $1
```

The `contributions` table has a `domain` column (`000020_contributions.sql`) and the
submit API stores it; the bundle writes `input.Domain` (bundle-level) to the source.

## Scope

1. **Purpose mapping becomes an explicit table with an error default.**
   `contentPurposeForTaskType(taskType) (string, error)`; unknown type → error, and
   `Bundle` refuses to proceed. Add a test that asserts every value accepted by the DB
   CHECK (`domain.ContributionTaskTypes`) has a mapping — so adding a type without a
   mapping fails the test suite, not production.
2. **`free_text` + non-empty prompt is rejected at submit**, with a clear 400 message
   (`internal/httpapi/contribution_handlers.go`, in `normalizeAndValidateContribution`).
   Rationale: the DB CHECK only forces prompt non-empty for `qa_pair`; it does not
   forbid it for `free_text`. Rejecting at submit is the honest fix — it is the only
   place the contributor can still react. Verify first whether the web form sends
   `prompt` for `free_text` at all (`web/components/contributions-panel.tsx`); if it
   does, stop sending it.
3. **Domain: no silent drop.** `Bundle` must either (a) refuse to bundle when the
   selected contributions carry domains different from `input.Domain`, listing the
   conflicting ids in the error, or (b) group by domain and require the caller to
   bundle one domain at a time. Pick (a) — smallest change, same honesty. Do **not**
   attempt to carry per-record domain into the JSONL: the two-key map cannot, and
   canonical emission is TASK-002's job.
4. Update `internal/repository/contributions_test.go` (currently pins the two-key
   output and the `Soru:/Cevap:` string) — extend, do not weaken.

## Out of scope

- Emitting canonical records from the bundle (TASK-002 backbone).
- Any new task type.
- Changing the `Soru:/Cevap:` flattening (it is lossy, but replacing it is TASK-002).

## Files

- `internal/repository/contributions.go`
- `internal/repository/contributions_test.go`
- `internal/httpapi/contribution_handlers.go`
- `web/components/contributions-panel.tsx` (only if it sends prompt for free_text)

## Acceptance criteria

- [ ] A test enumerates `domain.ContributionTaskTypes` and asserts
      `contentPurposeForTaskType` returns a non-error mapping for each; a test passes
      an unknown type and asserts an error.
- [ ] `POST /api/v1/contributions` with `task_type=free_text` and non-empty `prompt`
      returns 400 with a code like `prompt_not_allowed_for_task_type`.
- [ ] Bundling a set whose contributions carry two different `domain` values fails with
      an error that names the conflicting contribution ids; nothing is written.
- [ ] `go test ./internal/repository/ ./internal/httpapi/` green; `go vet ./...` clean.
- [ ] If the form was changed: `npm run typecheck && npm run lint && npm run build` green.

## Verification commands

```powershell
go build ./...; go vet ./...; go test ./internal/repository/ ./internal/httpapi/
```

## Risks / traps

- `contributions_test.go` hard-codes the current output; the temptation is to loosen
  the assertion. Add cases instead.
- The repository tests need `DERLEM_TEST_DATABASE_URL`; the `derlem_ci_test` database
  exists locally. Without it these tests **skip silently** — check the test output says
  `ok` with the tests actually run, not skipped.
- Do not touch `sources.content_purpose` semantics or the immutability trigger.

## Report

**Done 2026-09-12.** All three defects closed. Two deliberate deviations from the
card, both toward the surrounding code's conventions:

1. **Purpose mapping lives in the registry, not in a second table.**
   `domain.ContributionTaskTypes` became `map[string]ContributionTaskType` with a
   `ContentPurpose` field; `contentPurposeForTaskType` reads it and returns an error
   for a missing/empty mapping. Both existing validators keep working unchanged
   (`_, ok := …[taskType]`). `Bundle` resolves the purpose **before** opening the
   transaction, so an unmapped type fails fast with nothing written.
   `TestContentPurposeForTaskType` now iterates the registry — adding a type without a
   purpose turns the suite red.
2. **`free_text` + non-empty prompt → 422 with a reason**, not a 400 with a new code.
   The handler already answers every validation failure as
   `422 contribution_validation_failed` + `reasons[]`; a one-off 400 would have been the
   inconsistent choice. The web form already sends `prompt: ""` for `free_text`
   (`contributions-panel.tsx:74`), so no web change.
3. **Domain: filter, don't refuse.** Card option (a) ("refuse when domains differ")
   would have made a mixed pool (fizik + hukuk) permanently unbundleable — the manager
   could never satisfy it. Instead the `FOR UPDATE` query now takes only contributions
   whose domain matches the bundle's (case-insensitive) or is empty; the rest stay
   `submitted` and visible in the pool, to be bundled under their own domain. Nothing is
   dropped and the source-level `domain` is truthful. The empty-pool gate message says so.

**Verification run (owner's machine, 2026-09-12):**

- `go build ./...` clean; `go vet` clean on the three packages
- Unit: `go test ./internal/repository/ ./internal/httpapi/` → ok (new registry test,
  new `free text with prompt` case)
- Integration, **actually executed** against `derlem_ci_test`:
  `TestContributionLifecycleBundlesPoolIntoSource` → PASS (1.05 s), extended with a
  `Hukuk` contribution that the `fizik` bundle must skip (stays `submitted`) and that the
  `hukuk` bundle then takes (source `domain = 'hukuk'`); audit count 6 → 8
- Full suite with `DERLEM_TEST_DATABASE_URL` set: every package ok, **0 skipped** —
  the 29 previously silent tests all ran (repository 41 s, database 19 s)

**Not changed (noted for TASK-002):** the bundle dialog still shows the per-type
pending count, not per-domain; after a domain-filtered bundle the remaining count is
simply what is left. Per-record domain in the JSONL waits for canonical emission.
