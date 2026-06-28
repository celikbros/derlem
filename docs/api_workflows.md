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
GET   /sources/{id}/document-sample-generations
POST  /sources/{id}/documents/resample
POST  /sources/{id}/documents/bulk-reviews
GET   /documents/{id}
PATCH /documents/{id}
GET   /documents/{id}/reviews
POST  /documents/{id}/reviews
GET   /sources/{id}/reviews
POST  /sources/{id}/reviews
GET   /jobs?source_id={id}
GET   /releases
POST  /releases
GET   /releases/{id}
POST  /releases/{id}/freeze
POST  /releases/{id}/exports
GET   /releases/{id}/manifest
GET   /releases/{id}/exports/{format}/artifact
GET   /releases/{id}/exports/{format}/manifest
GET   /releases/{id}/sources/{source_id}/artifact
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
  -> index_document_fingerprints queued (yalnizca kanonik unique kaynak)
  -> sample_documents queued (yalnizca normalized dedup unique kaynak)
  -> auto_checked | quarantined
```

PII taramasi TCKN checksum, IBAN mod-97, Luhn-dogrulamali odeme karti, telefon
ve e-posta sayimlari uretir. Ham eslesme degerleri DB'ye yazilmaz.
Worker baslangicta daha once ingest edilmis ama exact duplicate sonucu olmayan
kaynaklar icin eksik kontrol job'larini idempotent olarak kuyruga ekler.
Byte-level kontrol kaynak artifact'inin SHA256 tekrarini yakalar. Normalize
document exact-dedup ise duz satir veya JSONL `text`, `content`, `body` alanini
NFKC + casefold + whitespace collapse ile fingerprint'e cevirir. DB'ye ham metin
degil, hash/ordinal/sayac yazilir. Near-dedup kontrolleri sonraki fazdadir.

`sample_documents`, kaynak dosyasini bounded satir okuyucuyla tarar ve
`risk-stratified-sha256-v1` orneklemini uretir. Ornek kotasinin en fazla yarisi
yuksek riskli belgelerden, kalani SHA256 seed'li temsil reservoir'undan gelir.
Varsayilan olarak en fazla 200 ornek secilir; tam ornek icerigi immutable object
store'a, ordinal/preview/surum/risk metadata'si PostgreSQL'e yazilir. Job sonucu
yalniz risk neden sayaclarini tasir, eslesen metni veya kimlik degerini tasimaz.
Bu tablo tum corpus'un document indeksi degil, insan incelemesi icin bounded
sample katmanidir. Ayrintili sozlesme: [Risk Bazli Ornekleme](risk_sampling.md).

## Kontrollu Yeniden Ornekleme

`POST /sources/{id}/documents/resample` yalniz admin rolune aciktir. Kaynak
sample edilmis olmali; aktif belgelerde edit, review veya kaynak onayi baslamis
olmamali. Kapilardan biri kapanmissa islem `422 document_resample_gate_blocked`
ile reddedilir.

Worker yeni ornek listesini eski nesil aktifken uretir. Son yayim transaction'i:

1. Eski generation snapshot'ini `superseded` yapar.
2. Eski aktif document satirlarini pasifler.
3. Yeni belgeleri insert/reactivate eder ve risk metadata'sini yazar.
4. Her secimi `document_sample_memberships` tablosuna sabitler.
5. Yeni generation'i `active`, kaynagi yeniden `sampled` yapar.

Herhangi bir adim hata verirse transaction geri alinir ve eski nesil aktif
kalir. Worker nihai olarak basarisiz olursa kaynak `resampling` durumundan eski
`sampled` durumuna doner. Nesil listesi
`GET /sources/{id}/document-sample-generations` ile okunur.

## Onay Kapisi

`approved` karari icin tamamlanmasi zorunlu kapilar:

- Dosya immutable depoya alinmis olmali.
- `rights_status=cleared` olmali.
- `license_evidence_ref` bulunmali.
- `pii_status=clear` olmali.
- `duplicate_status=unique` olmali.
- `normalized_dedup_status=unique` olmali.
- `document_sampling_status=sampled` olmali.
- Ornek belgelerin tamami guncel surumlerinde `approved` olmali.
- Reddedilmis veya hassas incelemeye yonlendirilmis belge bulunmamali.
- Kaynak daha once onaylanmamis olmali.

Belge duzenlemesi `PATCH /documents/{id}` ile yeni immutable object ve yeni
`document_versions` satiri uretir. Mevcut `version` zorunludur; eszamanli
degisiklikte `409 version_conflict` doner. Eski surum yerinde degistirilmez.
Belge duzenlenince onceki inceleme yalnizca eski surumun kaniti olarak kalir;
kaynak kapsama sayaclari yeniden hesaplanir ve kaynak yeniden incelemeye iner.

Belge incelemesi `POST /documents/{id}/reviews` ile `approved`, `rejected` veya
`sensitive_review` karari ve 1-5 kalite puani alir. Ret ve hassas incelemede
gerekce zorunludur. Her kayit belge surumu ve object SHA256 snapshot'i ile
degistirilemez kanit olarak saklanir. Ayni reviewer ayni belge surumunu ikinci
kez inceleyemez; admin disindaki kullanici kendi kaynagini inceleyemez.

Ret ve hassas inceleme kararlarinda gerekce zorunludur. Karar, kaynak surumu,
reviewer, kapilarin snapshot'i ve zaman bilgisiyle saklanir. Admin disindaki
kullanicilar kendi kaynagini inceleyemez.

## Toplu Belge Inceleme

`POST /sources/{id}/documents/bulk-reviews`, moderator ve uzmanlarin en fazla
200 bekleyen belgeyi tek kararla incelemesini saglar. Istek her belge icin
`document_id` ve reviewer'in ekranda gordugu `document_version` degerini tasir.

Tum belgeler tek PostgreSQL transaction'i icinde kilitlenir. Belgelerden biri
degismis, daha once ayni reviewer tarafindan incelenmis veya artik beklemede
degilse islem tamamen geri alinir; kismi onay birakilmaz. Ret ve hassas kararda
ortak gerekce zorunludur. Basarili istekte her belge icin ayri append-only
`document.reviewed` olayi, kaynak icin de `documents.bulk_reviewed` ozet olayi
yazilir.

```json
{
  "documents": [
    {"document_id": "...", "document_version": 1}
  ],
  "decision": "approved",
  "quality_score": 4,
  "reason": null
}
```

## Release Builder

`POST /releases`, ayni `content_purpose` degerindeki `approved_source`
kaynaklardan draft olusturur. `release_sources`, kaynak kimligi ve SHA256'nin
yaninda source version, lisans, hak durumu, dil, alan ve lineage snapshot'i
saklar. Draft olustuktan sonra kaynak degisirse freeze kapisi sert hata verir.

`POST /releases/{id}/freeze` yalnizca admin rolune aciktir ve `freeze_release`
isini PostgreSQL kuyruguna ekler. Worker zorunlu source, rights, PII, source
artifact duplicate, normalized document dedup ve document-review kapilarini
yeniden dogrular. Pretrain release'inde eval ve holdout kaynaklarinin belge
metinleri `document-text-sha256-v1` exact-match yontemiyle karsilastirilir.
Eslesme veya bounded satir limitinin asilmasi freeze'i bloke eder.

Basarili freeze, deterministik `derlem.release-manifest.v1` JSON manifestini
immutable store'a yazar, manifest SHA256'sini ve freeze zamanini sabitler.
Frozen release ve release-source satirlari veritabani trigger'lariyla
degistirilemez. Manifest ve kaynak artifact'leri consumer endpointlerinden
salt-okunur indirilir.

## Kanonik Export

`POST /releases/{id}/exports`, yalnizca `frozen` durumundaki release icin
`jsonl` veya `txt` formatinda `export_release` isi olusturur. Admin ve data
manager export baslatabilir; admin, data manager ve consumer team hazir
artifact'leri indirebilir.

Worker kaynak snapshot'larini `source_id` sirasinda, her kaynagi da satir
sirasinda okur. Tum cikti bellekte tutulmaz; gecici dosyaya akis halinde
yazilir. Her 50.000 kayitta `background_jobs.result.progress` icine okunan
girdi byte'i, yazilan kayit, tamamlanan kaynak ve cikti byte'i kaydedilir.

JSONL kaydi modelden bagimsizdir:

```json
{"id":"...","metadata":{"content_purpose":"instruction","document_sha256":"...","domain":"general","external_id":null,"language":"tr","license":"internal","source_id":"...","source_ordinal":1,"source_sha256":"..."},"text":"Ornek metin"}
```

`id`, `source_sha256 + source_ordinal + document_sha256` birlesiminin SHA256
degeridir. Model adi, tokenizer adi veya chat template etiketi saklanmaz.
Egitim katmani kanonik JSONL'i hedef modelin adapter'i ile donusturur. TXT
ciktisi kolay tuketim icin belge basina tek UTF-8 satir uretir.

Hazir artifact ve `derlem.export-manifest.v1` manifesti content-addressed
immutable store'a yazilir. Manifest; release kimligi ve manifest SHA256'si,
format, medya tipi, kayit sayisi, byte boyutu, export SHA256'si ve kaynak
dagilimini sabitler. Ayni frozen snapshot ve format icin siralama, JSON
serilestirme ve belge kimligi deterministik oldugundan cikti checksum'i da
deterministiktir.

## Denetim

Her create, metadata update, ingest queue, ingest completion, PII scan, exact
duplicate kontrolu, normalized dedup kontrolu, login, belge review, kaynak
review, release create, freeze queue, freeze, export queue, export ready/fail
ve freeze-block islemi
`audit_events` tablosuna eklenir.
Tablo update, delete ve truncate islemlerini trigger ile reddeder.
