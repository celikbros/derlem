# TASK-032 — In-app `import_hf_dataset` job: pinned revision, licence required, one record = one document, shard-resumable — Wikipedia-tr first

| Field | Value |
|---|---|
| Status | **DRAFT** — from the 2026-09-19 plan ([plan_2026_09.md](../plan_2026_09.md), Faz 4); needs the owner's approval before work starts |
| Kind | feature |
| Moratorium | **owner approval required** — owner ordering #2; new worker dependencies; HF token via env only |
| Estimate | 3 day(s) |
| Depends on | TASK-013, TASK-022, TASK-024, TASK-030 |
| Owner | (unassigned) |

## Goal

Import a Hugging Face dataset revision inside Derlem as a registered source with machine-readable licence, preserved document boundaries and reproducible bytes.

## Why

The only large volume lever (TASK-013 options 2–3). Rights (TASK-030), boundaries (TASK-022) and the overlap pilot (TASK-024) were done first so the new volume inherits neither the `celik_gold` problem nor the parent's flat lines.

## Scope

- Worker job `import_hf_dataset(dataset_id, config, split, revision)`: streaming download to `IMPORT_ROOT` by shard with per-shard SHA and resume; one document per record with paragraph breaks preserved in JSONL (never split); production manifest (repo, config, split, revision SHA, text field, record count, licence id, dataset-card snapshot SHA); register via the existing intake with `lineage_ref` = manifest, `license_id` from the card, `rights_status` per the licence note; gates follow.
- API endpoint + minimal admin/data_manager form fields (`DisallowUnknownFields`); progress counters like exports.
- Boundary rule per the policy note [belge_sinirlari_politikasi.md](../belge_sinirlari_politikasi.md) (TASK-022, §4): one record = one document, never split or merged; the text field only (title stays metadata); paragraph breaks kept as `\n` in the stored JSONL object and joined to a single space only by the txt export.
- Dry run of one record first (measured), then the full config.
- Tests with a local fixture dataset (no network): revision pinning, boundary preservation, resume after injected failure with identical SHA; control run. Docs `docs/hf_ice_alim.md`.

## Out of scope

- Reusing `mc4_scraper.py` as-is.
- mC4-tr (separate go/no-go after Wikipedia-tr is measured).
- Quality-filter changes (need TASK-020's number).

## Acceptance criteria

- [ ] Two runs of the same repo+revision → same object SHA256; source registered with `lineage_ref` containing the revision SHA and `license_id` set; zero documents shorter than the record boundary.
- [ ] Resume test: kill after N shards → rerun completes with identical output SHA.
- [ ] Measured in the card: bytes, documents, download and ingest minutes, MB/s, drop rates per reason, external duplicates against the family-excluded corpus, net-new tokens (into TASK-013).

## Owner actions

- Approve the card, the dependencies and the first dataset/revision; set the HF token in the worker env if needed; decide disk location and whether HF raw downloads are outside backup scope; go/no-go per dataset with disk numbers.

## Report

(not started)
