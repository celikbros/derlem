# TASK-013 — Volume plan: where the next tokens come from

| Field | Value |
|---|---|
| Status | **PLANNED — 2026-09-19: [docs/hacim_plani_2026_09.md](../hacim_plani_2026_09.md); runs need owner go/no-go** — was READY (planning only), opened 2026-09-18 by owner decision ("start planning, open a card"); nothing is run |
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
There is no collector for `celik_gold`; its provenance stays unknown. **Corrected 2026-09-19:**
`tr_corpus` does have one — `celik_ai-kod/CELIK_AI/celik_data/celik_data/pipeline/download_tr_corpus.py`
in the archive reads an existing `tr_corpus.txt` and expands it with Wikipedia paragraphs
(`20220301.tr` / `20231101.tr`); the share that is Wikipedia text is being measured in
[TASK-038](TASK-038-tr-corpus-provenance-wikipedia-share.md). This does not change v4
(S2 drops those lines; the same text is kept as whole articles in `wiki_oscar`).

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
      — open: asked in the plan §5 (with the tokenizer and the 2× margin); waiting for the shelf's next letter.
- [x] Per-source rights position from TASK-011 (at least for C4, Wikipedia, DergiPark).
      — done: TASK-011 S2 decision (2026-09-19) for the seven raw sources, TASK-023 for the six
      Hugging Face datasets; positions used as decided in the plan §2.
- [ ] A dry run of each collector against **one** page/record to confirm the code still
      works (sites change); recorded as measured, not assumed.
      — not done: the archived collectors are out of scope for volume (hundreds of MB); the dry run
      that matters is TASK-032's one-record run of `import_hf_dataset`, and it needs the owner's decision.
- [ ] Disk/backup plan: raw archive is deliberately outside the backup scope; new raw
      data of tens of GB needs the same decision made explicitly.
      — open: decision requested in the plan §4 (measured 112 GB free, 2026-09-19 23:55; peak need
      ≈ 76,8 GB for the recommended slice; Derlem's recommendation: raw outside, derived inside).
- [ ] Owner go/no-go per collector.
      — open: the list is in the plan §6 (9 rows, source by source, with the numbers).

## HF veri setleri — lisans özeti (TASK-023)

Notlar: `docs/haklar/hf-*.md` (okuma tarihi 2026-09-19, veri indirilmedi, hukuki görüş değil).
Sıralama: beklenen **net yeni token / lisans riski** — önce en çok yeni hacmi en tanıdık
şartlarla getiren. Token sayıları kaba tahmindir (raf çevrimi 5,405 bayt/token; kartların
kelime/bayt beyanından). "Örtüşme" = ana korpustaki `wiki_oscar` (mC4 + Wikipedia) ile.

| # | Veri seti / Türkçe alt küme | Kart lisansı | Üst kaynak şartı | Sabit sürüm | Türkçe boyut (kart) | Kaba token | Örtüşme | Öneri `rights_status` | Not |
|---|---|---|---|---|---|---|---|---|---|
| 1 | [`HuggingFaceFW/fineweb-2` `tur_Latn`](../haklar/hf-fineweb-2.md) | ODC-By 1.0 | Common Crawl ToU (atıf + AI tazmin) | `af9c133…` | 95,1 M belge; 284,52 GB UTF-8; 41,9 B kelime | ~53 B | Hayır (dolaylı: aynı CC kökeni) | `cleared` (ticari olmayan; wiki_oscar kabulleri genişletilir) | Açık erişim; PII/opt-out formu; en iyi hacim/risk oranı |
| 2 | [`allenai/c4` mC4 `tr` (kalan kısım)](../haklar/hf-allenai-c4.md) | ODC-BY | Common Crawl ToU | `1588ec4…` | ~87,6 M satır; 110 GB gzip (1.024 dosya) | ~50 B (bunun ~%11'i elimizde) | **Evet, kısmen** — akışın ilk ~9,75 M belgesi `wiki_oscar`'da | `cleared` (ticari olmayan; mevcut karar) | Aynı şartlar zaten kabul edildi; net yeni ≈ 78 M belge |
| 3 | [`HPLT/HPLT2.0_cleaned` `tur_Latn`](../haklar/hf-hplt-monolingual.md) | CC0 (yalnız paketleme) | İçerik lisansı **yok**; IA + CC kökenli; takedown | `d1324a5…` | 116,6 M satır; 262 GB parquet; 51,7 B kelime | ~70 B | Hayır (çoğu Internet Archive) | `restricted` (kurucu risk kabulü gerekir) | Farklı köken → en yüksek net yeni; hak konumu zayıf |
| 4 | [`HPLT/hplt_monolingual_v1_2` `tr` cleaned](../haklar/hf-hplt-monolingual.md) | CC0 (yalnız paketleme) | Aynı | `dbe8882…` (yalnız yükleyici; veri hplt-project.org'da) | 27,05 M belge; 47 GB; 42,65 B kelime | ~9 B | Hayır | `restricted` | v2 varken gereksiz; veri dosyaları HF dışında |
| 5 | [`uonlp/CulturaX` `tr`](../haklar/hf-culturax.md) | Lisans alanı yok; "mC4 + OSCAR şartları" | mC4: ODC-BY + CC ToU; OSCAR: içerik lisansı yok | `6a8734b…` | 94,2 M belge; 64,3 B token | ~64 B (büyük kısmı mC4 ile aynı) | **Evet, kısmen** (mC4 bileşeni) | `restricted` | Alınmasın: aynı hacim #1 + #2 ile daha temiz |
| 6 | [`wikimedia/wikipedia` `20231101.tr`](../haklar/hf-wikimedia-wikipedia.md) | CC BY-SA 3.0 + GFDL | Wikimedia ToU (CC BY-SA 4.0 + GFDL) | `b04c8d1…` | 534.988 makale; 997 MB | ~0,2 B | **Evet, tamamen** (aynı config) | `cleared` (ticari olmayan; mevcut karar) | Net yeni ≈ 0; TASK-024 pilotu için sabit referans |
| 7 | [`oscar-corpus/OSCAR-2301` `tr`](../haklar/hf-oscar-2301.md) | CC0 (yalnız üstveri/paketleme) | İçerik lisansı yok; CC Kas/Ara 2022 | `c293046…` | 26,65 M belge; 73,7 GB; 8,29 B kelime | ~14 B | Hayır | `blocked` (erişim askıda) | Gated-manuel, onay verilmiyor; açılırsa `restricted` |

Kurucu kararı (2026-09-19; kurucu, 2026-09-19 gece: "önerilerin ok"), notlardaki önerilere göre: (a) #1 FineWeb-2 için
`wiki_oscar` kabulleri (atıf, Common Crawl tazmin maddesi, ticari olmayan kapsam) **genişletildi**
— alındığında `cleared` (ticari olmayan); (b) #3/#4 HPLT için risk kabulü **verilmedi** —
`restricted` kalır; CulturaX izlenmez, OSCAR `blocked`; (c) share-alike (yalnız Wikipedia)
S2 kararında zaten kabul. Liste onaylandı. **Hiçbir şey indirilmedi**; alım TASK-032 (onay ister)
ve TASK-024 pilotuyla gelir.

## Report

**2026-09-19 — the volume plan is written: [`docs/hacim_plani_2026_09.md`](../hacim_plani_2026_09.md).**
Planning only; nothing was downloaded, no collector and no service was started, no DB was touched.

### Today's volume

| | Number | How |
|---|---|---|
| v3 candidate | 11,896,793,726 bytes / 5,827,650 lines | measured (v3 manifest) |
| v4 (after the S2 filter) | **≈ 11.26 GB expected** (−5.39 % of v3 bytes) | **expected** — the v4 manifest did not exist at 23:58; only the temp output (2.91 GB) and the finished held-out part (4,323,687 bytes / 1,641 lines) were on disk. Replace with `output_byte_size` when the manifest lands. |
| v4 tokens | **≈ 2.08 B** | estimate (5.405 bytes/token, the shelf's conversion) |
| Gap to 2.6 B | **0.52 B tokens ≈ 2.80 GB clean text** | estimate |
| Gap to a labelled 2× margin (5.2 B) | **3.12 B tokens ≈ 16.85 GB clean text** | estimate |

Raw-text equivalent uses the measured v3 retention (87.7 % of input bytes survived the pipeline):
≈ 3.19 GB net-new raw text to reach 2.6 B, ≈ 19.21 GB for the 2× margin.

### Sources, ranked (plan §2)

FineWeb-2 `tur_Latn` (`cleared` non-commercial after the owner extended the `wiki_oscar`
acceptances; ~53 B tokens; 134.79 GB parquet in 30 shards) → mC4-tr remainder (`cleared`,
same terms already accepted; net-new ≈ 78 M documents ≈ 44 B tokens) → Wikipedia-tr (net-new
≈ 0; its value is the overlap-method pilot) → HPLT (`restricted`, risk acceptance **not**
given → counts as zero today) → CulturaX and OSCAR (out). The archived collectors
(TDK/TTK/DergiPark/TRT) are out of scope for volume: their own READMEs claim hundreds of MB.
Overlap is **unmeasured** everywhere and is measured by TASK-024's net-new-share method.

### Recommended sequence (plan §3)

1. **Wikipedia-tr pilot** (TASK-024): 0.55 GB download, ≈ 2.7 GB peak disk, expected net-new
   ≈ 0 — it measures the method, not volume.
2. **FineWeb-2 first slice: 2 shards = 8.99 GB parquet ≈ 18.97 GB text**, ≈ 16.63 GB after
   cleaning ≈ 3.08 B new tokens → ≈ 5.16 B with v4 (1.98× the target). Machine time from the
   measured rates (3.4 h / 13.57 GB = 15.0 min/GB; fastText 25 min / 13.5 GB = 1.85 min/GB):
   **≈ 7.6 h for the joint v4 + slice pass** plus ≈ 56 min for the language drop list; download
   time **unmeasured**. The joint pass produces a **v5** candidate, so it resets the 200-sample
   review — it belongs after the v2 delivery.
3. mC4-tr remainder, separate go/no-go, high-numbered files first.

### Disk is the binding constraint (plan §4)

Measured `df -h /c` on 2026-09-19 **23:55**: 933 GB total, 822 GB used, **112 GB free** (89 %).
Every new raw byte lives in three places (IMPORT_ROOT file + object-store copy + derived
candidate), plus the deletable compressed download. Peak for the recommended 2-shard slice
**≈ 76.8 GB** (67.8 GB if the parquet is deleted after conversion, 47.9 GB if the intake file is
hard-linked as `wiki_oscar` was) — it fits. **3 shards would need ≈ 109.6 GB and does not fit.**

### Open decisions

Backup scope for tens of GB of new HF raw data (plan §4; Derlem's recommendation: raw outside
the backup because a pinned revision + manifest makes it reproducible, derived objects that
enter a frozen release inside); the shelf's three answers (plan §5: target tokens per language
and whether a margin is wanted, the tokenizer for a real count, and the packing/boundary
question already drafted in `belge_sinirlari_politikasi.md` §6); and the nine-row owner
go/no-go list (plan §6).
