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

## Bu belge nasıl güncellenir

Durum değişiklikleri tarihli olarak işlenir; satır silinmez. "Bitti" iddiası
ancak ölçüt sütunundaki koşul kanıtlanınca yazılır.
