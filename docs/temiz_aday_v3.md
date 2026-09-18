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
4. **Kalite süzgeci** (`--quality-policy tr-web-v2`) → atılır, rapora yazılır.
5. **Normalize tekrar** (`normalized-document-sha256-v1`) → ikinci görülen atılır,
   rapora `normalized_duplicate` + `duplicate_of` ile yazılır.
6. **Yakın kopya** (`--near-dedup`; `normalized-word-3gram-simhash64-v1`, Hamming ≤ 3,
   4 × 16 bit bant — dondurmadaki `release_near_duplicates` ile aynı yöntem) → ikinci
   görülen atılır, rapora `near_duplicate` + `duplicate_of` ile yazılır.
7. **Held-out bölmesi** (`--held-out-rule afacan-held-out-v1`): satırın yazılacak
   baytları (sondaki LF hariç) için `int(sha256[:8], 16) % 2500 == 0` ise held-out
   dosyasına, değilse eğitim adayına yazılır.

**Tekilleştirme (5 ve 6) iki akış için ortaktır.** Held-out'a düşen bir satırın birebir,
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

## Dil tespiti: bu turda yok (ölçüldü, 2026-09-18)

Python 3.14'te fastText derlenemedi; `lingua` 2.2.0 ve `langdetect` 1.0.9 kuruldu
(atılabilir ortamda). `lingua` (tüm diller) 82.239 uzun satırı 323 sn'de taradı ve 121'ine
(%0,147) güven ≥ 0,5 ile "Türkçe değil" dedi — **bunların 77'si (%64) Türkçe** (yabancı
özel ad yoğun futbolcu biyografileri "Tagalog 1.0", "İsveççe 1.0" çıktı). Kalan 44 çoğunlukla
ad listesi ve İngilizce kaynakça satırı. Gerçek yabancı dil oranı uzun satırlarda en fazla
%0,053; kazanç küçük, Türkçe metni atma riski büyük. `langdetect` aynı satırlarda 291 sn'de
84 satırı (%0,102) işaretledi, dil dağılımı daha makul (en 40, de 16, fr 7); yanlış pozitif
oranı **ölçülmedi**. Bu tur dil kuralı uygulanmaz; ölçüm dosyası
`var/olcum-2026-09-17/ornekler-dil-lingua.md`.

## Üretim komutu

```powershell
.\.venv\Scripts\python.exe -m derlem_worker.clean_candidate `
  --source-id 06ac330e-350f-45f0-b596-3dd4aa1dbc57 `
  --quality-policy tr-web-v2 --held-out-rule afacan-held-out-v1 --near-dedup
```

Çıktılar `var/derived/` altında: `<ad>_clean_candidate_v3.txt`,
`…_v3_heldout.txt`, `…_v3.txt.rejections.jsonl`, `…_v3.txt.manifest.json`. Sonra iki
dosya `IMPORT_ROOT` üzerinden kaynak olarak kaydedilir: eğitim adayı `pretrain`
(`derived_from` = ana kaynak), held-out `holdout`. İkisinin de hak durumu ana kaynak
gibi `unknown`'dır (türev girdisinden temiz olamaz).
