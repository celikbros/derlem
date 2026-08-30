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
JWT_TTL=8h
SESSION_IDLE_TTL=30m
LOGIN_FAILURE_WINDOW=15m
LOGIN_LOCKOUT_DURATION=15m
LOGIN_ACCOUNT_FAILURE_LIMIT=5
LOGIN_IP_FAILURE_LIMIT=30
BOOTSTRAP_ADMIN_EMAIL=admin@derlem.local
BOOTSTRAP_ADMIN_PASSWORD=strong-local-password
STORAGE_ROOT=./var/storage
STAGING_ROOT=./var/staging
IMPORT_ROOT=./var/import
```

Oturum ve brute-force korumasının ayrıntıları
[`session_security.md`](session_security.md) belgesindedir.

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

Arayuz `http://localhost:18400`, API `http://localhost:18401` adresindedir.

## Port sozlesmesi: 18400-18409

**Derlem asla standart/yaygin port kullanmaz.** Bu bir tercih degil, olculmus bir
zorunluluk: bu makinede `:8080`'i `examentor`, bir donem `:3000`'i `bioexamine`
tutuyordu ve Derlem baslatilinca hangi servise gittigi belirsizlesiyordu.

| Port | Servis |
|---|---|
| **18400** | Web (Next.js) |
| **18401** | Go API |
| 18402-18409 | Derlem'e ayrildi (worker metrikleri, ikinci ortam vb.) |

Kurallar:

- **49152 ve ustu KULLANILMAZ.** Windows'un dinamik port araligi orada baslar
  (`netsh int ipv4 show dynamicport tcp`); isletim sistemi giden baglantilara o
  portlari atayabilir ve sabit servisle carpisir.
- Yaygin portlardan uzak durulur: 80, 443, 3000, 3001, 5000, 5173, 8000, 8080,
  8081, 8443, 9000. Bunlar baska projelerin varsayilanidir.
- Yeni bir servis eklenirse **18402'den devam edilir**, rastgele port secilmez.
- Portlar `.env` (`HTTP_ADDR`, `WEB_ORIGIN`), `web/.env.local`
  (`DERLEM_API_URL`) ve `web/package.json` (`dev`/`start` icin `-p`) olmak uzere
  uc yerde tanimlidir; biri degisirse ucu birden degismelidir.

Kontrol: `netstat -ano | findstr ":184"` — yalniz Derlem'in surecleri gorunmelidir.

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

PDF/DOCX extraction güvenlik sınırları:

```text
EXTRACTION_MAX_SOURCE_BYTES=104857600
EXTRACTION_MAX_DOCX_ENTRIES=2048
EXTRACTION_MAX_DOCX_UNCOMPRESSED_BYTES=268435456
EXTRACTION_MAX_PDF_PAGES=1000
EXTRACTION_MAX_OUTPUT_CHARS=33554432
```

Worker parser'ı açmadan önce uzantıyla magic/format uyumunu doğrular. DOCX ZIP
girdi ve açılmış toplam içerik boyutu, PDF ise sayfa sayısı; bütün formatlarda
çıkarılan toplam metin sınırını aşarsa iş
açık bir extraction hatasıyla reddedilir. Bu sınırları yalnızca güvenilir
belgeler için ve kaynak tüketimini ölçerek yükseltin.

Uzun işlerde worker `WORKER_HEARTBEAT_INTERVAL` (varsayılan `30s`) aralığında
lease yeniler. Heartbeat `WORKER_LEASE_TIMEOUT` (varsayılan `5m`) boyunca
gelmezse başka bir worker işi güvenli retry/failure geçişine alır. Heartbeat
aralığı timeout değerinden kısa olmalıdır.

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

Surumlu Turkce web kalite filtresiyle v2 alt-kumesi uretmek icin:

```powershell
.\.venv\Scripts\python.exe -m derlem_worker.clean_candidate `
  --source-id <CLEARED_PARENT_SOURCE_ID> `
  --output-path .\var\import\candidate_v2.txt `
  --quality-policy tr-web-v1 `
  --quality-rejections-path .\var\import\candidate_v2.rejections.jsonl
```

Ret JSONL'i ham metin veya eslesen terim tasimaz; yalnizca parent
`source_ordinal` ve surumlu neden kodlarini tutar. Final hedefte `--force`
kullanilmaz. Gardas'a ozel insan ve ingest sirasi icin
`docs/gardas_clean_candidate_v2_runbook.md` belgesine bak.

## SimHash Kalibrasyonu

Kayitli bir kaynaktan deterministic, ham metinsiz esik raporu uretmek icin:

```powershell
.\.venv\Scripts\python.exe -m derlem_worker.similarity_calibration --source-id <SOURCE_ID> --sample-size 1000 --output-dir .\var\reports
```

Komut kaynagi bastan sona akis halinde tarar ve bellek kullanimini sample
boyutuyla sinirlar. Buyuk corpuslarda uzun surebilir; ayrintili Gardas komutu ve
rapor sozlesmesi icin [SimHash Kalibrasyon Raporu](similarity_calibration.md)
belgesine bakin.

Kalibrasyon raporundaki en yakin ciftleri insan incelemesine almak icin:

```powershell
.\.venv\Scripts\python.exe -m derlem_worker.similarity_review_import --report .\var\reports\similarity_calibration_pretrain_ebe29279.json
```

Importer kaynak ve rapor SHA256 degerlerini, ordinal belgeleri ve Hamming
mesafelerini yeniden dogrular. Buyuk kaynaklarda ilgili en buyuk ordinal
satirina kadar akacagi icin uzun surebilir. Tamamlanan kosu web arayuzundeki
`Benzerlik` gorunumunde listelenir; admin, moderator ve expert reviewer rolleri
bagimsiz karar ekleyebilir.

## Testler

```powershell
go test ./...
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

`POST /sources/{id}/ingest` yalnizca `admin` rolune aciktir. API sadece
`IMPORT_ROOT` altindaki sembolik bag icermeyen normal dosyalari kabul eder;
worker isi calistirmadan once ayni siniri yeniden dogrular. Dosyayi once bu
koke kopyalayip mutlak yolunu gonderin. Public katkida sunucu dosya yolu
alinmayacak; uretimde upload intent + S3/MinIO presigned upload kullanilacaktir.
