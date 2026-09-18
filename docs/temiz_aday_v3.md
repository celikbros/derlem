# Temiz aday v3 — kalite süzgeci, held-out bölmesi, yakın kopya atma, atma raporu

**Tarih:** 2026-09-18 · **Karar:** kurucu (raf mektubu 2026-09-17 üzerine) · **Kod:**
`worker/src/derlem_worker/clean_candidate.py`, `quality_filters.py`

Kural: hiçbir metin yerinde temizlenmez ([data_governance.md](data_governance.md)).
v3 girdiyi okur, **iki yeni nesne** (eğitim adayı + held-out) ve bir atma raporu yazar;
her biri kendi SHA256'sı ve manifestiyle. v1/v2 üretimleri değişmez.

## Tek geçişte sıra (satır başına)

1. **Aşırı büyük** satır (> `max_document_bytes`) → atılır (sayılır).
2. **Boş** satır → atlanır.
3. **Kişisel veri** (TCKN, IBAN, e-posta, telefon, kart) → atılır. Bu adım her şeyden
   önce çalışır; sonraki adımların raporuna kişisel veri taşıyan satır **hiç gelmez**.
4. **Atılacak-satır listesi** (`--drop-list`; dil kararı, dışarıda hesaplanır) → atılır,
   rapora gerekçe ve ayrıntıyla yazılır.
5. **Kalite süzgeci** (`--quality-policy tr-web-v2`) → atılır, rapora yazılır.
6. **Normalize tekrar** (`normalized-document-sha256-v1`) → ikinci görülen atılır,
   rapora `normalized_duplicate` + `duplicate_of` ile yazılır.
7. **Yakın kopya** (`--near-dedup`; `normalized-word-3gram-simhash64-v1`, Hamming ≤ 3,
   4 × 16 bit bant — dondurmadaki `release_near_duplicates` ile aynı yöntem) → ikinci
   görülen atılır, rapora `near_duplicate` + `duplicate_of` ile yazılır.
8. **Held-out bölmesi** (`--held-out-rule afacan-held-out-v1`): satırın yazılacak
   baytları (sondaki LF hariç) için `int(sha256[:8], 16) % 2500 == 0` ise held-out
   dosyasına, değilse eğitim adayına yazılır.

**Tekilleştirme (6 ve 7) iki akış için ortaktır.** Held-out'a düşen bir satırın birebir,
normalize ya da yakın kopyası eğitim adayına gidemez; sonra gelen kopya hangi tarafa
düşecek olursa olsun atılır. Dondurmada birebir dekontaminasyon kapısının **0** vermesi
bu yüzden yapı gereğidir; sıfırdan farklı sonuç üretim hatasıdır.

## `tr-web-v2` = `tr-web-v1` + iki kesin kural

| Gerekçe | Kural | Dilimde ölçülen (100k, 2026-09-17) |
|---|---|---|
| `encoding_corruption` | metinde `U+FFFD` var | 231 satır (%0,231) |
| `wiki_markup_residue` | `align="`, `{{`, `}}`, `[[`, `]]` ya da en az iki `\|\|` | 353 satır (%0,353) |

v1 kuralları 500–1.500 sözcük eşiği ister; bu ikisi uzunluktan bağımsızdır. v1'in
gerekçe listesi ve eşikleri değişmedi (`test_quality_filters.py` kontrol eder).

## Atma raporu (`clean-candidate-rejections-v2`)

JSONL, satır başına bir kayıt, anahtarlar sıralı:

```json
{"char_count":1402,"preview":"ilk 200 karakter…","reasons":["encoding_corruption"],"sha256":"<satır baytlarının sha256'sı>","source_ordinal":3114952}
```

Kopya atmalarında `duplicate_of` (kalan satırın numarası) eklenir. Önizleme kişisel
veri taşımaz (3. adım). Raporun SHA256'sı ve boyutu manifeste yazılır; raf raporu
örnekleyip yanlış-atma oranını ölçecek (ölçüt: atılan baytın %10'undan fazlası iyi
metinse kural gevşetme konuşulur).

## Manifest alanları (v3 ekleri)

`algorithm_version = clean-candidate-v3`, `quality_filter_version`,
`rejections_record_version`, `held_out_rule`, `held_out_path`, `held_out_lines`,
`held_out_byte_size`, `held_out_sha256`, `near_dedup_method`,
`near_dedup_hamming_threshold`, `removed_near_duplicate_lines`,
`simhash_indexed_lines`, `near_dedup_candidate_overflow_lines` (kova başına 5.000
aday sınırı aşılıp arama kısaltılan satır sayısı; 0 olmalı).

## 100.000 satırlık dilimde uçtan uca (2026-09-18)

Girdi 100.000 satır / 215.303.310 bayt (tohum 20260917). Süre **249 sn**.

| Sonuç | Satır | Bayt |
|---|---|---|
| Eğitim adayı | 99.007 | 202.923.864 (%94,25) |
| Held-out | 43 | 84.579 |
| Kalite süzgeci (`tr-web-v2`) | 937 | — |
| Yakın kopya (Hamming ≤ 3) | 13 | — |
| Normalize tekrar | 0 | — |

Kova taşması 0. Tam korpus (5.922.891 satır) için süre kestirimi ~4 saat; zamanı
SimHash hesabı belirler.

## Dil kuralı: fastText ile, atılacak-satır listesi olarak (ölçüldü, 2026-09-18)

Rafın kuralı: **≥ 200 karakter, `lid.176` güveni ≥ 0,5 ile Türkçe değilse at.** Araç
seçimi ölçümle yapıldı (aynı 82.239 uzun satır, 100k dilim):

| Araç | Süre | "Türkçe değil" | Bunların Türkçe olanı (Türkçe'ye özgü harf yoğunluğu ≥ %1) |
|---|---|---|---|
| lingua 2.2.0 (tüm diller) | 323 sn | 121 (%0,147) | 77 (%64) — futbolcu biyografileri "Tagalog 1.0" |
| langdetect 1.0.9 | 291 sn | 84 (%0,102) | ölçülmedi |
| **fastText lid.176.ftz** | **23 sn** | **30 (%0,036)** | 7 (%23); çoğu gerçekten karışık dilli |

fastText'in resmi paketi Python 3.14'te (proje ortamı) derlenemiyor; `fasttext-predict`
Python 3.13'te kuruluyor. Bu yüzden dil kararı **proje ortamının dışında** hesaplanır ve
üretime bir **atılacak-satır listesi** (`--drop-list`, JSONL: satır baytlarının `sha256`,
`lang`, `p`) olarak verilir. Listenin SHA256'sı, kayıt sayısı ve yöntemi
(`--drop-list-method`) manifeste yazılır; atılan her satır raporda
`language_not_turkish` gerekçesi ve `details: {lang, p}` ile görünür. Liste, 3.13
ortamındaki `lid.176.ftz` (SHA256 `8f3472cf…603e83`) ile ana kaynak üzerinde üretilir.
Tüm korpus için süre kestirimi ~25 dk.

Ölçüm dosyaları: `var/olcum-2026-09-17/ornekler-dil-fasttext.md`, `…-lingua.md`.

## Tam üretim (2026-09-18 → 19, ~3,4 saat)

Girdi: ana kaynak `gardash_faz2_tr_dedup_20260621` (`9826d58e…aa07b5`, 6.027.968 satır).

| Sonuç | Satır | Bayt | SHA256 |
|---|---|---|---|
| **Eğitim adayı** (`…_clean_candidate_v3.txt`) | 5.827.650 | 11.896.793.726 | `83dcac7721b7e22c9c1ea46c90e5c3c61f768c9503a85b4f663116b73d3c0059` |
| **Held-out** (`…_v3_heldout.txt`) | 2.239 | 4.630.115 | `4a8595db05d8dc9febefaa2b35f5f9f340a5d9573d445c4125a78b7e28952c45` |
| Atma raporu (`…_v3.txt.rejections.jsonl`) | 93.223 kayıt (kişisel veri satırları rapora girmez) | 36.329.616 | `2becaf9d0f1fc9a8ce48a0ea6cc4a78b83b21eac22ce2e1754fbfb5548fdd778` |
| Dil listesi (girdi) | 1.501 kayıt | 228.040 | `cdea5548a39340d3b8c34acbef305b54f1bcf74f3a6e0176728c20c9a4f4de86` |

Atılanlar: kişisel veri 104.853 · kalite (`tr-web-v2`) 55.677 · yakın kopya (Hamming ≤ 3)
**35.833** · dil (fastText) 1.492 (listedeki 1.501'in 9'u daha önce başka gerekçeyle
atılmıştı) · normalize tekrar 221 · aşırı büyük 3. Toplam birebir tutar. Kova taşması 0;
imzası çıkarılan satır 5.807.621.

Kalite gerekçeleri: işaretleme kalıntısı 21.984 · kodlama bozulması 12.751 · gezinme
kalıbı 12.513 · ticari doldurma 7.989 · arkadaşlık spam'i 6.793 · tekrarlanan bölüm 3.772 ·
yetişkin hizmet 2.516 · aşırı tekrar 2.176 · hashtag 1.120 · cinsel ilaç 533 · optik 198 ·
karışık alfabe 7 (bir satır birden çok gerekçe taşıyabilir).

Yakın kopya oranı (%0,59) dilim ölçümünün (%0,013) 45 katı: dilim içi ölçüm, korpus
oranını olduğundan düşük gösterir (bir kopya ancak iki üyesi de dilime düşerse sayılır);
belgede bu uyarı yazılıydı. Held-out 2.239 satır: v1 adayındaki 2.275'in 36'sı kalite,
yakın kopya ya da dil kuralına takıldı — kural gereği eğitime sızmadılar, dilim küçüldü.

## Üretim komutu

```powershell
.\.venv\Scripts\python.exe -m derlem_worker.clean_candidate `
  --source-id 06ac330e-350f-45f0-b596-3dd4aa1dbc57 `
  --quality-policy tr-web-v2 --held-out-rule afacan-held-out-v1 --near-dedup `
  --drop-list var\olcum-2026-09-17\fasttext-drop-list.jsonl `
  --drop-list-method fasttext-lid176-ftz-min200-p0.5 --drop-list-reason language_not_turkish
```

Çıktılar `var/derived/` altında: `<ad>_clean_candidate_v3.txt`,
`…_v3_heldout.txt`, `…_v3.txt.rejections.jsonl`, `…_v3.txt.manifest.json`. Sonra iki
dosya `IMPORT_ROOT` üzerinden kaynak olarak kaydedilir: eğitim adayı `pretrain`
(`derived_from` = ana kaynak), held-out `holdout`. İkisinin de hak durumu ana kaynak
gibi `unknown`'dır (türev girdisinden temiz olamaz).
