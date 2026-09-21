# Yeni-tutulanlar denetimi - yanlis-tutma orani (TASK-040)

**Puanlama:** 2026-09-21T20:59:25+00:00 · **Cetvel:** `C:\CELIKBROS PROJECTS\derlem\var\olcum-2026-09-21\task-040-yeni-tutulanlar-siki\2026-09-21-yeni-tutulanlar-siki-dolu.csv` (SHA256 `68d21e02aaf60c093d46ca4ccb1a4ef8e2b9ce28c0aa634579cc814d483a0130`) ·
**Rapor:** `var/derived/gardash_faz2_tr_dedup_20260621_06ac330e_clean_candidate_v3.txt.rejections.jsonl` (SHA256 `2becaf9d0f1fc9a8ce48a0ea6cc4a78b83b21eac22ce2e1754fbfb5548fdd778`, 93223 kayit) ·
**Tohum:** `20260921` · katman basina en cok 50 kayit · katman kurali: first reason in `reasons`; rows with more than one reason form the `multi_reason` stratum.

Bu belge `derlem_worker.clean_candidate_audit score` tarafindan yazilir; elle duzenlenen
bolumler bir sonraki puanlamada silinir. Karar ve takip notlari gorev kartina yazilir.

## Yontem

- Katman = kaydin `reasons` listesindeki ilk gerekce (bazi cetvellerde birden fazla gerekceli
  satirlar ayri `multi_reason` katmanina toplanir; kural cetvelin `stratum_rule` ust bilgisinden
  okunur). Katman agirligi `w_s` = katmanin rapordaki `char_count` toplaminin tum raporun
  toplamina orani (raporda bayt yok; karakter sayisi baytin yerine gecer).
- Katman orani `p_s` = `garbage` / (`garbage` + `ok_to_keep`); `unsure` ve bos satirlar payda disi.
  Aralik: Wilson skor araligi, %95 - tabakadaki karar sayisi tabakanin rapordaki nufusuna esit
  ya da buyukse (tam sayim) orneklem hatasi yoktur, nokta deger raporlanir.
- Toplam yanlis-tutma orani = sum(`w_s` * `p_s`) / sum(`w_s`), yalnizca karara baglanmis
  satiri olan katmanlar uzerinden. Aralik: Wilson, etkin orneklem `n_eff` = 1 / sum((`w_s`/W)^2 /
  `n_s`) (Kish); tam sayim tabakalari bu toplama katilmaz (agirlikca oran ortalamasina hala
  girerler). Butun kapsanan tabakalar tam sayimsa aralik nokta degerdir.
- Katki = `w_s` * `p_s`: katmanin toplam yanlis-tutma orani payina getirdigi pay; en yuksek
  uc katman asagida siralanir.
- Rafin esigi: tutulan baytin %10,00'undan fazlasi cop metinse kural sikilastirma konusulur.

## Gerekce basina

| Gerekce | Rapor kayit | Rapor karakter | Agirlik | Cetvel | garbage | ok_to_keep | unsure | bos | Oran | %95 aralik (ya da tam sayim) | Katki | Karakter agirlikli oran |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|---:|---:|
| `encoding_corruption` | 1847 | 3838869 | %8,20 | 50 | 12 | 38 | 0 | 0 | %24,00 | %14,30 - %37,41 | %1,97 | %16,37 |
| `wiki_markup_residue` | 1923 | 23819396 | %50,90 | 50 | 14 | 36 | 0 | 0 | %28,00 | %17,47 - %41,67 | %14,25 | %29,15 |
| `extreme_repetition` | 16 | 105257 | %0,22 | 16 | 15 | 1 | 0 | 0 | %93,75 | TAM SAYIM (%93,75) | %0,21 | %93,33 |
| `commercial_keyword_stuffing` | 401 | 8526737 | %18,22 | 50 | 27 | 23 | 0 | 0 | %54,00 | %40,40 - %67,03 | %9,84 | %55,06 |
| `dating_spam_cluster` | 624 | 8932652 | %19,09 | 50 | 12 | 38 | 0 | 0 | %24,00 | %14,30 - %37,41 | %4,58 | %24,42 |
| `optics_spam_cluster` | 18 | 203415 | %0,43 | 18 | 5 | 13 | 0 | 0 | %27,78 | TAM SAYIM (%27,78) | %0,12 | %25,64 |
| `sexual_pharma_spam_cluster` | 48 | 1184130 | %2,53 | 48 | 38 | 10 | 0 | 0 | %79,17 | TAM SAYIM (%79,17) | %2,00 | %72,09 |
| `multi_reason` | 11 | 189234 | %0,40 | 11 | 7 | 4 | 0 | 0 | %63,64 | TAM SAYIM (%63,64) | %0,26 | %53,80 |

## Toplam

| Olcu | Deger |
|---|---|
| Cetvel satiri | 293 (garbage 130 · ok_to_keep 163 · unsure 0 · bos 0) |
| Kapsanan agirlik (karari olan katmanlar) | %100,00 |
| **Bayt agirlikli yanlis-tutma orani** | **%33,23** |
| %95 aralik (Wilson, n_eff = 149,1) | %26,17 - %41,13 |
| Karakter agirlikli oran (katman icinde de karakterle) | %33,24 |
| %10,00 esigi ile karsilastirma | **ustunde** (aralik tumuyle esigin ustunde) |

## En yuksek katkili uc gerekce

| Sira | Gerekce | Oran | Katki |
|---:|---|---:|---:|
| 1 | `wiki_markup_residue` | %28,00 | %14,25 |
| 2 | `commercial_keyword_stuffing` | %54,00 | %9,84 |
| 3 | `dating_spam_cluster` | %24,00 | %4,58 |

## Degerlendirici uyumu

Ikinci cetvel verilmedi; uyum sayisi yok.

## Karar

Kural degisikligi karari ve varsa takip karti gorev kartina yazilir; bu belge yalnizca
olcumu tasir.
