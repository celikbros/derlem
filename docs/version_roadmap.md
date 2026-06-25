# Derlem Versiyon Yol Haritasi

**Tarih:** 2026-06-25
**Kapsam:** Derlem veri atölyesinin versiyon versiyon hedefleri, mevcut konumu ve sonraki işler.

Bu belge Derlem'i LLM/tokenizer projelerinden bağımsız, modelden bağımsız ve
denetlenebilir bir veri üretim sistemi olarak planlar. LLM veya tokenizer
modeline müdahale edilmez; Derlem kanonik veriyi, metadata'yı, kalite kanıtını,
manifestleri ve release artifact'lerini üretir. Model ekipleri bu çıktıları kendi
adaptörleriyle kullanır.

## Neredeyiz?

Şu an pratik olarak **v0.1 Core MVP** tamamlandı ve yerel makinede çalışıyor.
Sistem artık tek dosya/tek kaynak ölçeğinde güvenli bir uçtan uca akış üretiyor:

- Go API, JWT auth, roller ve RBAC çalışıyor.
- PostgreSQL metadata, job queue ve append-only audit için kullanılıyor.
- Büyük metinler DB blob'u değil, içerik-adresli immutable local object store'da duruyor.
- Kaynak kaydı, browser upload ve güvenilir local ingest var.
- Worker; SHA256, UTF-8, byte/line count, PII, source artifact exact duplicate,
  normalized document exact-dedup ve bounded sample çıkarıyor.
- İnsan review kapısı; lisans kanıtı, hak durumu, PII, dedup ve tüm örnek onaylarını zorunlu tutuyor.
- Belge örneği açma, düzenleme, yeni immutable sürüm ve belge review geçmişi var.
- Release Builder; aynı `content_purpose` içindeki onaylı kaynaklardan draft/frozen release üretiyor.
- Frozen manifest, kaynak SHA256 snapshot'ı, release audit'i ve artifact download uçları var.
- Pretrain release için eval/holdout exact decontamination kapısı var.
- Next.js web arayüzünde kaynak katalogu, inceleme, işler ve sürümler ekranları çalışıyor.
- GitHub Actions CI backend/worker/web için yeşil.

Eksik olan şey artık temel güvenlik omurgası değil; **ölçekli corpus operasyonu**:
Gardas/Faz 2 gibi büyük kaynakları tam corpus seviyesinde indekslemek, toplu review
akışları kurmak, export/shard üretmek, kalite skorlarını derinleştirmek ve üretim
ölçeğine taşımak.

## Versiyon İlkeleri

- `v0.x` sürümleri MVP ve kapalı pilot dilimleridir; hızlı ama audit garantilerini bozmayacak şekilde ilerler.
- `v1.0` ilk üretim-ready sürümdür; ekipler Derlem release'lerini gerçek eğitim işlerinde kullanabilir.
- Her versiyon bir "çıktı" üretmelidir: çalışan kod, migration, UI akışı, test ve doküman.
- Donmuş release değişmez; hata düzeltmesi yeni release/version olarak çıkar.
- Yeni model çıktığında Derlem verisi model bazlı yeniden onaylanmaz. Model uyarlaması eğitim/export katmanının işidir.

## Sürüm Özeti

| Sürüm | Durum | Ana hedef | Çıktı |
|---|---|---|---|
| v0.1 | Tamamlandı | Güvenli çekirdek veri atölyesi | Kaynak -> kalite kapıları -> review -> frozen release |
| v0.2 | Sıradaki | Büyük corpus ingest ve tam document indeks | Gardas/Faz 2 seed'i gerçek operasyon kaynağı olur |
| v0.3 | Planlandı | Toplu review, kalite skorları, export/shard | Eğitim ekiplerine kanonik JSONL/TXT paketleri |
| v0.4 | Planlandı | Gelişmiş dedup/decontam ve veri karışımı | MinHash/SimHash, mixture raporu, risk bazlı örneklem |
| v0.5 | Planlandı | Katkı, ajan ve servis hesabı pilotu | Açık/kapalı katkı kuyruğu ve ajan audit modeli |
| v0.6 | Planlandı | Üretim altyapısı ve ölçek hazırlığı | S3/MinIO, Redis/NATS ölçümü, backup/restore, gözlemlenebilirlik |
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

**Durum:** Sıradaki aktif hedef.

Amaç, Derlem'i örnek kaynak akışından büyük corpus operasyonuna taşımak. İlk büyük
hedef Gardas/Faz 2 verisinin immutable store'a kontrollü alınması ve tam corpus
document indeksinin çıkarılmasıdır.

Yapılacaklar:

- Gardas/Faz 2 seed manifestini güncelle: path, sha256, byte size, line count, doküman sayısı.
- Seed dosyasını sadece path ile değil, immutable object store'a kopyalayarak kanonikleştir.
- Büyük dosya ingest için resume edilebilir job raporu ekle.
- Tam corpus document fingerprint indeksini source bazında çıkar.
- Index job'larında ilerleme metrikleri ekle: okunan byte, satır, indexed document, skipped oversized.
- `documents` tablosunu sadece sample için tutmaya devam et; tam indeks ham metin saklamasın.
- Review UI'da büyük kaynaklar için "tam corpus özet kartı" göster.
- Büyük kaynaklarda bounded sample stratejisini risk bazlı hale getirmek için hazırlık yap.

Kapanış kriteri:

- Gardas/Faz 2 kaynak olarak katalogda görünür.
- Dosya immutable store'dadır.
- Tam document fingerprint index tamamlanır.
- Dedup/PII/document count raporu UI ve audit'te görünür.
- Büyük kaynak release'e girmeden önce tüm zorunlu kapılar çalışır.

## v0.3 - Toplu Review, Kalite Skoru ve Export

**Durum:** Planlandı.

Amaç, veri yöneticisinin ve reviewer ekibinin tek tek örnek açmadan yüzlerce/binlerce
örneği verimli inceleyebilmesi ve model ekiplerinin Derlem çıktısını doğrudan
alabilmesidir.

Yapılacaklar:

- Toplu belge review ekranı: filtre, sıra, hızlı karar, kalite puanı.
- Risk bazlı sample yoğunlaştırma: PII riski, domain, kaynak tipi, dedup bulgusu.
- Çok boyutlu kalite skoru: dil, format, uzunluk, tekrar, kalite, özel nitelikli veri riski.
- Export Builder: frozen release'ten JSONL/TXT üret.
- Export manifest: release id, source sha256, document count, token tahmini, kalite gate sonuçları.
- Modelden bağımsız canonical format ve model ekibi adaptör sözleşmesi.

Kapanış kriteri:

- Reviewer UI toplu çalışır.
- Frozen release'ten indirilebilir JSONL/TXT export üretilir.
- Export tekrar üretildiğinde checksum aynı çıkar.

## v0.4 - Gelişmiş Dedup, Decontamination ve Mixture

**Durum:** Planlandı.

Amaç, büyük corpus kalitesini model eğitimine daha uygun hale getirmek.

Yapılacaklar:

- MinHash/SimHash near-dedup pilotu.
- Near-dedup politikasını veri tipine göre ayır: pretrain, instruction, eval, holdout.
- Approximate decontamination: eval/holdout ile n-gram veya fingerprint overlap.
- Mixture raporu: dil, domain, kaynak tipi, lisans, kalite bandı.
- Release içi tekrar ve kaynaklar arası tekrar oranları.
- Dedup kararlarını geri alınabilir rapor olarak sakla; ham dosyayı değiştirme.

Kapanış kriteri:

- Büyük corpus release'i near-dedup raporu üretir.
- Eval/holdout sızıntısı approximate kontrolle de raporlanır.
- Mixture raporu model ekipleri için anlaşılırdır.

## v0.5 - Katkı, Ajan ve Servis Hesapları

**Durum:** Planlandı.

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

- Storage interface'in S3/MinIO implementasyonu.
- Object lock veya WORM benzeri değişmezlik politikası.
- PostgreSQL backup/restore prosedürü.
- Job queue ölçümü: PostgreSQL yeterliyse devam, darboğaz varsa Redis Streams/NATS değerlendirmesi.
- Gözlemlenebilirlik: job süreleri, queue depth, ingest throughput, hata oranı.
- Rate limit ve büyük upload dayanıklılığı.
- Ortam ayrımı: local/staging/production.

Kapanış kriteri:

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

- En az bir gerçek büyük corpus release'i frozen olur.
- LLM/tokenizer ekipleri bu release'i manifest ve checksum ile tüketir.
- Geriye dönük izlenebilirlik audit + manifest + storage hash ile kanıtlanır.

## Hemen Sonraki İş Listesi

Önümüzdeki pratik sıra:

1. Gardas/Faz 2 seed manifestini ve immutable ingest yolunu netleştir.
2. Büyük dosya ingest job'una progress/result raporu ekle.
3. Tam corpus fingerprint indeksini büyük kaynak üzerinde çalıştır.
4. Kaynak ayrıntısına corpus özet kartı ekle.
5. Toplu review ekranı için UX iskeletini başlat.
6. Export Builder tasarımını ve ilk JSONL/TXT çıktısını oluştur.

## Şu Anki Karar

Derlem'in yönü doğru: önce güvenlik ve izlenebilirlik omurgası kuruldu, şimdi
ölçekli veri üretim kapasitesi eklenecek. Bir sonraki sürüm adı **v0.2 - Büyük
Corpus Ingest ve Tam Document İndeks** olmalı.
