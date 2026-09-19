# TASK-023 — Licence notes for Turkish Hugging Face datasets in the TASK-011 format

| Field | Value |
|---|---|
| Status | **DONE (research) 2026-09-19** — 6 notes in `docs/haklar/hf-*.md` (7 datasets; HPLT v1.2 and v2.0 share one note), summary table in [TASK-013](TASK-013-hacim-plani.md). Owner actions (shortlist confirmation, acceptance of attribution-only / share-alike / "packaging-only CC0" terms) still open. Was: DRAFT — from the 2026-09-19 plan ([plan_2026_09.md](../plan_2026_09.md), Faz 2) |
| Kind | research |
| Moratorium | allowed — research |
| Estimate | 1 day(s) |
| Depends on | TASK-011 |
| Owner | (unassigned) |

## Goal

One evidence note per shortlisted Turkish dataset (Wikipedia, mC4/C4, 2–3 others such as OSCAR/HPLT/FineWeb-2 tr) so the same registry fields can hold them and the volume plan can rank them.

## Why

Owner decision #2: each dataset arrives with a documented licence. Card licences can be looser than the upstream content licence; the note records both and recommends on the stricter.

## Scope

- Per dataset `docs/haklar/hf-<dataset>.md`: dataset-card licence, upstream content licence, pinned revision/snapshot, redistribution/attribution/share-alike duties, Turkish subset bytes, recommended `rights_status`, and an 'already inside the parent?' flag (`wiki_oscar` was an mC4 + Wikipedia download).
- Summary table in TASK-013 ordered by expected net-new tokens per licence risk.

## Out of scope

- Downloading anything (TASK-024).
- Legal advice.

## Acceptance criteria

- [x] ≥ 4 notes with licence id, evidence URL + retrieval date, pinned revision, Turkish bytes, recommended status and overlap flag. (6 notes, 7 datasets, 2026-09-19)
- [x] Summary table present in TASK-013. (section "HF veri setleri — lisans özeti (TASK-023)")

## Owner actions

- Confirm the shortlist; decide whether share-alike and attribution-only terms are acceptable for the shelf's use.

## Report (2026-09-19)

Method: each dataset card read on huggingface.co (page, raw `README.md`, HF API for commit sha
and gating, datasets-server / tree API for Turkish file sizes) plus the upstream terms pages
(Common Crawl ToU, ODC-BY 1.0, CC BY-SA 3.0, CC0, Wikimedia ToU, oscar-project.org,
hplt-project.org). Nothing downloaded. No legal advice; terms recorded as written.

| Note | Card licence | Upstream content terms | Pinned revision | Turkish size (card) | Recommended `rights_status` | Already in parent? |
|---|---|---|---|---|---|---|
| [hf-wikimedia-wikipedia.md](../haklar/hf-wikimedia-wikipedia.md) `20231101.tr` | cc-by-sa-3.0 + gfdl | Wikimedia ToU: CC BY-SA 4.0 + GFDL | `b04c8d1ceb2f…` | 534 988 rows, 997 254 242 bytes | `cleared` (non-commercial; attribution + share-alike accepted in S2) | **yes, fully** (same config; 9.4 % of `wiki_oscar` records) |
| [hf-allenai-c4.md](../haklar/hf-allenai-c4.md) mC4 `tr` | odc-by | Common Crawl ToU (third-party copyright, AI indemnity) | `1588ec454efa…` | ~87.6 M rows est.; 110.0 GB gzip measured (card gives no per-language size) | `cleared` (non-commercial; existing S2 acceptance) | **yes, partially** — first ~9.75 M docs of the stream are in `wiki_oscar` (90.6 % of records) |
| [hf-oscar-2301.md](../haklar/hf-oscar-2301.md) `tr` | cc0-1.0 (metadata/packaging only) | none granted; Common Crawl Nov/Dec 2022; local TDM/research exception | `c2930464071f…` | 26 654 330 docs, 8.29 B words, 73.7 GB | `blocked` — access gated-manual and suspended; would be `restricted` if reopened | no |
| [hf-hplt-monolingual.md](../haklar/hf-hplt-monolingual.md) v1.2 `tr` / v2.0 `tur_Latn` | cc0-1.0 (packaging only) | none granted ("we do not own any of the text"); Internet Archive + Common Crawl; takedown policy | v1.2 `dbe88820461d…` (loader only, data on hplt-project.org); v2.0 `d1324a5283f7…` | v1.2 cleaned 27.05 M docs / 47 GB; v2.0 116 566 047 rows / 262.2 GB parquet, 51.7 B words | `restricted` (owner risk acceptance needed) | no (different origin) |
| [hf-fineweb-2.md](../haklar/hf-fineweb-2.md) `tur_Latn` | odc-by | Common Crawl ToU; 96 snapshots 2013–2024; PII/opt-out form | `af9c13333eb9…` | 95 129 129 docs, 41.9 B words, 284.52 GB UTF-8 / 125.53 GB disk (134.8 GB parquet measured) | `cleared` (non-commercial; extend S2 acceptance in writing) | no (indirect Common Crawl overlap unmeasured) |
| [hf-culturax.md](../haklar/hf-culturax.md) `tr` (optional) | **no licence field**; "follows mC4 and OSCAR" | mC4 + OSCAR terms; gated-auto form with liability acknowledgement | `6a8734bc69fe…` | 94 207 460 docs, 64.3 B tokens | `restricted` — recommend not pursuing | **yes, partially** (mC4 component) |

Findings that matter for the volume plan: FineWeb-2 `tur_Latn` alone (~53 B tokens rough,
same licence class as the already-accepted mC4) is far above the ~2.6 B target; the mC4 `tr`
remainder is the second lever under terms already accepted; HPLT v2 is the largest
different-origin source but its publisher grants no content licence at all. Wikipedia adds no
volume (fully inside the parent) but is the right fixed reference for the TASK-024 overlap
pilot. OSCAR cannot be obtained today. Could not verify: OSCAR's gated README (401; licence text
taken from the HF API `extra_gated_prompt` and oscar-project.org instead); hplt-project.org's
v2.0 Turkish row disagrees with the HF card, so the card numbers were used; the datasets-server
size call for `fineweb-2/tur_Latn` timed out, so card + tree-API figures were used.
