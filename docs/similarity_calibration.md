# SimHash Kalibrasyon Raporu

**Şema:** `derlem.similarity-calibration.v1`

Bu araç release politikasını otomatik değiştirmeden, içerik amacı ve gerçek
corpus örneği için SimHash eşik kanıtı üretir. JSON ve Markdown raporları ham
belge metni içermez.

## Neyi Ölçer?

- İçerik-adresli kaynaklardan deterministik bottom-k belge örneği.
- Örnek belgelerin token uzunluk dağılımı: `5-7`, `8-15`, `16-31`, `32+`.
- Dört kontrollü token bozulmasının Hamming mesafesi:
  - orta tokenı silme,
  - orta tokenı değiştirme,
  - iki orta tokenın yerini değiştirme,
  - orta `%10` aralığı silme.
- Corpus örneğindeki tüm doğal belge çiftlerinin mesafe dağılımı.
- Ham metin olmadan en yakın doğal çiftlerin kaynak SHA256 ve ordinal kimlikleri.
- `0..10` eşikleri için sentetik yakalama oranı ve corpus çift oranı.
- Aday sınırı aşılmadığı sürece 4x16 release LSH indeksinin tam aday garantisinin geçerli olduğu eşikler.

Kalibrasyon örnekleyicisi `source_sha256 + ordinal` SHA256 önceliğine göre en
küçük K belgeyi seçer. Kaynak sırası sonucu değiştirmez; bellek kullanımı örnek
boyutuyla sınırlıdır. Varsayılan ve izin verilen üst sınır sırasıyla 1.000 ve
2.000 belgedir.

## Karar Sınırı

Raporun kararı bilinçli olarak `human_labels_required` değeridir. Sentetik
bozulma recall'u ve doğal corpus çift oranı, etiketli precision değildir.
`closest_pairs` içindeki doğal çiftler insanlar tarafından aynı/yakın/farklı
olarak etiketlenmeden purpose-specific eşik etkinleştirilmez.

Aktif release politikası hâlâ:

- `policy_id`: `universal-report-only-h3-4x16-v1`
- eşik: Hamming `3`
- mod: `report_only`
- purpose durumu: `pending_labeled_calibration`

## Küçük Smoke Sonucu

`Bulk Review Smoke` instruction kaynağında 3 belgenin tamamı 6 tokendır.
Hamming 3 ve 10 eşiklerinde kontrollü varyant yakalama oranı `%0` çıkmıştır.
Bu küçük sonuç politika değiştirmek için yeterli değildir; fakat kısa instruction
belgelerinde 64-bit SimHash'in kararsız olabileceğini görünür kılar.

## Gardas Uzun Tarama

Bu komut `gardash_faz2_tr_dedup_20260621_clean_candidate_20260625` kaynağının
5.922.891 belgesini akış halinde tarar. Uzun sürebileceği için asistan tarafında
beklenmeden kullanıcı terminalinde çalıştırılmalıdır:

```powershell
cd "C:\CELIK- DERLEM"
.\.venv\Scripts\python.exe -m derlem_worker.similarity_calibration `
  --source-id f63352dd-fdd1-4e4b-a8d2-b167b3c856cf `
  --sample-size 1000 `
  --threshold-max 10 `
  --closest-pair-limit 100 `
  --output-dir .\var\reports `
  --force
```

Tarama her 100.000 belgede ilerlemeyi stderr'e yazar. Tamamlandığında JSON ve
Markdown yollarını stdout'ta döndürür. Sonraki adım, rapordaki token uzunluk
bantlarını ve en yakın çiftleri inceleyerek pretrain politikasını kararlaştırmaktır.

## Yerel Dosya Deneyi

Kayıtlı kaynak yerine doğrudan dosya kullanılacaksa içerik SHA256 ve amaç
zorunludur. CLI dosyayı hash'ler ve verilen SHA256 ile eşleşmezse durur:

```powershell
.\.venv\Scripts\python.exe -m derlem_worker.similarity_calibration `
  --input-path .\data\sample.jsonl `
  --source-sha256 <64_HEX_SHA256> `
  --content-purpose instruction `
  --sample-size 500
```
