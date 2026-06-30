# Yerel Gelistirme

Derlem ilk asamada Docker, Redis veya MinIO gerektirmez.

Login ekraninda yerel gelistirme hesabini gostermek ve alanlari otomatik
doldurmak icin ignore edilen `web/.env.local` dosyasinda su opsiyonel
degiskenler kullanilir:

```text
NEXT_PUBLIC_LOCAL_LOGIN_EMAIL=admin@derlem.local
NEXT_PUBLIC_LOCAL_LOGIN_PASSWORD=local-only-password
```

Bu degerler `NEXT_PUBLIC` oldugu icin web bundle'inda gorunur; yalnizca yerel
gelistirmede kullanilmali, production ortaminda tanimlanmamalidir.

## Gereksinimler

- Go 1.25+
- PostgreSQL 17+
- Python 3.12+
- Node.js 22+

## Yapilandirma

Kok dizindeki `.env.example` dosyasini `.env` olarak kopyalayin ve yerel
degerleri girin. `.env` ve `web/.env.local` git tarafindan izlenmez.

Zorunlu ana ayarlar:

```text
DATABASE_URL=postgresql://USER:PASSWORD@localhost:5432/derlem?sslmode=disable
JWT_SECRET=at-least-32-random-characters
BOOTSTRAP_ADMIN_EMAIL=admin@derlem.local
BOOTSTRAP_ADMIN_PASSWORD=strong-local-password
STORAGE_ROOT=./var/storage
```

## Ilk Kurulum

```powershell
go mod download
go run ./cmd/migrate
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".\worker[dev]"
Set-Location web
npm install
Set-Location ..
```

## Servisler

Uc ayri terminalde:

```powershell
go run ./cmd/api
```

```powershell
.\.venv\Scripts\python.exe -m derlem_worker
```

```powershell
Set-Location web
npm run dev
```

Arayuz `http://localhost:3000`, API `http://localhost:8080` adresindedir.

Worker bir dosyayi ice aldiktan sonra otomatik olarak `scan_pii` ve
`check_exact_duplicate` islerini acar. TCKN, IBAN, e-posta, telefon ve odeme
karti kontrolleri ile exact SHA256 tekrar kontrolu tamamlanmadan kaynak insan
onayina gecemez. Kanonik unique kaynak icin `sample_documents` isi bounded
inceleme ornekleri olusturur; orneklerin tam icerigi object store'da kalir.

Belge ornekleme ayarlari:

```text
DOCUMENT_SAMPLE_SIZE=200
MAX_DOCUMENT_BYTES=262144
```

## Kaynak Triage Raporu

Bir kaynak karantinaya dustugunde yerel, Git disi rapor uretmek icin:

```powershell
.\.venv\Scripts\python.exe -m derlem_worker.triage --source-id <SOURCE_ID> --output-dir .\var\reports
```

Bu rapor ham metin veya PII degeri yazmaz; gate durumlarini, release blocker
listesini ve PII/dedup sayilarini ozetler. Satir ordinali bazli PII triage
gerekiyorsa asagidaki opsiyon kullanilir, fakat buyuk corpuslarda dosyayi
bastan sona okuyacagi icin uzun surebilir:

```powershell
.\.venv\Scripts\python.exe -m derlem_worker.triage --source-id <SOURCE_ID> --output-dir .\var\reports --scan-pii-lines
```

## Clean Candidate Uretimi

Karantinadaki ham kaynak degistirilmez. PII iceren satirlari, oversized satirlari
ve normalize fingerprint fazlaliklarini cikararak yerel bir temiz aday dosya
uretmek icin:

```powershell
.\.venv\Scripts\python.exe -m derlem_worker.clean_candidate --source-id <SOURCE_ID> --output-dir .\var\derived
```

Bu komut buyuk corpuslarda dosyayi bastan sona okur; Gardas/Faz 2 gibi 13 GB+
dosyalarda uzun surebilir. Hizli duman testi icin:

```powershell
.\.venv\Scripts\python.exe -m derlem_worker.clean_candidate --source-id <SOURCE_ID> --output-dir .\var\derived --limit-lines 10000 --force
```

Uretilen `.manifest.json` dosyasi ham metin veya PII degeri icermez; yalnizca
hangi tur satirlarin kac adet cikarildigini ve cikti SHA256 bilgisini tutar.

## SimHash Kalibrasyonu

Kayitli bir kaynaktan deterministic, ham metinsiz esik raporu uretmek icin:

```powershell
.\.venv\Scripts\python.exe -m derlem_worker.similarity_calibration --source-id <SOURCE_ID> --sample-size 1000 --output-dir .\var\reports
```

Komut kaynagi bastan sona akis halinde tarar ve bellek kullanimini sample
boyutuyla sinirlar. Buyuk corpuslarda uzun surebilir; ayrintili Gardas komutu ve
rapor sozlesmesi icin [SimHash Kalibrasyon Raporu](similarity_calibration.md)
belgesine bakin.

## Testler

```powershell
go test ./...
$env:TEMP='C:\tmp'
$env:TMP='C:\tmp'
.\.venv\Scripts\python.exe -m pytest worker\tests
Set-Location web
npm run lint
npm run build
```

## Verinin Yeri

Dosyalar `STORAGE_ROOT/objects/sha256/aa/bb/<sha256>` yapisinda tutulur. Dosya
kimligi path degil SHA256 degeridir. PostgreSQL yalnizca metadata, is akisi,
job ve denetim kaydini tutar.

## Yerel Dosya Yolu Uyarisi

`POST /sources/{id}/ingest` yalnizca guvenilir admin/data manager kullanicilari
icin yerel gelistirme yoludur. Public katkida sunucu dosya yolu alinmayacak;
uretimde upload intent + S3/MinIO presigned upload kullanilacaktir.
