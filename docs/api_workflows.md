# API ve Is Akislari

API kok adresi yerelde `http://localhost:8080/api/v1` degeridir.

## Endpointler

```text
POST  /auth/login
GET   /me
GET   /sources
POST  /sources
GET   /sources/{id}
PATCH /sources/{id}
POST  /sources/{id}/ingest
POST  /sources/{id}/upload
GET   /sources/{id}/pii-scans
GET   /sources/{id}/documents
GET   /documents/{id}
PATCH /documents/{id}
GET   /sources/{id}/reviews
POST  /sources/{id}/reviews
GET   /jobs?source_id={id}
```

`PATCH /sources/{id}` optimistic locking kullanir. Istekte mevcut `version`
gonderilir; kayit arada degistiyse API `409 version_conflict` dondurur.
`content_purpose` update sozlesmesinde yoktur ve veritabani trigger'i tarafindan
da degistirilemez.

## Ingest Zinciri

```text
source_registered
  -> ingest_local_file queued
  -> immutable SHA256 object
  -> raw_ingested
  -> scan_pii + check_exact_duplicate queued
  -> sample_documents queued (yalnizca kanonik unique kaynak)
  -> auto_checked | quarantined
```

PII taramasi TCKN checksum, IBAN mod-97, Luhn-dogrulamali odeme karti, telefon
ve e-posta sayimlari uretir. Ham eslesme degerleri DB'ye yazilmaz.
Worker baslangicta daha once ingest edilmis ama exact duplicate sonucu olmayan
kaynaklar icin eksik kontrol job'larini idempotent olarak kuyruga ekler.
MVP kontrolu kaynak artifact'inin byte-level SHA256 tekrarini yakalar;
normalize edilmis dokuman ve near-dedup kontrolleri sonraki fazdadir.

`sample_documents`, kaynak dosyasini bounded satir okuyucuyla tarar ve SHA256
seed'li deterministik reservoir sample uretir. Varsayilan olarak en fazla 200
ornek secilir; tam ornek icerigi immutable object store'a, ordinal/preview/surum
metadata'si PostgreSQL'e yazilir. Bu tablo tum corpus'un document indeksi degil,
insan incelemesi icin bounded sample katmanidir.

## Onay Kapisi

`approved` karari icin tamamlanmasi zorunlu kapilar:

- Dosya immutable depoya alinmis olmali.
- `rights_status=cleared` olmali.
- `license_evidence_ref` bulunmali.
- `pii_status=clear` olmali.
- `duplicate_status=unique` olmali.
- `document_sampling_status=sampled` olmali.
- Kaynak daha once onaylanmamis olmali.

Belge duzenlemesi `PATCH /documents/{id}` ile yeni immutable object ve yeni
`document_versions` satiri uretir. Mevcut `version` zorunludur; eszamanli
degisiklikte `409 version_conflict` doner. Eski surum yerinde degistirilmez.

Ret ve hassas inceleme kararlarinda gerekce zorunludur. Karar, kaynak surumu,
reviewer, kapilarin snapshot'i ve zaman bilgisiyle saklanir. Admin disindaki
kullanicilar kendi kaynagini inceleyemez.

## Denetim

Her create, metadata update, ingest queue, ingest completion, PII scan, exact
duplicate kontrolu, login ve review islemi `audit_events` tablosuna eklenir.
Tablo update, delete ve truncate islemlerini trigger ile reddeder.
