# TASK-010 — Take custody of the recovered objects and the Faz-2 raw sources

| Field | Value |
|---|---|
| Status | **IN PROGRESS** — 2026-09-17. Objects restored, raw archive taken and verified, duplicate removed, rules written. Source registration of the 7 raw corpora is the open part. |
| Kind | ops (data custody) |
| Moratorium | allowed — data custody, no new product surface |
| Owner | (unassigned) |
| Trigger | Two letters from the model shelf, hand-carried by the founder, 2026-09-17: `gardas-modeller/mektuplar/2026-09-17-raf-derlem-kayip-nesneler.md` and `…-ham-kaynaklar.md` |

## Goal

1. Put the 422 objects the shelf recovered back into the content-addressed store and
   close the "permanently lost" record.
2. Become the custodian of the seven Faz-2 raw sources, whose only copy sat in a
   backup folder the founder is about to delete.
3. Write down the two rules the founder asked for (raw archive outside the backup
   scope; no text is ever cleaned in place).

## Why

- The 422 objects were declared **permanently lost** on 2026-08-29 so the monthly
  restore drill would stop failing. They were not lost: every one of them was in the
  old OneDrive backup. "Permanently lost" is a decision, not a measurement.
- The seven raw sources are the only root from which Faz-2 can be rebuilt byte for
  byte. The local `gardash\` folder was deleted the same day, taking the
  source-labelled `gardash_tr_dedup.jsonl` (13.8 GB) with it — regenerable **only**
  from these seven files.

## Report

### 1. The 422 objects — DONE, 2026-09-17

- Independently verified in the recovery folder before touching anything:
  **422/422 files' SHA256 equals their filename**, 394,291 bytes, none corrupt.
- Measured against our own store: **422/422 were missing locally**; the database had
  a `storage_objects` row for **422/422** (414 `text/plain; charset=utf-8`,
  5 `text/plain`, 3 `application/json`). So only the files were gone; the catalogue
  was waiting for them, and restoring the files made the record consistent again.
- Copied into `var/storage/objects/sha256/<aa>/<bb>/<sha>` through a temporary
  `.incoming` file, hashing **after** the write and reading the final file back:
  422 copied, 422 verified, 0 failures. No database write was needed.
- `deploy/known_lost_objects.txt`: the 422 lines are gone; the file now states that
  the list is empty, and carries the history (2026-07-16 loss → 2026-08-29 list
  opened → 2026-09-17 closed). The drill treats an empty set as "every missing
  object is a problem", which is the strict behaviour we want back.
- `docs/backup_restore.md`: the known-lost section is marked closed, with the lesson.

### 2. Faz-2 raw sources — DONE (archive), 2026-09-17

- Copied (never moved — the recovery folder held the only copy) to
  `var/raw-derlem/`: `ham-derlem/` 24.65 GB / 10 files, `celik_ai-kod/` 158 files
  (the scrapers — the only record of how these corpora were collected), plus the
  recovery README.
- `sha256sum -c SHA256SUMS` in the copy: **9/9 OK**.
- Kept out of git (`var/` is ignored) and, by the founder's decision, out of the
  backup scope. Documented in [ham_arsiv_faz2_kaynaklari.md](../ham_arsiv_faz2_kaynaklari.md).
- Rights: every source will be registered `rights_status = 'unknown'` — such a source
  cannot enter a release. Research stays open as
  [TASK-011](TASK-011-ham-kaynak-hak-arastirmasi.md).

### 3. The 12.85 GB duplicate — DONE, 2026-09-17

`var/derived/gardash_faz2_tr_dedup_20260621_06ac330e_clean_candidate.txt` was
byte-identical to a store object. Verified here before deleting: hashed the file
(`ebe292793d87…0d989`, 12,850,383,067 bytes) and confirmed an object with that digest
and size exists in the store. No running code reads that path (`var/derived` is only
the default `--output-dir` of the clean-candidate script; the e2e test matches the
**source name** in the database, not the file). Deleted; 12 GB freed (114.4 → 126.4 GB).
Its 1,339-byte manifest was kept as the record of how the derivative was produced.

### 4. Rules written down — DONE, 2026-09-17

- `docs/data_governance.md`: **no text is ever cleaned in place.** Every cleaning step
  produces a new object, a new SHA256 and a new version name; models are trained only
  from a frozen release and that release's SHA goes into the model card. The design
  already worked this way (`derive_clean_candidate` refuses to overwrite its input,
  objects are immutable, frozen manifests cannot change retroactively); the founder
  asked for the rule to be written, not invented.
- `docs/backup_restore.md`: the raw archive is **deliberately** outside the backup
  scope, with the founder's reasoning and the accepted risk.

### 5. Open — source registration of the seven corpora

Not started. Order (founder's decision: small first, the two big ones last):
`trt` → `tdk` → `academic` → `ttk` → `tr_corpus` (~0.65 GB together), then
`celik_gold` and `wiki_oscar` (13.0 + 12.8 GB). Each goes through `IMPORT_ROOT` and
the admin-only local-file intake, `content_purpose = pretrain`,
`rights_status = unknown`, lineage pointing at the letter and the archive doc.
Expect the normalized-dedup gate to quarantine `celik_gold` as a duplicate: it is an
input of the Faz-2 text we already hold. That is the correct answer, not a bug.

### 6. Open — restore drill

Worth running now that the known-lost list is empty: it proves the chain check passes
without the exemption. It restores a dump into a **separate** `derlem_restore_drill`
database (the working database is untouched) and needs the founder's go-ahead plus
`BACKUP_PASSPHRASE` and the PostgreSQL binaries.
