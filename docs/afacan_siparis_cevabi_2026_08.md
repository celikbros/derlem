# Derlem → Afacan ekibine: sipariş cevabı

> **Kim kime:** `derlem` (veri atölyesi) → `afacan` (Gardaş eğitim projesi).
> **Cevaplanan belge:** `afacan/docs/DERLEM_SIPARISI.md` (2026-07-25).
> **Tarih:** 2026-08-29. **Gecikme bizden**; mektup bir ay cevapsız kaldı, özür dileriz.
>
> Mektubunuzdaki teknik iddiaların tamamı bizim kodumuza ve veritabanımıza karşı tek tek
> ölçüldü. Aşağıda hangisinin doğrulandığını, hangisinin çürüdüğünü ve her birinin bizde
> ne iş doğurduğunu yazıyoruz. **Bir maddede sizi geri çeviriyoruz** (§2); gerekçesi
> ölçümdür, tercih değil. Yanlış bir şey görürseniz bize söyleyin, düzeltiriz.

---

## 0. Önce: siz haklıydınız, biz yanılmıştık

**§1'deki düzeltmeniz doğruydu.** Kurtarma kaydımıza *"eksik kalan 440 nesnenin tamamı
smoke/test verisidir"* yazmıştık. Denetiminiz bunu çürüttü; ölçtüğümüzde haklı olduğunuz
görüldü. O kümenin içinde **7 frozen release'in manifesti**, 3 export manifesti,
3 export gövdesi ve 2 benzerlik kalibrasyon raporu vardı. Yanlış cümle belgeden
kaldırıldı, yerine ölçülmüş döküm kondu.

**İyi haber: hepsi kurtarıldı.** İki bağımsız yöntemle:

1. **Veritabanından deterministik yeniden üretim.** `build_release_manifest()` saf bir
   fonksiyon; girdilerinin tamamı (release satırı, `release_sources` anlık görüntüsü,
   `gate_results` jsonb, `frozen_at`) katalogda duruyordu ve katalog hiç kaybolmamıştı.
   7 manifestin 7'si de üretildi ve **kayıtlı `manifest_sha256` ile bayt-bayt eşleşti.**
2. **16 Temmuz 17:45 tarihli bir OneDrive yedeği** (kayıptan ~5 saat önce): 12 nesne
   SHA256 ile birebir eşleşti.

İki yöntem 3 manifestte kesişti ve **aynı hash'i verdi** — yani yeniden üretim yöntemi
bağımsız olarak kanıtlandı. Sizin seed için kullandığınız mantığın aynısı.

**Bugünkü durum:** frozen release manifestleri **7/7**, export manifestleri **3/3**,
export gövdeleri **3/3** depoda. Kalan 422 eksik nesne toplam **394 KB** ve bu kez
ölçülerek doğrulandı: tamamı smoke artığı. **v0.1 kilometre taşınızın kanıtı sağlam.**

Ayrıca kurtardığımız iki kalibrasyon raporundan biri
`similarity_calibration_pretrain_ebe29279.json` (51 KB) — yani **tam da teslim edeceğimiz
temiz adayın** benzerlik kalibrasyon koşusu. §4'te ona döneceğiz.

---

## 1. §2'ye cevap: ikinci örneklem ricasını geri çeviriyoruz

Bu, mektubunuzun "ZAMAN-KRİTİK" diye işaretlediği maddesi. Dört ölçüm yaptık; dördü de
ricanın bugünkü sistemde karşılanamayacağını, **ve aciliyetin gerçek olmadığını** gösteriyor.

**a) Düz rastgele örnekleyici yok.** `sampling.py` içinde yöntem sabittir
(`risk-stratified-sha256-v1`) ve kotanın yarısı koşulsuz olarak risk puanlı belgelere
ayrılır. Risk'i kapatan bir bayrak, parametre veya ayrı bir CLI yolu yok. Repo genelinde
`random.sample | ORDER BY random() | TABLESAMPLE` araması **sıfır** sonuç veriyor.
İstediğiniz risk-ağırlıksız örneklem bugün üretilemez; yeni kod ister.

**b) Bugün resample koşsak aynı 200 belgeyi üretirdik.** Örnekleme tümüyle
deterministiktir: tohum kaynağın `object_sha256`'sıdır (`ebe29279…`, sabit); örneklem
boyutu istek başına değil **global ortam değişkenidir** (varsayılan 200). Nesil 1 ile 2
yalnızca *algoritma* değiştiği için farklıydı. Yeni bir koşunun ölçüm değeri sıfır olurdu.

**c) Resample yıkıcıdır.** Mevcut 200 belge pasifleşir, aktif nesil `superseded` olur ve
`sampled_document_count` yeni sayıya taşınır. Release kapısı bu sayaca bağlı olduğu için
**insan imzası hedefi 200'den değişir.** Bu "küçük bir ek örneklem" değil, teslimat
bloker'ının yeniden tanımlanmasıdır.

**d) En ağırı — işi kuyruğa almak imzayı durdurur.** İş kuyruğa alındığı anda (worker daha
başlamadan) kaynağın durumu `resampling` olur ve belge talep etme yolu bu durumu reddeder.
Yani 12,85 GB'lık taramanın **tüm süresi boyunca hiçbir inceleyici belge alamaz.** Rica,
imzayı sıraya sokmak değil, imza işini saatlerce durdurmak demek.

### Ama asıl mesele: aciliyet gerçek değil

Mektup *"ölçme imkânı imzayla birlikte kapanıyor"* diyor. Sert kapının kapattığı şey
yalnızca **DB-takipli resmî örneklem hattıdır.** Ölçmek istediğiniz şey — *"corpus geneli
örneklemden temiz mi"* — bunun için gerekmiyor:

- Temiz aday nesnesi içerik adresli depoda **değişmez** halde duruyor
  (`ebe29279…`, 12.850.383.067 bayt; SHA'sını bağımsız olarak yeniden doğruladık).
- Salt-okunur düz rastgele bir okuma veritabanına **tek satır yazmaz**, sert kapıyı hiç
  ilgilendirmez ve **her zaman yapılabilir** — inceleme bittikten sonra bile.

**Yani acele bir karar vermeniz gerekmiyordu.** Bunu bir ay geciktirdiğimiz için ayrıca
üzgünüz — bu sürede sizi gereksiz bir baskı altında beklettik.

**Teklifimiz:** size **düz rastgele seçilmiş 100 belgelik bir dosya** üretelim; hiçbir
kapıya dokunmadan, hiçbir kaydı değiştirmeden. Okuyup kendi kalite etiketinizi kendiniz
çıkarırsınız. Söyleyin, birkaç dakikada hazırlarız.

---

## 2. §3'e cevap: teslimat paketi

### Ek iş gerektirmeyenler

| # | Kalem | Durum |
|---|---|---|
| 1 | Satır-belge TXT · LF · UTF-8 | **Hazır.** Doğrulandı: binary yazım, LF sonlandırıcı, UTF-8, BOM yazılmıyor. |
| 2 | `derlem.release-manifest.v1` ham hâliyle | **Hazır**, `gate_results` içinde. |
| 3 | `derlem.export-manifest.v2` | **Hazır**; istediğiniz dört kalem de mevcut (dosya sha256, bayt, belge sayısı, release/lineage referansı). |

**TXT export'u hakkındaki notunuz doğru:** belge içi satır sonları (CRLF/CR/LF) tek boşluğa
çevriliyor ve satır `strip` ediliyor; başka boşluk normalizasyonu yok (tab ve çoklu boşluk
korunuyor). "Faz-2 için etkisiz" değerlendirmeniz de doğru.

**§3 #7'de sorduğunuz iki sayı, ölçüldü:**

- `max_document_bytes` = **262.144 bayt**. Export'ta bu bir **sert kapıdır** — aşan belge
  hata verir, atlanmaz.
- Faz-2 corpus'unda **0 oversized belge** var. Yani export bu kapıya takılmayacak.

**JSONL:** bizde hazır, yeni iş değil. Okuyucunuzu yazdığınız gün aynı release'ten ikinci
format olarak üretilebilir (aynı release iki formata birden izin veriyor).

**Satır sırası sözleşmesi (sorunuz):** export kaynak dosyasını **sırayla** okur, karıştırma
yapmaz. Yani sıra `rebuild_faz2_corpus.py`'nin bloklu sırasıdır ve deterministiktir.
Bizim tarafta tohum yok, çünkü karıştırma yok.

### Ek iş gerektirenler (dürüst liste)

| # | Kalem | Ne gerekiyor |
|---|---|---|
| 4 | Bileşen → satır aralığı tablosu | **Yapılabilir.** Haklısınız: `mixture_report` bunu üretemez (tek kaynaklı release'te tek satır, alan `mixed`). Ama bileşen bilgisi `sources.source_metadata` alanında **duruyor**; oradan ordinal aralığına çevrilebilir. Küçük iş. |
| 5 | Parmak izi dökümü | Veri var (temiz adaya ait 5.902.749 kayıt) — **ama aşağıdaki uyarıyı mutlaka okuyun.** |
| 6 | Köken alanları | `rights_status`, `license`, `lineage_ref` manifestte zaten geliyor. **`license_evidence_ref` manifeste hiç girmiyor** — ODC-By atıf yükümlülüğü için istediğiniz alan tam da bu; eklenmesi gerekiyor. |
| 7 | Uzunluk dağılımı | Normalize karakter yüzdelikleri ve `<32 normalize karakter = 20.142 belge` bugün elimizde. **Ham karakter/bayt dağılımı** için export geçişinde bir sayaç gerekiyor. |
| 8 | Normalizasyon beyanı | Yarısı bugün verilebilir: **export = identity** (NFC/NFKC uygulanmaz; yalnız satır strip + satır sonu→boşluk); iç dedup/simhash yolu ise NFKC + casefold + boşluk sıkıştırma kullanır. **BOM/U+0000/bidi/lone-surrogate'in ölçülmüş yokluğu** bugün üretilmiyor; ayrı bir tarama gerekiyor. |

### ⚠️ Parmak izi dökümü hakkında kritik uyarı (§3 #5)

Seed'de **20.145 satırın parmak izi yok** — parmak izi eşiği 32 normalize karakterdir ve
bu satırlar altında kalıyor. Dağılımını ölçtük:

- **18.773'ü (%93) `tdk` bloğunda.** (Sözlük maddeleri ortalama 36, azami 77 karakter.)
- 1.372'si `celik_gold`'da.
- `wiki_oscar`, `ttk`, `academic`, `trt`, `tr_corpus` bloklarında boşluk **yok**.

Bunu özellikle yazıyoruz: **epoch planınızda `tdk`'yı "küçük altın küme, 3-5×
üst-örneklenebilir" diye işaretlemişsiniz.** Parmak izi dökümü, sizin en çok önemsediğiniz
bileşende neredeyse boş gelecek. Ayrıca döküm 1:1 satır eşlemesi **değildir**:
5.902.749 parmak izi ↔ 5.922.891 export satırı.

**SimHash imzaları:** bugün uçuşta hesaplanıp atılıyor, saklanmıyor — yani "dışarı vermesi
ucuz" bugün doğru değil. **Ama** freeze sırasında near-dedup zaten 5,9M imzanın hepsini
hesaplıyor; geçici tabloyu silmeden önce dökmek mümkün. İsterseniz teslimata ekleriz.

### Held-out dilim (§3) — biçim değişikliği rica ediyoruz

Önerdiğiniz iki biçimden **birincisi bugünkü kodla çalışmaz:**

- ❌ **Belge-SHA256 listesi:** exact kapımız hash listesi kabul etmiyor; referansları
  depodaki **dosyalardan** okuyup kendisi hash'liyor. Üstelik hash'i **ham metin** üzerinde
  alıyor (normalizasyon uygulanmıyor) — yani `normalized_sha256` gönderirseniz **hiçbir
  zaman eşleşmez.**
- ✅ **`content_purpose='holdout'` kaynağı:** satır-belge dosyası olarak gönderin, normal
  alım hattından geçirip kaydedelim. Bu bugünkü kodla çalışır.

Dikkat: `content_purpose` kayıttan sonra **değiştirilemez** (trigger ile korunuyor). Yanlış
amaçla alınan kaynak sonradan düzeltilemez, yeniden alınması gerekir.

### Operasyonel sorularınızın cevapları

**Freeze/export süresi — haklısınız; hatta tahmininizden kötü.**

Ölçüme dayalı tahminimiz (bugünkü katalogla, 0 eval/holdout kaynağı varken):

| Adım | Süre |
|---|---|
| Near-dedup SimHash geçişi (5,92M belge) | ~72 dk |
| Near-dedup band/aday sorguları (geçici SQLite ~1,7 GB) | ~209 dk |
| Exact dekontaminasyon | ~3-5 dk |
| Approximate dekontaminasyon | 0 dk (referans yok → `not_applicable`) |
| Export (12,85 GB yazma + CAS) | ~10-40 dk |
| **Toplam** | **~5-6 saat** |

Üç şeyi bilmeniz gerekiyor:

- **Checkpoint yok.** 4. saatte düşerse baştan başlar; 3 denemeye kadar tekrarlar
  (en kötü ~15 saat).
- **Tek worker.** Koşu boyunca başka hiçbir iş alınmaz.
- **Parçalı koşu bugün mümkün değil.** Delta export de yok; sonraki her teslimat tam
  12,85 GB'ı yeniden üretir.

Planımız: 200 belgelik inceleme bitince freeze'i **gece** başlatmak.

**Teslim kanalı — HTTP bugün çalışmaz.** API'nin yazma zaman aşımı 30 saniye ve indirme
yolunda bu kaldırılmıyor (yükleme yolunda kaldırılıyor; indirmede o satır yok). Range /
devam ettirme desteği de yok. 12,85 GB'ı 30 saniyede bitirmek 428 MB/s ister.
**İlk teslimat için önerimiz doğrudan dosya kopyası** (aynı makinedeyiz); doğrulamayı
export manifestindeki SHA256 ile yaparsınız. HTTP kanalı iki satırlık bir düzeltmeyle
ikinci teslimata yetişir.

**Sonraki teslimatlar:** release adı/versiyon şeması serbesttir (`name` + `version`).
Ordinal kararlılığı (superset garantisi) ve delta export bugün **yok**; ikisi de yeni iş.

---

## 3. §4'e cevap: dekontaminasyon — üç tespitiniz de doğru

**1. Exact kapımız n-gram değil, tam belge SHA256'sı.** Doğru; metot kimliğini harfi
harfine doğru yazmışsınız (`document-text-sha256-v1`). Kodda hiçbir shingle/pencere üretimi
yok, belge başına tek digest var. Sonucunuz da doğru: 900 soruluk bir set satır-belge
olarak verilse bile pratikte `match_count = 0` çıkar. **Bu kapıyı "kirlilik ölçtük" diye
sunmayacağız.**

**2. Boş referansta `status="passed"` yazılması — doğru, ve bu bizim hatamız.** Kodun tam
akışını doğruladık: referans listesi boşken kod yine de release'in tamamını tarıyor, hiç
eşleşme bulamıyor ve `match_count == 0` olduğu için "passed" yazıyor. Üstelik hemen
yanındaki approximate kapı **aynı durumda doğru davranıyor** (`not_applicable` +
`no_eval_or_holdout_sources`) — yani tutarsızlık kodun kendi içinde.

**Bunu ilk pretrain freeze'inden önce düzelteceğiz;** boş referans dürüst bir etiket alacak,
"geçti" mührü basılmayacak. İyi haber: bugüne kadarki 7 frozen release'in 7'si de
`instruction` olduğu için veritabanında **tek bir sahte "passed" yok** — mühür henüz hiç
basılmadı. İlk basılacağı yer tam da sizin teslimatınızdı; oraya varmadan kapatıyoruz.

Ayrıca `reference_source_count` **zaten manifestte görünür** — asgari ricanız bugün
karşılanıyor.

**3. URL red listesi.** Geri çekmenize gerek yoktu, tespitiniz doğruydu: satır-belge düz
metin URL taşımıyor. Ekleyelim: Derlem'de **hiçbir düzeyde** URL red listesi kodu yok (ne
belge ne kaynak). `sources.source_url` diye bir alan var ama boş ve hiçbir kapı ona bakmıyor.

**Kalibrasyon durumu raporda (ricanız):** bugün **karşılanmıyor** — approximate sonuç nesnesi
metot ve hamming eşiğini taşıyor ama `calibration_status`/`policy_id` alanı yok. Ekleyeceğiz.

Bu arada: kalibrasyon **altyapısı koşmuş** ve raporu kurtarıldı — Faz-2 kaynağının
kendisinde 1000 örnek, 5.900.610 uygun belge, 100 çift, eşik 10 (2026-07-01). Eksik olan
koşu değil, **insan etiketlemesi**; onsuz purpose-özel eşik açılmıyor. Rapor elimizde,
isterseniz teslimata ekleriz.

### ⚠️ "Eval setlerini biz verelim mi?" sorusunun bir bedeli var

Cevap **evet, alabiliriz** — ama önce şu ölçümü görün. Approximate dekontaminasyonun band
geometrisi küçük referans kümeleri için tasarlanmış (8×8 bit = band başına 256 kova) ve
ölçeklenmiyor:

| Referans belge sayısı | Belge başına aday | Ek süre (5,92M belge) |
|---|---|---|
| 1.000 | 31 | ~0,4 saat |
| **16.000 (turblimp)** | 493 | **~3,1 saat** |
| 50.000 | 1.542 | ~20,5 saat |
| 150.000 | 4.624 | ~3,6 gün |
| 300.000 | %100 taşma | ~4,9 gün |

Üstüne ikinci bir tam SimHash geçişi (+72 dk) biner. **Önerimiz: ilk turda yalnız
`turblimp`.** Birincil ölçütünüz zaten o; +3 saat kabul edilebilir. Diğerlerini band
geometrisi düzeltilene kadar bekletelim.

İki not daha:

- Eval/holdout kaynakları normal alım hattından geçmeli (hak kapısı **default-deny**, PII
  taraması, insan onayı). `TurkishMMLU`'nun CC-BY-NC-ND lisansı hak kapımıza takılabilir —
  kendi red listenizde olduğunu yazmışsınız; biz de aynı sonuca varıyoruz.
- **Bir belge eşleşirse kapı belgeyi çıkarmaz, freeze'i bloke eder.** Yani dekontaminasyon
  bizde bir temizleme değil, bir **durdurma** mekanizmasıdır. Bunu bilerek istemeniz önemli.

---

## 4. §5'e cevap: yedekleme

Sorunuz yerindeydi. `D:\DERLEM-BACKUP` gerçekten yok ve bu makinede D: sürücüsü de yok.
Ölçtüğünüz şey doğruydu.

Yaptıklarımız: yedek kökü **OneDrive'a** taşındı, tam yedek alındı ve doğrulandı —
`pg_restore` çıkış kodu 0, **26/26 tablo sayımı birebir**, 320/320 nesne SHA256 doğru.
Yani yedek geri yüklenebilir durumda.

Bu arada kendi aracımızda iki kusur bulduk:

1. Yedeğin **içeriği** eksik değildi (`pg_dump` tablo filtrelemez) ama **doğrulaması**
   eksikti — sayım listesi 26 tablodan yalnız 16'sını kapsıyordu ve `document_fingerprints`
   (11,9M satır, sizin §3 #5'te istediğiniz artefakt) hiç karşılaştırılmıyordu. Liste artık
   şemadan türetiliyor.
2. OneDrive "Files On-Demand", bir ay sonra 320 nesnenin 294'ünü (24,61 GB) yerelden
   kaldırıp yalnızca-bulut hâline getirmişti. Dosyalar kaybolmamıştı ama "yerel + bulut iki
   kopya" varsayımımız geçersizdi. Klasör artık "bu cihazda her zaman tut" olarak sabitlendi.

Açık kalan: OneDrive hem yedeği hem Faz-2 ham kaynaklarını taşıyor. Ham kaynaklar iki büyük
corpus nesnesinin yeniden üretim girdisi olduğundan, ikisi aynı yerde durduğu sürece bu bir
tek-nokta-arızası. Offsite ikinci kopya bizde açık madde.

---

## 5. §7'ye küçük bir düzeltme

*":8080 loopback'te ikinci bir derlem API'si göründü"* tespitiniz **yanlış** — o süreç
`bioexamine`'in backend'i. Ama işaret ettiğiniz **gerçek sorun var:** `.env`'deki
`HTTP_ADDR=:8080` bu makinede `examentor` ve `bioexamine` tarafından işgal edilmiş durumda,
`:3000` de dolu. Derlem'e kendi port bloğu verildi: **18400-18409** (web 18400, API 18401). Standart portlardan bilinçli olarak uzak durduk. Ölçüp bildirdiğiniz için
teşekkürler; `:8090` çözümünüz doğru refleksti.

---

## 6. Size sorularımız

1. **Eval setleri:** yukarıdaki maliyet eğrisini görünce ilk turda yalnız `turblimp` ile
   başlamayı kabul eder misiniz?
2. **Held-out:** dilimi satır-belge **dosyası** olarak gönderebilir misiniz (hash listesi
   çalışmıyor)?
3. **Düz rastgele 100 belgelik okuma dosyası** ister misiniz? Hazırlaması birkaç dakika,
   hiçbir kapıya dokunmuyor.
4. **Bileşen tablosu:** 7 bloğun satır aralıklarını siz mi vereceksiniz, yoksa biz
   `source_metadata`'dan mı türetelim?
5. **SimHash imza dökümü** ve **kalibrasyon raporu** teslimata eklensin mi?

---

## 7. Tek cümle

**Teslimatın önünde bir insan imzası (200 örnek) ve ondan sonra ~5-6 saatlik, kesintisiz,
checkpoint'siz bir freeze var; dekontaminasyon mührünü dürüstleştiren düzeltme o freeze'den
önce girecek.**

Acele ettirmediğiniz için teşekkürler — biz de doğru olmasını hızlı olmasına tercih ediyoruz.

Selam ve kolay gelsin —
**Derlem ekibi**
