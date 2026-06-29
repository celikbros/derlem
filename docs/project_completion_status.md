# Derlem Proje Tamamlanma Durumu

**Tarih:** 2026-06-29
**Kapsam:** Derlem veri atölyesinin mevcut gerçek durumu, kalan işler ve tamamlanma yorumu.

## Kısa Cevap

Derlem'in **çekirdek MVP'si tamamlandı**. Yani sistem artık yerel makinede kaynak
kaydedebiliyor, dosyayı immutable store'a alıyor, PII/dedup kapılarını çalıştırıyor,
örnek çıkarıyor, insan review zinciri tutuyor ve frozen release üretebiliyor.

Derlem'in v0.3 teknik hedefleri tamamlandı. **Gerçek büyük corpus üretim aracı**
olarak operasyon kapanışı için Gardas insan/hak kapıları; üretim platformu için
v0.4-v1.0 işleri gerekiyor. En pratik ifadeyle:

| Hedef | Durum | Kalan |
|---|---:|---|
| Yerel Core MVP | %100 | Bitti |
| Gardas temiz adayını onaylı kaynak yapmak | %75-80 | Hak/lisans kanıtı + 200 örnek review |
| Model ekiplerine düzenli JSONL/TXT export vermek | %85-90 | Gardas onayı + ilk büyük release |
| Büyük corpus pilotu | %85-90 | Gardas review/export kapanışı |
| Üretim-ready v1.0 | %45-50 | v0.4-v0.6 + hukuk/KVKK + prod altyapı |

Bu yüzden "proje bitti mi?" sorusunun cevabı hedefe göre değişir:

- **MVP olarak:** bitti.
- **Gardas temiz verisini onaylı release yapmak için:** az kaldı, ama insan/hak kapıları bekliyor.
- **LLM/tokenizer ekiplerinin rahatça kullanacağı temel veri fabrikası için:** Export Builder ve toplu review hazır; Gardas kapılarının kapanması ve risk bazlı kalite katmanı sırada.
- **Milyonlarca kullanıcı/üretim sistemi için:** daha erken aşamadayız; mimari doğru ama prod işleri bitmedi.

## Veritabanındaki Güncel Durum

Öne çıkan kaynak:

| Alan | Değer |
|---|---|
| Kaynak | `gardash_faz2_tr_dedup_20260621_clean_candidate_20260625` |
| Source ID | `f63352dd-fdd1-4e4b-a8d2-b167b3c856cf` |
| Durum | `sampled_for_review` |
| Doküman/satır | `5,922,891` |
| PII | `clear` |
| Exact dedup | `unique` |
| Normalize dedup | `unique` |
| Örnekleme | `sampled` |
| Örnek nesli/yöntemi | `2 / risk-stratified-sha256-v1` |
| Örnek sayısı | `200` |
| İncelenen/onaylanan örnek | `0 / 200` |
| Hak durumu | `unknown` |
| Lisans | `unknown` |
| Lisans kanıtı | eksik |

Bu kaynak teknik temizlik açısından iyi bir noktada. Release'e girmesini engelleyen
ana kapılar artık teknik değil:

1. Hak/lisans kararı girilmeli.
2. Lisans kanıt referansı kaydedilmeli.
3. 200 örnek insan tarafından incelenip onaylanmalı.
4. Sonra kaynak onayı verilmeli.
5. Ardından release/export üretilebilir.

## Şu Ana Kadar Biten Ana Parçalar

- Go API, JWT auth, roller ve RBAC.
- PostgreSQL metadata, job queue ve append-only audit.
- Content-addressed immutable local object storage.
- Browser upload ve local ingest.
- PII taraması: TCKN checksum, IBAN, telefon, e-posta, kart.
- Source artifact exact duplicate.
- Normalize document exact dedup.
- Bounded deterministic document sampling.
- Belge edit/version/review akışı.
- Kaynak approval gates.
- Release Builder ve frozen manifest.
- Pretrain exact decontamination.
- Web UI: kaynak katalogu, inceleme, işler, sürümler.
- Gardas ham seed import + triage.
- Gardas temiz aday üretimi ve ingest.
- Review kuyruğu önceliklendirme.
- Corpus özet paneli.
- Deterministik JSONL/TXT Export Builder.
- Export manifesti, artifact checksum'u, job progress'i ve rol kontrollü indirme.
- En fazla 200 bekleyen belge için atomik toplu review ve ortak kalite puanı.
- Deterministik risk-stratified örnekleme, risk filtresi ve açıklanabilir neden etiketleri.
- Generation/membership snapshot'lı kontrollü yeniden örnekleme ve rollback.
- Ingest, PII, fingerprint ve sample/resample işlerinde canlı byte/satır/doküman ilerlemesi.
- Büyük ingest işlerinde job UUID'sine bağlı, kaynak önekini yeniden doğrulayan resume/checkpoint desteği.
- Gardas clean candidate nesil 2 risk örneklemi: 5.922.891 belge tarandı, 200 örneğin 115'i risk kotasından seçildi.
- `multidimensional-v1` insan kalite rubric'i, tekil/toplu review ve kaynak ortalamaları.
- `derlem.canonical-sample.v1` conversation/tool/preference doğrulaması ve yapısal JSONL export.
- `unicode-codepoint-range-v1` yöntem kimlikli token tahmin aralığı, manifest/API/UI kaydı.

## Kalan Teknik İşler

### v0.2 İçin Kalanlar

- Gardas temiz adayının hak/lisans ve örnek review kapılarını kapatmak.

### v0.3 Durumu

- Teknik hedefler tamamlandı; Gardas'ın ilk büyük gerçek release/export operasyonu v0.2 insan/hak kapanışına bağlı.

### v1.0 İçin Kalanlar

- Hukuk/KVKK/telif sürecinin resmi karara bağlanması.
- Takedown/delete policy.
- S3/MinIO veya production object storage.
- Backup/restore.
- Gözlemlenebilirlik ve rate limit.
- Üretim kullanıcı/rol yönetimi.
- Operasyon runbook'u.
- Model ekipleriyle ilk resmi tüketim sözleşmesi.

## Pratik Kapanış Tahmini

Kod tarafında yakın hedef şudur:

1. **Gardas clean candidate onayı:** hak/lisans + 200 örnek review tamamlanırsa aynı gün içinde kaynak onaylanabilir.
2. **İlk gerçek export:** Tamamlandı; küçük frozen release ile JSONL/TXT artifact ve manifest checksum zinciri doğrulandı.
3. **Pilot tamam:** v0.3 teknik olarak bitti; Gardas insan/hak kapıları kapanıp ilk büyük export üretildiğinde operasyon pilotu tamamlanır.

Benim mühendislik değerlendirmem:

- **Yerel güvenli veri atölyesi:** tamam.
- **Büyük corpus pilotu:** teknik hat ve kesintiden devam hazır; Gardas insan/hak kapanışı kaldı.
- **Model ekiplerine üretilebilir veri teslimi:** temel JSONL/TXT teslim hattı hazır; Gardas temiz adayının kapıları kapanınca büyük gerçek corpus export edilebilir.
- **Tam üretim platformu:** ayrıca altyapı, hukuk ve operasyon gerekir.
