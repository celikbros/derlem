# Derlem v1 Otopsi Raporu

**Tarih:** 2026-07-07
**Nitelik:** Adli analiz — teknik borç, mantık hataları ve felsefi çelişkiler.
Övgü içermez. Tüm bulgular kod, canlı veritabanı ve git geçmişinden doğrulanmıştır.
**Amaç:** Bu rapor, sonraki yol haritasının (diyet planının) dayanağıdır.

---

## 1. Projenin gerçek DNA'sı

Teknik olarak: **dosya kimliklendirme ve onay-zinciri makinesi.** Metin dosyası
alır, SHA256 ile kimlikler (`internal/storage/local.go:51`), PostgreSQL'de
künyesini tutar, Python worker'la tarar (PII/dedup/örneklem), insan onayından
geçirir, dondurulmuş paket üretir.

Hiyerarşi dört katman:

1. Go API — kapı bekçisi (auth, RBAC, CRUD, stream upload)
2. PostgreSQL — hem veri hem *politika* (trigger'lar kural uygular) hem iş kuyruğu
3. Python worker — hamal (ingest, kapılar, freeze, export)
4. Next.js BFF — 32 adet elle yazılmış proxy dosyası (`web/app/api/**/route.ts`)

Asıl DNA tespiti: **proje veri üretmiyor, veri hakkında bürokrasi üretiyor.**
Var oluş amacı "güven zinciri" — ve zincir, ürünün önüne geçmiş durumda.

**Kanıt:** Canlı veritabanında 7 release var, yedisi de smoke test
("Near Dedup Smoke" release'i 2 belge içerir). Gerçek veri teslimatı,
projenin ömründe (2026-06-24 → 2026-07-07): **sıfır.**

## 2. Kullanıcı/geliştirici çilesi

En yıkıcı kanıt: **sistemin sahibi ve tek gerçek kullanıcısı iki kez
"çalıştırdım, hiçbir şey anlamadım" dedi.** Ürün tek kullanıcısında
başarısızsa bu kullanıcı hatası değil ürün hatasıdır.

Nedenleri:

1. **Kavram yüzeyi, zihinsel modelin katbekat üstünde.** Sahibin modeli
   "ekip, konu, kitap"; ürünün modeli "kaynak, amaç, kapı, nesil,
   fingerprint, freeze, manifest, rubric, SimHash." Boşluğu kapatan
   Rehber/senaryo belgeleri ancak son hafta yazıldı; v0.1'de yazılmalıydı.
2. **Ayağa kaldırma:** 4 servis + 2 env dosyası + 3 terminal
   (`README.md`, Yerel Kurulum). Worker çökükse hiçbir iş ilerlemez ve
   arayüz *nedenini* söylemez — sadece "queued" gösterir.
3. **Ortam kırılganlığı (yaşanmış):** klasör taşınınca venv sessizce kırıldı
   (editable install mutlak yol tutar); pytest `TEMP=C:\tmp` hilesi
   istiyordu; düzeltme conftest'i bile CI'ı 6 push boyunca kırdı (var/
   temiz checkout'ta yok); boşluklu Windows yolu tek oturumda üç ayrı araç
   hatası üretti.
4. **Geliştirici sürtünmesi:** tek endpoint eklemek 5 dokunuş ister — Go
   handler + `authorization.go` kaydı + matris testi + BFF proxy dosyası +
   panel kodu. 32 proxy dosyasının her biri elle yazılmış tekrardır.

## 3. Saçmalıklar, aşırı mühendislik, ölü ağırlık

Ağırdan hafife, kanıtlı:

| # | Bulgu | Kanıt |
|---|---|---|
| 1 | **Güvenlik tiyatrosu — "append-only audit":** README garanti diye satar; uygulama DB'ye `postgres` süper-kullanıcısıyla bağlanır (.env). Trigger'ı koyan el tek satır `DROP TRIGGER` ile kaldırabilir — tek gerçekçi tehdit modeli zaten o el. | README "Tasarım İlkeleri" 5 vs `.env` DATABASE_URL; backlog SEC-P0-04 itiraf ediyor, vitrin etmiyor |
| 2 | **Güvenlik tiyatrosu — "immutable store":** değişmezlik = `chmod 0444`; aynı OS kullanıcısı özniteliği kaldırır. | `internal/storage/local.go:78`; SEC-P0-06 |
| 3 | **Yönetişim tiyatrosu:** 7 rol, self-review yasağı, körlemeli inceleme — ve 8 hesabın tamamı aynı insan, aynı ortak parolayla. "Bağımsız onay" = aynı kişinin hesap değiştirmesi. | `docs/local_role_testing.md` |
| 4 | **5 belgeye konuşma sözleşmesi:** tool_call, preference, reasoning-visibility, train-policy alanlı tam şema; veritabanındaki toplam instruction belgesi: 5. Hiç var olmamış tool-call'lar için şema v1. | `worker/src/derlem_worker/canonical.py`; canlı sorgu: instruction=5 belge |
| 5 | **103 çift için alt sistem:** benzerlik körleme incelemesi = 3 tablo (migration 000016) + 4 endpoint + UI paneli + 420 satır import CLI + 624 satır kalibrasyon CLI. Ömür boyu kullanım: 103 çift, 2 inceleme. Kalibrasyonun kendisi SimHash'in Türkçede zayıf olduğunu ölçtü (sentetik recall %32,7) — altyapı muhtemelen yanlış algoritmanın etrafına kuruldu. | `internal/httpapi/authorization.go:83-86`, `similarity_review_import.py`, `similarity_calibration.py` |
| 6 | **200 örnek kapısının söylenmeyen matematiği:** 5.922.891 belgeden 200 = %0,0034. Belgelerin %0,1'i çöpse (≈5.900 belge) örneklem bunu ~%82 ihtimalle ıskalar. En kıt kaynağı (insan saati) tüketen kapı, zincirin en zayıf istatistiksel garantisini verir; %100 kapsamalı gerçek işi PII tarayıcı yapar. Kapının dürüst adı "kalite kontrolü" değil "sorumluluk imzası"dır — etrafına 3 migration'lık nesil/üyelik makinesi kurulmuştur (000011-13). | Basit binom hesabı: (1-0.001)^200 ≈ 0.82 |
| 7 | **Kimsenin okumadığı ikinci dil:** 58 doküman, 7.244 satır markdown; kod 17.042 satır (%42 doküman/kod). 14 İngilizce ikiz; İngilizce konuşan paydaş yok ve ikizler şimdiden kaydı (son hafta backlog değişiklikleri .en.md'lere işlenmedi). | `ls docs/*.en.md` = 14 |
| 8 | **Kurgu production:** `deploy/nginx` içinde `ssl`/`443` geçen satır: 0. systemd unit'leri hiç çalıştırılmadı; runbook hiç icra edilmedi; E2E testleri CI'da hiç koşmadı (ci.yml'de playwright: 0). | `deploy/nginx/`, `.github/workflows/ci.yml` |
| 9 | **Kütüphaneye gömülü makine yolu:** `DEFAULT_MANIFEST = C:\CELIKBROS PROJECTS\gardash\...` — pakete gömülü mutlak yol; pyproject bunu kalıcı CLI olarak kaydeder. | `worker/src/derlem_worker/seed_gardas.py:18`, `worker/pyproject.toml` |
| 10 | **Mixin bölünmesi (yeni borç):** jobs.py monoliti mixin'lere bölündü; her mixin başka mixin'de tanımlı `self` metotlarını çağırır — örtük bağımlılık. Mekanik olarak güvenli bir ara istasyon, varış değil. | `worker/src/derlem_worker/jobs/` |
| 11 | **Şema çalkantısı:** 14 günde 18 migration. | `internal/database/migrations/` |

## 4. Felsefe mi hatalı, uygulama mı?

**Felsefe doğru — hatta vizyoner.** "Eğitim verisinin kökeni, hakkı, temizliği
kanıtlanabilir olmalı" tezi, telif davaları çağında sektörün geç kaldığı
ihtiyaçtır. Model-bağımsız kanonik veri ve şema seviyesinde eval ayrımı
gerçekten iyi tasarımlardır. Fikir ölü doğmamıştır.

Patlama iki yerdedir:

1. **Sıralama ters kuruldu: güven altyapısı önce, değer teslimi sonra.**
   Kanıt: v0.2'nin kapanışı (30 dakikalık karar + 1-2 saatlik okuma) iki
   haftadan uzun beklerken, aynı sürede v0.3-v0.4 özellikleri, mixture
   v2'ler, kalibrasyon CLI'ları bitirildi. Roadmap "v0.3 tamamlandı" der;
   "tamamlanan" her şey smoke veriyle doğrulanmıştır. Aktivite metriği,
   çıktı metriğinin yerine geçmiştir.
2. **Garantiler dürüst etiketlenmedi.** README'nin sattığı "append-only,
   immutable, bağımsız inceleme" garantilerinin her biri bugün aynı tek
   kişiye ve aynı süper-kullanıcıya karşı geçersizdir. Backlog bunu bilir ve
   yazar — proje kendine dürüst, vitrinine değildir. Eksik olan tek cümle:
   "Bu garantiler N kişilik ekip + ayrıcalık ayrımı geldiğinde devreye
   girer; bugün disiplin provasıdır."

## 5. Karar: Yık mı, kurtar mı?

**Karar: YIKMA. Refactor da değil — DİYET.**

Yeniden yazım neyi çözmez: projenin üç gerçek hastalığı kodda değildir —
(1) sahip ile ürün arasındaki kavram uçurumu, (2) tek kişilik gerçekliğe
çok aktörlü tören, (3) değer-son önceliklendirme. Greenfield bu üçünü aynen
miras alır ve 4-8 haftalık sıfır-değer dönemi ekler.

Çekirdek sağlamdır ve yeniden yazan biri aynısını yazar: içerik adresli
depo atomik ve doğru (`local.go:57-77`, `O_EXCL` yayın deseni), kapı zinciri
82 testle yeşil, deterministik export kanıtlı, şema kısıtları yerinde.

### Diyet planı (yol haritası tohumu)

| Öncelik | Eylem | Ölçüt |
|---|---|---|
| 0 | **Asıl iş:** 200 örneği oku, kaynağı onayla, release'i dondur, Gardash'a teslim et | Gerçek teslimat sayısı 0 → 1 |
| 1 | **Yüzey moratoryumu:** gerçek release #1 ve gerçek ikinci insan gelene kadar yeni özellik yok | Yeni endpoint/tablo/panel sayısı = 0 |
| 2 | **Dondur:** benzerlik inceleme alt sistemi, canonical'ın tool_call/preference kolları, v0.5-v0.6 iddiaları — kod kalsın, yol haritasından çıksın | Roadmap revizyonu |
| 3 | **Kes:** 14 İngilizce ikiz (sil veya "güncellenmiyor" damgası), tek atımlık CLI'ların kalıcı entry-point kaydı, koddaki mutlak yol | `docs/*.en.md` kararı; pyproject temizliği |
| 4 | **Dürüst etiketle:** README'ye tek paragraf — garantilerin tek-operatör kurulumunda "disiplin provası" olduğu beyanı | README güncellemesi |
| 5 | **Sadeleşme dalgası (moratoryum sonrası):** BFF proxy tekrarının tek catch-all route'a indirilmesi; mixin'lerin gerçek modüllere evrimi; 200-örnek kapısının amacının (sorumluluk imzası) belgeye yazılması | LOC ve dosya sayısı düşer |

**Özet hüküm:** Hasta ameliyatla kurtulmaz, çünkü hastalık organlarda değil;
perhizle kurtulur. Organlar (depo, kapılar, şema) sağlam; vücut kendi
bağışıklık sistemini beslemekten, beslenmeyi unutmuştur.
