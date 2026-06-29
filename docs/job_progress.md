# Arka Plan İşi İlerleme Sözleşmesi

Derlem uzun süren işleri PostgreSQL `background_jobs` kuyruğunda çalıştırır.
Geçici ilerleme bilgisi yeni bir tablo yerine çalışan job kaydının
`result.progress` alanında tutulur.

## Kapsam

Canlı ilerleme üreten işler:

- `ingest_local_file` ve `ingest_staged_file`
- `scan_pii`
- `index_document_fingerprints`
- `sample_documents` ve `resample_documents`
- `export_release`

## JSON Sözleşmesi

```json
{
  "phase": "fingerprinting",
  "progress": {
    "input_bytes_processed": 5368709120,
    "input_bytes_total": 12884901888,
    "lines_read": 2480000,
    "documents_scanned": 2478000,
    "indexed_documents": 2394000,
    "skipped_oversized": 3,
    "skipped_too_short": 83997
  }
}
```

Alanlar iş tipine göre genişleyebilir. Ortak alanlar byte ilerlemesi ve okunan
satır sayısıdır. Fingerprint işi indekslenen belge sayılarını, sampling işi
uygun/riskli aday sayılarını, PII işi toplam bulgu sayısını ekler.

## Fazlar

| Faz | Anlamı |
|---|---|
| `validating_checkpoint` | Önceki ingest checkpoint'i kaynak önekiyle byte byte doğrulanıyor |
| `ingesting` | Dosya doğrulanıyor ve immutable store'a kopyalanıyor |
| `scanning_pii` | Temel PII desenleri taranıyor |
| `fingerprinting` | Normalize document fingerprint'leri üretiliyor |
| `matching_duplicates` | Üretilen fingerprint'ler karşılaştırılıyor |
| `sampling` | Temsil ve risk kotalı örnek seçiliyor |
| `publishing_samples` | Seçilen örnek nesli atomik olarak yayınlanıyor |
| `building` | Release export artifact'i üretiliyor |

## Yazma ve Yenileme Politikası

- Worker tarama sırasında yaklaşık her 64 MiB'de bir progress yazar.
- Ingest progress yazılmadan önce checkpoint `flush` ve `fsync` edilir; retry aynı
  job UUID'sine ait doğrulanmış byte konumundan devam eder.
- Progress ayrı PostgreSQL bağlantısıyla commit edilir; uzun corpus transaction'ı
  tamamlanmadan UI tarafından görülebilir.
- Retry başladığında eski `result` ve `last_error` temizlenir.
- İş başarıyla tamamlandığında geçici progress, kanonik final result ile
  değiştirilir.
- İşler ekranı aktif job varken iki saniyede bir sessiz yenilenir.

Progress operasyon görünürlüğüdür; release veya kaynak kanıtı değildir. Kalıcı
kanıt final job result, audit event, manifest ve object SHA256 kayıtlarıdır.
