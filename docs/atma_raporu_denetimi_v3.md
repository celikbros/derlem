# Atma raporu denetimi v3 - yanlis-atma orani (TASK-020)

**Puanlama:** 2026-09-20T13:55:44+00:00 · **Cetvel:** `C:\CELIKBROS PROJECTS\derlem\var\olcum-2026-09-19\atma-denetimi-v3\denetim-sayfasi-dolu-raf.csv` (SHA256 `e12b188a02369fad09477df5750ac094051bc082f3adfeaa05fc104d9a708821`) ·
**Rapor:** `C:\CELIKBROS PROJECTS\derlem\var\derived\gardash_faz2_tr_dedup_20260621_06ac330e_clean_candidate_v3.txt.rejections.jsonl` (SHA256 `2becaf9d0f1fc9a8ce48a0ea6cc4a78b83b21eac22ce2e1754fbfb5548fdd778`, 93223 kayit) ·
**Tohum:** `20260919` · katman basina en cok 50 kayit · katman kurali: first reason in `reasons` (primary reason).

Bu belge `derlem_worker.clean_candidate_audit score` tarafindan yazilir; elle duzenlenen
bolumler bir sonraki puanlamada silinir. Karar ve takip notlari gorev kartina yazilir.

## Yontem

- Katman = kaydin `reasons` listesindeki ilk gerekce. Katman agirligi `w_s` = katmanin
  rapordaki `char_count` toplaminin tum raporun toplamina orani (raporda bayt yok; karakter
  sayisi baytin yerine gecer).
- Katman orani `p_s` = `good` / (`good` + `correct_drop`); `unsure` ve bos satirlar payda disi.
  Aralik: Wilson skor araligi, %95.
- Toplam oran = sum(`w_s` * `p_s`) / sum(`w_s`), yalnizca karara baglanmis satiri olan katmanlar
  uzerinden. Aralik: Wilson, etkin orneklem `n_eff` = 1 / sum((`w_s`/W)^2 / `n_s`) (Kish).
- Katki = `w_s` * `p_s`: katmanin toplam yanlis-atma payina getirdigi pay; en yuksek uc katman
  asagida siralanir.
- Rafin esigi: toplam oran > %10,00 ise kural gevsetme konusulur.

## Gerekce basina

| Gerekce | Rapor kayit | Rapor karakter | Agirlik | Cetvel | good | correct_drop | unsure | bos | Oran | %95 aralik | Katki | Karakter agirlikli oran |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|---:|---:|
| `encoding_corruption` | 12751 | 66811388 | %7,60 | 50 | 27 | 21 | 2 | 0 | %56,25 | %42,28 - %69,30 | %4,27 | %72,58 |
| `wiki_markup_residue` | 21938 | 160201115 | %18,21 | 50 | 18 | 32 | 0 | 0 | %36,00 | %24,14 - %49,86 | %6,56 | %46,42 |
| `extreme_repetition` | 2117 | 44979909 | %5,11 | 50 | 11 | 39 | 0 | 0 | %22,00 | %12,75 - %35,24 | %1,13 | %17,40 |
| `hashtag_stuffing` | 1012 | 16277620 | %1,85 | 50 | 17 | 31 | 2 | 0 | %35,42 | %23,43 - %49,56 | %0,66 | %38,90 |
| `mixed_script_artifact` | 6 | 644808 | %0,07 | 6 | 0 | 6 | 0 | 0 | %0,00 | %0,00 - %39,03 | %0,00 | %0,00 |
| `repeated_segments` | 1334 | 49002101 | %5,57 | 50 | 13 | 36 | 1 | 0 | %26,53 | %16,21 - %40,26 | %1,48 | %19,00 |
| `navigation_boilerplate` | 11354 | 294688466 | %33,50 | 50 | 22 | 27 | 1 | 0 | %44,90 | %31,85 - %58,68 | %15,04 | %38,83 |
| `commercial_keyword_stuffing` | 1756 | 34860220 | %3,96 | 50 | 19 | 29 | 2 | 0 | %39,58 | %27,02 - %53,69 | %1,57 | %58,88 |
| `dating_spam_cluster` | 2266 | 30126262 | %3,43 | 50 | 17 | 32 | 1 | 0 | %34,69 | %22,92 - %48,69 | %1,19 | %36,44 |
| `optics_spam_cluster` | 105 | 1345161 | %0,15 | 50 | 31 | 19 | 0 | 0 | %62,00 | %48,15 - %74,14 | %0,09 | %63,92 |
| `adult_service_spam_cluster` | 892 | 12874650 | %1,46 | 50 | 0 | 49 | 1 | 0 | %0,00 | %0,00 - %7,27 | %0,00 | %0,00 |
| `sexual_pharma_spam_cluster` | 146 | 8184458 | %0,93 | 50 | 12 | 38 | 0 | 0 | %24,00 | %14,30 - %37,41 | %0,22 | %8,00 |
| `near_duplicate` | 35833 | 158816282 | %18,06 | 50 | 26 | 23 | 1 | 0 | %53,06 | %39,38 - %66,30 | %9,58 | %60,25 |
| `normalized_duplicate` | 221 | 27839 | %0,00 | 50 | 0 | 41 | 9 | 0 | %0,00 | %0,00 - %8,57 | %0,00 | %0,00 |
| `language_not_turkish` | 1492 | 725566 | %0,08 | 50 | 2 | 48 | 0 | 0 | %4,00 | %1,10 - %13,46 | %0,00 | %34,85 |

## Toplam

| Olcu | Deger |
|---|---|
| Cetvel satiri | 706 (good 215 · correct_drop 471 · unsure 20 · bos 0) |
| Kapsanan agirlik (karari olan katmanlar) | %100,00 |
| **Bayt agirlikli yanlis-atma orani** | **%41,79** |
| %95 aralik (Wilson, n_eff = 254,7) | %35,90 - %47,92 |
| Karakter agirlikli oran (katman icinde de karakterle) | %44,31 |
| %10,00 esigi ile karsilastirma | **ustunde** (aralik tumuyle esigin ustunde) |

## En yuksek katkili uc gerekce

| Sira | Gerekce | Oran | Katki |
|---:|---|---:|---:|
| 1 | `navigation_boilerplate` | %44,90 | %15,04 |
| 2 | `near_duplicate` | %53,06 | %9,58 |
| 3 | `wiki_markup_residue` | %36,00 | %6,56 |

## Degerlendirici uyumu

Ikinci cetvel: `C:\CELIKBROS PROJECTS\derlem\var\olcum-2026-09-19\atma-denetimi-v3\denetim-sayfasi-dolu-kurucu.csv`.

| Olcu | Deger |
|---|---|
| Ikisinde de karar olan satir | 50 |
| Ayni karar | 33 (%66,00) |
| Cohen kappa | 0,361 |

## Karar

Kural degisikligi karari ve varsa takip karti gorev kartina (TASK-020) yazilir; bu belge
yalnizca olcumu tasir.
