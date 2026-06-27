# Derlem Kanonik Export Sozlesmesi

**Surum:** `derlem.export-manifest.v1`

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

Her satir tek bir belge tasir:

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

## TXT Ciktisi

TXT artifact belge basina tek UTF-8 satir uretir. Belge icindeki `CRLF`, `CR`
ve `LF` karakterleri tek bosluga donusturulur. Bu format hizli pretraining
tuketimi icindir; lineage ve metadata gerektiren tuketiciler JSONL kullanir.

## Determinizm

Checksum garantisini su kurallar saglar:

1. Kaynaklar `source_id` ile siralanir.
2. Belgeler kaynak icindeki kalici satir sirasinda okunur.
3. Belge kimligi `source_sha256`, satir numarasi ve metin SHA256'sinden uretilir.
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

Arayuz bu sayaclari Isler gorunumunde gosterir. Gardas temiz adayinin export'u
buyuk bir disk okuma/yazma isi oldugu icin yeterli bos alan kontrol edilerek
ve worker log'u izlenerek baslatilmalidir.

## Yetkiler

- Export baslatma: `admin`, `data_manager`
- Artifact ve manifest indirme: `admin`, `data_manager`, `consumer_team`
- Diger roller: release metadata'sini gorebilir, artifact indiremez

## Sonraki Genisleme

Mevcut sozlesme text corpus icindir. Instruction, tool-call, preference ve
conversation verileri icin `messages`, `tools`, `chosen/rejected` gibi modelden
bagimsiz yapisal alanlar ayri canonical sema surumunde eklenecektir. Hedef
modelin Jinja/chat template'i yine Derlem veritabanina tasinmayacaktir.
