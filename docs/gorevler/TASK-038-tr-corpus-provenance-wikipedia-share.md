# TASK-038 — `tr_corpus` provenance: how much of it is Wikipedia paragraphs

| Field | Value |
|---|---|
| Status | **DONE** — 2026-09-19, measured; result in `docs/hak_kanit_paketi_2026_09.md` |
| Kind | research |
| Moratorium | allowed — measurement, no product surface |
| Estimate | 0.5 day(s) |
| Depends on | TASK-016, TASK-022 (findings) |
| Owner | (unassigned) |

## Goal

Measure what share of `tr_corpus.txt` (1,502,165 lines, 457,814,564 bytes, S2: `unknown`,
dropped from v4) is text that also appears inside Wikipedia records of `wiki_oscar`
(`source = wikipedia`, CC BY-SA 3.0 + GFDL, already `cleared` non-commercial).

## Why

TASK-011 recorded `tr_corpus` as "collector not found". Two later findings contradict that:
the archived `celik_ai-kod/.../download_tr_corpus.py` reads an existing `tr_corpus.txt` and
expands it with Wikipedia (`20220301.tr` / `20231101.tr`) paragraphs; TASK-022 found 366 of
the first 500 `tr_corpus` lines to be substrings of `wiki_oscar` records. If most of
`tr_corpus` is Wikipedia text, its rights question largely falls away. It does **not** change
v4 (those lines are dropped; the same text is already kept as whole articles in `wiki_oscar`),
so this is evidence for TASK-011, not a re-derivation trigger.

## Scope

- Read-only scan of `var/raw-derlem/ham-derlem/tr_corpus.txt` and `wiki_oscar_corpus.jsonl`.
- Per `tr_corpus` line (whitespace-collapsed, casefolded): contained in some Wikipedia record /
  in some mC4 record / neither; line and byte shares; length distribution per class; 20 examples
  of "neither"; runtime.
- Result section appended to TASK-011's evidence packet (`docs/hak_kanit_paketi_2026_09.md`).

## Out of scope

- Changing `rights_status` of `tr_corpus` (owner decision after the number).
- Any re-derivation.

## Acceptance criteria

- [x] Shares (lines, bytes) for wikipedia / mc4 / neither, summing to 100 %; method and runtime written.
- [x] Recommendation line for the owner (keep `unknown`, or treat the Wikipedia share as covered).

## Report

**2026-09-19 — measured, read-only, one process.** Scripts and raw outputs:
`var/olcum-2026-09-19/task-038/` (`prep_lines.py`, `scan.py`, `scan2.py`, `report.py`,
`report2.py`, `report.json`, `report_merged.json`, `scan*.log`). Nothing under `var/derived`
or `var/import` was touched; no rights status was changed.

### Method

Normalisation on both sides, same code path (TASK-016 rule): whitespace runs collapsed to a
single space, stripped, casefolded, encoded utf-8. Every normalised `tr_corpus` line is
>= 50 bytes long, so no short-line special case was needed.

*Anchor index (exact, not a heuristic).* K = 8 byte windows of length L = 32, evenly spaced
over each line ("anchors"), are hashed to 64 bit (rolling polynomial hash over the byte
array, computed with a numpy `cumsum` over `b[i]·P^-i` and re-scaled by `P^i`, then a
splitmix64 finaliser) — 12,017,320 anchors for the 1,502,165 lines, held as a sorted
`uint64` array plus two 128 MB byte filters. `wiki_oscar` is streamed in 8 MB batches; all
length-32 windows of every record are hashed and looked up. If a line is contained in a
record then *every* window of the line — in particular all 8 anchors — occurs in that
record, so the scan cannot miss a containment; a (record, line) pair becomes a candidate at
>= 2 anchor hits (containment implies 8) and each candidate is then verified with an exact
`bytes in bytes` check against that record. Hash collisions can only add candidates, which
verification drops. Lines already found inside a Wikipedia record are pruned out of the
index, which is what keeps the run linear (12,017,320 → 2,087,640 anchors).

*Shingle rule (the approximate rule, measured against the exact one).* For candidate pairs
that fail the exact check, the line counts as "near-contained" when >= 95 % of its k-word
shingles (k = min(8, word count); lines with fewer than 8 words use their whole word
sequence as one shingle) occur in the record's k-word shingle set.

*Typography pass.* 40,5 % of the lines that matched nothing carry the typographic apostrophe
U+2019 while 0,00 % of the matched lines do. The residue was therefore re-scanned with the
same exact method after folding curly quotes/apostrophes, dashes and the ellipsis to ASCII
on both sides (`scan2.py`).

### Result (1,502,165 lines, 457,814,564 bytes; byte = raw line incl. newline)

Strict rule (exact containment, whitespace + casefold only):

| Class | Lines | Line share | Bytes | Byte share | len p10/p50/p90 (norm.) |
|---|---:|---:|---:|---:|---|
| (a) in a `wikipedia` record | 1,243,012 | 82,748 % | 369,389,846 | 80,685 % | 64 / 188 / 660 |
| (b) in an `mc4` record only | 1,452 | 0,097 % | 208,600 | 0,046 % | 58 / 75 / 288 |
| (c) neither | 257,701 | 17,155 % | 88,216,118 | 19,269 % | 61 / 192 / 793 |

Adding the >= 95 % shingle rule moves 5,384 lines (+0,36 pp) to (a) and 18 to (b).
Adding the typography folding moves a further 114,972 lines to (a) and 52 to (b):

| Class | Lines | Line share | Bytes | Byte share | len p10/p50/p90 |
|---|---:|---:|---:|---:|---|
| (a) Wikipedia | 1,357,984 | 90,402 % | 430,400,365 | 94,012 % | 65 / 205 / 699 |
| (b) mC4 only | 1,504 | 0,100 % | 223,365 | 0,049 % | 58 / 76 / 295 |
| (c) neither | 142,677 | 9,498 % | 27,190,834 | 5,939 % | 57 / 82 / 378 |

`wiki_oscar` itself: 4,253,739 records, 399,373 `wikipedia` (845 MB normalised) and
3,854,366 `mc4` (11,85 GB) — the 9,4 / 90,6 split TASK-016 sampled. 334,502,172 anchor hits
produced 26,027,947 candidate pairs, all verified exactly.

### Validation (2,000 random lines, seed 20260919)

An independent Aho-Corasick automaton over the 2,000 sampled lines was run across **every**
record in the same pass (exact multi-pattern substring search, no anchors involved). Ground
truth: 1,651 wikipedia, 1 mC4-only, 348 neither.

| Rule | TP | FP | FN | Precision | Recall |
|---|---:|---:|---:|---:|---:|
| anchor index + exact verify (used for the table) | 1,651 | 0 | 0 | **1,0000** | **1,0000** |
| >= 95 % shingle rule vs. exact containment | 1,651 | 8 | 0 | **0,9952** | **1,0000** |

The anchor method reproduces brute force exactly, as the construction argues. The shingle
rule's 8 false positives are real near-copies (the collector's `clean_wiki_text` strips
`'''bold'''`, `[[link|text]]`, `<ref>`), not noise — that is why it is reported as a separate
row and not folded into the headline number.

### 20 random class (c) lines (seed 20260919, truncated to 200 chars)

`[W]` = matched a Wikipedia record after the typography folding, `[-]` = matched nothing at
all. 10 of these 20 are `[W]`, in line with the 114,972 / 257,701 rate.

```text
[W] 76399   Bir süre sonra Şems, Mevlânâ Celâleddîn Rûmî’in oğlu Sultan Veled’in çağrısı üzere Konya’ya geri gelir. Mevlânâ bir daha şehirden ayrılmasın diye, onu bir kızla evlenmeye iknâ eder; bu kız Celâleddîn
[W] 85311   1889'da okuldan mezun oldu. Yaşamını yazarak geçirmeye karar verdi. Yazı hayatına 1891’de 21 yaşındayken yayımladığı André Walter'in Günlükleri (Les Cahiers d'André Walter) ve Narsis Üstüne İnceleme i
[W] 123700  1301'de Karl, İtalya’ya gelerek Bianchileri Popolo ve Nerilerin yararına ortadan kaldırmayı istediğinde ise, Papa tarafından Paciaro, yani barış getirici olarak ilan edildi. 1 Kasım’da Karl Floransa’y
[W] 130852  Saraybosna kütüphanesi İslam yazmaları kısmında 72 sayfalık bir Saltık-name yazması olduğunu G.Martin Smith bahsetmiştir. Şimdiye kadar altı nüshası tespit edilebilmiştir. Bunların içerisinde başı ve
[-] 185842  Bilim ve felsefe kavramlarının çoğu sıklıkla kültürel olarak ve sosyal olarak tanımlanır. Bu fikir Thomas Kuhn tarafından Bilimsel Devrimlerin Yapısı (1962) adlı kitabında detaylandırılmıştır. Peter L
[-] 468527  Pampaneira, İspanya'nın on yedi özerk bölgesinden, ülkenin en çok nüfusa sahip olan ve güney sınırında bulunan, Endülüs otonom bölgesine bağlı sekiz eyaletinden Akdeniz'e kıyısı bulanan Granada'ya bağ
[-] 553877  Davulbaz, Yozgat ilinin Akdağmadeni ilçesine bağlı bir köydür.
[-] 561152  Köy, Kastamonu il merkezine 62 km, Hanönü ilçe merkezine 8 km uzaklıktadır.
[W] 613697  Corcoran, John ve Weber, Leonardo, 2015. "Tarski sözleşme T: durum beta (Tarski’s convention T: condition beta)", South American Journal of Logic. 1, 3–32.
[W] 652674  Kare dalga kuvvet durumuna döndüğümüzde, birinci öğe 0.5 N’luk sabit bir kuvvettir ve frekans spektrumunda “0” Hz’lik bir değerle temsil edilir. Sonraki öğe ise 1 Hz’lik ve 0.64 genliğinde bir sinüs d
[W] 881915  Savaşın başlamasının hemen ardından Nazi işgaline karşı küçük bir direniş grubu kurar. Willem Dolleman ve Ab Menist ile birlikte kurdukları yapının adı Marx-Lenin-Luxemburg-Cephesi olur. Grup genelde
[W] 996806  1083 yılında Kutalmışoğlu Süleyman Şah Çukurova’daki Ermenileri itaat altına aldı. Bu tarihten itibaren bölgeye Türkmen akını hız kazandı. Bölgeye gelen bu Türkmenlerin yardımıyla da 1375 yılında Mekl
[W] 1026223 WPAT-FM veya bilinen ismi ile 93.1 Amor ABD’de İspanyolca yayın yapan bir radyo istasyonudur. 93.1 FM frekansından yayın yapan ve merkezi New Jersey eyaletinin Paterson şehri olan radyo ağırlıklı New
[-] 1108676 NGC 6608, Yeni Genel Katalog'da yer alan bir galaksidir. Gökyüzünde Ejderha takımyıldızı yönünde bulunur. Scd tipi bir sarmal galaksidir. Amerikan astronom Lewis A. Swift tarafından 1883 yılında 40,64
[W] 1160108 Semyon İvanoviç Aralov (Rusça: Семён Иванович Аралов) (18 (30) Aralık 1880 Moskova - 22 Mayıs 1969 Moskova) Sovyet asker, devlet adamı ve devrimci. Kızıl Ordu’ya bağlı istihbarat teşkilatı GRU kurucul
[-] 1182044 Daşdan tikilmiş şəhər (film, 2008) (Uzun metraj televizyon belgeseli) (İTV)
[-] 1207190 Tomasz Radzinski - Everton FC, Fulham FC - 2001-07
[-] 1230428 Lucille Désirée Ball (6 Ağustos 1911 - 26 Nisan 1989), özellikle I Love Lucy, The Lucy–Desi Comedy Hour, The Lucy Show, Here's Lucy ve Life With Lucy sitkomları ile tanınan, Amerikalı komedyen, sinema
[-] 1247007 Türkçe çevirisi: Marina, Kırmızı Kedi Yayınları, 2018, ISBN: 9786052982280
[-] 1334076 (10.02.1994) Efes Pilsen - Virtus Buckler Bologna: 83 - 77 (G)
```

Every one of them reads as Wikipedia (article paragraphs, village stubs, cast/reference
lists) — the `[-]` half is what the 20220301 dump has and the 20231101 dump in `wiki_oscar`
does not, plus list fragments that `wiki_oscar`'s copy formats differently.

### Runtime (one process, peak RSS ~1,6 GB, alongside the running derivation)

line prep 29 s · main scan **1,611 s** (26,9 min; parse 344 s, hash 285 s, lookup 269 s,
verify 341 s, validation automaton 252 s) · typography pass over the residue 2,187 s
(36,5 min) · reports ~60 s. **Total ≈ 64 min** for 12,81 GB + 458 MB.

### Recommendation for the owner (decision is the owner's)

`tr_corpus` is not "origin unknown": **94,0 % of its bytes are, byte for byte, Turkish
Wikipedia text that `wiki_oscar` already carries** (`cleared`, non-commercial, CC BY-SA 3.0 +
GFDL), 0,05 % is mC4 and 5,9 % (142,677 short lines, 27,2 MB — category lists, cast lists,
stub sentences, reference lines; median 82 bytes) matches nothing, most probably an older
Wikipedia dump (the collector reads `20220301.tr`, `wiki_oscar` carries `20231101.tr`).
Recommendation: **keep the source record at `unknown`** — v4 drops these lines anyway and
the same text is kept as whole articles in `wiki_oscar`, so nothing is gained by changing it —
but record in TASK-011's packet that the rights question for 94 % of `tr_corpus` is the
Wikipedia question, and that if `tr_corpus` is ever wanted back, the Wikipedia-contained
share can be admitted under the `wiki_oscar` terms while the 5,9 % residue stays out.
