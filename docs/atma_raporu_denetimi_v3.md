# Atma raporu denetimi v3 — yanlış-atma oranı (TASK-020)

**Durum:** cetvel çıkarıldı, kararlar bekleniyor (2026-09-19) · **Kod:**
`worker/src/derlem_worker/clean_candidate_audit.py` · **Görev kartı:**
[TASK-020](gorevler/TASK-020-rejection-report-false-drop-audit-pack.md)

Bu belge iskelettir. Kararlar doldurulup puanlayıcı çalıştırıldığında
(`score` alt komutu) belge baştan yazılır: gerekçe başına tablo, bayt ağırlıklı
toplam oran ve %95 aralık, en yüksek katkılı üç gerekçe, %10 eşiğiyle
karşılaştırma ve varsa değerlendirici uyumu. Karar ve takip notları görev
kartına yazılır; bu belge yalnızca ölçümü taşır.

## Neden

Rafın tek açık isteği: atılan baytın %10'undan fazlası iyi metinse
`tr-web-v2` kurallarını gevşetmeyi konuşuruz ([temiz_aday_v3.md](temiz_aday_v3.md)).
93.223 kayıtlık atma raporu kimsenin denetlemediği kurallarla üretildi; sonuç
v4/HF geçişleri için kural kararını belirler, v2'nin koşulu değildir.

## Cetvel nasıl çekildi

| Alan | Değer |
|---|---|
| Rapor | `var/derived/gardash_faz2_tr_dedup_20260621_06ac330e_clean_candidate_v3.txt.rejections.jsonl` |
| Rapor SHA256 | `2becaf9d0f1fc9a8ce48a0ea6cc4a78b83b21eac22ce2e1754fbfb5548fdd778` (93.223 kayıt, 36.329.616 bayt) |
| Kayıt biçimi | `clean-candidate-rejections-v2` |
| Tohum | `20260919` |
| Katman kuralı | kaydın `reasons` listesindeki **ilk (birincil) gerekçe**; liste sırası `quality_filters._REASON_ORDER` ile sabit |
| Katman başına | min(50, katman büyüklüğü) |
| Seçim | katman içinde `sha256(f"{tohum}:{sha256}:{source_ordinal}")` anahtarına göre sıralanır, ilk 50 alınır (Python RNG'sine bağlı değil; 3.13 ve 3.14 aynı satırları verdi) |
| Cetvel | `var/olcum-2026-09-19/atma-denetimi-v3/gardash_faz2_tr_dedup_20260621_06ac330e_clean_candidate_v3_audit_sheet_seed20260919.csv` (+ aynı adla `.md`) |
| Cetvel satırı | **706** = 14 × 50 + 6 (`mixed_script_artifact` katmanında yalnızca 6 birincil kayıt var) |
| Cetvel CSV SHA256 | `fac0e207927ea48be6b7be0f9835d38584f3eecb0088432ef082466783144b1e` |

`var/` sürüme girmez; cetvel yeniden çekilirse satırlar aynıdır, yalnızca
üst bilgideki `generated_at` değişir (SHA bu yüzden farklı çıkar).

### Katmanlar (tam rapor)

| Katman | Kayıt | Karakter (`char_count` toplamı) | Cetvel |
|---|---:|---:|---:|
| `encoding_corruption` | 12.751 | 66.811.388 | 50 |
| `wiki_markup_residue` | 21.938 | 160.201.115 | 50 |
| `extreme_repetition` | 2.117 | 44.979.909 | 50 |
| `hashtag_stuffing` | 1.012 | 16.277.620 | 50 |
| `mixed_script_artifact` | 6 | 644.808 | 6 |
| `repeated_segments` | 1.334 | 49.002.101 | 50 |
| `navigation_boilerplate` | 11.354 | 294.688.466 | 50 |
| `commercial_keyword_stuffing` | 1.756 | 34.860.220 | 50 |
| `dating_spam_cluster` | 2.266 | 30.126.262 | 50 |
| `optics_spam_cluster` | 105 | 1.345.161 | 50 |
| `adult_service_spam_cluster` | 892 | 12.874.650 | 50 |
| `sexual_pharma_spam_cluster` | 146 | 8.184.458 | 50 |
| `near_duplicate` | 35.833 | 158.816.282 | 50 |
| `normalized_duplicate` | 221 | 27.839 | 50 |
| `language_not_turkish` | 1.492 | 725.566 | 50 |
| **Toplam** | 93.223 | 879.565.845 | 706 |

Kalite gerekçelerinin katman sayıları manifestteki belge sayılarından küçüktür
(ör. `navigation_boilerplate` 12.513 → 11.354): bir satır birden çok gerekçe
taşıyabilir, katman yalnızca ilkine göre atanır. 10.793 kayıt birden çok gerekçe
taşıyor; `reasons` sütunu hepsini gösterir.

Ağırlık için raporda bayt yok; `char_count` toplamı baytın yerine geçer
(`navigation_boilerplate` tek başına %33,5, `wiki_markup_residue` %18,2,
`near_duplicate` %18,1).

## Cetvel nasıl doldurulur

- CSV'yi açın (UTF-8, BOM'lu; Excel Türkçe harfleri doğru gösterir). `# ` ile
  başlayan üst bilgi satırlarına ve sütun başlığına dokunmayın.
- Her satırda `preview` (ilk 200 karakter) ve `reasons` görünür; tam satıra
  gerek varsa `source_ordinal` ana kaynaktaki satır numarasıdır
  (`gardash_faz2_tr_dedup_20260621`, `9826d58e…aa07b5`).
- Kopya atmalarında `duplicate_of` kalan satırın numarasıdır; partner raporda
  yoksa (kural gereği genelde yok) `duplicate_of_preview` boştur.
- `verdict` sütununa yalnızca şunlardan biri yazılır:
  - `good` — metin eğitime girmeliydi (yanlış atma),
  - `correct_drop` — atma doğru,
  - `unsure` — karar verilemedi (payda dışı kalır, sayısı raporlanır).
- Boş bırakılan satır "karar yok" sayılır. Başka değer yazılırsa puanlayıcı
  satırı ve değeri göstererek durur, belge yazılmaz.
- İki değerlendirici: aynı CSV'nin iki kopyası; ikinci kopya aynı satırların
  (ya da bir alt kümesinin, ör. 100 satır) kararını taşır.

## Puanlayıcı nasıl çalıştırılır

Depo kökünden:

```powershell
$env:PYTHONPATH = "worker/src"; $env:PYTHONIOENCODING = "utf-8"
.\.venv\Scripts\python.exe -m derlem_worker.clean_candidate_audit score `
  --sheet var\olcum-2026-09-19\atma-denetimi-v3\gardash_faz2_tr_dedup_20260621_06ac330e_clean_candidate_v3_audit_sheet_seed20260919.csv `
  --second var\olcum-2026-09-19\atma-denetimi-v3\ikinci-degerlendirici.csv   # istege bagli
# varsayilan cikti: docs/atma_raporu_denetimi_v3.md (bu belge); --out ile degistirilir
```

Cetveli yeniden çekmek için (`--force` mevcut dosyaların üstüne yazar):

```powershell
.\.venv\Scripts\python.exe -m derlem_worker.clean_candidate_audit sheet `
  --report var\derived\gardash_faz2_tr_dedup_20260621_06ac330e_clean_candidate_v3.txt.rejections.jsonl `
  --output-dir var\olcum-2026-09-19\atma-denetimi-v3 `
  --expect-report-sha256 2becaf9d0f1fc9a8ce48a0ea6cc4a78b83b21eac22ce2e1754fbfb5548fdd778
```

## Puanlayıcının yöntemi

- Katman ağırlığı `w_s` = katmanın rapordaki `char_count` toplamı / tüm raporun toplamı.
- Katman oranı `p_s` = `good` / (`good` + `correct_drop`); aralık Wilson skor aralığı, %95.
- Toplam oran = Σ `w_s` · `p_s` / Σ `w_s`, yalnızca karara bağlanmış satırı olan
  katmanlar üzerinden; aralık Wilson, etkin örneklem
  `n_eff` = 1 / Σ ((`w_s`/W)² / `n_s`) (Kish) ile. Kapsanan ağırlık ayrıca yazılır.
- Katkı = `w_s` · `p_s`; en yüksek üç katman listelenir.
- İkincil ölçü: katman içinde de karakter ağırlıklı oran (iyi satırların
  karakteri / karara bağlanmış satırların karakteri).
- Uyum (ikinci cetvel varsa): ikisinde de karar olan satırlarda aynı karar payı
  ve Cohen kappa (üç kategori).

## Sonuç

(kararlar bekleniyor — puanlayıcı bu bölümü tablolarla değiştirir)
