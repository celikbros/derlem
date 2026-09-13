# TASK-002 — Contribution task-type registry (translation, preference, reasoning)

> ## Revision 2026-09-12 — reframed after the expert panel
>
> A six-lens panel with per-proposal code verification
> (`docs/katki_gorev_tipleri_karar_notu.md`) changed the **shape** of this card, not
> its facts. Everything below the header still holds; read it through these corrections:
>
> 1. **This is not "add three types". It is one plumbing change that opens a family.**
>    The wall is `map[string]string{"id","text"}` at `contributions.go:196` plus
>    `DisallowUnknownFields` at `json.go:35` — not the form and not the taxonomy.
>    Deliverable of this card = the **backbone** (karar notu §2, four coordinated edits:
>    `payload jsonb` + per-type allowed-key schema in Go + canonical emission from the
>    bundle + explicit purpose table), **plus exactly one new type**.
> 2. **The first new type is `response_edit_pair`, not translation.** Three texts,
>    canonically native (shared context + chosen/rejected), no tie/both-bad wall, one
>    gate (diff at submit). Translation waits: it needs the typed-language format
>    decision, per-language PII (TASK-005), side-by-side review, four new rubric
>    dimensions — 12–18 days on its own (§5, §6).
> 3. **Reasoning is not a task type in this card.** It is a per-message attribute
>    (`reasoning_content` + `reasoning_visibility`, `canonical.py:42-52`); offering a
>    visibility selector **before** the bundle emits canonical records promises the
>    contributor something the pipeline cannot keep (§7.4). The backbone must land first;
>    a reasoning *task* waits for an automatic verifier (§3).
> 4. **Prerequisites, all moratorium-compatible, all independent of this card:**
>    TASK-004 (bundle silent loss), TASK-005 (PII language honesty), TASK-006 (identical
>    preference branches). Every new type would inherit those defects.
> 5. **The one owner decision that replaces D2–D4:** which fields are **typed**
>    (validated, gate-able, queryable — requires touching the closed `TOP_LEVEL_FIELDS`
>    whitelist that blocks releases on unknown keys) versus **untyped** (ride in
>    `metadata`, cheap, but no gate can ever see them). **For Phase A this does not
>    bite**: `response_edit_pair` is three texts, all canonically native. It bites at
>    translation (language pair) and preference (verdict/tie) — Phase B cards must open
>    with that decision. Working default until then, from karar notu §2: language pair
>    and preference verdict **typed**; rationale/notes/label sets in `metadata`.
>
> **Owner decisions 2026-09-12:** TASK-004/005/006 go to programmers now; Phase A of
> this card starts now (moratorium exception granted). Release #1's 35-document human
> review remains the delivery blocker and is not affected by either.
>
> Sequencing: TASK-004/005/006 → this Phase A → `preference_pair` → `translation_pair`.

| Field | Value |
|---|---|
| Status | **IN PROGRESS** — Phase A, owner approved 2026-09-12. TASK-004/005/006 landed. Slice S1 done 2026-09-13; see the slice table under Report. New migration number is **`000028`** (`000027` was taken by TASK-005). |
| Kind | feature |
| Moratorium | **Exception granted by the owner 2026-09-12** for Phase A (backbone + `response_edit_pair`). `docs/diyet_yol_haritasi.md` otherwise still applies; Phase B types (translation, preference, reasoning) are **not** covered by this exception and need their own cards. |
| Estimate | **8–12 working days** for Phase A. The worker-side canonical intake (§3d) is the bulk of it and is not optional. |
| Owner | (unassigned) |
| Verified against code | 2026-08-30, adversarial pass (6 agents, 76 claims checked). Line numbers refer to the working tree on that date, **including the uncommitted change set** — see Hard dependencies. |

## Goal

Make the **Katkılar** screen a systematic entry point for several kinds of training
data, not just two. Today a contributor can submit a *question–answer pair* or *free
text*. The owner wants the same screen to accept, each with its own form and its own
validation:

- **translation pairs** (TR↔EN, TR↔FR, TR↔AR, TR↔KU, … — any pair)
- **preference comparisons** (same prompt, two answers, which is better)
- **reasoning traces** (prompt → step-by-step reasoning → final answer; "chain of thought")

and be structured so the next type (classification, summarisation, correction…) is
one registry entry, not a rewrite.

## Why

Raw bulk data enters through **Kaynaklar** (file upload) and always will — that is
where millions of documents come from. **Katkılar** is the human-authored door: low
volume, high value (expert answers, hard translation cases, worked reasoning). A door
that only accepts two shapes cannot be the "systematic data entry" the owner
described. Each new data type must arrive **with its own gate**, otherwise the system
stamps "checked" on things it never looked at — the failure class fixed in commit
`0e5c7c5` (decontamination "passed" on an empty reference set).

## Hard dependencies (why this is BLOCKED)

1. ~~The uncommitted change set must land on `main` first.~~ **CLEARED 2026-08-30**
   (commits `5aebb3c` + `f1c2685`): migrations `000021`–`000026` are tracked, the chain
   is contiguous through `000026`, and the working tree is clean. Your new migration is
   therefore **`000027_…`** — re-verify with
   `git ls-files internal/database/migrations | tail -1` before creating it.
2. **TASK-001 must land first.** It edits the same `.terms-check` label/CSS this card
   changes (attestation text per origin); parallel work guarantees a conflict on
   `contributions-panel.tsx`.

## Decisions — resolved 2026-09-12

| | Decision | Effect on this card |
|---|---|---|
| **D1** | **Granted** by the owner for Phase A only. | Start now. Phase B needs its own approval. |
| **D2** | **(a)** — bundled sources stay `data_origin = 'unknown'`; origin lives on the contribution row and in record `metadata`. | No `production_runs` work. (b) stays a follow-up card. |
| **D3** | **(a)** — visibility is fixed at collection time. But see karar notu §7.4: **do not show a visibility selector until the bundle emits canonical records** (this card's §3a). Phase A collects no reasoning, so no selector ships in Phase A. | Nothing to build now; a rule for Phase B. |
| **D4** | **Included** — §3d is in scope. Without it the new type is unreviewable. | Bulk of the estimate. |

The original analysis behind D2–D4 is kept below for the implementer.

**D2 — Provenance strategy for bundled sources (analysis).** On disk, migration `000024`
(`validate_source_production_provenance`, lines ~896–955, enforced BEFORE INSERT on
`sources`) rejects any `sources.data_origin <> 'unknown'` unless the row carries a
`production_run_id` whose run matches the origin (run_kind `human_authored` /
`model_generation` / `hybrid_generation`, implementation key + digest,
`config_sha256` for model/hybrid). Migration `000026` additionally blocks freezing a
`model`/`hybrid` source into a release without a `production_run_completions` row —
which **only the distillation job writes**. No code today creates `human_authored`
runs. Options:

- (a) Keep bundled sources at `data_origin = 'unknown'`; carry origin only on the
  contribution row and inside each canonical record's `metadata`. Cheapest; the
  release contract will not "see" origin at source level.
- (b) Teach the bundler to create a `production_runs` row (and, for model/hybrid, a
  completion row matching the ingested object). Correct but ~2 extra days and a
  design conversation with whoever owns 000024/000026.
- **Recommendation: (a) for this card**, with (b) as a follow-up card.

**D3 — Review-only reasoning has no "flip".** The canonical parser **strips**
`reasoning_content` from the sanitised record unless `reasoning_visibility ==
'export_allowed'` (`canonical.py:213-216`), export writes the sanitised value
(`releases.py:776-791`), and a bundled source's object is immutable. So "stays
review-only until an admin flips it" is not implementable post-bundle. Options:
(a) model-origin reasoning is review-only forever (state it in the form hint);
(b) an admin PATCH on a *submitted* (not yet bundled) contribution sets visibility.
**Recommendation: (a)** now; (b) later if needed.

**D4 — Canonical intake scope.** See §3b: the worker cannot read canonical records
today. Either this card includes the canonical-aware text extractor (recommended,
otherwise the new types are effectively unreviewable), or the card is split.

## Current state (measured, 2026-08-30)

**Database** — `internal/database/migrations/000020_contributions.sql`:

```sql
task_type text NOT NULL CHECK (task_type IN ('qa_pair', 'free_text')),
prompt    text NOT NULL DEFAULT '' CHECK (char_length(prompt) <= 10000),
body      text NOT NULL CHECK (char_length(body) BETWEEN 1 AND 100000),
status    text NOT NULL DEFAULT 'submitted' CHECK (status IN ('submitted','withdrawn','bundled')),
CHECK (task_type <> 'qa_pair' OR char_length(btrim(prompt)) > 0),
```

Two free-text columns, no language columns, `domain` free string ≤ 100. The table is
**deliberately excluded** from the generic row-change ledger (`000023_row_change_events.sql:492-494`,
with a test asserting zero generic events) because prompt/body are raw user content;
the semantic audit event on submit records only task_type/domain/terms_ack
(`contributions.go:63-67`).

**Registry (Go)** — `domain.ContributionTaskTypes` map, `internal/domain/contribution.go:8-11`,
consumed by both validators in `internal/httpapi/contribution_handlers.go` (:28, :127),
which hard-code the error text "qa_pair veya free_text". The API decoder uses
`DisallowUnknownFields`, so request structs must change before the form does.

**Other hard-coded copies of the two types** (all must move to the registry):
`web/lib/types.ts:141,154` (unions); `web/components/contributions-panel.tsx:9-11`
(`taskTypeLabels`), `:134-135` (`pendingByType`), `:150-153` (submit `<select>`),
`:271-274` (bundle `<select>`, which also hard-codes the "→ instruction / → pretrain"
labels); `web/components/derlem-app.tsx:132-137` (guide copy); `web/lib/roles.ts:128,131,136`.

**Bundling** — `internal/repository/contributions.go:184-208` (`buildContributionJSONL`,
`contentPurposeForTaskType`) and `Bundle` (:214+, `WHERE status='submitted' AND task_type=$1`,
:221-226). Pending contributions of one task type are locked `FOR UPDATE`, written to a
staging JSONL, ingested as **one new source** with a single `language` (defaults to `tr`)
and single origin. The JSONL is *not* canonical: `{"id": …, "text": …}`, with a QA pair
flattened to `"Soru: <prompt>\n\nCevap: <body>"`. Purpose mapping: `qa_pair → instruction`,
else `pretrain`.

**Canonical record format** — `worker/src/derlem_worker/canonical.py`
(ignore the stale packaged copy under `worker/build/lib/`). The target format
**already supports** what this card needs:

- `TOP_LEVEL_FIELDS` (:26-38): `schema_version`, `record_type`, `sample_id`,
  `content_purpose`, `task_type`, `language`, `domain`, `train_policy`, `messages`,
  `tools`, `preference`, `metadata`. **Unknown top-level keys are rejected** — so
  the current `id` / `text` keys cannot appear on a canonical line; use `sample_id`.
- Required: `schema_version` (`derlem.canonical-sample.v1`), `record_type`,
  `sample_id` (:85), `content_purpose` (:86-90, must equal the purpose the parser is
  called with → `content_purpose_mismatch`).
- `RECORD_TYPES = {"conversation","preference"}`; preference requires
  `content_purpose == 'preference'` (:116) and `preference = {chosen:[…], rejected:[…]}`.
- `MESSAGE_FIELDS` (:42-52) includes `reasoning_content`, `reasoning_visibility`
  (`REASONING_VISIBILITIES = {"hidden","review_only","export_allowed"}`, :24) and
  `metadata`. Reasoning is validated non-empty; **only** `export_allowed` keeps it
  (counted in `semantic_texts`); otherwise it is popped from the sanitised record.
- Shape references: `data_samples/example_canonical_conversations.jsonl`,
  `example_canonical_preferences.jsonl` (read by
  `worker/tests/test_canonical.py::test_repository_examples_follow_the_runtime_contract`).

**Where the canonical gate actually runs** — **export, not freeze.**
`parse_canonical_sample` is called per line by `build_release_export`
(`releases.py`). Freeze runs near-dedup and decontamination, whose text extraction
(`similarity.py`) swallows `CanonicalSampleError` and falls back to plain text. So a
malformed bundle freezes cleanly and fails at the **first export request** with
`invalid_canonical_sample`. Also: once any source in a release contains canonical
records, that release can only be exported as **jsonl** (`structured_record_requires_jsonl`).

**Worker intake does not understand canonical records (the big gap).**
`sampling.py:236-247` `_document_from_line` extracts `text | content | body`; a
canonical line has none, so the **entire raw JSON line becomes the document text**,
every record gets the `missing_text_field` risk reason (+2, `sampling.py:183-193`),
exact/normalised dedup is neutralised (each `sample_id` makes lines unique), PII
regexes scan JSON-escaped text, and reviewers see raw JSON. Fingerprinting
(`fingerprints.py`) and `gate_jobs.py` use the same extractor.

**API** — under `/api/v1/`: `POST /contributions`, `GET /contributions/mine`,
`DELETE /contributions/{id}` (admin + contributor); `GET /contributions`,
`POST /contribution-bundles` (admin + data_manager) — `authorization.go:80-84`. The
web BFF proxies `/api/contributions` → `/api/v1/contributions` verbatim
(`request.text()`), so new fields need no BFF change.

**Design doc** — `docs/katki_platformu_tasarimi.md` §2 lists translation (EN→TR),
preference comparison and others as planned, with one hard rule for translation:
**the source text's rights must be cleared** (translation is a derivative work;
only permitted / public-domain source text).

## Scope

### 1. Registry — Phase A ships exactly these rows

Extend (do not duplicate) `domain.ContributionTaskTypes` into a table-driven
registry; every other copy listed above derives from it or is drift-tested against it.
A registry row declares: the **allowed and required payload keys** with max lengths,
the **canonical mapping**, the **content_purpose**, and the **submit-time gate**.

| task_type | fields | canonical mapping | content_purpose |
|---|---|---|---|
| `qa_pair` (exists) | prompt, body | conversation: user=prompt, assistant=body | instruction |
| `free_text` (exists) | body | plain `{"id","text"}` line (unchanged) | pretrain |
| **`response_edit_pair`** (new, Turkish label "Cevap düzeltme (öncesi / sonrası)") | prompt, `payload.original_response`, `payload.edited_response`, optional `payload.edit_note` (≤ 2000) | preference: messages=[user=prompt], preference={chosen:[assistant=edited_response], rejected:[assistant=original_response]}; `metadata.edit_note` if present | **preference** |

Why this type first (karar notu §8.2): three texts, canonically native, no tie/both-bad
wall (both branches are mandatory by construction), no quorum problem, and its only
gate — original ≠ edited — runs cheapest at submit while the three values are still
separate. It proves the whole backbone end to end.

**Phase B — reference only, NOT in this card, each needs its own card and approval:**

| task_type | fields | canonical mapping | content_purpose |
|---|---|---|---|
| `translation_pair` | source_text, target_text, source_language, target_language, source_rights_attestation | conversation: user=`Çevir (<src>→<tgt>): <source_text>`, assistant=target_text; top-level `language`=target; `metadata.source_language`=src — **needs the typed-language format decision and TASK-005 first** | instruction |
| `preference_pair` | prompt, chosen, rejected (+ verdict/tie, needs format decision) | preference record | preference |
| `reasoning` (as a task) | prompt, reasoning, answer, reasoning_format | conversation with `reasoning_content` — **not before an automatic verifier exists** (karar notu §3) | instruction |

Every canonical line carries `schema_version`, `record_type`, `sample_id` (= the
contribution uuid), `content_purpose` (= the registry value, which must also equal
the bundled source's purpose), `task_type`, `language`, `domain`. All types carry
`data_origin` and `model_id` (see §2) into `metadata`.

### 2. Schema (new migration, number = last on `main` + 1 after the dependency lands)

Additive only; must not break existing rows or `bundled` rows. This is the
**backbone**: one change that every later type reuses (karar notu §2, option 3).

- Widen `task_type` CHECK to `('qa_pair','free_text','response_edit_pair')`.
- **`payload jsonb NOT NULL DEFAULT '{}'`** with `CHECK (jsonb_typeof(payload) = 'object')`.
  `prompt`/`body` stay as the legacy two-field case; new types put their type-specific
  fields in `payload`. **The DB does not validate payload keys** — that is deliberate;
  the per-type allowed/required-key schema lives in Go (`normalizeAndValidateContribution`)
  and is enforced on every submit. An unvalidated jsonb is the "junk drawer" the RFC
  rejects (`versioned_data_profiles_rfc.md:336, 414-417`); the Go schema is what makes
  it not one.
- `data_origin text NOT NULL DEFAULT 'human'` with the **same vocabulary as
  `sources_data_origin`** in `000024_versioned_data_profiles.sql:862-863`
  (`unknown|human|model|hybrid`); `model_id text` (CHECK required when
  `data_origin IN ('model','hybrid')`). Applies to **every** task type — a pasted
  model answer in a `qa_pair` has the same provenance problem.
- Per-type non-empty CHECKs stay for `qa_pair`. For `response_edit_pair` the non-empty
  and original≠edited rules are Go-side (they read into jsonb); add a DB CHECK only for
  `prompt` non-empty on that type.
- `status` unchanged. Language columns are **Phase B** (translation) — do not add them now.
- **No row-change trigger on `contributions`** (000023 excludes it on purpose). Extend
  the `contribution.submitted` audit details with `data_origin`, `model_id`,
  `source_language`/`target_language`, attestation flag — never the text fields.

### 3. Bundler

**3a. Emit canonical JSONL** for `qa_pair` and `response_edit_pair`; keep plain text
for `free_text`. This replaces the two-key `map[string]string` at
`contributions.go:196` with a typed struct per record — the single wall the panel
identified. `contentPurposeForTaskType` must already be an explicit table with an
error default (**TASK-004**); do not re-implement it here, rebase on it. Commit the Go golden output as
`data_samples/example_contribution_bundles.jsonl`, have the Go test regenerate-and-
compare it, and add the path to `worker/tests/test_canonical.py::test_repository_examples_follow_the_runtime_contract`.
(CI has no cross-language step — `backend` and `worker` are separate jobs — so a
shared fixture file is the only workable contract test.)

**3b. Partition bundles.** Extend `BundleContributionsInput` and the `FOR UPDATE`
query so a bundle selects `task_type` + `data_origin`; reject a selection that would
mix origins. Language-pair partitioning is Phase B. Update `pendingByType` and the
bundle dialog accordingly. The per-contribution `domain` conflict rule comes from
**TASK-004** — keep it.

**3c. Source provenance** per D2 (recommended: leave `sources.data_origin='unknown'`,
origin lives on the contribution row and in record `metadata`).

### 3d. Canonical-aware worker intake (per D4)

Add one shared text extractor used by `sampling.py`, `fingerprints.py`, `gate_jobs.py`
(and the reviewer document view): if a line parses as a canonical record, derive the
document text from `parse_canonical_sample(...).semantic_texts` (or an equivalent
join of message contents); otherwise fall back to today's `text|content|body`.
Acceptance: a bundled canonical source gets no `missing_text_field` risk, exact
dedup catches two identical QA pairs with different `sample_id`s, and the review
screen shows readable text, not JSON.

### 4. Gates — Phase A

- `response_edit_pair` at submit: `prompt`, `original_response`, `edited_response`
  non-empty; reject when `original_response` and `edited_response` are identical after
  whitespace normalisation (`edit_pair_no_change`). The canonical-level identical-branch
  check (**TASK-006**) is the fail-closed backstop for the same rule at export; both
  are needed (submit = user feedback, canonical = cannot be bypassed by file upload).
- Whether the edit is an *improvement* is **human review**, not code — do not fake it.
  What a reviewer sees is §3d's job.
- All types: PII / dedup / sampling gates run at ingest — **only meaningfully after 3d.**

Phase B gates (translation rights attestation, language pair, reasoning ≠ answer)
are listed in the karar notu §7 table with what each one must never claim.

### 4a. Reasoning traces are model-specific — do not bake one model's syntax in

The owner supplied a real Gemma trace (2026-08-30): a `Thinking Process:` header,
numbered steps, bulleted draft options, a "select the best option" step, then the
final output. Other models emit a flat paragraph, `<think>…</think>` tags, or JSON.
**Derlem is model-agnostic**, so:

- Store `reasoning_content` **verbatim**; never reformat or strip headers/numbering.
- Record the format: `messages[].metadata.reasoning_format` — free tag, suggested
  `freeform`, `numbered_steps`, `gemma_thinking_v1`, `think_tags`; unknown → `freeform`.
- Record the origin (§2 `data_origin`, `model_id`). The attestation text *"Bu metni
  kendim ürettim"* is false for a pasted model trace; for `model`/`hybrid` the form
  shows *"I have the right to submit this model output and have reviewed it"* instead.
- `reasoning_visibility` per **D3**: default `review_only`; contributors may choose
  `export_allowed` only for `human`/`hybrid`. Note for implementers and data managers:
  **`review_only` reasoning never reaches an export** — the parser strips it; the
  export record keeps only the visibility flag.
- **Bulk model output does not belong here.** Hundreds of Gemma traces are a
  distillation job (`docs/distilasyon.md`: provider + model recorded in a manifest,
  key never stored). The contribution door is for single, human-touched traces. Say so
  in the form hint.
- Reviewer note: Gemma's trace drafts *several* candidate answers and then picks one.
  `answer` must hold only the selected final output (`Merhaba! Nasılsınız?`), not the
  option list; the equality gate above is the only automatic check.

### 5. Web form

One `<select>` driven by the registry (both the submit and the bundle selects); the
field set switches per type. `response_edit_pair`: prompt + two side-by-side boxes
("Orijinal cevap" / "Düzeltilmiş cevap") + optional "Ne düzeltildi?" note + origin
selector (`human` default; `model`/`hybrid` reveals `model_id`). "My contributions"
shows the new type. Request structs first (API rejects unknown JSON fields), then the
form. Phase B forms (language selects, reasoning/format tag) are not built now.

### 6. Copy

`web/lib/roles.ts` contributor `duties`/`firstSteps`; `derlem-app.tsx:132-137` guide
copy; `docs/katki_platformu_tasarimi.md` §2 (mark implemented rows);
`docs/api_workflows.md` (request examples per type, under `/api/v1/`);
`docs/diyet_yol_haritasi.md:70` if the moratorium exception is granted.

## Out of scope

- Trust tiers, N-approval, golden tasks, self-signup, CLA/OIDC (design doc §3–§5).
- Bulk import of translation corpora (Sources path, works today).
- Automatic quality judgement of translations or reasoning.
- Creating `production_runs` for human-authored bundles (D2 option b) — follow-up card.
- Per-language PII patterns for AR/KU (follow-up; see Risks).
- i18n of the UI (separate roadmap item).

## Files

- `internal/database/migrations/0000NN_contribution_task_types.sql` (new)
- `internal/domain/contribution.go` (registry, request/response structs),
  `internal/repository/contributions.go`, `internal/httpapi/contribution_handlers.go`
- Tests to **rewrite**, not extend: `internal/repository/contributions_test.go:30`
  (asserts the flattened "Soru:/Cevap:" text), `contributions_integration_test.go:178-180`
  (greps the staged file for it), `internal/httpapi/contribution_handlers_test.go:28`
  (uses `translation` as the *invalid* fixture — replace with e.g. `classification`);
  the two validation messages in `contribution_handlers.go`.
- `worker/src/derlem_worker/sampling.py`, `fingerprints.py`, `jobs/gate_jobs.py`
  (shared canonical-aware extractor, §3d); `worker/tests/test_canonical.py` (fixture path)
- `data_samples/example_contribution_bundles.jsonl` (new golden)
- `web/lib/types.ts`, `web/components/contributions-panel.tsx`, `web/lib/roles.ts`,
  `web/components/derlem-app.tsx`
- docs listed in §6

## Acceptance criteria

- [ ] `SELECT conname, pg_get_constraintdef(oid) FROM pg_constraint WHERE conrelid='contributions'::regclass`
      shows the three task types, the `payload` object CHECK, the origin/model_id CHECKs.
- [ ] `POST /api/v1/contributions` with `task_type=response_edit_pair` and a payload key
      not in the registry (e.g. `payload.foo`) returns 400 naming the key — proves the
      Go-side key schema is enforced, i.e. the jsonb is not a junk drawer.
- [ ] A contributor can submit a `response_edit_pair` from the UI; it appears in
      "my contributions" with the label "Cevap düzeltme (öncesi / sonrası)".
- [ ] `response_edit_pair` with identical original/edited is rejected (HTTP 4xx,
      field-level message in the form); `model`/`hybrid` without `model_id` is rejected.
- [ ] Bundling `qa_pair` and `response_edit_pair` produces a source whose staged JSONL
      lines all pass `parse_canonical_sample` with the mappings in §1 (worker fixture
      test); `free_text` still bundles as plain text; a bundle cannot mix origins.
- [ ] After ingest of a bundled canonical source: no `missing_text_field` risk reason;
      two identical QA pairs with different `sample_id`s are flagged as exact duplicates;
      the review screen shows readable text **with both sides of an edit pair visible**
      (§3d — this is the criterion most likely to be skipped; do not skip it).
- [ ] Worker-level test: the bundled `response_edit_pair` fixture passes
      `build_release_export` for purpose `preference` in `jsonl` format (proves the
      **export-time** canonical gate accepts it). The full UI path (bundle → ingest/PII/
      dedup/sample → sample review by a *different* user → source approval → `preference`
      release → freeze → export) is a separate half-day walk-through; budget it.
- [ ] Registry drift test: Go registry, worker constants and web select options asserted equal.
- [ ] `go test ./...`, `pytest worker/tests`, `npm run typecheck && npm run lint && npm run build` pass.

## Verification commands

```powershell
go test ./...
.\.venv\Scripts\python.exe -m pytest worker\tests -q
Set-Location web; npm run typecheck; npm run lint; npm run build
```

Plus the UI walk-through on the running stack (`http://localhost:18400`).

## Risks / traps

- **Scope creep into Phase B.** The temptation is to "also add translation while in
  there". Do not. Translation needs a format decision the owner has not made and a PII
  fix (TASK-005) that may not have landed. One type, end to end, reviewed on screen.
- **Merge order with TASK-004.** Both edit `contributions.go`. TASK-004 first; rebase.
- **CI is green again** (since 2026-09-12) and runs backend / worker / web as separate
  jobs — there is no cross-language step, which is why the shared golden fixture (§3a)
  is the only contract test between Go emission and Python parsing. Locally, 12 of the
  `internal/repository` tests **skip silently** when `DERLEM_TEST_DATABASE_URL` is unset
  — including the release-contract test that guards this area. Point it at the
  `derlem_ci_test` database before trusting `go test ./...`.
- **Provenance trigger (D2)**: writing `sources.data_origin <> 'unknown'` without a
  `production_runs` row fails at INSERT (`000024`, `validate_source_production_provenance`).
- **Export-time gate**: a malformed canonical line surfaces at the first export, not
  at freeze; canonical sources force jsonl-only exports.
- **PII gate is Turkish-calibrated** (TCKN, IBAN, TR phone patterns). AR/KU text passes
  it without being meaningfully checked. State this in the bundled source's notes;
  a follow-up card must add per-language PII patterns before any AR/KU release is frozen.
- **Translation rights** attestation is a legal control; keep it adjacent to its label
  (TASK-001 fixes the CSS).
- Ignore `worker/build/lib/` (stale packaged copy); source of truth is `worker/src/`.
- Do not hand-copy the type list; the drift test exists to catch exactly that.

## Close-out

Commit in small steps (schema → Go → worker → web), Turkish commit messages with the
two `Co-Authored-By` trailers from `CLAUDE.md`; push to `main`; set Status here and
in `docs/gorevler/README.md`; fill **Report** with test output and SHAs.

## Report

Implemented by Claude at the owner's request, in slices. Each slice is one commit, and
CI must be green for it before the next slice starts.

| Slice | Work | Status |
|---|---|---|
| S1 | Worker reads canonical records (§3d) | **done** 2026-09-13, `6a8d06d`, CI green |
| S2 | Migration `000028`: `payload jsonb`, new task type, origin columns (§2) | **done** 2026-09-13, `4b409f6`, CI green |
| S3 | Go: per-type allowed/required payload keys, submit validation (§1, §4) | **done** 2026-09-13, `9a8d460`, CI green |
| S4 | Bundle emits canonical JSONL + shared Go↔Python golden fixture (§3a–3b) | **done** 2026-09-13, `7ec1273`, CI green |
| S5 | Web form driven by the registry, `response_edit_pair` fields (§5) | **done** 2026-09-13 |
| S6 | Review view shows both sides of an edit pair (acceptance, §3d) | next |
| S7 | End-to-end walk-through, copy, docs (§6) | — |

### S5 — Web form driven by the registry (§5) — 2026-09-13

**No second list.** The Go registry now also declares everything the form shows — type label,
prompt and body labels, payload-field labels and order, display order — plus ordered origin
options (`ContributionDataOriginOptions`, each flagged `requires_model_id`).
`domain.ContributionTaskTypeCatalog()` renders that view, and
`TestContributionCatalogMatchesWebFixture` writes and compares
`web/lib/contribution-task-types.json` byte for byte (regenerate with
`DERLEM_UPDATE_GOLDEN=1`). The web imports that file through
`web/lib/contribution-task-types.ts`; `types.ts` no longer unions the old type names.
`TestContributionCatalogCoversEveryRegistryEntry` requires a label for every type and field,
a unique positive display order, `distinct_from_body` to be a declared payload key, and origin
options identical to the validation vocabulary with a matching `requires_model_id`.

**Form (`contributions-panel.tsx`).** The type select comes from the catalog. The prompt is
shown unless the type forbids it, and required when the type says so. The `distinct_from_body`
field — the original answer — is rendered **beside** the body — the edited answer — so both
sides sit next to each other; other payload fields take the full width. An origin select adds a
required model-name field when the origin needs one, and the terms attestation switches from
*"I produced this text myself"* (false for model output) to *"I have the right to submit this
model output and have reviewed it"* for model and hybrid origins. Payload values are sent only
when non-empty. The form name "Yeni katkı" and its heading are kept for
`authorization.spec.ts`. The contributor's list and the manager's pool use catalog labels and
summarise an edit pair as *question — original → edited*; the bundle dialog lists every type
with its pending count and target purpose.

**Copy.** The contributor texts in `roles.ts` and two guide sentences in `derlem-app.tsx`
enumerated the two old types. They now describe the flow without listing types, which would
only drift again.

**Verification (owner's machine, 2026-09-13):**

- `gofmt -l` clean, `go vet` clean; `internal/domain` catalog tests pass; full
  `go test ./...` against the scratch database — every package `ok`
- web: `npm run typecheck`, `npm run lint`, `npm run build` clean
- a grep of `web/` for the task-type names and their old Turkish labels finds nothing outside
  the generated catalog

**Control run.** In a temporary worktree at `7ec1273` with the S5 registry and catalog: the
unmodified copy passes; changing a type label in Go without regenerating the JSON turns
`TestContributionCatalogMatchesWebFixture` red (*"contribution registry drifted"*); dropping one
origin option turns the coverage test red (*"origin options (3) and validation vocabulary (4)
differ"*).

**Not verified in a browser.** This session has no browser automation, and Derlem services are
started by the owner. The web dev server hot-reloads, so the new form is already visible on
port 18400 — but the running API predates S3, so submitting a `response_edit_pair` is rejected
until the API is restarted.

### S4 — Bundle emits canonical records + shared Go↔Python fixture (§3a–3b) — 2026-09-13

**Emission is a registry field.** `Bundleable` became `BundleEmission`: `plain_text` for
`free_text` (the unchanged `{"id","text"}` line), `canonical_conversation` for `qa_pair`
(user = prompt, assistant = body), and `canonical_preference` for `response_edit_pair`
(context = prompt; chosen = body, the edited answer; rejected = the `DistinctFromBody`
payload key, the original answer). An empty emission means the type cannot be bundled.
Using `DistinctFromBody` as the rejected branch ties the two languages together: S3's submit
gate already guarantees that TASK-006's `preference_branches_identical` can never block an
export on a bundled edit pair.

**Nothing is dropped.** Every canonical record carries `sample_id` (the contribution id),
`task_type`, `language`, the contribution's own `domain` — omitted when empty, because the
parser rejects empty strings and one invalid record blocks a whole release at export —
`train_policy: assistant_only`, and `metadata` holding `data_origin`, `model_id` when
present, and every payload key not already written as a branch (`edit_note`). Contributor
identity is never written. S3's two temporary guards are gone: edit pairs bundle, and
`model` / `hybrid` contributions bundle with their origin in metadata. Source-level
`data_origin` stays `unknown` (D2a).

**A contract that binds both languages.** CI runs backend and worker as separate jobs, so one
committed file ties them: `data_samples/example_contribution_bundles.jsonl`.
`TestContributionBundleGoldenFixture` rebuilds it from fixed items and compares byte for byte
(regenerate with `DERLEM_UPDATE_GOLDEN=1`); `worker/tests/test_contribution_bundle_fixture.py`
reads the same file with the worker's real parser and document-text extractor. It is a
separate Python test rather than an addition to
`test_repository_examples_follow_the_runtime_contract`, whose record-type list is exact.

**Behaviour changes.**

- A release containing a `qa_pair` bundle can now be exported only as JSONL
  (`releases.py:762-775`: any canonical record requires JSONL). That is inherent to keeping
  question and answer apart; `free_text` bundles stay plain and TXT-exportable. The working
  database holds **0** contribution-bundle sources, so nothing existing is affected.
- §3b asked a bundle to reject mixed origins. With origin carried per record and the
  source-level origin fixed at `unknown`, mixing is lossless, so it is allowed.

**Verification (owner's machine, 2026-09-13):**

- `gofmt -l` clean; `go build ./...`, `go vet ./internal/...` clean
- `internal/repository` unit tests: golden fixture byte-equal; `qa_pair` emitted as a
  canonical conversation (separate messages, empty domain omitted, origin and model id in
  metadata, no `created_by`, raw UTF-8); edit pair emitted as a preference (chosen = edited,
  rejected = original, `edit_note` in metadata, original not duplicated there); `free_text`
  unchanged; an edit pair without a rejected branch is refused; an unknown type is refused;
  the registry test now also requires an emission for every type
- integration `TestContributionPayloadRoundTripAndCanonicalBundles`: the edit-pair bundle's
  source has purpose `preference` and its staged record keeps every field, including the raw
  marker; human and hybrid `qa_pair`s both bundle with origin and model id; nothing is left
  `submitted`; audit details carry no content. The lifecycle test now expects the canonical
  record instead of the flattened `Soru:` text.
- full `go test ./...` against the scratch database — every package `ok`
- Python: the fixture contract test 3/3; full worker suite 254 passed, 1 skipped

**Control run — does the cross-language contract actually bind?** In a temporary worktree at
`9a8d460` with the S4 files copied in: the unmodified copy passes on both sides. With
`omitempty` removed from `domain`, so an empty tag is written as `""`: the Go unit test fails
(*"an empty domain must be omitted"*), the regenerated fixture contains the `"domain":""` line,
and **all three Python tests fail** with `CanonicalSampleError: sample_domain_must_be_string` —
the exact error that would block a release at export. The worktree was removed; the committed
fixture is untouched.

**Deploy.** No migration. The API must be restarted to bundle this way; the running API
predates S3.

### S3 — Go registry and submit validation (§1, §4) — 2026-09-13

**Registry.** Each `domain.ContributionTaskTypes` row now declares everything validation and
bundling need: content purpose, prompt required or forbidden, allowed payload keys (required?
maximum characters), a `DistinctFromBody` gate, and `Bundleable`. No handler branch names a
task type, and the unknown-type message lists the registry, so the next type is one row.
`response_edit_pair`: purpose `preference`; prompt required; `payload.original_response`
required (≤ 100,000 characters); `payload.edit_note` optional (≤ 2,000); the original answer
must differ from `body` ignoring whitespace.

**Validation.** Unknown payload keys are rejected **by name**; missing required keys and
over-long values are separate reasons; values are trimmed and empty optional keys dropped.
Data origin defaults to `human` with the `sources.data_origin` vocabulary; `model` / `hybrid`
need a `model_id`, `human` / `unknown` must not carry one; `model_id` ≤ 200. Errors stay
`422 contribution_validation_failed` with reasons. JSON decoding errors are a generic
`400 invalid_json` (`json.go`), which is why key problems are reported by validation, not by
decoding.

**Repository.** Submit stores `payload` (a nil map is written as `{}`, never `null`, so the
object CHECK holds), `data_origin` and `model_id`; `ListMine` and `ListPending` return them.
The submit audit event records `data_origin` and `model_id` — never prompt, body or payload
values, which are raw user content (`000023`).

**Two silent-loss guards, both removed by S4.** Today's bundle line is `{"id","text"}`:

- a type with `Bundleable: false` (`response_edit_pair`) is refused with a `GateError` (422)
  instead of being bundled body-only with the original answer silently dropped;
- `model` / `hybrid` contributions are not selected by a bundle and stay visible in the pool,
  because the plain line cannot carry origin or model id.

**Verification (owner's machine, 2026-09-13):**

- `gofmt -l` clean; `go build ./...`, `go vet ./internal/...` clean
- `internal/httpapi`: 11 contribution tests pass — new: every registered type is named in the
  unknown-type message; an edit pair is accepted and normalised; ten rejection cases each
  matched by their reason text; hybrid origin with `model_id` accepted
- `internal/repository`: new `TestContributionPayloadRoundTripAndBundleGuards` passes —
  payload and origin round-trip through `Submit`, `ListMine`, `ListPending`; the edit-pair
  bundle is refused; a `qa_pair` bundle takes only the human row while the hybrid row and the
  edit pair stay `submitted`; the submit audit records origin and model id and contains no
  content marker. The existing lifecycle test is unchanged and green.
- full `go test ./...` against the scratch database: every package `ok`

**Control run.** In a temporary git worktree at `4b409f6` with the S3 files copied in (main
tree untouched, worktree removed afterwards): the unmodified copy passes; **(A)** with the
`Bundleable` guard removed the test fails with *"bundling response_edit_pair must be refused
with a GateError, got <nil>"* — the bundle would have succeeded and silently dropped the
original answer; **(B)** with the origin filter removed it fails with *"expected only the
human qa pair bundled, got 2"*.

**Deployed.** Migration `000028` applied to the working database 2026-09-13 03:15 with the
owner's go-ahead: `000027` → `000028`, the three columns and seven constraints present,
0 rows before and after, still only the `contributions_set_updated_at` trigger. The running
API predates S3 and is unaffected; it must be restarted to serve S3.

Web is unchanged: responses gain fields, and the TypeScript types move in S5.

### S2 — Migration `000028`: contribution backbone (§2) — 2026-09-13

**Schema.** The `task_type` CHECK is widened to `qa_pair | free_text | response_edit_pair`
(its real name, `contributions_task_type_check`, was read from the live database first,
not assumed). New columns: `payload jsonb NOT NULL DEFAULT '{}'`, which must be a JSON
object and carries a 1 MiB defense-in-depth cap; `data_origin text NOT NULL DEFAULT
'human'` with the same vocabulary as `sources.data_origin` (`000024:862-863`); and
`model_id`, required when the origin is `model` or `hybrid`. A `response_edit_pair` must
have a non-empty prompt. Exact per-key character limits belong to S3's Go registry: a
100,000-character Turkish answer can exceed 200 KB in UTF-8, so a tight database cap would
reject valid contributions.

**Field placement — refines §1.** `body` stays `NOT NULL`, 1–100,000 characters. Rather
than weaken that rule, `response_edit_pair` stores the **edited** answer in `body` (it is
the text the contribution produces) and the **original** answer in
`payload.original_response`, with an optional `payload.edit_note`. Previews built from
`prompt` + `body` stay meaningful. §1's table put both answers in `payload`; this is the
implemented shape.

**Ledger.** The row-change ledger is an explicit allow-list — 32 tables, each with its own
`CREATE TRIGGER` across `000023`–`000026` — and `contributions` is deliberately excluded
(`000023:492-494`: raw user content). `000028` adds no trigger. Its test asserts that the
file contains none and, at runtime, that inserting an edit pair whose payload holds a
marker string produces zero ledger events and leaks no marker.

**Existing data.** The working database's `contributions` table is empty, so no rows
change. Existing two-column inserts keep working through the new defaults (asserted).

**Verification (owner's machine, 2026-09-13):**

- `TestContributionPayloadMigrationIsInChainAndAddsNoLedgerTrigger` — PASS
- `TestContributionPayloadConstraintsOnPostgres` — PASS: edit pair accepted, origin defaults
  to `human`, legacy insert works; five invalid rows each rejected with SQLSTATE 23514
  (non-object payload, empty edit-pair prompt, model origin without `model_id`, unknown
  origin, unknown task type); hybrid origin with `model_id` accepted; 0 ledger events
- `TestMigrateAppliesAllMigrationsAndIsIdempotent` and both row-change ledger tests — PASS
  with `000028` in the chain
- full `go test ./...` — every package `ok`

**No separate control run, deliberately.** The database test's first statement writes a
`response_edit_pair` into a `payload` column; without `000028` that column does not exist
and the type is rejected, so the test cannot pass without the migration. Demonstrating it
would mean hand-applying a partial chain; running it against the working database would
mean writing to it.

**Deployed** 2026-09-13 03:15 with the owner's go-ahead, together with S3 — see the S3
report for the before/after checks. S2 on its own changed no application behaviour; S3 is
the first code that reads the new columns.

### S1 — Worker reads canonical records (§3d) — 2026-09-13

**Design.** `sampling._document_from_line` is the single text extractor behind sampling,
fingerprinting (`fingerprints.py`, `jobs/gate_jobs.py`), the quality filter
(`clean_candidate.py`), exact decontamination (`releases.py`) and — now — similarity. A
line carrying `schema_version` is parsed with `parse_canonical_sample` using the
record's **own** `content_purpose`: none of the callers know the source's purpose, and
they do not need to (`similarity.py` already used this pattern). A valid record's
document text is `"\n".join(semantic_texts)` — the same text the export counts, with
`review_only` reasoning excluded — and its external id is `sample_id`. An invalid record
is returned raw, never repaired. `similarity._similarity_text_from_line` now delegates to
it: one source of truth instead of two copies.

**Risk scoring.** A valid canonical record no longer receives `missing_text_field` (+2).
An invalid one receives the new reason `invalid_canonical_sample` (+5): export blocks the
whole release on a single invalid record (`releases.py:747-758`), so review must see it
first. Non-canonical JSON without a text key still receives `missing_text_field` (the
existing test is unchanged).

**Fingerprint compatibility — measured, no version bump.** Normalized dedup filters by
`fingerprint_version` (`gate_jobs.py:316,422,439`); bumping it would orphan all
11.9M `normalized-document-sha256-v1` rows. Before changing extraction, every source
object still on disk was read (first 64 KB): **0** canonical lines. The export of the
release named "Canonical Export Smoke" records `record_type_counts = {"text": 2}` — plain
text despite the name. Seven small smoke sources' objects are missing from disk (the
2026-07-16 object-store loss) and could not be checked; the worst case is a missed
near-duplicate against a test source that is unrecoverable anyway. An earlier check on
`documents.text_preview` also returned 0 but was not trusted: `schema_version` sits at the
end of the line, where a truncated preview cannot show it.

**Verification (owner's machine, 2026-09-13):**

- new `worker/tests/test_canonical_intake.py` — 8 passed: semantic text and `sample_id`;
  an edit pair's text holds the prompt and both answers; an invalid record is returned
  raw; plain JSON is unchanged; a valid record is not flagged `missing_text_field`; an
  invalid one is flagged `invalid_canonical_sample`; **two identical canonical records
  with different `sample_id`s get the same fingerprint** (acceptance criterion); sampling
  stores semantic text, not JSON
- `test_similarity.py` and `test_sampling.py` unchanged and green (26 passed together)
- full worker suite against the scratch database: 251 passed, 1 skipped (pre-existing
  Windows symlink case)

**Control run.** The same new tests, run in-process against the pre-S1 `sampling.py`
loaded from git `HEAD`: **6 failed, 2 passed** — exactly the six behaviours S1 adds. The
two passes (plain JSON unchanged; invalid record returned raw) are behaviours the old code
already had.

**Limitation handed to S6.** For a preference record the parser adds the context (the
prompt) once per branch, so the document text reads *prompt, chosen, prompt, rejected*
without labels. That is consistent for dedup, but a reviewer cannot tell the original
answer from the edited one. The labelled review view is S6.

**Edge-case behaviour change (no existing data affected):** a valid canonical record whose
messages carry only non-text parts (image, audio) previously yielded empty similarity
text; it now yields the raw line, so the document stays visible instead of being skipped.
