# Scalability Architecture

Bu belge, Web Veri Atolyesi'nin milyonlarca kullanici ve yuksek hacimli veri
girisi/edit/onay akisini kaldirabilmesi icin onerilen mimariyi tanimlar.

## Ana Karar

Milyonlarca kullanici hedefi icin performansi tek bir dil secimiyle cozemeyiz.
Dogru cozum yatay olceklenebilir, kuyruklu ve dogrudan object-store odakli
tasarimdir.

Uretim hedefi:

- **Core API:** Go
- **Data workers:** Python
- **Frontend:** Next.js + TypeScript
- **DB:** PostgreSQL
- **Object store:** MVP'de icerik-adresli local store; uretimde MinIO/S3
- **Queue/event:** PostgreSQL ile basla; gerekirse Redis Streams, daha sonra Kafka veya NATS JetStream
- **Agi isleme:** Python + Polars + DuckDB; gerekirse Rust yardimci CLI

## Neden Go Core API

Go, public API, auth, metadata, review workflow ve release orchestration icin iyi
bir merkezdir:

- Tek binary deploy kolayligi.
- Yuksek concurrency icin sade runtime.
- `net/http` ve `database/sql` gibi olgun standart kutuphaneler.
- Stateless API replica'lariyla yatay olceklenir.

Python yine kritik kalir, fakat request path disinda:

- PII tarama
- dosya analizi
- dedup raporlari
- DuckDB/Polars isleri
- export/render batch job'lari

Rust ana backend icin ilk tercih degil; ileride cok hizli hash/dedup/parser CLI
gerektiginde eklenebilir.

## Milyonlarca Kullanici Icin Temel Prensipler

1. **API stateless olur.**
   - Session state Redis/PostgreSQL tarafinda tutulur.
   - API replica sayisi yatay artar.

2. **Dosya yukleme API uzerinden akmaz.**
   - API sadece upload intent ve metadata olusturur.
   - Kullanici dosyayi presigned URL ile object store'a yukler.
   - API sonradan checksum/job kaydi acar.

3. **Agi isler request-response icinde calismaz.**
   - Encoding, PII, dedup, line count, decontamination ve export job'a gider.
   - Kullanici job durumunu gorur.

4. **PostgreSQL sadece metadata ve audit icindir.**
   - Metin blob'u DB'ye basilmaz.
   - Buyuk tablolar partition edilir.
   - Kritik indexler bastan tasarlanir.

5. **Audit append-only kalir.**
   - `audit_events` silinmez/duzenlenmez.
   - Yuksek hacimde zaman veya tenant bazli partition edilir.

6. **Backpressure vardir.**
   - Kuyruk dolarsa upload/review job'lari rate-limit edilir.
   - Kullaniciya "queued" durumu doner.

7. **Read/write path ayrilir.**
   - Public dashboard ve listeleme query'leri cache/read replica ile ayrilabilir.
   - Kritik yazma islemleri primary DB'ye gider.

## Katmanlar

```text
CDN/WAF
  -> Load Balancer
    -> Go API replicas
      -> PostgreSQL primary/read replicas
      -> PostgreSQL job queue; olcekte Redis Streams
      -> MinIO/S3 object store
    -> Python worker pool
      -> DuckDB/Polars/Presidio jobs
      -> immutable release exports
```

## Veri Tablolari Icin Olcek Notlari

Partition adaylari:

- `audit_events`: zaman veya tenant/org bazli
- `documents`: source_id veya created_at bazli
- `reviews`: created_at veya reviewer_id bazli
- `background_jobs`: status + created_at
- `release_items`: release_id

Index adaylari:

- `sources(status, content_purpose)`
- `documents(source_id, approval_status)`
- `documents(object_sha256)`
- `reviews(status, assignee_id)`
- `audit_events(actor_id, created_at)`
- `background_jobs(status, priority, created_at)`

## Kuyruk Tasarimi

Ilk asama:

- PostgreSQL `background_jobs` tablosu
- Worker claim: `FOR UPDATE SKIP LOCKED`
- Retry, idempotency ve hata durumlari DB'de izlenir
- job tipleri:
  - `ingest_file`
  - `compute_checksum`
  - `count_lines`
  - `scan_pii`
  - `exact_dedup`
  - `decontaminate_exact`
  - `build_export`

Olculmus ihtiyac sonrasi:

- Redis Streams
- Birden fazla worker consumer
- Backpressure ve daha hizli dispatch

Buyume asamasi:

- Kafka veya NATS JetStream
- consumer group'lar
- retry/dead-letter queue
- job idempotency

## API Tasarim Kurallari

- Her endpoint idempotent olmaya calisir.
- Buyuk listeleme cursor pagination kullanir.
- Bulk edit/onay asenkron job olur.
- Upload request'i sadece object store hedefi uretir.
- Her write islemi audit event uretir.
- Rate limit:
  - user
  - IP
  - organization
  - API token

## Dil Secimi Ozeti

| Katman | Dil | Gerekce |
| --- | --- | --- |
| Core API | Go | Yuksek concurrency, sade deploy, stateless API |
| Data workers | Python | Polars, DuckDB, Presidio, NLP/veri ekosistemi |
| Frontend | TypeScript | Next.js ve guvenli UI gelistirme |
| Hot-path CLI | Rust, opsiyonel | Dedup/hash/parser gibi dar performans isleri |

## MVP'ye Etkisi

MVP'de Kubernetes, mikroservis veya Docker zorunlu degil. Servisler dogrudan
gelistirme makinesinde calisir:

- `api-go`
- `worker-python`
- `postgres`
- `frontend`

Yerel dosya deposu storage interface arkasindadir. Uretimde MinIO/S3'e gecis ve
servislerin container olarak paketlenmesi API sozlesmesini degistirmez.
