# TASK-002 — Contribution task-type registry (translation, preference, reasoning)

| Field | Value |
|---|---|
| Status | DRAFT — **owner decisions required** (see Decisions). Dependency 1 (uncommitted work) **CLEARED 2026-08-30**; dependency 2 (TASK-001) still open. |
| Kind | feature |
| Moratorium | **not allowed by default.** `docs/diyet_yol_haritasi.md` permits only bug fixes / pruning / documentation / Phase 0 (delivery) support; `docs/katki_platformu_tasarimi.md` §6 places translation and preference tasks in **Phase C**. Starting this pulls Phase C forward — the owner's call, not the implementer's. |
| Estimate | **8–12 working days** (was 3–5 before verification; the worker-side canonical intake and the provenance contract were not visible from the surface). Excludes the owner decisions below. |
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

## Decisions required from the owner (before coding)

**D1 — Moratorium.** Pull Phase C forward or not.

**D2 — Provenance strategy for bundled sources.** On disk, migration `000024`
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

### 1. Registry

Extend (do not duplicate) `domain.ContributionTaskTypes` into a table-driven
registry; every other copy listed above derives from it or is drift-tested against it.

| task_type | fields | canonical mapping | content_purpose |
|---|---|---|---|
| `qa_pair` (exists) | prompt, body | conversation: user=prompt, assistant=body | instruction |
| `free_text` (exists) | body | plain `{"id","text"}` line (unchanged) | pretrain |
| `translation` | source_text, target_text, source_language, target_language, source_rights_attestation | conversation: user=`Çevir (<src>→<tgt>): <source_text>`, assistant=target_text; top-level `language`=target; `metadata.source_language`=src | instruction |
| `preference` | prompt, chosen, rejected | preference: messages=[user=prompt], preference={chosen:[assistant], rejected:[assistant]} | **preference** |
| `reasoning` | prompt, reasoning, answer, reasoning_format | conversation: user=prompt, assistant.content=answer, assistant.reasoning_content=reasoning (verbatim), assistant.reasoning_visibility per D3, assistant.metadata={reasoning_format, data_origin, model_id} | instruction |

Every canonical line carries `schema_version`, `record_type`, `sample_id` (= the
contribution uuid), `content_purpose` (= the registry value, which must also equal
the bundled source's purpose), `task_type`, `language`, `domain`. All types carry
`data_origin` and `model_id` (see §2) into `metadata`.

### 2. Schema (new migration, number = last on `main` + 1 after the dependency lands)

Additive only; must not break existing rows or `bundled` rows.

- Widen `task_type` CHECK to the five values.
- `source_language text`, `target_language text` (nullable; CHECK required and
  distinct for `translation`; lowercase tags `tr`, `en`, `fr`, `ar`, `ku`, …).
- `data_origin text NOT NULL DEFAULT 'human'` with the **same vocabulary as
  `sources_data_origin`** in `000024_versioned_data_profiles.sql:862-863`
  (`unknown|human|model|hybrid`); `model_id text` (CHECK required when
  `data_origin IN ('model','hybrid')`). Applies to **every** task type — a pasted
  model answer in a `qa_pair` has the same provenance problem.
- Secondary per-type fields (`rejected`, `reasoning`, `reasoning_format`,
  `source_rights_attestation`): explicit nullable columns if ≤ 3, otherwise
  `extra jsonb NOT NULL DEFAULT '{}'`; document the choice.
- Per-type non-empty CHECKs (as `qa_pair` has today). `status` unchanged.
- **No row-change trigger on `contributions`** (000023 excludes it on purpose). Extend
  the `contribution.submitted` audit details with `data_origin`, `model_id`,
  `source_language`/`target_language`, attestation flag — never the text fields.

### 3. Bundler

**3a. Emit canonical JSONL** for `qa_pair`, `translation`, `preference`, `reasoning`;
keep plain text for `free_text`. Commit the Go golden output as
`data_samples/example_contribution_bundles.jsonl`, have the Go test regenerate-and-
compare it, and add the path to `worker/tests/test_canonical.py::test_repository_examples_follow_the_runtime_contract`.
(CI has no cross-language step — `backend` and `worker` are separate jobs — so a
shared fixture file is the only workable contract test.)

**3b. Partition bundles.** Extend `BundleContributionsInput` and the `FOR UPDATE`
query so a bundle selects `task_type` + (translation) `source_language`/`target_language`
+ `data_origin`; derive the source's `language` from the pair (target) instead of the
`tr` default; reject a selection that would mix origins or pairs. Update
`pendingByType` and the bundle dialog accordingly.

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

### 4. Gates (one per type)

- `translation`: both texts non-empty; languages differ; **source-text rights
  attestation** checkbox ("the source text is public-domain / licensed for derivative
  use"), stored and copied into lineage; reject at submit without it.
- `preference`: `chosen` and `rejected` non-empty and not identical after whitespace
  normalisation.
- `reasoning`: `reasoning` and `answer` non-empty; reject when
  `reasoning.strip() == answer.strip()`. Whether the reasoning *supports* the answer
  is **human review**, not code — do not fake it.
- All types: PII / dedup / sampling gates run at ingest — **only meaningfully after 3d.**

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
field set switches per type. Language selects for translation (curated list + free
entry). Preference: prompt + two side-by-side answer boxes. Reasoning: prompt /
reasoning / answer + format tag + origin. "My contributions" shows the new types.
Request structs first (API rejects unknown JSON fields), then the form.

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
      shows the five task types, the language/origin/model_id CHECKs, and per-type non-empty CHECKs.
- [ ] A contributor can submit one of each new type from the UI; each appears in
      "my contributions" with the correct type label.
- [ ] `translation` with `source_language == target_language`, or without the rights
      attestation, is rejected (HTTP 4xx, field-level message in the form).
- [ ] `preference` with identical chosen/rejected is rejected.
- [ ] `reasoning` with `reasoning == answer` is rejected; `model`/`hybrid` without `model_id` is rejected.
- [ ] Bundling each type produces a source whose staged JSONL lines all pass
      `parse_canonical_sample` with the mappings in §1 (worker fixture test); `free_text`
      still bundles as plain text; a bundle cannot mix language pairs or origins.
- [ ] After ingest of a bundled canonical source: no `missing_text_field` risk reason;
      two identical QA pairs with different `sample_id`s are flagged as exact duplicates;
      the review screen shows readable text (§3d).
- [ ] Bundled `reasoning` records carry `reasoning_visibility: "review_only"` by default;
      an export of such a source contains **no** `reasoning_content`.
- [ ] Worker-level test: the bundled `preference` fixture passes `build_release_export`
      for purpose `preference` in `jsonl` format (proves the **export-time** canonical
      gate accepts it). The full UI path (bundle → ingest/PII/dedup/sample → sample review
      by a *different* user → source approval → `preference` release → freeze → export)
      is a separate half-day walk-through; budget it.
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

- **Moratorium (D1)** and the remaining dependency (TASK-001 first).
- **CI has been dead since 2026-07-16** — real failures on 07-25/07-29, then from 08-29
  the jobs stop starting entirely (billing block; three jobs, zero steps, no logs).
  A green local run is the ONLY verification you will get. Also note 12 of the 46
  `internal/repository` tests are skipped locally when `DERLEM_TEST_DATABASE_URL` is
  unset — including the release-contract test that guards this area. Set that variable
  against a scratch database before trusting `go test ./...`.
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

_(filled by the implementer)_
