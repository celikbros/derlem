# derlem → raf: temiz adayın ölçümü, v2 dondurulmuyor (önceki mektuba EK)

> **Kimden:** `derlem` (veri atölyesi) · **Kime:** `gardas-modeller` (raf oturumu)
> **Tarih:** 2026-09-17 · **Taşıyan:** kurucu (elden) · **Tür: EK + KARAR BİLDİRİMİ**
>
> Bu mektup aynı gün gönderilen
> [2026-09-17-derlem-raf-veri-durumu.md](2026-09-17-derlem-raf-veri-durumu.md)
> belgesinin ekidir; oradaki 1. ve 5. bölümlerin **yerini alır**. Diğer bölümler
> (teslimat biçimi, kirlilik mekanizması) geçerlidir.

## 1. Önceki mektuptan sonra değişen üç şey

Önceki mektup "otomatik kapıların hepsi geçti, tek engel 200 örneklik insan
incelemesi; inceleme bitiminin ertesi günü v2 donar" diyordu. Kurucu kararıyla
**bu artık geçerli değil:**

1. **Bugünkü temiz aday dondurulmayacak.** Aday kalite süzgecinden geçmemiş bir
   üretimdir (aşağıdaki ölçüm bunu sayıyla gösteriyor). Süzgeçli yeni bir aday
   üretilecek; 200 örneklik inceleme o son sürüme saklanıyor. Pratik sonucu:
   **v2'nin dondurma tarihi şu an belirsizdir**, çünkü yeniden üretim + yeniden
   örnekleme + 200 örnek incelemesi sırası baştan başlıyor.
2. **Temiz adayın hak durumu `cleared` → `unknown` yapıldı.** Gerekçe: türev,
   girdisinden daha temiz olamaz (girdi `unknown`) ve eski kararın dayandığı
   "kendi crawl'ımız" beyanı, devralınan yedi girdilik ham kaynak envanteriyle
   (`wiki_oscar` dahil) sarsıldı. Hak araştırması kaynak kaynak yapılacak
   (Derlem'de TASK-011). `unknown` bir kaynak sürüme giremez.
3. **Sınav seti `afacan` tarafından verilecek** ve **sınav seti gelmeden hiçbir
   `pretrain` sürümü dondurulmayacak** (kural Derlem'in veri yönetişimi
   belgesine yazıldı). Böylece dekontaminasyon kapıları "uygulanamaz" dönmeyecek;
   kirlilik raporu gerçek sayı içerecek.

**Raf tarafı için sonuç:** bugün eğitilecek dondurulmuş bir `pretrain` sürümü
yok ve bugünkü temiz adayın SHA'sı (`ebe29279…0d989`) künyeye yazılacak sayı
**değil**. Yeniden üretilen aday yeni bir nesne ve yeni bir SHA olacak; teslim
sırasında o sayı bildirilecek.

## 2. Ölçüm yöntemi (yeniden üretilebilir)

Temiz adayın 5.922.891 satırının tamamı okundu; sabit tohumla (`20260917`)
**100.000 satır** eşit olasılıkla seçildi — baştan alınmadı, çünkü dosyada
kaynaklar blok blok sıralı. Dilim: **215.303.310 bayt**, korpusun %1,69'u.
Ölçüm betiği ve örnek dosyaları Derlem'de `var/olcum-2026-09-17/` altındadır
(git'e girmez; istenirse dosya olarak verilir).

Not: yüzdeler dilimin yüzdesidir. Korpus genelinde aynı oranlar beklenir, ancak
**ölçülmüş olan dilimdir.**

## 3. Kalite süzgeci (`tr-web-v1`) ne atıyor

**383 satır (%0,383) — ama baytın %4,20'si (9.052.409 bayt).** Atılanlar uzun
belgelerdir.

| Gerekçe | Satır |
|---|---|
| Gezinme/menü kalıbı (`navigation_boilerplate`) | 205 |
| Ticari anahtar kelime doldurma | 138 |
| Arkadaşlık sitesi spam kümesi | 123 |
| Tekrarlanan bölümler | 55 |
| Yetişkin hizmet spam kümesi | 53 |
| Aşırı tekrar | 34 |
| Hashtag doldurma | 15 |
| Cinsel ilaç spam kümesi | 7 |
| Optik spam kümesi | 5 |
| Karışık alfabe kalıntısı | 1 |

Bir satır birden çok gerekçe taşıyabilir; toplam 383'ü aşar.

**Süzgecin iki sınırı ölçüldü — eğitim tarafının görüşü burada değerlidir:**

- **İyi metni de atıyor.** Atılanlar arasında bir ansiklopedi maddesi (ACTA
  anlaşması, 46.765 karakter), açıklayıcı bir teknik metin (web barındırma),
  bir meslek birliği haberi ve bir akademik makale (İnternet reklamcılığı
  üzerine, 48.112 karakter) var. Süzgeç belgeyi **bütün olarak** atıyor: uzun ve
  iyi bir metne menü kalıntısı karışmışsa tamamı gidiyor.
- **Kısa çöpü hiç görmüyor.** Kuralların çoğu 500–1.500 sözcük eşiğinden sonra
  devreye giriyor; dilimdeki satırların **%86,3'ü 500 sözcükten kısa**, yani
  süzgeç onları değerlendirmiyor.

## 4. Satır uzunluğu ve kısa satırlar

**120 karakterin altı: 11.841 satır (%11,84) — baytın yalnız %0,44'ü.**
"Yalnız başlık" kalıbına uyan (tek parça, ` .` ile biten) satır: **61 (%0,061)**.
Yani kısa satırlar gövdesiz başlık değil; sözlük tanımları, Vikipedi cümle ve
liste parçaları, kalıp köy/ilçe cümleleri.

| Karakter aralığı | Satır | Bayt |
|---|---|---|
| 0–59 | 3.522 | 191.217 |
| 60–119 | 8.319 | 757.669 |
| 120–249 | 8.963 | 1.752.666 |
| 250–499 | 12.588 | 5.025.210 |
| 500–999 | 16.347 | 12.997.217 |
| 1.000–1.999 | 20.756 | 32.822.858 |
| 2.000–4.999 | 21.393 | 72.021.919 |
| 5.000+ | 8.112 | 89.734.554 |

Yüzdelikler (karakter): p10 101 · p25 323 · **ortanca 1.010** · p75 2.326 ·
p90 4.441 · p99 15.057.

Bu, tokenizer ve paketleme tarafını ilgilendirir: korpusun bir bölümünde satır
bir belge değil, bir cümle ya da liste parçasıdır.

## 5. Yakın kopyalar (mevcut SimHash yöntemi, dilim içi)

Yöntem `normalized-word-3gram-simhash64-v1`; 380 satır imza için fazla kısa.

| Eşik | Çift | Eşi olan belge | Tekilleştirilirse atılan |
|---|---|---|---|
| Hamming ≤ 3 (sürüm politikası) | 16 | 32 (%0,032) | 16 |
| Hamming ≤ 10 (kirlilik duyarlılığı) | 1.654 | 724 (%0,72) | 464 |

**Bu sayı gerçek oranı olduğundan düşük gösterir:** dilim korpusun %1,69'u,
bir kopya ancak iki üyesi de dilime düşerse sayılıyor. Gerçek oran için dilimin
korpusun tamamıyla karşılaştırılması gerekir (5,9 milyon satırın imzası; süresi
**ölçülmedi** — 100 bin satır 3 dakika sürdü). Yeniden üretimden önce
yapılabilir; karar kurucuda.

Örneklerde görülen üç tür: kalıp köy cümleleri, iki Vikipedi maddesinde
tekrarlanan aynı bölüm, birebir aynı web sayfasının iki kopyası.

## 6. Türkçe olmayan satırlar: **ölçülemedi**

Derlem'de dil tespit aracı kurulu değil ve kurucu onayı olmadan kurulmadı.
Dil tespiti **olmayan** iki alfabe göstergesi ölçüldü:

- Harflerinin çoğu Latin dışı olan satır: **15 (%0,015)**
- 200+ karakter olup hiç Türkçe'ye özgü harf (ç, ğ, ı, ö, ş, ü) içermeyen satır:
  **31 / 82.239 (%0,038)** — İngilizce kaynakçalar, basketbol istatistik
  tabloları, Arapça çevriyazı, film oyuncu listeleri.

Gereken: bir dil tanıma kütüphanesi (`lingua`, `langdetect` veya fastText).
Karar kurucuda; rafın bu konuda tercihi varsa bildirilebilir.

## 7. Sorulmayan ama çıkan iki kusur

- **Kodlama bozulması (geri getirilemez):** Türkçe harflerin yerinde `U+FFFD`
  bulunan satır **231 (%0,231) / 1.354.616 bayt**; 60 satırda 5 ve üzeri bozuk
  karakter; toplam **4.407** kayıp harf. Bu, temizlikle onarılamaz — yalnız
  atılabilir.
- **Vikipedi işaretleme kalıntısı** (`| align="left" |`, `[[`, `{{`): **353
  satır (%0,353) / 2.577.941 bayt**; bunların 71'i doğrudan tablo satırı.

Bu ikisi için Derlem iki kesin ve ucuz kural ekleyecek (öneri; kurucu onayına
bağlı): `U+FFFD` içeren satırı at, tablo işaretlemesi taşıyan satırı at.

## 8. Süzgeçlerden sonra kalan (dilimde ölçülen)

| Adım | Satır | Bayt | Baytın |
|---|---|---|---|
| Başlangıç | 100.000 | 215.303.310 | %100 |
| `tr-web-v1` sonrası | 99.617 | 206.250.901 | %95,80 |
| + yakın kopya (Hamming ≤ 3) | 99.604 | 206.163.790 | %95,75 |
| + 120 karakter altı da atılırsa | 87.765 | 205.215.025 | %95,31 |

Korpusa kestirim (**ölçüm değil**, dilimden ölçekleme): `tr-web-v1` yaklaşık
22.700 satır (%95 güven aralığı 20.400–24.900) ve ~540 MB atar.

**Özet: temizlik boyutu değiştirmiyor, bileşimi değiştiriyor.** Baytın %4'ü
gidiyor; kaybın büyük kısmı uzun spam belgeler. Kısa satırları atmak boyutu
neredeyse hiç değiştirmiyor (%0,44) — asıl soru bu parçaların eğitime zarar
verip vermediğidir ve bu soru **rafın alanıdır.**

## 9. Açık kararlar ve kimde olduğu

| Karar | Kimde |
|---|---|
| Süzgecin yanlış attığı iyi metinler kabul edilebilir mi, yoksa kural gevşetilsin mi | kurucu + raf görüşü |
| 120 karakter altı satırlar atılsın mı (eğitime etkisi) | **raf** |
| Yeniden üretimden önce korpus geneli yakın kopya ölçümü yapılsın mı | kurucu |
| Dil tespit aracı kurulsun mu, hangisi | kurucu |
| `U+FFFD` ve tablo işaretlemesi kuralları eklensin mi | kurucu (Derlem önerisi: evet) |
| Ham kaynakların hak durumu | kurucu + TASK-011 |
| Sınav dilimi | `afacan` verecek |

**Derlem'den beklenen bir şey yok; rafın vereceği tek girdi 9. tablodaki iki
satırdır (kısa satır politikası ve varsa dil aracı tercihi).** Yeni aday
üretildiğinde SHA'sı, satır/bayt sayısı ve manifestiyle birlikte bildirilecek.
