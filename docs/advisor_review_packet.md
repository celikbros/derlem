# Advisor Review Packet

Bu paket, veri atölyesi kurulurken danismanlardan kisa ve karar verdiren yorum almak icin hazirlandi.

## Baglam

Iki ekip var:

- LLM ekibi: `C:\CELIK-GARDASH`
- Tokenizer ekibi: `C:\TURKCE-TOKENIZER`

Mevcut Faz 2 corpus'unda yaklasik 26 GB ham Turkce veri vardi. Full cross-source exact/whitespace dedup sonrasinda yaklasik 6.0M benzersiz dokuman ve 2.5B effective token kaldi. Bu miktar ilk model validasyonu icin faydali ama daha guclu model icin yetersiz. Bu nedenle Turkce merkezli, cok dilli ve ileride kod/veri karisimi da icerebilecek daha buyuk bir corpus factory kurulacak.

## Danismandan Beklenen

Lutfen uzun genel yorum yerine su karar noktalarina net cevap verin.

## Karar Sorulari

1. Buyuk corpus icin dogru saklama modeli sizce nedir?
   - Ham ve temiz metin object storage/filesystem, metadata PostgreSQL yaklasimi yeterli mi?
   - DVC/lakeFS/Iceberg benzeri veri surumleme katmani hangi olcekte zorunlu olur?

2. Turkce merkezli karisim nasil buyutulmali?
   - Turkce ana govdeye Ingilizce, kod, Turk dilleri, Osmanlica/Arap alfabesi, Avrupa dilleri hangi sirayla ve hangi risklerle eklenmeli?
   - Tokenizer retrain gerektirecek "material mixture change" esigi ne olmali?
   - Turkce ana pay hedefi ne olmali: %80, %90, %95?
   - Ingilizce, kod, noisy web, sosyal/informal Turkce ve diger diller icin ust sinirlar ne olmali?

3. Normalizasyon politikasi ne kadar muhafazakar olmali?
   - Unicode normalization, whitespace cleanup, mojibake repair ve OCR cleanup icin hangi islemler geri donulmez risk tasir?
   - Tokenizer ve LLM ekipleri icin hangi alanlarda identity policy korunmali?

4. Dedup stratejisi nasil olmali?
   - Exact dedup zorunlu. Near-dedup/MinHash hangi veri siniflarinda uygulanmali, hangi siniflarda veri kaybi riski nedeniyle ertelenmeli?
   - Eval/holdout sizintisi icin hangi overlap kontrolleri minimum sayilmali?

5. Onay ve kalite kapilari yeterli mi?
   - PII, telif, hassas alan, bozuk OCR, spam ve dusuk dogal Turkce icin hangi otomatik kapilar eksik?
   - Hangi kaynaklar mutlaka insan/uzman review gerektirir?

6. Release contract yeterli mi?
   - `final_corpus_manifest.json`, canonical text view, dedup/mixture/normalization raporlari ve checksum paketi LLM/tokenizer el sikismasi icin yeterli mi?
   - Tokenized package icin `tokens.bin`, `loss_mask.bin`, `index.jsonl`, `sidecar.jsonl`, `manifest.json`, `checksums.json` yeterli mi?
   - Dokuman sinirlari korunmali mi, yoksa one-document-per-line canonical text view yeterli mi?

7. Basari olcutu ne olmali?
   - Token sayisi disinda hangi metrikler release kalitesini belirlemeli?
   - Kucuk model probe, fertility/BPB, heldout eval ve manual audit nasil agirliklandirilmali?
   - Release gate esikleri ne olmali: fallback rate, fertility regresyonu, BPB farki, protected span kirilmasi?

## Kisa Cevap Formu

```text
Danisman:
Uzmanlik:
Tarih:

1. En kritik risk:
2. Onayladiginiz mimari kararlar:
3. Degismesi gereken kararlar:
4. Tokenizer ekibine ozel not:
5. LLM ekibine ozel not:
6. Veri toplama/onay surecine ozel not:
7. Release oncesi zorunlu dediginiz gate:
8. Ek kaynak/veri onerisi:
```
