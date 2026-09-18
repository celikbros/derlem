# TASK-013 — Volume plan: where the next tokens come from

| Field | Value |
|---|---|
| Status | **READY (planning only)** — opened 2026-09-18 by owner decision ("start planning, open a card"); nothing is run |
| Kind | plan (data acquisition) |
| Moratorium | planning is allowed; running any collector needs a separate owner decision |
| Owner | (unassigned) |
| Blocked by | [TASK-011](TASK-011-ham-kaynak-hak-arastirmasi.md) for every source that would be re-collected |

## Why

Shelf letter 2026-09-17 §5: after cleaning, the whole corpus is ~2.28 B tokens (their
conversion, 5.405 bytes/token), below the ~2.6 B a single training run of a 130 M model
wants. Cleaning changes composition, not volume. The next unit of work is volume.

## What we hold (inventory, measured 2026-09-18)

`var/raw-derlem/celik_ai-kod/CELIK_AI/corpus_builder/` — the collectors that produced
the Faz-2 raw sources, with `sources.json` as the control panel and a step-by-step
README. Collectors and their targets, **as declared in the code** (not verified live):

| Collector | Target | Method | README's own size/time claim |
|---|---|---|---|
| `mc4_scraper.py` | Hugging Face `allenai/c4` (mC4) + `wikimedia/wikipedia` dumps | dataset download, 18 languages, tr cap 9.75 M docs | "~35 GB, 1–4 weeks" |
| `tdk_scraper.py` | `sozluk.gov.tr` (TDK dictionary) | JSON API (`autocomplete.json`, `gts?ara=`) | "~50 MB, 2–4 h" |
| `ttk_scraper.py` | `belleten.gov.tr` full texts | web scrape (`/tam-metin/{id}`) | "~200 MB, 3–6 h" |
| `academic_scraper.py` | DergiPark | OAI-PMH abstracts | — |
| `news_scraper.py` | `trthaber.com` | RSS feeds | — |

A second, older copy of the same collectors sits in `celik_training/data_pipeline/`.
There is no collector for `celik_gold` or `tr_corpus`; their provenance stays unknown.

**Consequence for TASK-011:** the "own crawl" premise of the 2026-07-07 rights decision
is contradicted by the code: the largest input is a third-party dataset download
(C4/mC4 under its own terms, Wikipedia CC BY-SA), and the rest are scrapes of
institutional sites with their own terms of use.

## Options to plan (not decided)

1. **Re-run existing collectors** (TDK, TTK, DergiPark, TRT) — small yield (hundreds of
   MB), same rights questions, but the code exists.
2. **mC4/Wikipedia Turkish** — the only large lever; licence terms are documented by the
   publishers, which makes the rights work tractable. Wikipedia alone is a few GB of
   Turkish text; mC4-tr is tens of GB before filtering.
3. **Other licensed corpora** (OSCAR, HPLT, FineWeb-2 tr subsets) — same class as 2;
   requires per-dataset licence review.
4. **Contribution platform** — human-written data; high quality, low volume; already
   live at office scale.

## What this card must produce before anything runs

- [ ] Target size from the shelf (tokens, per language) and the product deadline.
- [ ] Per-source rights position from TASK-011 (at least for C4, Wikipedia, DergiPark).
- [ ] A dry run of each collector against **one** page/record to confirm the code still
      works (sites change); recorded as measured, not assumed.
- [ ] Disk/backup plan: raw archive is deliberately outside the backup scope; new raw
      data of tens of GB needs the same decision made explicitly.
- [ ] Owner go/no-go per collector.
