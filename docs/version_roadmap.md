# Derlem Versiyon Yol Haritasi

> **DONDURULDU (2026-07-07):** Aktif yol haritası artık
> [Diyet Yol Haritası](diyet_yol_haritasi.md)'dır ([v1 Otopsi](v1-autopsy.md)
> uyarınca). Bu belgedeki v0.4 sonrası hedefler (v0.5 katkı/ajan, v0.6 üretim
> altyapısı) diyet tamamlanana kadar dondurulmuştur. Not: buradaki
> "tamamlandı" iddialarının teknik doğrulamaları smoke (sentetik) verilerle
> yapılmıştır; gerçek corpus teslimatı henüz gerçekleşmemiştir.

**Tarih:** 2026-07-01
**Kapsam:** Derlem veri atölyesinin versiyon versiyon hedefleri, mevcut konumu ve sonraki işler.

Bu belge Derlem'i LLM/tokenizer projelerinden bağımsız, modelden bağımsız ve
denetlenebilir bir veri üretim sistemi olarak planlar. LLM veya tokenizer
modeline müdahale edilmez; Derlem kanonik veriyi, metadata'yı, kalite kanıtını,
manifestleri ve release artifact'lerini üretir. Model ekipleri bu çıktıları kendi
adaptörleriyle kullanır.

## Neredeyiz?

Güncel tamamlanma değerlendirmesi için ayrıca
[Derlem Proje Tamamlanma Durumu](project_completion_status.md) belgesi tutulur.
Canlı sunucu kurulumu için [Production Deployment](production_deployment.md)
runbook'u kullanılacaktır.

Şu an pratik olarak **v0.1 Core MVP** tamamlandı ve yerel makinede çalışıyor.
Sistem artık tek dosya/tek kaynak ölçeğinde güvenli bir uçtan uca akış üretiyor:

- Go API, JWT auth, roller ve RBAC çalışıyor.
- PostgreSQL metadata, job queue ve append-only audit için kullanılıyor.
- Büyük metinler DB blob'u değil, içerik-adresli immutable local object store'da duruyor.
- Kaynak kaydı, browser upload ve güvenilir local ingest var.
- Worker; SHA256, UTF-8, byte/line count, PII, source artifact exact duplicate,
  normalized document exact-dedup ve bounded sample çıkarıyor.
- Büyük ingest, PII, fingerprint ve sample/resample işleri 64 MiB aralıklı canlı
  byte/satır/doküman ilerlemesini İşler ekranına yazıyor.
- İnsan review kapısı; lisans kanıtı, hak durumu, PII, dedup ve tüm örnek onaylarını zorunlu tutuyor.
- Belge örneği açma, düzenleme, yeni immutable sürüm ve belge review geçmişi var.
- Release Builder; aynı `content_purpose` içindeki onaylı kaynaklardan draft/frozen release üretiyor.
- Frozen manifest, kaynak SHA256 snapshot'ı, release audit'i ve artifact download uçları var.
- Pretrain release için eval/holdout exact decontamination kapısı var.
- Pretrain release için eval/holdout SimHash64 yaklaşık decontamination pilot raporu var.
- Tüm release amaçları için kaynak içi/kaynaklar arası SimHash64 near-dedup raporu var.
- Next.js web arayüzünde kaynak katalogu, inceleme, işler ve sürümler ekranları çalışıyor.
- GitHub Actions CI backend/worker/web için yeşil.

Yerel kapalı pilotun temel güvenlik omurgası hazırdır; fakat bu durum production
hardening'in tamamlandığı anlamına gelmez. Ölçekli corpus operasyonuna ek olarak
[Güvenlik Hardening Backlog'u](security_hardening_backlog.md) içindeki P0
maddeleri internet-facing staging/production için bloklayıcıdır.

## Versiyon İlkeleri

- `v0.x` sürümleri MVP ve kapalı pilot dilimleridir; hızlı ama audit garantilerini bozmayacak şekilde ilerler.
- `v1.0` ilk üretim-ready sürümdür; ekipler Derlem release'lerini gerçek eğitim işlerinde kullanabilir.
- Her versiyon bir "çıktı" üretmelidir: çalışan kod, migration, UI akışı, test ve doküman.
- Donmuş release değişmez; hata düzeltmesi yeni release/version olarak çıkar.
- Yeni model çıktığında Derlem verisi model bazlı yeniden onaylanmaz. Model uyarlaması eğitim/export katmanının işidir.

## Yatay Güvenlik Kapısı

- Yerel ve kapalı Gardas review/release pilotu devam edebilir.
- P0 güvenlik maddeleri kapanmadan internet-facing staging/production açılamaz.
- Açık katkı veya dış kullanıcı erişimi P0 auth, authorization, upload ve audit
  maddeleri tamamlanmadan etkinleştirilemez.
- `v1.0`, açık P0/P1 güvenlik maddesi varken tamamlandı sayılamaz.
- Güvenlik maddesi yalnızca kod, negatif test ve production/restore kanıtıyla kapanır.

## Sürüm Özeti

| Sürüm | Durum | Ana hedef | Çıktı |
|---|---|---|---|
| v0.1 | Tamamlandı | Güvenli çekirdek veri atölyesi | Kaynak -> kalite kapıları -> review -> frozen release |
| v0.2 | Operasyon kapanışı | Büyük corpus ingest ve tam document indeks | Gardas/Faz 2 seed'i gerçek operasyon kaynağı olur |
| v0.3 | Tamamlandı | Toplu review, kalite skorları, yapısal export ve token tahmini | Eğitim ekiplerine kanonik JSONL/TXT paketleri |
| v0.4 | Aktif | Gelişmiş dedup/decontam ve veri karışımı | MinHash/SimHash, mixture raporu, risk bazlı örneklem |
| v0.5 | Planlandı | Katkı, ajan ve servis hesabı pilotu | Açık/kapalı katkı kuyruğu ve ajan audit modeli |
| v0.6 | Planlandı | P0 güvenlik, üretim altyapısı ve ölçek hazırlığı | RBAC hardening, session/audit, S3/MinIO, backup/restore, gözlemlenebilirlik |
| v1.0 | Hedef | Üretim-ready Derlem | Hukuk/KVKK süreçleri, SLA, release sözleşmesi, model ekipleriyle resmi kullanım |

## v0.1 - Core MVP

**Durum:** Tamamlandı.

Amaç, danışmanın kırmızı çizgilerini kod ve altyapı ile zorlayan küçük ama gerçek
bir sistem kurmaktı.

Tamamlanan hedefler:

- Auth ve rol modeli.
- Append-only audit.
- Immutable content-addressed storage.
- Zorunlu `content_purpose`.
- PII minimumu: TCKN checksum, IBAN, kart, telefon, e-posta.
- Source artifact exact duplicate.
- Normalized document exact-dedup.
- Bounded deterministic document sample.
- İnsan review ve self-review engeli.
- Document edit/version/review.
- Draft/frozen Release Builder.
- Pretrain exact decontamination.
- Manifest ve artifact download.

Kapanış kriteri:

- Local API/web/worker çalışıyor.
- CI yeşil.
- En az bir frozen release başarıyla üretildi.

## v0.2 - Büyük Corpus Ingest ve Tam Document İndeks

**Durum:** Teknik hedefler tamamlandı; Gardas review/hak kapanışı sürüyor.

Amaç, Derlem'i örnek kaynak akışından büyük corpus operasyonuna taşımak. İlk büyük
hedef Gardas/Faz 2 verisinin immutable store'a kontrollü alınması ve tam corpus
document indeksinin çıkarılmasıdır.

Güncel operasyon notu:

- Gardas/Faz 2 seed import kaydı: [Gardas Seed Import](gardash_seed_import.md).
- Seed dosyası immutable local object store'a kopyalandı ve SHA256 doğrulandı.
- Exact file dedup kapısı `unique` sonucu verdi.
- PII scan `flagged`, normalized document dedup `duplicates_found` sonucu verdi; ham seed karantinada.
- Yerel source triage raporu `var/reports` altında üretildi; rapor ham metin veya PII değeri içermez.

Yapılacaklar:

- Gardas/Faz 2 seed manifestini güncelle: path, sha256, byte size, line count, doküman sayısı.
- Seed dosyasını sadece path ile değil, immutable object store'a kopyalayarak kanonikleştir. **Tamamlandı.**
- Büyük dosya ingest için canlı progress/result raporu ekle. **Tamamlandı.**
- Job UUID'sine bağlı, kaynak önekini byte byte doğrulayan resume/checkpoint desteği ekle. **Tamamlandı.**
- Tam corpus document fingerprint indeksini source bazında çıkar. **Tamamlandı.**
- Index job'larında ilerleme metrikleri ekle: okunan byte, satır, indexed document, skipped oversized. **Tamamlandı.**
- `documents` tablosunu sadece sample için tutmaya devam et; tam indeks ham metin saklamasın.
- Review UI'da büyük kaynaklar için "tam corpus özet kartı" göster. **Tamamlandı.**
- Büyük kaynaklarda bounded sample stratejisini risk bazlı hale getir. **Tamamlandı; Gardas nesil 2 aktif, 200 örneğin 115'i risk kotasından seçildi.**

Kapanış kriteri:

- Gardas/Faz 2 kaynak olarak katalogda görünür.
- Dosya immutable store'dadır.
- Tam document fingerprint index tamamlanır.
- Dedup/PII/document count raporu UI ve audit'te görünür.
- Büyük kaynak release'e girmeden önce tüm zorunlu kapılar çalışır.
- Kesilen büyük ingest aynı job checkpoint'ini doğrulayıp kaldığı byte konumundan devam eder.

## v0.3 - Toplu Review, Kalite Skoru ve Export

**Durum:** Teknik hedefler tamamlandı; Gardas operasyon kapanışı sürüyor.

Amaç, veri yöneticisinin ve reviewer ekibinin tek tek örnek açmadan yüzlerce/binlerce
örneği verimli inceleyebilmesi ve model ekiplerinin Derlem çıktısını doğrudan
alabilmesidir.

Yapılacaklar:

- Toplu belge review ekranı: filtre, seçim, ortak kalite puanı ve atomik hızlı karar. **Tamamlandı.**
- Risk bazlı sample yoğunlaştırma: uzunluk, format, tekrar, kontrol karakteri ve kimlik/iletişim kalıbı. **Tamamlandı.** Cross-source domain/source-type mixture sonraki dilimde.
- Çok boyutlu kalite rubric'i: genel, dil, tutarlılık, bilgi yoğunluğu ve temizlik; legacy review ayrımı ve kaynak ortalamaları. **Tamamlandı.**
- Export Builder: frozen release'ten JSONL/TXT üret. **Tamamlandı.**
- Export manifest: release id, source sha256, document count, checksum ve yöntem kimlikli token tahmin aralığı. **Tamamlandı.**
- Modelden bağımsız canonical text, conversation, tool-call ve preference formatı. **Tamamlandı; `derlem.canonical-sample.v1` çalışıyor.**

Kapanış kriteri:

- Reviewer UI toplu çalışır. **200 belgeye kadar sürüm kontrollü transaction ile doğrulandı.**
- Yeni review'lar beş boyutlu rubric taşır; eski tek puanlı kayıtlar değiştirilmez. **Doğrulandı.**
- Frozen release'ten indirilebilir JSONL/TXT export üretilir. **Doğrulandı.**
- Export tekrar üretildiğinde checksum aynı çıkar. **Deterministik üretici testiyle doğrulandı.**
- Yapısal kayıtlar model template'i uygulanmadan JSONL'e çıkar; TXT yapısal kaydı reddeder. **Doğrulandı.**

## v0.4 - Gelişmiş Dedup, Decontamination ve Mixture

**Durum:** Aktif; mixture v2 kalite bantları, release near-dedup ve yaklaşık decontamination pilotları tamamlandı.

Amaç, büyük corpus kalitesini model eğitimine daha uygun hale getirmek.

Yapılacaklar:

- MinHash/SimHash near-dedup pilotu. **Tamamlandı; `derlem.release-near-dedup-report.v1`, Hamming 3 / 4x16, report-only.**
- Near-dedup politikasını veri tipine göre ayır: pretrain, instruction, eval, holdout. **Purpose-aware kalibrasyon CLI'si ve Gardas 1.000 belge/499.500 doğal çift taraması tamamlandı. Hamming 3/10 sentetik recall `%32,69/%80,22`; doğal örnekte mesafe 10 altında çift yok, en yakın mesafe 15. En yakın 100 çiftin 178 benzersiz belgesi append-only inceleme koşusuna import edildi; bağımsız insan etiketleri bekleniyor. Aktif politika değiştirilmedi.**
- Approximate decontamination: eval/holdout ile n-gram veya fingerprint overlap. **Tamamlandı; `normalized-word-3gram-simhash64-v1-hamming10-bands8x8-v1`, report-only pilot.**
- Mixture raporu: dil, domain, kaynak tipi, lisans, hak durumu ve insan kalite örneklemi. **Tamamlandı; `derlem.mixture-report.v2` + `derlem.quality-mixture.v2`, coverage ve yöntem kimlikli review snapshot SHA256 dahil.**
- Release içi tekrar ve kaynaklar arası tekrar oranları. **Tamamlandı; aday çift sayıları ayrı raporlanıyor.**
- Dedup kararlarını geri alınabilir rapor olarak sakla; ham dosyayı değiştirme.

Kapanış kriteri:

- Büyük corpus release'i near-dedup raporu üretir. **Teknik hat `Near Dedup Smoke` frozen manifestinde checksum zinciriyle doğrulandı; Gardas kalibrasyon taraması tamamlandı. Release ölçümü ve insan/hak kapanışı devam ediyor.**
- Eval/holdout sızıntısı approximate kontrolle de raporlanır. **Tamamlandı.**
- Mixture raporu model ekipleri için anlaşılırdır. **Tamamlandı; kaynak dağılımı ve beş boyutlu kalite bantları UI/manifestte ayrıdır. `Quality Mixture V2 Smoke` ile partial coverage, yöntem kimliği ve manifest checksum zinciri doğrulandı.**

## v0.5 - Katkı, Ajan ve Servis Hesapları

**Durum:** Planlandı. Kitlesel ölçek vizyonu ve güven modeli:
[Kitlesel Katkı Platformu Tasarımı](katki_platformu_tasarimi.md).

Amaç, Derlem'i sadece iç ekip aracı olmaktan çıkarıp kontrollü katkı ve ajan destekli
operasyonlara hazırlamak.

Yapılacaklar:

- Katkı kuyruğu: açık kullanıcı verisi doğrudan corpus'a girmez, karantinada bekler.
- Güvenilir onaycı modeli: N bağımsız onay ve kendi katkısını onaylama yasağı.
- Servis hesapları: ajanlar insanlarla aynı API/rol modeline tabi olur.
- Ajan audit alanları: model adı, sürüm, prompt/template kimliği, işlem amacı.
- Kritik kapılarda insan zorunluluğu: hak/lisans temizleme, release freeze, güven seviyesi yükseltme.
- Sentetik veri etiketi: insan/ajan üretimi ayrımı.

Kapanış kriteri:

- Katkı kaynağı corpus'a doğrudan değil, onay zinciriyle yükselir.
- Ajan işlemleri audit'te insandan ayırt edilir.
- Saf-insan pretrain havuzu ajan üretimi içeriği reddedebilir.

## v0.6 - Üretim Altyapısı ve Ölçek Hazırlığı

**Durum:** Planlandı.

Amaç, yerel MVP garantilerini üretim ortamına taşımak.

Yapılacaklar:

- [Güvenlik Hardening Backlog'u](security_hardening_backlog.md) içindeki tüm P0 maddelerini kapat.
- [x] Raw/karantina içerik için default-deny endpoint rol matrisi ve negatif yetki testleri (`SEC-P0-01`, 2026-07-01).
- [x] Login throttling, server-side session revoke ve auth-version invalidation (`SEC-P0-02`, 2026-07-01).
- Production fail-closed ve audit attribution hardening.
- Storage interface'in S3/MinIO implementasyonu.
- Object lock veya WORM benzeri değişmezlik politikası.
- PostgreSQL backup/restore prosedürü.
- Job queue ölçümü: PostgreSQL yeterliyse devam, darboğaz varsa Redis Streams/NATS değerlendirmesi.
- Gözlemlenebilirlik: job süreleri, queue depth, ingest throughput, hata oranı.
- Rate limit ve büyük upload dayanıklılığı.
- Ortam ayrımı: local/staging/production.

Kapanış kriteri:

- Açık P0 güvenlik maddesi yoktur.
- Staging ortamı sıfırdan kurulabilir.
- Backup'tan geri dönüş denenmiştir.
- Büyük ingest job'u izlenebilir ve yeniden başlatılabilir.

## v1.0 - Üretim Ready Derlem

**Durum:** Hedef.

Amaç, Derlem'in LLM/tokenizer ekipleri tarafından resmi veri kaynağı olarak
kullanılmasıdır.

Yapılacaklar:

- Hukuk/KVKK/telif süreçleri netleşir.
- Takedown/delete policy veri modeline ve release sürecine bağlanır.
- Release sözleşmesi yayımlanır: canonical data, manifest, export, checksum, gate sonuçları.
- Kullanıcı ve rol yönetimi üretim standardına gelir.
- Operasyon runbook'u yazılır.
- Model ekipleriyle ilk gerçek eğitim/export tüketimi yapılır.

Kapanış kriteri:

- Açık P0 veya P1 güvenlik maddesi yoktur; ASVS Level 2 kontrol matrisi kanıtlıdır.
- En az bir gerçek büyük corpus release'i frozen olur.
- LLM/tokenizer ekipleri bu release'i manifest ve checksum ile tüketir.
- Geriye dönük izlenebilirlik audit + manifest + storage hash ile kanıtlanır.

## Hemen Sonraki İş Listesi

Önümüzdeki pratik sıra:

1. Gardas/Faz 2 seed manifestini ve immutable ingest yolunu netleştir. **Tamamlandı.**
2. Büyük dosya ingest job'una progress/result raporu ekle. **Tamamlandı.**
3. Tam corpus fingerprint indeksini büyük kaynak üzerinde çalıştır. **Tamamlandı.**
4. Toplu review ekranını kaynak bazlı özet ve öncelik sırasıyla genişlet. **Tamamlandı.**
5. Export Builder tasarımını ve ilk JSONL/TXT çıktısını oluştur. **Tamamlandı.**
6. Büyük dosya ingest ve index job'larında progress/result raporunu derinleştir. **Tamamlandı.**
7. Büyük ingest için resume/checkpoint desteği ekle. **Tamamlandı.**
8. Gardas nesil 2 örneklerini hak/lisans kararıyla birlikte insan review'dan geçir.
   **Gardash Spark takvimi bu kapanışa kilitli; kritik yol ve 1-2 iş günlük plan:
   [Gardash Feedback 2026-07](gardash_feedback_2026_07.md).**
9. v2 web-ölçekli TR alımını (FineWeb-2/HPLT/CulturaX + sentetik ders kitabı)
   [v2 Alım Planı](v2_intake_plan.md) fazlarına göre başlat; faz 0-1 GPU gerektirmez.
10. Public/staging açmadan önce P0 güvenlik backlog'unu sırayla kapat.
    (`SEC-P0-08`'in bağımlılık tarama dilimi 2026-07-05'te CI'ya eklendi:
    govulncheck + pip-audit + npm audit.)

## Şu Anki Karar

Derlem'in yönü doğru: güvenlik ve izlenebilirlik omurgası ile büyük corpus teknik
hattı kuruldu. v0.3 teknik hedefleri tamamlandı. Şimdiki teknik odak **v0.4 -
gelişmiş dedup, yaklaşık decontamination ve mixture raporu**; Gardas insan/hak
operasyonu paralel sürer. Bu çalışma yerel kapalı pilot içindir; production
deployment P0 güvenlik kapısı kapanana kadar blokludur.
