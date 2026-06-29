# Derlem Kanonik Export Sozlesmesi

**Surum:** `derlem.export-manifest.v2`

**Durum:** Calisan MVP

**Formatlar:** JSONL, TXT

## Amac

Derlem veriyi GLM, DeepSeek, Kimi veya baska bir modelin chat template'ine
gore saklamaz. Frozen release, modelden bagimsiz kanonik bir artifact'e
donusturulur. Tokenizer ve LLM ekipleri bu artifact'i kendi adapter ve egitim
pipeline'lariyla hedef modele uyarlar.

Bu sinir yeni bir model ciktiginda Derlem verisinin tekrar onaylanmasini
gerektirmez. Yalnizca tuketici taraftaki adapter degisir.

## JSONL Kaydi

Her satir tek bir text, conversation veya preference kaydi tasir. Duz metin
kaydi geriye uyumlu belge bicimini korur:

```json
{
  "id": "stable-document-id",
  "metadata": {
    "content_purpose": "pretrain",
    "document_sha256": "...",
    "domain": "general",
    "external_id": null,
    "language": "tr",
    "license": "internal",
    "source_id": "...",
    "source_ordinal": 42,
    "source_sha256": "..."
  },
  "text": "Belge metni"
}
```

Alanlar alfabetik ve kompakt JSON serilestirmesiyle yazilir. UTF-8 karakterler
ASCII kacislarina donusturulmez. Her kayit `LF` ile biter.

Yapisal kayitlar `derlem.canonical-export-record.v1` zarfi icinde kaynak
`derlem.canonical-sample.v1` sample'ini degistirmeden tasir. `messages`, `tools`,
`tool_calls`, multimodal content part'lari ve preference `chosen/rejected`
dallari model template'ine render edilmez. Kaynak SHA256 ve satir sirasi
zarfin `lineage` alanindadir.

## TXT Ciktisi

TXT artifact belge basina tek UTF-8 satir uretir. Belge icindeki `CRLF`, `CR`
ve `LF` karakterleri tek bosluga donusturulur. Bu format hizli pretraining
tuketimi icindir; lineage ve metadata gerektiren tuketiciler JSONL kullanir.
Conversation veya preference kaydi TXT export'a girerse islem sert hatayla
bloke edilir.

## Determinizm

Checksum garantisini su kurallar saglar:

1. Kaynaklar `source_id` ile siralanir.
2. Belgeler kaynak icindeki kalici satir sirasinda okunur.
3. Kayit kimligi `source_sha256`, satir numarasi ve export edilen kanonik payload
   SHA256'sinden uretilir.
4. JSON anahtarlari sirali ve bosluksuz serilestirilir.
5. Manifestte calisma zamani gibi degisken alanlar kullanilmaz; release'in
   sabit `frozen_at` ve manifest SHA256 degerleri kullanilir.

## Saklama ve Audit

Artifact ve export manifesti once SHA256 ile content-addressed object store'a
yazilir. `release_exports` kaydi `ready` olduktan sonra PostgreSQL trigger'i
update ve delete islemlerini reddeder. Su olaylar append-only audit'e eklenir:

- `release.export_queued`
- `release.export_ready`
- `release.export_failed`

## API

```text
POST /api/v1/releases/{release_id}/exports
GET  /api/v1/releases/{release_id}/exports/{format}/artifact
GET  /api/v1/releases/{release_id}/exports/{format}/manifest
```

POST govdesi:

```json
{"format":"jsonl"}
```

Yalniz `frozen` release export edilebilir. Ayni release ve format icin hazir
veya devam eden kayit varken API `409 release_export_conflict` dondurur.

## Buyuk Corpus Davranisi

Worker dosyayi bellekte toplamaz. Artifact gecici dosyaya akitilir ve sonra
immutable store'a yayimlanir. Her 50.000 kayitta job sonucuna su ilerleme
sayaclari yazilir:

- `input_bytes_processed`
- `records_written`
- `sources_completed`
- `source_count`
- `output_bytes_written`
- `estimated_tokens`

Arayuz bu sayaclari Isler gorunumunde gosterir. Gardas temiz adayinin export'u
buyuk bir disk okuma/yazma isi oldugu icin yeterli bos alan kontrol edilerek
ve worker log'u izlenerek baslatilmalidir.

## Token Tahmini

Manifestteki `token_estimate`, tokenizer sonucu degildir. Derlem model veya
tokenizer secmeden semantik metinlerin Unicode codepoint, UTF-8 byte ve
whitespace-unit sayilarini toplar. `unicode-codepoint-range-v1` yontemi:

- alt sinir: `max(whitespace_units, ceil(codepoints / 6))`
- merkez tahmin: `max(alt_sinir, ceil(codepoints / 4))`
- ust sinir: `max(merkez_tahmin, ceil(codepoints / 2))`

Bu genis aralik kapasite planlama icindir. Egitim ekibi hedef tokenizer ile exact
sayimi kendi katmaninda yapar; Derlem verisi yeniden onaylanmaz.

## Yetkiler

- Export baslatma: `admin`, `data_manager`
- Artifact ve manifest indirme: `admin`, `data_manager`, `consumer_team`
- Diger roller: release metadata'sini gorebilir, artifact indiremez

## Kanonik Yapisal Kayit

Calisan sema `schemas/conversation_sample.schema.json`, ingest-ready ornekler ise
`data_samples/example_canonical_conversations.jsonl` ve
`data_samples/example_canonical_preferences.jsonl` altindadir. Model adi,
`model_compatibility`, chat template, ozel token veya render edilmis prompt bu
semaya kabul edilmez. Bunlar LLM/tokenizer ekibinin turetilmis artifact'leridir.
Yapisal export zarfi `schemas/canonical_export_record.schema.json` ile
dogrulanabilir.
