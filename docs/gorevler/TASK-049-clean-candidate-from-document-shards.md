# TASK-049 — Clean candidate from document shards: FineWeb2-HQ → first `tr-web-v4` pretrain candidate

| Field | Value |
|---|---|
| Status | **IMPLEMENTED — 200 k slice measured; full run waits for the owner's MT pair (A/B), registration waits for the full run** — 2026-10-13 |
| Kind | feature (derivation path) |
| Moratorium | owner approval given 2026-10-13 (delivery path for the first real candidate) |
| Estimate | 2 day(s) |
| Depends on | TASK-032 (import, DONE), TASK-044 (selection list, DONE), TASK-046 (`tr-web-v4`, MEASURED), TASK-048 (threshold, DONE) |
| Owner | Derlem session (Claude, opus) |

## Why

The FineWeb2-HQ import (`ba80dc1c…`, 8,578,808 documents, 105 `derlem.document.v1` shards) is a
raw source: PII-flagged (phone 108,729, e-mail 59,701, card 4,612, IBAN 326, TCKN 115), quarantined
by design. `clean_candidate` only reads line sources (txt/jsonl), so the raw source cannot become a
candidate, cannot be reviewed and cannot be frozen. The jury says 47 % junk before rules and 39 %
after `tr-web-v4`; the rules exist, the path from shards to a candidate does not.

## Scope

- `clean_candidate` accepts an **import-manifest source** (`derlem.import-manifest.v1` → shards via
  `import_manifest.py`): iterates documents in shard order (`source_ordinal` = shard index + row),
  reuses the same decision code path as the line reader: PII (the existing per-document PII
  decision; findings → `pii` decision, reject), `tr-web-v4` quality rules (`url` from
  `provenance.url`), exact duplicate by `doc_id`, near-duplicate SimHash (Hamming ≤ 3, same policy
  as v5), held-out rule `afacan-held-out-v1`, oversized/empty; writes the **selection list**
  (`derlem.selection.v1`) + decision rows (`derlem.decision.v1`, judge `tr-web-v4@<sha>`) + manifest
  with `quality_judge`, source manifest SHA, policy ids, interpreter/zlib (as v5's manifest does).
- `selection.materialize` works from shards (text per `doc_id`/ordinal), producing the candidate
  **text object** (one document per line, `\n` inside documents escaped exactly as the Faz-2 line
  format does — check `releases.py`/`canonical_exports.md` for the line contract) and the held-out
  object; both deterministic (same input → same SHA, two runs).
- Registration: the candidate and held-out are registered the way v5 was (derived source with
  `derived_from_source_id`, `lineage_ref` = derivation manifest, `content_purpose` pretrain /
  holdout, rights inherited from the parent's note) — follow the v5 registration script/notes
  (`docs/temiz_aday_v3.md`, `var/olcum-2026-09-21/v5/` if still present, `hak_kanit_paketi`); the
  existing gates (PII, dedup, sampling, 200-sample review with the 10 % threshold) then run on the
  candidate through the normal path. **Registration writes the DB: the agent prepares the command,
  the owner or Fable runs it.**
- Measurement on a 200 k-document slice first (time, drop rates per decision type, SHA stability),
  then the full-run command + estimate; the **full run is launched only after the owner picks the
  MT target pair (A: 5 % cap / B: 7.5 % cap, TASK-046)** — the thresholds are a policy constant.
- Tests: shard reader = line reader on the same documents (byte-identical selection + decisions for
  a fixture with PII/dup/near-dup/oversized/empty/MT/commercial cases); determinism; materialize
  from shards = text copy; control runs for each guard.

## Out of scope

- Freezing a `document_shards` source directly (the candidate is a text object; the existing
  freeze/export path applies). Tokenized export (TASK-033). Jury in-job judging (TASK-047 API path).

## Acceptance criteria

- [x] `clean_candidate --selection-list` runs on the FineWeb2-HQ import manifest; decisions per
      type counted; manifest reproducible (two runs → same selection-list and decisions SHA).
      *(200 k slice; full run waits for A/B)*
- [x] Materialized candidate text object + held-out object, SHAs recorded; a second materialize
      gives the same SHAs. *(200 k slice)*
- [x] 200 k slice measured (time per 100 k docs, drop rates); full-run estimate written.
- [ ] Registration command prepared; after the owner runs it the candidate shows on the source
      list with gates running. *(prepared and dry-run on the slice; owner runs it after the full run)*

## Owner actions

- Pick the MT target pair (A/B, TASK-046) before the full run.
- Run the registration command when it is handed over (database write).

## Report

**2026-10-13 — Derlem session (Claude, opus).** Measurements: `var/olcum-2026-10-13/task-049/`
(`olc.py` steps, `olcum-*.json`, `kontrol-kosulari.json`). Nothing written to the database,
`var/storage`, services or git.

### What changed

| File | Change |
|---|---|
| `import_manifest.py` | `CANDIDATE_LINE_FORMAT = "derlem.candidate-line.v1"`, `candidate_line()` (`{"text","url"}`, sorted keys, compact, UTF-8 unescaped, LF), `manifest_candidate_lines()` (the `_bounded_lines` contract from shards: ordinal = document `source_ordinal`, oversized = line bytes + LF > limit, every shard SHA-verified, optional document limit), `manifest_shards_covering()` |
| `clean_candidate.py` | Input that is an import manifest is read from shards through the **same loop** (`store_root`; `--source-id` uses the configured store, `--input-path` needs `--store-root`, refused otherwise). PII: for JSON-record lines the extracted text is scanned too (union, per-key max) — a number split by `\n` is invisible in the escaped line. New `--decided-at` (with `--run-id` → reproducible decisions file); `--limit-lines` allowed in selection mode only for import-manifest slices (`document_limit` in the manifest). Report: `machine_translation_target`, `input_kind`, `import_manifest`; selection manifest: `parent.kind/line_format/store_root/shards/document_limit`, `policies` |
| `selection.py` | `materialize` reads an import-manifest parent from the listed shards (SHA-verified; refuses if the list differs from the import manifest or the line format is unknown); `--store-root`; method `import-manifest-candidate-lines-by-ordinal-sha256-verified-v1` |
| `machine_translation.py` | `THRESHOLD_SETS = {"A": cap 5 % (unchanged values), "B": cap 7.5 % (olc-mt.json `frontier["7.5"]`: strong 14‰, "Bu," 4‰)}`, **`MT_TARGET = "A"` — the one policy constant**, `THRESHOLDS = THRESHOLD_SETS[MT_TARGET]`. The file is in `RULE_SOURCE_FILES`, so the choice enters the judge id: A = `tr-web-v4@288f5da2f783`, B = `tr-web-v4@4559662a171d` (was `@bb0e396ee7b5`; A verdicts are unchanged, only the file bytes) |
| tests | new `test_clean_candidate_shards.py` (14); `test_quality_v4.py`: both pairs pinned, boundary tests follow `MT_TARGET`, A/B difference test |
| `docs/belge_kaydi_v1.md` | §6.1 shard sources |

**Line format decision.** The candidate is JSONL, one document per line: `{"text": …, "url": …}`.
Paragraph breaks are JSON-escaped, text never rewritten (the TXT export flattens them as for every
source; JSONL export keeps them). `url` is in the line because `tr-web-v4` reads it — that is what
makes the shard reader and the line reader give byte-identical decisions, and the candidate
re-filterable on its own. The Common Crawl `id` is **not** in the line: the PII gate scans whole
lines and the uuid's digit groups match the phone/card patterns (139 of the first 30,000 documents,
0.46 %, all false hits); it is recoverable from the ordinal. Cost of `url` in the line: URL-borne
PII hits (225 / 200 k = 0.11 %, mostly long numeric ids read as card/phone, a few real e-mails in
URLs) are dropped — conservative and consistent with the candidate's own PII gate. `doc_id` in the
selection/decision files = SHA256 of the candidate line (as for line sources), **not** the document
record's text SHA; the held-out rule applies to the candidate line bytes.

**v1–v5 unchanged:** the PII union only runs when the extracted text differs from the line (JSON
records). In the v5 parent (6,027,968 lines) that never happens (`olcum-v5-json-satir.json`: 0).

### 200 k slice (first 200,000 documents = shards 0–1 + 29,686 of shard 2; tr-web-v4, held-out `afacan-held-out-v1`, SimHash Hamming ≤ 3, max 262,144 bytes)

Five runs in parallel (one process each) while the worker ran `index_document_fingerprints`:

| Run | Time | s / 100 k docs | selection SHA | decisions SHA |
|---|---:|---:|---|---|
| shard reader A, run 1 | 1,375 s | 688 | `5b118ab0…5d3b7e` | `2f9fe922…584441` |
| shard reader A, run 2 | 1,381 s | 691 | `5b118ab0…5d3b7e` | `2f9fe922…584441` |
| **line reader** A (same 200 k as JSONL, `dilim.jsonl` `361d81ff…`) | 1,365 s | 683 | `5b118ab0…5d3b7e` | `2f9fe922…584441` |
| line reader A, **text copy** (old path) | 1,360 s | 680 | — | — |
| shard reader **B** | 1,364 s | 682 | `86e1c17b…945824` | `a960b910…d3c7539` |

Expected/materialized text (A): candidate `b72fcbe28e42c5d323603eb823c30e095563156697383189259b763bccdfdac1`
(463,027,720 bytes, 174,980 lines), held-out `68c91b1cc233d121b1bcda7cd4cff25c5ea70701caded481ba11f32c00c87daf`
(97,262 bytes, 62 lines) — identical in both shard runs, the line-reader selection run and the old
text copy; **two materializes from shards: same SHAs, byte-for-byte equal to the text copy**
(`olcum-mat.json`, 13.6 s each). B: candidate `7ff4d8df…b06fa38` (438,376,786 bytes, 169,946 lines),
held-out `4e92a080…bf337580` (61 lines). Selection list 6.5 MB + decisions 0.9 MB (1.6 % of the text).
Bucket overflow 0.

Drop rates (documents counted once by their first decision; bytes = text UTF-8 bytes; slice
585,171,485 bytes):

| Decision | A docs | A bytes | B docs | B bytes |
|---|---:|---:|---:|---:|
| `pii` | 1,953 (0.98 %) | 2.25 % | same | same |
| `quality_rule` (tr-web-v4) | 22,964 (11.48 %) | 19.02 % | 27,999 (14.00 %) | 23.13 % |
| — of which `machine_translation` | 19,819 (9.91 %) | 14.84 % | 25,106 (12.55 %) | 19.43 % |
| — `commercial_page` | 3,159 (1.58 %) | 4.36 % | same | same |
| — v3 reasons (wiki markup 950, navigation 234, encoding 80, …) | ≈ 1,380 | ≈ 2.9 % | same | same |
| `duplicate` (normalized) | 0 | 0 | 0 | 0 |
| `near_duplicate` | 2 | 0.003 % | 2 | 0.003 % |
| `oversized` (> 262,144 line bytes) | 39 (0.02 %) | 2.83 % | same | same |
| `empty_text` | 0 (a shard cannot hold an empty document) | | | |
| **dropped total** | **24,958 (12.48 %)** | **24.10 %** | **29,993 (15.00 %)** | **28.21 %** |
| kept (train + held-out) | 175,042 | 444.2 MB text | 170,007 | 420.1 MB |

PII gaps measured on the slice: 15 documents have PII only in the text (number split by a line
break — caught by the union), 225 only in the line (URL). The slice is **not representative for
MT**: shards 0–2 are early-dump-heavy (TASK-046 full pass: MT 10.2 % docs / 15.8 % bytes in shards
0–2 vs 17.2 % / 30.6 % corpus-wide) — near-duplicates are also under-counted in any slice.

### Full run: command and estimate (NOT started)

```bash
# 1. owner picks A or B: worker/src/derlem_worker/machine_translation.py -> MT_TARGET = "A" | "B"
# 2. from the repo root (Git Bash):
bash var/olcum-2026-10-13/task-049/tam_kosu.sh A      # or B; refuses if MT_TARGET differs
```

The script runs `clean_candidate --source-id ba80dc1c-… --output-path var/derived/fineweb2hq_tur_ba80dc1c_trweb4<X>.jsonl
--quality-policy tr-web-v4 --held-out-rule afacan-held-out-v1 --near-dedup --selection-list
--run-id task-049-fineweb2hq-trweb4<X> --decided-at <start, UTC>`, then `selection materialize`
twice (write + hash only) and asserts the two outputs match. DB: SELECT only.

| | Estimate |
|---|---|
| Selection pass | 8,578,808 docs × 6.9–10 ms ≈ **17–24 h** single process (6.9 ms measured under 5-way load; 10 ms in a 3,000-doc probe). Quality rules ≈ 80 %, SimHash ≈ 10–35 % of the time (profile). Memory ≈ 1.5–2 GB (fingerprint dict + SimHash index) |
| Materialize | ≈ 10–15 min each (13.6 s / 200 k) |
| Candidate size (A) | corpus-wide drop ≈ 34.9 % bytes tr-web-v4 (TASK-046 sample, final code) + ≈ 2.2 % PII + ≈ 2.8 % oversized → **≈ 6.8–6.9 M documents, ≈ 15.2 GB text ≈ 15.7 GB JSONL**; held-out ≈ 2,700 docs, ≈ 7 MB |
| Candidate size (B) | MT drops ≈ 1.3× A's (slice ratio) → **≈ 6.4–6.5 M documents, ≈ 13.6 GB JSONL** |
| Selection + decisions files | ≈ 300 MB + ≈ 50–150 MB |
| Disk | ≥ 50 GB free (candidate + ingest copy on Windows + store object); 152 GB free now |

A parallel pre-compute of the per-document pure work (PII, rules, fingerprint, SimHash) with the
order-dependent decisions kept in one process would cut the selection pass to ~3–4 h on 8 cores;
not done (moratorium; serial is the path the equivalence is proven on).

### Registration (prepared, NOT run — database write)

```bash
.venv/Scripts/python.exe var/olcum-2026-10-13/task-049/kayit.py A --kuru       # verify + print requests
.venv/Scripts/python.exe var/olcum-2026-10-13/task-049/kayit.py A --calistir   # API + worker running
```

Same path as v5 (`var/olcum-2026-09-21/v5/v5_kayit.py`): checks both text objects against
`expected_materialization`, refuses a slice manifest (`document_limit`) or a wrong MT target,
hard-links into `var/import`, reads the parent through the API and copies its rights fields
(`odc-by`, `rights_status` as the parent — today `unknown`, owner decision pending in
`docs/haklar/hf-fineweb2-hq.md` §8 — evidence note, language, domain), creates
`fineweb2_hq_tur_latn_clean_candidate_trweb4<X>_<date>` (pretrain, `derived_clean_corpus`,
`derived_from_source_id` = `ba80dc1c…`, `lineage_ref` = derivation summary: import-manifest SHA,
line format, judge, MT target, policies, selection/decision SHAs and run id, selection-manifest
SHA, interpreter/zlib, output SHA) → **PUT threshold 10 % before ingest** → ingest; then the
held-out (`holdout`, `derived_heldout`) → ingest. Gates (PII, dedup, sampling, 200-sample review
with 10 %) then run the normal way. Dry run on the slice: `kayit-kuru-dilim.txt`.

### Tests and control runs

- `DERLEM_SKIP_DB_TESTS=1 pytest worker/tests`: **606 passed, 37 skipped** (591 before + 14 new in `test_clean_candidate_shards.py` + 1 new in `test_quality_v4.py`).
- `test_clean_candidate_shards.py`: fixture with clean (paragraph breaks), e-mail PII, number split
  by `\n` (text-only PII), e-mail in URL, oversized, MT via URL (same text without signature URL
  is kept), strong-profile MT, commercial, normalized duplicate (same text, other URL),
  near-duplicate, held-out, three shards — shard reader = line reader byte-for-byte (selection,
  decisions, expected SHAs, oversized list); text copy from shards = line text copy = two
  materializes; determinism; oversized LF boundary; document limit + shard list; tampered shard,
  shard-list mismatch, unknown line format, foreign doc_id refused; missing store root refused;
  CLI reproducible with `--run-id/--decided-at`, guarded.
- Control runs (`kontrol.py` → `kontrol-kosulari.json`, package copied to scratch, 3 test files,
  112 tests): untouched green; **15 mutations → 15 red** (line format ±id/url, LF boundary,
  limit, shard SHA check, manifest not recognised, PII union off, materialize shard-list / line
  format / routing checks, shard list not written, `--decided-at` ignored, `THRESHOLDS` not
  following `MT_TARGET`, B values drifting); **`MT_TARGET = "B"` alone → green** (the one-line
  owner choice); restored green.

### Open

- Owner: pick A or B (`MT_TARGET`), then run `tam_kosu.sh`, then `kayit.py --calistir`.
- Parent `rights_status` is `unknown` (HQ licence note §8 decision) — the candidate inherits it.
- The decision rows use the candidate-line SHA as `doc_id`; joining them with jury rows keyed by
  the document text SHA (TASK-047) needs the ordinal (or a recomputation).
- `var/olcum-2026-10-13/task-046/kontrol_kosulari.py` no longer applies as-is (`min_words=75`
  now occurs twice in `machine_translation.py`); TASK-046's results stand.
