# TASK-050 — Cross-source duplicate subtraction: remove documents already held by unrelated sources from a candidate, without re-deriving

| Field | Value |
|---|---|
| Status | **DONE — old candidate purge pending (owner)** — 2026-10-14: 1,149 cross-source duplicates subtracted without re-deriving; new candidate `97f300a9…` (6,601,402 documents) registered as `07a2b7e0-853b-4ce2-8a8c-653c1f31d921`; gates: PII clear, exact unique, **normalized dedup unique (0 external)**, `auto_checked`, 200-sample draw running; quarantined `b255c3d8…` to be purged by the owner |
| Kind | fix (derivation step) |
| Moratorium | allowed — the first real candidate is blocked at the dedup gate |
| Estimate | 1 day |
| Depends on | TASK-049 (DONE) |
| Owner | Derlem session (Claude, opus) |

## Why

The FineWeb2-HQ `tr-web-v4` (B) candidate `b255c3d8-9e3e-48db-8f0b-3f9bfe1ece06` (6,602,551
documents, object `a502b9dd…`) was quarantined by the normalized-document dedup gate on
2026-10-14: 1,149 of its documents (0.017 %) also exist in unrelated sources — the Faz-2 parent
corpus `gardash_faz2_tr_dedup_20260621` (1,149), `faz2_ham_tr_corpus_20260918` (865),
`faz2_ham_wiki_oscar_20260919` (289), `faz2_ham_ttk_20260918` (2). Both corpora come from Common
Crawl, so the same pages appear in both. The gate is right ("Soy Ailesi Tekrar Sayılmaz" in
`data_governance.md`: unrelated sources count) and stays as it is. The candidate must not carry
the overlap; the first-registered source keeps the document.

Re-running the full derivation with a drop list costs ~3 hours (signal tables were deleted after
the run). The selection list makes a cheaper, exact path possible: subtract.

## Scope

- **Drop list from the database (SELECT only):** candidate documents (`document_fingerprints`
  rows of `b255c3d8…`, `source_ordinal` = candidate line number) whose `normalized_sha256` exists
  in any source outside the candidate's lineage family (same family logic as the gate:
  `derived_from_source_id` + `source_lineage_inputs`, ancestors, siblings, descendants). Write it
  as `derlem.decision.v1` rows (`decision_type=duplicate`, `verdict=reject`, reason
  `cross_source_normalized_duplicate`, judge `normalized-document-sha256-v1`, plus the other
  source ids in the reason/extra) with a SHA in the manifest.
- **Subtract:** `python -m derlem_worker.selection subtract --manifest <selection manifest>
  --drop <decisions parquet> --out <new prefix>` → new selection list (train rows minus the drops,
  held-out partition unchanged), decisions = old decisions + drop rows, new manifest whose
  `parent` is unchanged and which records the subtraction (input selection SHA, drop SHA, count).
  Map candidate line ordinal → selection row → parent ordinal exactly; refuse if any mapping is
  ambiguous or a drop is not in the train partition.
- **Materialize** the new candidate from the shards (existing path); two runs, same SHA; the new
  candidate equals the old candidate file with exactly those lines removed (verify by streaming
  both).
- **Self-check before registering:** normalize every remaining line with the gate's own function
  and confirm 0 hits against the other sources' `normalized_sha256` set (SELECT).
- **Registration (prepared, run by Fable through the API):** extend `var/olcum-2026-10-13/task-049/kayit.py`
  or add a sibling that registers the new candidate (`…_trweb4B_xdedup_20261014`, pretrain,
  derived from `ba80dc1c…`, 10 % threshold before ingest). The existing held-out `ffde0f72…` stays
  (unique, sampled). **Purge plan** (dry-run only) for the quarantined `b255c3d8…` in
  `deploy/purge_plans/` — the owner runs `--execute`.
- Tests on a fixture: subtract = re-derive with the drop list (byte-identical selection, decisions,
  materialized text); held-out untouched; ambiguous / out-of-partition drops refused; control runs.

## Out of scope

- Changing the dedup gate. Re-deriving. Purging the Faz-2 sources (owner keeps them).

## Acceptance criteria

- [x] New candidate: 6,602,551 − n documents, n = drop count (≈1,149), SHA recorded, two
      materializations identical, line-by-line equal to the old file minus the drops.
      *(n = 1,149 → 6,601,402, `97f300a9…`)*
- [x] Self-check: 0 normalized overlaps with unrelated sources.
- [x] Registration and purge-plan dry run ready; after registration the dedup gate returns `unique`.
      *(2026-10-14: registered `07a2b7e0…` via the API, threshold 10 % before ingest; fingerprint job 23:05 → `unique`, duplicate_count 0; the job was interrupted once by a service stop at 21:25 and re-ran from the start.)*
      *(ready: `kayit_xdedup.py --kuru` passed, purge dry run clean; the gate result comes after
      `--calistir`)*

## Owner actions

- Run the purge `--execute` for the old quarantined candidate when handed over.

## Report

**2026-10-14 — Derlem session (Claude, opus).** Measurements and scripts:
`var/olcum-2026-10-14/task-050/`. Database: SELECT only (read-only transactions). Nothing written to
`var/storage`, services or git; registration `--calistir` and purge `--execute` NOT run.

### What changed

| File | Change |
|---|---|
| `selection.py` | New `subtract` command + `load_subtraction_drops()`; `materialize`'s loop moved into `_stream_selected()` (same checks, shared with subtract); `SelectionRecorder.record()` writes a ready decision row verbatim |
| `clean_candidate.py` | `--post-dedup-drop <decisions parquet>` (and `post_dedup_drop_path`): the re-derive counterpart of subtract — applied **after** the duplicate / near-duplicate decisions, before the held-out/train write; a held-out hit, a candidate-line mismatch or an unmatched entry stops the run. Report: `post_dedup_drop_path/_sha256/_entries`, `removed_post_dedup_drop_lines` |
| `worker/tests/test_selection_subtract.py` | new, 16 tests |
| `deploy/purge_plans/2026-10-14-karantina-aday.json` | purge plan for `b255c3d8…` (keeps the other 13 sources: 11 Faz-2/eval/sample sources, the parent `ba80dc1c…`, the held-out `ffde0f72…`) |
| `var/olcum-2026-10-14/task-050/` | `cikarma_listesi.py` (drop list), `kos.sh` (2 materializes + compare + self-check), `karsilastir.py`, `oz_denetim.py`, `kayit_xdedup.py`, `kontrol.py`, outputs/logs |

**Why "post-dedup" and not the existing `--drop-list`.** The old drop list acts before quality and
dedup, so a dropped document leaves the dedup state and its later copies would be selected — and
those copies carry the same normalized hash, i.e. the same cross-source overlap. Subtract keeps the
dropped document in the dedup record (its later duplicates stay rejected as copies of it); the
re-derive path does the same, which is why the two are byte-identical. Real data: 1 near-duplicate
rejection points at a dropped document (`rejections_referencing_dropped`: `near_duplicate:reject` 1,
`duplicate` 0) — under the old drop-list semantics it would have entered the candidate.

### Drop list (`cikarma_listesi.py`, DB snapshot 2026-10-14T16:58:07Z)

The gate's own family CTE (the script refuses to run if the text is not found verbatim in
`gate_jobs.py`) for `b255c3d8…`: family = `ba80dc1c…` (parent) + `ffde0f72…` (held-out sibling).
**1,149** candidate documents (= the gate's `external_duplicate_count`; internal 0); per other
source (a document can be in several): `gardash_faz2_tr_dedup_20260621` 1,149,
`faz2_ham_tr_corpus_20260918` 865, `faz2_ham_wiki_oscar_20260919` 289, `faz2_ham_ttk_20260918` 2.
The candidate object was streamed (whole-file SHA `a502b9dd…` verified, 6,602,551 lines); for every
dropped line the normalized SHA was recomputed with the gate's function and equals the DB value
(1,149/1,149), `doc_id` = line SHA256. Output: `var/derived/fineweb2hq_tur_ba80dc1c_trweb4B.xdedup-drop.decisions.parquet`
**`bb71032c207abd2445f09efb7298ee9a0333088688eb9429335f61cd14d394be`** (1,149 rows, `duplicate` /
`reject` / judge `normalized-document-sha256-v1`, reason `cross_source_normalized_duplicate;sources=<ids>`,
run `task-050-xdedup-20261014`, `source_ordinal` = candidate line number) + summary `….xdedup-drop.json`.

### Subtract

```bash
python -m derlem_worker.selection subtract \
  --manifest var/derived/fineweb2hq_tur_ba80dc1c_trweb4B.selection.manifest.json \
  --drop var/derived/fineweb2hq_tur_ba80dc1c_trweb4B.xdedup-drop.decisions.parquet \
  --out var/derived/fineweb2hq_tur_ba80dc1c_trweb4B_xdedup          # 394 s
```

Mapping: candidate line k → k-th `train` row of the selection (doc_id must match) → parent ordinal;
refused if a drop is in held-out, beyond the train partition, its doc_id differs or occurs twice in
the selection, a line/doc_id is listed twice, a row is not a `reject`, the parent ordinal already
has a decision row, the input SHAs differ from the manifest, or an output exists. Then the new
selection is hashed from the shards (expected materialization); held-out must be unchanged.

| | Old (TASK-049) | New (`…_trweb4B_xdedup`) |
|---|---|---|
| selection | `b2edd5b0…` 6,605,203 rows | **`6fe9cecc325c0952debd18ab7a564adbcbb07ca827c3f31b80e34fb59e7dd3d8`** 6,604,054 rows (train 6,601,402, held-out 2,652) |
| decisions | `5ae5aae2…` 2,126,293 rows | **`220ff753a34f3bd804eb227e9478301fe4ca65dac76c49ae52a20926268a04d6`** 2,127,442 rows (`duplicate:reject` 22 → 1,171) |
| train text | `a502b9dd…` 15,244,828,410 B, 6,602,551 lines | **`97f300a93cdacaffcfe952752be8d3109d0b39df2c9c37772c0ee6a682d695a0`** 15,243,666,531 B, 6,601,402 lines |
| held-out | `e498e6fb…` 2,652 | same (the registered `ffde0f72…` stays valid) |

New manifest `…_xdedup.selection.manifest.json`: `parent` unchanged; `subtraction` = method
`selection-subtract-v1`, input manifest/selection/decisions SHAs, input expected materialization,
drop SHA/rows/judge/run id, the 1,149 parent ordinals, `rejections_referencing_dropped`.

### Materialize, comparison, self-check (`kos.sh`)

- Materialize 1 (writes `var/derived/fineweb2hq_tur_ba80dc1c_trweb4B_xdedup.jsonl`, 6.5 min) and
  materialize 2 (hash only): both `97f300a9…` / 15,243,666,531 B / 6,601,402, held-out `e498e6fb…`.
- `karsilastir.py`: old file (SHA re-verified) and new file streamed together — at each of the 1,149
  dropped line numbers the old line's SHA equals the drop's doc_id and is skipped, every other line is
  byte-equal, both end together → `equal: true`.
- `oz_denetim.py` (DB snapshot 17:36:44Z, 15.5 min): every line of the new file through the gate's path (`_bounded_lines(262144)` → strip → `_document_from_line` → `document_fingerprint`): 6,601,402 distinct normalized hashes, internal duplicates 0, too short 0, oversized 0. Streamed all `normalized-document-sha256-v1` rows outside the family (`b255c3d8…`, `ba80dc1c…`, `ffde0f72…` excluded, family from the gate's CTE): **11,995,448 rows of 11 sources, 0 hits** (`gardash_faz2…` 6,007,823, `faz2_ham_wiki_oscar…` 4,253,736, `faz2_ham_tr_corpus…` 1,502,165, `faz2_ham_tdk…` 98,079, `faz2_ham_ttk…` 84,789, `faz2_ham_academic…` 45,208, evals/others 3,648). The same normalization reproduced the DB hash for all 1,149 dropped lines (drop-list step), so the 0 is not a function mismatch.

### Registration (prepared, NOT run — database write)

```bash
.venv/Scripts/python.exe var/olcum-2026-10-14/task-050/kayit_xdedup.py --kuru       # passed (kayit-kuru.txt)
.venv/Scripts/python.exe var/olcum-2026-10-14/task-050/kayit_xdedup.py --calistir   # API + worker running
```

Candidate only (held-out unchanged). Checks the manifest (subtract output, parent, MT B, no slice,
drop count = drop summary, held-out = `e498e6fb…`), the file SHA/size, `karsilastir.json` and
`oz-denetim.json` (0 hits, same SHA); then hard link into `var/import`, rights from the parent,
`POST /sources` `fineweb2_hq_tur_latn_clean_candidate_trweb4B_xdedup_20261014` (pretrain,
`derived_clean_corpus`, derived from `ba80dc1c…`) → **PUT threshold 10 % before ingest** → ingest.
`lineage_ref` names the old object only as `a502b9dd0fa9…`: a full 64-hex SHA in a source row would
make the purge keep the old object. Family for the new source = parent + siblings (`b255c3d8…`,
`ffde0f72…`), so the gate should return `unique` whether or not the purge ran first.

### Purge plan (dry run only)

`deploy/purge_plans/2026-10-14-karantina-aday.json` → `purge-dry-run.txt`: 1 source
(`b255c3d8…`), rows: `document_fingerprints` 6,602,551, `pii_scans` 1, `sources` 1,
`background_jobs` 4, `storage_objects` 1 (total 6,602,558); object `a502b9dd…` 15.24 GB to the
quarantine; no shared objects kept, no problems; 13 keep sources verified. Owner, after the new
candidate's dedup gate returns `unique` (PowerShell, repo root):

```powershell
$env:PYTHONPATH="worker/src"; $env:PYTHONIOENCODING="utf-8"; .venv\Scripts\python.exe -m derlem_worker.purge_sources --plan deploy/purge_plans/2026-10-14-karantina-aday.json --execute --quarantine-dir var\purge-quarantine\2026-10-14 --report var/olcum-2026-10-14/task-050/purge-execute.txt
```

The purge moves the store copy to the quarantine; the old text also exists as one more file, hard
linked as `var/derived/fineweb2hq_tur_ba80dc1c_trweb4B.jsonl` and
`var/import/fineweb2hq_tur_ba80dc1c_trweb4B.jsonl` (another 15 GB until both names are removed).

### Tests and control runs

- `DERLEM_SKIP_DB_TESTS=1 pytest worker/tests`: **640 passed, 37 skipped** (624 + 16).
- `test_selection_subtract.py` (TASK-049 shard fixture; drops = candidate lines 1 and 3, whose later
  normalized copy and near-copy exist): subtract = `derive_selection_list(post_dedup_drop_path=…)` =
  CLI `--post-dedup-drop` byte for byte (selection, decisions, expected SHAs); two materializes =
  text-copy re-derive = old text minus lines 1 and 3; held-out rows/text unchanged; old decision rows
  kept in order, drop rows at their parent ordinals with their own run id; the copy and near-copy
  stay rejected; manifest `subtraction`; determinism; refusals (held-out doc, line/doc_id mismatch,
  foreign doc_id, beyond train, line or doc_id listed twice, non-reject, missing line number, doc_id
  twice in the selection — line fixture with a repeated short line —, tampered decisions, existing
  output, output = input; re-derive: held-out, line mismatch, unmatched entry), no output left
  behind; subtract CLI.
- Control runs (`kontrol.py` → `kontrol-kosulari.json`, package copied to scratch, 3 test files,
  54 tests): untouched green; **19 mutations → 19 red** (each subtract/loader guard, drop rows
  appended instead of merged, candidate line kept as ordinal, input SHA check, overwrite checks,
  materialize core doc_id check, re-derive writing the drop with the run's id, held-out / line /
  unmatched guards, CLI flag not passed); restored green.

### Open

- Fable/owner: `kayit_xdedup.py --calistir`; confirm the gate returns `unique`; then the purge `--execute`.
- The jury rows of TASK-047 are keyed by text SHA; unaffected (no document text changed).
