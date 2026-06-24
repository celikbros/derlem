# Web Veri Atolyesi MVP Plani

Bu planin amaci, LLM veya tokenizer koduna mudahale etmeden veri kumelerini
kaydetmek, duzenlemek, onaylamak, surumlemek ve ilgili ekiplere export etmek
icin ilk calisir web sistemini kurmaktir.

## Kapsam

Atolye sunlari yapar:

- Kaynak ve veri kaydi tutar.
- Ham veya temiz metin dosyalarini sisteme alir.
- Metadata, lisans, risk ve kalite bilgisini yonetir.
- Editor/moderator/uzman onay akislarini calistirir.
- Onayli kayitlardan dataset release uretir.
- LLM ve tokenizer ekiplerine manifest, checksum, rapor ve JSONL/TXT export verir.

Atolye sunlari yapmaz:

- LLM egitimi calistirmaz.
- Tokenizer egitimi veya tokenization calistirmaz.
- Model kalitesi iddiasi uretmez.
- Lisansi belirsiz veriyi "sonradan bakariz" diyerek release'e almaz.

## Baslangic Verisi

Ilk seed kaynak:

```text
C:\CELIK-GARDASH
```

Gardas tarafindaki mevcut Faz 2 corpus once kataloglanir, sonra sha256 kimligi
ile icerik-adresli degismez depoya kopyalanir. Orijinal path yalnizca lineage
bilgisi olarak tutulur. Kaynak ancak kopyalama, checksum ve haklar kapisindan
sonra onayli seed kaynak sayilir.

- original path
- immutable object id / sha256
- dokuman/satir sayisi
- kaynak/karisim notu
- dedup raporu path'i
- mevcut release/manifest path'i

## Onerilen Stack

- Core API: Go
- DB: PostgreSQL
- Dosya saklama: MVP'de storage interface arkasinda icerik-adresli local immutable store; uretimde MinIO/S3
- Background jobs: MVP'de PostgreSQL `FOR UPDATE SKIP LOCKED`; olculmus ihtiyacta Redis Streams
- Agir isleme: DuckDB + Polars
- PII tarama: Presidio + TCKN checksum dogrulamasi
- Frontend: React/Next.js
- Auth: basit oturum/JWT ilk gunden; ileride Keycloak/OAuth
- Export: JSONL/TXT ilk gun, Parquet ikinci faz

Not: Python request path'in ana backend'i degil, veri isleme worker katmani
olarak kullanilir. Docker gelistirme icin zorunlu degildir. Milyonlarca
kullanici hedefi icin core API stateless Go servisi olarak tasarlanir.
Ayrinti: `docs/scalability_architecture.md`.

## Roller

| Rol | Yetki |
| --- | --- |
| `admin` | Kullanici, rol, sistem ayarlari, release freeze |
| `data_manager` | Kaynak ekleme, yukleme, havuz/karisim yonetimi |
| `editor` | Metin duzenleme, metadata tamamlama, kalite puani |
| `moderator` | Onay, ret, sensitive review yonlendirme |
| `expert_reviewer` | Hassas alanlarda uzman onayi |
| `contributor` | Veri onerme veya gorev tamamlama |
| `consumer_team` | Onayli release ve raporlari okuma/indirme |

## Ana Ekranlar

1. Dashboard
   - Toplam kaynak, onay bekleyen veri, riskli veri, son release, kalite dagilimi.

2. Kaynak Katalogu
   - Kaynak adi, tip, lisans, dil, domain, risk, path, checksum, durum.

3. Veri Yukleme
   - TXT, JSONL, CSV yukleme.
   - Tek metin girisi.
   - Kaynak metadata formu.

4. Kontrol Kuyrugu
   - Encoding, dil tahmini, PII/telif/sensitive uyarilari.
   - Cok kisa, cok uzun, tekrarli veya bozuk metin isaretleri.

5. Editor Ekrani
   - Orijinal metin ve duzenlenmis metin.
   - Metadata duzeltme.
   - Kalite puani.

6. Moderator Kuyrugu
   - `needs_review`, `sensitive_review`, `approved`, `rejected`.
   - Ret nedeni ve audit notu.

7. Dataset Havuzlari
   - `raw_sources`
   - `clean_tr_text`
   - `pretraining_candidates`
   - `instruction_answer`
   - `preference`
   - `evaluation_holdout`
   - `sensitive_review`

8. Release Builder
   - Kaynak/havuz secimi.
   - Train/eval/post-training ayrimi.
   - Export format secimi.
   - Manifest ve checksum uretimi.

9. Release Arsivi
   - Eski release'ler immutable kalir.
   - LLM/tokenizer ekipleri buradan path veya export alir.

## Ilk Veri Modeli

Minimum tablolar:

```text
users
roles
sources
documents
document_versions
conversation_samples
messages
message_parts
tool_definitions
tool_calls
tool_results
model_adapters
export_profiles
prompt_renderings
reviews
quality_scores
datasets
dataset_items
releases
release_items
audit_events
background_jobs
```

Minimum nesneler:

- `source`: veri nereden geldi?
- `document`: kayit/metin nedir?
- `document_version`: duzenleme gecmisi nedir?
- `conversation_sample`: model bagimsiz konusma/gorev ornegi nedir?
- `message`: system/user/assistant/tool rolleriyle mesaj nedir?
- `message_part`: text, image, video, audio veya tool_reference parcasi nedir?
- `tool_call` ve `tool_result`: arac cagri/sonuc baglantisi nedir?
- `model_adapter`: GLM, DeepSeek, Kimi gibi model ailelerinin render kurali nedir?
- `export_profile`: sample hangi standart export sozlesmesine uyar?
- `prompt_rendering`: kanonik veriden belirli adapter ile uretilen prompt artifact'i nedir?
- `review`: kim ne zaman onayladi/reddetti?
- `quality_score`: kalite ve risk puani nedir?
- `dataset`: hangi havuza ait?
- `release`: hangi surum donduruldu?

Not: LLM promptlari model-spesifik chat template veya encoder ile render
edildigi icin veritabani tek bir modelin template'ine gore tasarlanmaz. Kanonik
conversation/message/tool/multimodal veri tutulur; GLM, DeepSeek veya Kimi icin
render islemi `model_adapters` ve `prompt_renderings` katmaninda izlenir.

## Coklu Model Kullanilabilirligi

Veriler tek bir model ailesi icin degil, birden fazla modelin egitim,
post-training ve degerlendirme sureclerinde kullanilabilir olacak sekilde
saklanir.

- Kanonik veri model bagimsiz kalir.
- Model-spesifik chat template, ozel token ve encoder sonucu turetilmis artifact sayilir.
- Ayni sample birden fazla `model_adapter` ile render edilebilir.
- Veri Atolyesi model bazli uyumluluk onayi vermez.
- Hangi sample'in hangi standart export sozlesmesine uydugu `export_profile`
  ile izlenir.
- Yeni bir model ciktiginda modeli egiten katman kanonik export'u kendi
  adapter'i ile donusturur; sample'lar tek tek yeniden onaylanmaz.
- Release Builder kanonik export ve model-spesifik export'u ayri uretir.
- Model-spesifik rendered prompt saklanacaksa immutable object store'a yazilir,
  DB'ye buyuk prompt blob'u basilmaz.

## Zorunlu Metadata

MVP'de bir kaynak release'e girebilmek icin en az su alanlari tasimalidir:

- `source_name`
- `source_type`
- `content_purpose`: pretrain, instruction, preference, eval, holdout, post_training
- `license`
- `rights_status`
- `language`
- `domain`
- `source_url` veya kaynak kaniti
- `license_evidence_ref`
- `lineage_ref`
- `object_sha256`
- `sha256`
- `line_count` veya `doc_count`
- `pii_status`
- `risk_level`
- `approval_status`
- `created_by`
- `created_at`

Release freeze icin ek zorunlu alanlar:

- `frozen_by`
- `frozen_at`
- `release_manifest_path`
- `release_sha256`
- `export_format`
- `source_ids`
- `source_sha256s`
- `pipeline_config_version`
- `gate_results`
- `audit_event_id`

## Veri Yonetimi Kirmizi Cizgileri

- Lisansi belirsiz veri release'e giremez.
- KVKK/PII riski isaretlenmeden export uretilemez.
- Eval/holdout verisi pretraining adaylarina karisamaz.
- Pretrain release'i exact-match dekontaminasyon kapisindan gecmeden dondurulamaz.
- Frozen release degistirilemez; hata varsa yeni release acilir.
- Raw veri overwrite edilmez.
- Ret nedeni olmadan rejection kaydi kapanmaz.
- Instruction, preference ve eval havuzlari pretraining havuzlarindan teknik olarak ayrilir.
- `content_purpose` kayit aninda zorunludur ve sonradan degistirilemez.
- Kanonik veri model-spesifik template'e overwrite edilmez.
- Render edilmis prompt birincil veri sayilmaz; yeniden uretilebilir artifact'tir.
- Ajanlar hak/lisans temizleyemez, release donduramaz, kullanici guven seviyesi yukseltmez.

## Danisman Yanitiyle Kesinlesen Kararlar

Gercek danisman yaniti `docs/advisor_response_web_data_atolyesi_mvp.md`
dosyasina islendi. Bu yanita gore asagidaki kararlar plana kesin olarak eklendi.

- Buyuk corpus satir satir insan onayina sokulmayacak; kaynak veya shard bazli
  onay ve orneklem denetimi kullanilacak.
- PostgreSQL metin blob deposu olmayacak; metadata, review, audit ve release
  kayitlarini tutacak.
- Otomatik kontroller Faz 4'e birakilmayacak; checksum, encoding, dosya boyutu,
  satir/dokuman sayimi, lisans durumu, exact duplicate ve temel PII uyarilari
  Faz 1-2'de zorunlu olacak.
- Release Builder'dan once kalite ve risk kapilari calisacak.
- Raw dosya sadece path ile referanslanmayacak; sha256 kimligiyle degismez depoya kopyalanacak.
- Frozen release degistirilmeyecek; hata varsa yeni release acilacak.
- Auth Faz 0'da baslayacak; OAuth ertelenebilir ama kimlik dogrulama ertelenemez.
- Audit log append-only olacak; ideal hedef hash-zincirli denetim kaydi.
- `content_purpose` zorunlu ve immutable olacak.
- Pretrain release oncesi eval/holdout setlerine karsi exact-match dekontaminasyon zorunlu olacak.
- Haklar kapisi default-deny calisacak; belirsiz hak/lisans release'i bloke edecek.
- Temel PII kontrolune TCKN checksum, IBAN, telefon, e-posta ve kart uyarilari eklenecek.
- Parquet, OAuth, gelismis dashboard, near-dedup, kapsamli PII modeli,
  gelismis kalite skoru ve MinIO/S3 ilk MVP sonrasi fazlara ertelenebilir.

## Durum Makinesi

Kaynak/dosya akisi:

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

Kayit/katki akisi:

```text
submitted
  -> auto_filter
  -> needs_review
  -> edited
  -> approved | rejected | sensitive_review
  -> export_ready
```

## MVP Fazlari

### Faz 0: Iskelet

Sure: 1 hafta

- Go core API proje iskeleti
- Python worker proje iskeleti
- PostgreSQL migration altyapisi
- Kullanici/rol modeli
- Basit oturum/JWT ile gercek auth
- Append-only audit log tablosu
- Storage interface tasarimi
- Local immutable storage dizinleri ve PostgreSQL job queue
- Temel admin login

Kabul kriteri:

- Admin giris yapar.
- Kaynak metadata'si manuel eklenir.
- Audit event eklenir, silinmez ve duzenlenmez.
- Auth olmadan admin/API islemi yapilamaz.

### Faz 1: Veri Giris ve Kaynak Katalogu

Sure: 1-2 hafta

- Kaynak ekleme formu
- TXT/JSONL yukleme
- `content_purpose` zorunlu ve immutable alan
- Checksum hesaplama
- Dosya boyutu kaydi
- Satir/dokuman sayimi
- UTF-8/encoding okunabilirlik kontrolu
- Lisans ve rights_status zorunlu alan kontrolu
- Gardas seed dahil dosyayi icerik-adresli immutable store'a kopyalama
- Original path'i sadece lineage olarak saklama
- Kaynak listeleme/arama

Kabul kriteri:

- Gardas Faz 2 verisi seed kaynak olarak gorunur.
- Gardas Faz 2 verisi onayli seed olmadan once immutable store'a kopyalanir.
- Yeni bir TXT/JSONL dosyasi kaydedilir.
- Dosya sha256/object id, original path ve checksum DB'ye yazilir.
- `content_purpose` eksikse kayit kabul edilmez.
- Lisans/rights_status eksikse kaynak release adayi olamaz.

### Faz 2: Review, Duzenleme ve Hafif Kalite Kapilari

Sure: 2 hafta

- Document listeleme
- Editor ekrani
- Moderator onay/ret
- Kalite puani
- Review/audit gecmisi
- Exact duplicate kontrolu
- Temel PII uyarilari: TCKN checksum, IBAN, telefon, e-posta, kart
- Risk level ve sensitive flag
- Ret nedeni zorunlulugu
- Haklar kapisi: unknown/blocked rights_status release adayini bloke eder

Kabul kriteri:

- Bir kayit duzenlenir.
- Moderator onay veya ret verir.
- Ret nedeni ve audit log saklanir.
- Temel PII veya duplicate uyarisi olan kayit moderator tarafindan acikca ele alinir.
- TCKN checksum ile dogrulanmis PII bulgusu export'a otomatik gecmez.

### Faz 3: Release Builder

Sure: 1-2 hafta

- Dataset havuzu secimi
- JSONL/TXT export
- Manifest uretimi
- Checksum dosyasi
- Release arsivi
- Freeze eden kullanici ve freeze zamani
- Release oncesi zorunlu kalite/risk kapisi kontrolu
- Release oncesi exact-match decontamination: eval/holdout icerigi pretrain havuzunda varsa bloke
- Release manifest hash'i ve kaynak sha256 snapshot'i
- Yanlis `content_purpose` seciminde sert hata

Kabul kriteri:

- Onayli kayitlardan frozen release uretilir.
- Release daha sonra degistirilemez.
- Consumer ekip release dosyalarini indirebilir veya path alabilir.
- Release checksum ve manifest audit log'a baglanir.
- Decontamination gate PASS olmadan pretrain release dondurulemez.
- Freeze audit kaydinda kaynak ID'leri ve o andaki sha256'lar bulunur.

### Faz 4: Gelismis Otomatik Kontroller

Sure: 2 hafta

- Daha iyi dil tespiti
- Bozuk karakter/mojibake skoru
- Near-dedup denemesi
- Daha kapsamli PII modeli
- Approximate decontamination / n-gram overlap
- Riskli domain/sensitive flag
- Kalite skoru iyilestirme

Kabul kriteri:

- Gelismis uyarilar mevcut review akisini bozmadan eklenir.
- Moderator uyarilari filtreleyebilir ve raporlayabilir.

## Ilk Sprint Isleri

1. Go core API + PostgreSQL proje iskeleti.
2. `sources` ve `releases` tablolarini olustur.
3. Auth ve append-only audit log'u olustur.
4. Icerik-adresli storage interface ve local immutable store'u olustur.
5. Python worker icinde Gardas Faz 2 seed dosyasini sha256 ile immutable store'a kopyalayacak script yaz.
6. Kaynak katalogu API'sini yaz.
7. Checksum, dosya boyutu, satir sayimi ve encoding kontrolunu ekle.
8. `content_purpose` alanini zorunlu ve immutable yap.
9. Basit admin UI'da kaynaklari listele.

Ilk calisan dilimde Redis, Kafka, NATS, MinIO ve Docker yoktur. Bunlar ancak
olcumler veya uretim saklama gereksinimleri gerekli kilarsa eklenir.

## Danisman Yanitiyle Kapanan Kararlar

1. PostgreSQL + dosya/object storage ayrimi dogru; metin DB blob'u olmayacak.
2. Local filesystem ile baslanabilir, ancak dosya kimligi path degil sha256 olacak ve storage interface MinIO/S3 gecisine hazir tasarlanacak.
3. Gardas seed sadece path/checksum ile onayli kaynak sayilmayacak; once immutable store'a kopyalanacak.
4. Web-scale corpus icin kaynak/shard bazli onay + istatistiksel/risk bazli orneklem denetimi kullanilacak.
5. `content_purpose` zorunlu, immutable ve Release Builder tarafinda sert kural olacak.
6. Pretrain release oncesi eval/holdout setlerine karsi exact-match decontamination calisacak.
7. Haklar kapisi default-deny olacak; belirsiz lisans/hak durumu release'i bloke edecek.
8. Auth Faz 0'da baslayacak; OAuth/Keycloak ertelenebilir ama kimlik dogrulama ertelenemez.
9. Audit log append-only olacak; freeze aninda source id + sha256 snapshot'i saklanacak.

## Acik Kalan Hukuk Kararlari

Bu plan muhendislik/surec tasarimidir. Lisans, KVKK, telif, takedown ve ozel
nitelikli veri politikasi icin hukuk danismani tarafindan ayri onay gerekir.

## Uygulama Durumu - 2026-06-24

Tamamlanan calisan dilim:

- Go API: auth, roller, source CRUD, optimistic locking ve cursor pagination
- PostgreSQL: append-only audit, immutable `content_purpose`, job queue ve review snapshot
- Worker: immutable ingest, SHA256, UTF-8, satir sayimi ve otomatik PII job zinciri
- PII minimumu: TCKN checksum, IBAN mod-97, kart Luhn, telefon ve e-posta
- Exact duplicate kapisi: SHA256 ile kanonik ilk kaynagi belirleme, tekrar kaynagi karantinaya alma
- Bounded belge ornekleme: SHA256 seed'li deterministik reservoir sample, immutable document surumleri
- Document editor: tam icerigi object store'dan okuma, optimistic locking ile yeni surum kaydetme
- Document moderation: 1-5 kalite puani, surum/checksum snapshot'li immutable review ve self-review engeli
- Review kapisi: dosya + cleared rights + lisans kaniti + clear PII + unique exact duplicate + tum belge orneklerinde guncel onay zorunlu
- Next.js: kaynak katalogu, metadata duzenleme, inceleme ve job gorunumu

PII taramasi eslesen ham degerleri saklamaz; yalnizca tur bazinda sayim tutar.
Admin disindaki reviewer kendi olusturdugu kaynagi onaylayamaz.
