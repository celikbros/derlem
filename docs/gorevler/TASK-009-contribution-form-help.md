# TASK-009 — Contribution form explains nothing

| Field | Value |
|---|---|
| Status | **IN REVIEW** — 2026-09-16, implemented by Claude at the owner's request; owner's on-screen check pending |
| Kind | fix (usability of the TASK-002 Phase A form) |
| Moratorium | allowed — makes the delivered contribution flow usable |
| Estimate | 0.5 day |
| Owner | (unassigned) |
| Verified against code | 2026-09-16 |

## Goal

A contributor who has never seen the form can fill it in without asking anyone:
every field says what it wants, shows an example, and the chosen task type says what
it is for. A data manager can bundle without guessing the domain string.

## Why

Owner, first look at the S5 form (2026-09-16): many input boxes, no explanation of what
goes into *Soru*, *Ne düzeltildi?* or *Alan*, and the *Bu ekranda ne yapabilirim?* box
did not help. Asked for a help icon with a hint next to each field.

Measured problems behind that:

- The catalog carried labels only — no description, hint or example for any type or field.
- *Alan* (domain) is free text. Bundling matches it case-insensitively
  (`lower(domain) = lower($2)`) and **always includes contributions with an empty
  domain**, but a typo or a synonym (`fzik`, `Fizik bilimi`) silently keeps a
  contribution out of a bundle. The bundle dialog asked the manager to type the domain
  from memory, with no view of which domains were waiting.
- Validation messages named JSON keys: *"payload.original_response metinle aynı…"*.
- No guidance on the origin of an edit pair, although its original answer normally
  comes from a model.

## Scope (done)

1. **Help texts live in the Go registry** (`internal/domain/contribution.go`), not in
   the web: per type `Description`, `PromptHint`/`PromptPlaceholder`,
   `BodyHint`/`BodyPlaceholder`, `OriginHint`, `DefaultDataOrigin`; per payload field
   `Hint`/`Placeholder`; per origin option `Hint`. They flow through the generated
   catalog (`web/lib/contribution-task-types.json`).
   `TestContributionCatalogExplainsEveryField` fails when a type, field or origin is
   added without them, when a payload label carries the "(opsiyonel)" marker (the form
   adds it; labels are also used in error messages), or when a default origin is not
   in the vocabulary.
2. **Form (`contributions-panel.tsx`).** Every field is a `FormField`: label, a
   **(?) button** (`aria-expanded`, works on touch and keyboard — not hover-only) that
   opens the hint, and the control, linked with `label htmlFor` and
   `aria-describedby` (the hint is announced even while collapsed). The button is not
   inside the `<label>`: as the first labelable descendant it would have taken the
   label from the textarea. Boxes show examples as placeholders. The selected type's
   description is always visible under the type select. Optional fields say so.
3. **Origin.** `response_edit_pair` defaults to *Model çıktısını düzenledim* (hybrid);
   its origin hint explains when to pick *Kendim yazdım* instead. The origin help lists
   every option with its meaning. Model name has a hint.
4. **Domain.** Contributor: hint (*one word, lower case; leave empty if unsure — the
   data manager sets it when bundling*) and a suggestion list of the contributor's own
   earlier domains. Bundle dialog: the type defaults to the first type with pending
   items; domain suggestions come from the pending pool of that type (auto-filled when
   there is exactly one); a live preview says how many contributions the choice will
   bundle and how many of them have no domain; chips list the other waiting domains;
   the submit button is disabled when the choice would bundle nothing. The preview uses
   the same rule as the query (empty domain, or case-insensitive equal).
5. **Messages** use the field labels: *"Orijinal cevap ile Düzeltilmiş cevap aynı;
   değişiklik yoksa bu katkı gönderilmez."*, *"Orijinal cevap zorunludur."* Unknown
   keys keep their technical name (they are not form fields).
6. **Guide box** (*Bu ekranda ne yapabilirim?*) for the contribution view: concrete
   steps, the three types in one sentence each, domain and personal-data advice; for
   managers, the preview and the self-review rule (admin excepted, as in
   `ClaimForReview`).

## Out of scope

- A fixed domain vocabulary (a data-policy decision for the owner).
- Server-side normalisation of stored domains.
- Playwright coverage of the help buttons (needs the running stack; see Report).

## Report

**Verification (2026-09-16):**

- `gofmt -l` clean; `go vet` on `internal/domain`, `internal/httpapi` clean
- catalog regenerated with `DERLEM_UPDATE_GOLDEN=1`
- `go test ./...` against the scratch database `derlem_ci_test`: every package `ok`
  (`domain`, `httpapi`, `repository` ran uncached)
- web: `npm run typecheck` and `eslint` on the changed files clean
- `npm run build` **not** run locally: the owner's `next dev` was running on 18400 and
  shares `.next`; CI builds

**Owner check pending.** The web dev server hot-reloads, so the hints are visible at
once. The new validation messages are Go-side: the API must be restarted to show them.
