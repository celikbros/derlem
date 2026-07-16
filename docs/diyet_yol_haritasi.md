# Diyet Yol Haritası (Aktif Yol Haritası)

**Tarih:** 2026-07-07
**Dayanak:** [v1 Otopsi Raporu](v1-autopsy.md)
**İlke:** Bu yol haritası özellik eklemez; teslim eder, budar ve dürüstleştirir.
[version_roadmap.md](version_roadmap.md) içindeki v0.4-sonrası hedefler, bu
plan tamamlanana kadar **dondurulmuştur**.

## Tek cümlelik hedef

Sistem, var olma sebebini ilk kez yerine getirir: **gerçek bir corpus'u
gerçek bir tüketiciye teslim eder** — ve bunu yaparken kendisini besleyen
bürokrasiyi budar.

## Fazlar

### Faz 0 — TESLİMAT (pazarlık dışı; her şeyi bloke eder)

| Adım | Sorumlu | Durum |
|---|---|---|
| Hak kararı + kanıt referansı | Veri sahibi | ✅ 2026-07-07 (web politikası, Celikbros onayı) |
| 200 örneğin moderatör incelemesi + kaynak onayı | **İnsan — moderator hesabı** (1-2 saat) | ⏳ BEKLİYOR — tek bloker |
| Draft release → freeze → JSONL/TXT export | Otomatik/Claude | Hazır, tetik bekliyor |
| Manifest + SHA256 zinciriyle Gardash'a teslim | Claude | Hazır |

**Ölçüt:** Gerçek teslimat sayısı 0 → 1. DGX Spark v1 girdisi verilmiş olur.

**Durum güncellemesi (2026-07-12):** DGX Spark donanımı gecikti; Gardash
teslimatı beklemeye alındı (sahip kararı). Faz 0 artık takvim-kritik DEĞİL.
Teslimat yine kapatılır (frozen release beklemeye dayanıklıdır; donanım
geldiğinde paket hazır olur). Claude'un 200 örneklik ön-inceleme raporu
hazırlanmıştır; insan onayı ~20 dakikaya iner.

**Faz 0 destek kaydı (2026-07-07):** Kullanıcı giriş ekranında hangi hesabı
seçeceğini bilemedi → her yerel hesap kartına görev açıklaması ve her ekrana
rol-duyarlı "Bu ekranda ne yapabilirim?" yardım kutusu eklendi. Moratoryum
istisnası kapsamındadır (teslimatı açan rehberlik; yeni yetenek değil).

### Faz 1 — MORATORYUM (bugün yürürlüğe girer)

Gerçek release #1 teslim edilene VE sisteme ikinci gerçek insan (ekip üyesi)
girene kadar:

- Yeni endpoint, tablo, migration, panel, özellik: **YOK.**
- İzinli işler: hata düzeltme, budama, dokümantasyon, Faz 0 desteği.
- Bu kural Claude dahil herkesi bağlar.

**REVİZYON (2026-07-12, sahip kararı):** "Teslimattan önce başka veriler de
girmemiz gerekebilir; önce sistemi yapalım bitirelim." DGX gecikmesiyle
birlikte moratoryum şu şekilde revize edildi: **yeniden büyüme adayları
listesindeki işler sırayla açılmıştır** (1. belge ekstraksiyonu → 2.
distilasyon → 3. i18n). Liste dışı yeni özellik hâlâ yasaktır. Faz 0
teslimatı iptal değil, ertelidir: ön-inceleme raporu hazır, insan onayı
~20 dk; veriler tamamlanınca release daha zengin içerikle dondurulur.

**Ölçüt:** Moratoryum süresince `feat:` commit sayısı = 0.

### Faz 2 — BUDAMA (moratoryumla paralel; bugün başladı)

| Eylem | Ölçüt | Durum |
|---|---|---|
| İngilizce ikiz dokümanlara "güncellenmiyor" damgası | 14 `.en.md` damgalı; bakım yükümlülüğü resmen sıfır | Bugün |
| Tek atımlık CLI'ların kalıcı entry-point kaydını kaldır (yalnız `derlem-worker` kalır) | `pyproject.toml [project.scripts]` = 1 kayıt | Bugün |
| Pakete gömülü mutlak makine yolunu kaldır (`seed_gardas.py`) | `--manifest` zorunlu argüman | Bugün |
| Benzerlik inceleme alt sistemi + canonical tool_call/preference kolları: **DONDURULDU** | Kod kalır; yol haritasından çıkar; yeni yatırım yapılmaz | Bugün (kayıt) |
| v0.5 (katkı/ajan) ve v0.6 (üretim altyapısı) iddiaları | "Planlandı" → "Dondurulmuş — diyet sonrası yeniden değerlendirilecek" | Bugün (kayıt) |

### Faz 3 — DÜRÜSTLEŞTIRME (bugün başladı)

| Eylem | Ölçüt |
|---|---|
| README'ye garanti kapsamı paragrafı: append-only/immutable/bağımsız-inceleme garantileri çok kullanıcılı + ayrıcalık ayrımlı kurulumda geçerlidir; tek operatörlü yerel kurulumda disiplin provasıdır | README'de yazılı |
| 200-örnek kapısının gerçek işlevinin belgelenmesi: istatistiksel kalite garantisi değil, **sorumluluk imzası** (binom gerçeği: %0,1 kusur oranını ~%82 ihtimalle ıskalar) | Bu belgede yazılı — kayıt tamam |
| Roadmap'te "tamamlandı" iddialarının smoke-veri dipnotu | version_roadmap başlığında not |

### Faz 4 — SADELEŞME (yalnız moratoryum kalktıktan sonra)

Şimdi YAPILMAZ; sıraya kayıt:

1. 32 BFF proxy dosyasının tek catch-all route'a indirilmesi.
2. jobs mixin'lerinin örtük `self` bağımlılıklarından açık bağımlılıklara evrimi.
3. `postgres` süper-kullanıcısından ayrı runtime DB rolüne geçiş (SEC-P0-04'ün
   ilk gerçek adımı — "append-only" iddiasını tiyatro olmaktan çıkarır).
4. SimHash yerine karakter n-gram MinHash pilotu (kalibrasyon verisi mevcut).

### Faz 5 — YENİDEN BÜYÜME KAPISI

Şu üç koşul sağlanınca dondurulmuş hedefler (v2 alımı, katkı platformu)
yeniden değerlendirilir:

1. Gerçek teslimat ≥ 1 (Faz 0 bitti).
2. Sistemde en az bir ikinci gerçek insan düzenli çalışıyor.
3. Faz 2-3 ölçütlerinin tamamı yeşil.

### Yeniden büyüme adayları — öncelik sırası (2026-07-08 sahip talebi)

Sahibin kararı: "Tüm işlemler Derlem ile yapılabilmeli; dışarıdan script'e
gerek kalmamalı." Moratoryum kalktığında İLK yatırım, üretim modülleridir:

1. **Belge ekstraksiyon işi:** ✅ **v1 TAMAMLANDI (2026-07-12).** PDF ve
   DOCX yüklemeleri worker'da otomatik olarak satır-belge TXT'ye çevrilir
   (`text-extraction-v1`: paragraf normalize + 4000 karakterlik parça);
   ham ikili, lineage kanıtı olarak içerik adresli depoya alınır ve audit'e
   işlenir; görüntü tabanlı PDF açık hatayla reddedilir (OCR v2). Canlı
   duman testi: DOCX upload → ekstraksiyon → PII/dedup/örnekleme zinciri
   uçtan uca geçti. Kalan: EPUB desteği, OCR, karantina tarayıcısı
   (SEC-P0-07 ile birlikte).
2. **Distilasyon işi:** ✅ **v1 TAMAMLANDI (2026-07-12).** Sağlayıcıdan
   bağımsız tek tip HTTP katmanı: Claude, ChatGPT, Gemini, Grok, Qwen ve
   OpenAI-uyumlu diğerleri arayüzden seçilir; ağ/anahtar gerektirmeyen Echo
   sağlayıcısıyla test edilir. `distill_source` işi N belge üretir, üretim
   manifestini immutable depoya alır (`source.distilled` audit'i), sonra
   normal PII/dedup/örneklem/insan kapılarına sokar. API anahtarı ve ortam
   değişkeni adı ARAYÜZE girilmez; allowlist'teki sağlayıcı worker tarafında
   sabit anahtar ortamına eşlenir, anahtar değeri hiçbir yere yazılmaz
   (SEC-P0-05 uyumlu). Canlı Echo duman testi (API + UI)
   uçtan uca geçti. Detay: [distilasyon.md](distilasyon.md). Kalan: model
   kimliği doğrulaması, hız/oran sınırı, maliyet tahmini/onayı, prompt başına
   durable checkpoint/idempotency ve sentetik etiket filtresi.
3. **Arayüz uluslararasılaştırma (i18n):** sahibin ürün vizyonu kararı
   (2026-07-08): Derlem yalnız Türkçe bilenlerin aracı olmayacak — herhangi
   bir ulus/ekip (Japon, Alman, Arap...) kendi egemen veri bankasını bu
   platformla kurabilmeli. Gereken: çeviri katmanı (~500+ arayüz metni),
   dil seçici, önce TR+EN, mimari ja/de/ar'a hazır (Arapça için RTL).
   Not: i18n altyapısı ERKEN kurulursa ucuzdur — her yeni ekran metni
   borcu büyütür; bu yüzden moratoryum kalkar kalkmaz ilk dalgada yapılır.
   Veri tarafı zaten çok dillidir (dil alanı + UTF-8; seçici 2026-07-08'de
   eklendi).
4. Dondurulmuş eski hedefler (v2 web alımı, katkı platformu) bunlardan sonra
   yeniden değerlendirilir.

**Ürün vizyonu kaydı (2026-07-08):** "Veri bankası yapay zekânın ana besin
kaynağıdır." Derlem'in hedef kimliği: çok dilli, kullanıcı dostu, profesyonel,
dayanıklı ve hızlı bir egemen-veri-atölyesi ürünü. Bu beş sıfatın karşılıkları:
çok dilli = i18n (yukarıda), kullanıcı dostu = rehber/yardım katmanı (yapıldı,
sürer), profesyonel = tasarım yenileme (başladı) + gerçek teslimat sicili,
dayanıklı = SEC-P0 backlog'u + yedekleme (tatbikat PASS), hızlı = Go/stream
mimarisi (mevcut) + ölçüm.

Gerekçe dengesi (kayıt): sahip argümanı — dışarıda dolaşan dosya/script hem
güvenlik riski hem iş yükü; içerideki iş audit'li ve tek tip olur. Karşı not —
ayrıştırıcı ve API anahtarı içeri alınınca YENİ saldırı yüzeyi doğar; bu
modüller güvenlik maddeleriyle birlikte, teslimat #1'den önce DEĞİL, sonra
yapılır.

## Bu belge nasıl güncellenir

Durum değişiklikleri tarihli olarak işlenir; satır silinmez. "Bitti" iddiası
ancak ölçüt sütunundaki koşul kanıtlanınca yazılır.
