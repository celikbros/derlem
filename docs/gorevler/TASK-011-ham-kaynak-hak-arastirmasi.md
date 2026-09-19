# TASK-011 — Rights research for the seven Faz-2 raw sources

| Field | Value |
|---|---|
| Status | **DONE (for v2)** — owner decision 2026-09-19: **S2, non-commercial use** (unknown-provenance `tr_corpus`/`celik_gold`-own lines and TRT out; `wiki_oscar`, `ttk`, `academic`, `tdk` in; owner risk acceptance for `academic`/`tdk`, scoped non-commercial). Recorded in [hak_kanit_paketi_2026_09.md](../hak_kanit_paketi_2026_09.md); applied by deriving v4 (TASK-012 follow-up). Re-open before any commercial use. Earlier: research half done 2026-09-19: [hak_kanit_paketi_2026_09.md](../hak_kanit_paketi_2026_09.md) (publisher terms read and quoted for every source that has one; TDK has none; celik_gold/tr_corpus unknown). Decision half (A/B/C) waits for the owner, before review session two. Was: READY — opened 2026-09-17 by the founder's decision ("rights research stays open as separate work; it will be done before the product ships") |
| Kind | research (data rights) |
| Moratorium | allowed — no new product surface; unblocks releases |
| Owner | (unassigned) |
| Blocks | any release that would include these sources |

## Goal

Decide, per source, what Derlem is allowed to do with it, and replace
`rights_status = 'unknown'` with a defensible value (`cleared`, `restricted` or
`blocked`) plus evidence.

## Why

The seven raw corpora behind Faz-2 are now in Derlem's custody
([ham_arsiv_faz2_kaynaklari.md](../ham_arsiv_faz2_kaynaklari.md)), registered
`unknown` as the safe default. `unknown` keeps them out of every release, so nothing
is at risk today — but the Faz-2 text derived from them is already in the store, and
a product that ships a model trained on it needs an answer to "where did this text
come from and what allows you to use it?".

## Scope

For each source: what it is, who holds the rights, under what licence the text may be
used for model training, and what evidence we can keep.

| Source | What it is | First questions |
|---|---|---|
| `wiki_oscar` | Wikipedia / OSCAR-style web text | Which dumps, which snapshot, which licence version; attribution and share-alike duties for a trained model |
| `tdk` | Dictionary/lexicon material | Terms of use of the source site; whether the extraction is a database right issue |
| `ttk` | Historical-institution texts | Publication licence; public-domain status by age |
| `academic` | Academic texts | Per-publisher; open-access status per document, not per corpus |
| `trt` | News (388 documents) | Broadcaster's terms; news text is rarely freely licensed |
| `tr_corpus` | Mixed Turkish text | Provenance unknown — needs the scraper code to reconstruct |
| `celik_gold` | Curated "gold" corpus | What went into it; it is the largest input and the least documented |

Inputs: the scraper code in `var/raw-derlem/celik_ai-kod/` (the only record of how
the corpora were collected), the shelf letter, and
[gardash_faz2_rights_decision.md](../gardash_faz2_rights_decision.md).

## Evidence found so far (2026-09-18, from the archived collector code)

`var/raw-derlem/celik_ai-kod/CELIK_AI/corpus_builder/sources.json` and the scrapers
declare the origins (not yet verified against the actual files):

| Source | Declared origin | Method |
|---|---|---|
| `wiki_oscar` (likely) | Hugging Face `allenai/c4` (mC4) and `wikimedia/wikipedia` | dataset download — **not own crawl** |
| `tdk` | `sozluk.gov.tr` | official JSON API |
| `ttk` | `belleten.gov.tr` | full-text scrape |
| `academic` | DergiPark | OAI-PMH abstracts |
| `trt` | `trthaber.com` | RSS |
| `celik_gold`, `tr_corpus` | no collector found | unknown |

So the premise of the 2026-07-07 `cleared` decision ("our own crawl of Turkish sites")
does not hold for the largest input. Next step: match each raw file to a collector by
content (field names, URL patterns) and read each publisher's terms.

## Report (research half, 2026-09-19)

Evidence pack: [hak_kanit_paketi_2026_09.md](../hak_kanit_paketi_2026_09.md). Measured/read:
mC4 = ODC-BY + Common Crawl terms (third-party copyright, AI-use indemnity); Wikipedia =
CC BY-SA 3.0 + GFDL (attribution, share-alike); Belleten = CC BY-NC 4.0 (non-commercial);
DergiPark = per-journal licences, no platform licence; TRT Haber terms forbid copying and
automated collection → `blocked`; TDK: no licence statement on sozluk.gov.tr or tdk.gov.tr;
`celik_gold`/`tr_corpus`: no collector, unknown. Options A/B/C written for the owner.

## Out of scope

- Re-collecting or replacing any corpus.
- Legal advice; the deliverable is evidence and a recommendation per source, and the
  founder decides.

## Acceptance criteria

- [ ] A per-source note: licence, evidence reference, recommended `rights_status`.
- [ ] Sources whose rights cannot be established stay `unknown` or become `blocked` —
      never silently `cleared`.
- [ ] `license_evidence_ref` on each source row points at that note.
- [ ] The decision is reflected in `docs/data_governance.md` if it changes a rule.
