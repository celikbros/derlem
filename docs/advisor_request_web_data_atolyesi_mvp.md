# Danisman Inceleme Istegi: Web Veri Atolyesi MVP

> **Durum notu (2026-06-23):** Bu belge danismana yoneltilen tarihsel istegi
> korur. Uygulama kararlari danisman yaniti ve sonraki teknik degerlendirmeyle
> degismistir: aktif kaynak `docs/web_data_atolyesi_mvp_plan.md` belgesidir.
> Ilk uygulamada kuyruk PostgreSQL'dir; ham dosya onaydan once SHA256 adresli
> immutable depoya kopyalanir.

## Kisa Baglam

Turkce Veri Atolyesi, LLM veya tokenizer koduna mudahale etmeyecek. Amacimiz
veri kaydetmek, duzenlemek, onaylamak, surumlemek ve LLM/tokenizer ekiplerine
onayli dataset export paketleri vermek.

Ilk seed veri `C:\CELIK-GARDASH` tarafindaki mevcut Gardas/Faz 2 corpus olacak.
Dosyayi ilk asamada kopyalamak yerine path, checksum, doc/satir sayisi ve rapor
path'leriyle sisteme kaydetmeyi planliyoruz.

Plan belgesi:

```text
docs/web_data_atolyesi_mvp_plan.md
```

Ic on degerlendirme notlari:

```text
docs/advisor_feedback_web_data_atolyesi_mvp.md
```

## Onerilen Mimari

- Core API: Go
- Data workers: Python
- DB: PostgreSQL
- Dosya: local filesystem, ileride MinIO/S3
- Queue: Redis Streams veya Redis-backed queue
- Frontend: React/Next.js
- Export: JSONL/TXT ilk gun, Parquet ikinci faz

Buyuk metin blob'lari PostgreSQL'e basilmayacak. PostgreSQL sadece metadata,
review, kalite, audit ve release kayitlarini tutacak.

## MVP Rolleri

- `admin`
- `data_manager`
- `editor`
- `moderator`
- `expert_reviewer`
- `contributor`
- `consumer_team`

## MVP Ekranlari

1. Dashboard
2. Kaynak katalogu
3. Veri yukleme
4. Kontrol kuyrugu
5. Editor ekrani
6. Moderator kuyrugu
7. Dataset havuzlari
8. Release builder
9. Release arsivi

## Zorunlu Metadata Taslagi

Bir kaynak release'e girebilmek icin en az su alanlari tasimasi planlanir:

- `source_name`
- `source_type`
- `license`
- `rights_status`
- `language`
- `domain`
- `storage_path`
- `sha256`
- `line_count` veya `doc_count`
- `risk_level`
- `approval_status`
- `created_by`
- `created_at`

Release freeze icin ek alanlar:

- `frozen_by`
- `frozen_at`
- `release_manifest_path`
- `release_sha256`
- `export_format`
- `source_ids`
- `audit_event_id`

## Planlanan Akis

Kaynak/dosya:

```text
source_registered
  -> license_review
  -> raw_ingested
  -> normalized
  -> auto_checked
  -> sampled_for_review
  -> approved_source
  -> release_candidate
  -> frozen_release
```

Kayit/katki:

```text
submitted
  -> auto_filter
  -> needs_review
  -> edited
  -> approved | rejected | sensitive_review
  -> export_ready
```

## Faz Plani Ozeti

### Faz 0: Iskelet

- Go core API proje iskeleti
- Python worker proje iskeleti
- PostgreSQL migration altyapisi
- Kullanici/rol modeli
- Local storage dizinleri
- Temel admin login

### Faz 1: Veri Giris ve Kaynak Katalogu

- Kaynak ekleme formu
- TXT/JSONL yukleme
- Checksum hesaplama
- Dosya boyutu kaydi
- Satir/dokuman sayimi
- UTF-8/encoding okunabilirlik kontrolu
- Lisans ve `rights_status` zorunlu alan kontrolu
- Immutable raw dosya kaydi
- Kaynak listeleme/arama

### Faz 2: Review, Duzenleme ve Hafif Kalite Kapilari

- Document listeleme
- Editor ekrani
- Moderator onay/ret
- Kalite puani
- Review/audit gecmisi
- Exact duplicate kontrolu
- Temel PII regex uyarilari
- Risk level ve sensitive flag
- Ret nedeni zorunlulugu

### Faz 3: Release Builder

- Dataset havuzu secimi
- JSONL/TXT export
- Manifest uretimi
- Checksum dosyasi
- Release arsivi
- Freeze eden kullanici ve freeze zamani
- Release oncesi zorunlu kalite/risk kapisi kontrolu

### Faz 4: Gelismis Otomatik Kontroller

- Daha iyi dil tespiti
- Bozuk karakter/mojibake skoru
- Near-dedup denemesi
- Daha kapsamli PII modeli
- Kalite skoru iyilestirme

## Simdiden Plana Eklenen Ic On Degerlendirme Kararlari

Bu maddeler gercek danisman yaniti degildir; danismandan bunlari onaylamasini
veya duzeltmesini bekliyoruz:

- Buyuk corpus satir satir insan onayina sokulmayacak; kaynak veya shard bazli
  onay ve orneklem denetimi kullanilacak.
- PostgreSQL metin blob deposu olmayacak.
- Otomatik kontroller Faz 4'e kalmayacak; checksum, encoding, dosya boyutu,
  satir/dokuman sayimi, lisans durumu, exact duplicate ve temel PII uyarilari
  Faz 1-2'de zorunlu olacak.
- Release Builder'dan once kalite ve risk kapilari calisacak.
- Raw dosya immutable kabul edilecek.
- Frozen release degistirilmeyecek; hata varsa yeni release acilacak.
- Parquet, OAuth, gelismis dashboard, near-dedup, kapsamli PII modeli,
  gelismis kalite skoru ve MinIO/S3 ilk MVP sonrasi fazlara ertelenebilir.

## Danismandan Istedigimiz Yorum

Lutfen ozellikle su kararlara yorum verin:

1. PostgreSQL + local filesystem ile baslamak dogru mu, yoksa MinIO/S3 ilk gunden gerekli mi?
2. Web-scale corpus icin kaynak/shard bazli onay yeterli mi?
3. Ilk MVP'de zorunlu metadata alanlari neler olmali?
4. PII, KVKK, lisans ve telif icin minimum kabul edilebilir kontrol seviyesi nedir?
5. Release freeze icin hangi audit kayitlari zorunlu olmali?
6. Instruction/preference/eval verisinin pretraining adaylarina karismamasi icin hangi teknik kural gerekir?
7. Gardas Faz 2 verisini seed olarak sadece path/checksum ile kaydetmek yeterli mi?
8. MVP faz siralamasinda eksik veya ters sirada gordugunuz bir is var mi?
9. Yukaridaki ic on degerlendirme kararlarini onaylar misiniz; hangileri degismeli?

## Beklenen Cevap Formati

```text
1. En kritik risk:
2. Onayladiginiz kararlar:
3. Degismesini onerdiginiz kararlar:
4. MVP'ye mutlaka eklenmeli:
5. MVP'den sonraya ertelenebilir:
6. Veri yonetimi/acil kirmizi cizgiler:
7. Kisa nihai tavsiye:
```
