# Yerel Gelistirme

Derlem ilk asamada Docker, Redis veya MinIO gerektirmez.

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
onayina gecemez.

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
