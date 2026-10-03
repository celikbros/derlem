# FineWeb2-HQ (`tur_Latn`) değerlendirmesi — indirmeden önce ölçülenler

**Tarih:** 2026-10-04 · **Karar:** kurucu · **Durum:** ölçüm bitti; indirme ve alım kararı bekliyor
**Bağlam:** kurucu kararı "B" (2026-09-29): v5 dondurulmuyor, sıradaki korpus `epfml/FineWeb2-HQ`
tabanlı ([plan_2026_09.md](plan_2026_09.md)). Bu belge o kararın sayılarını verir.
**Veri seti indirilmedi.** Okunan: veri kartı ve API üstverisi, 1.200 belgelik örnek, bir parquet
dosyasının altbilgisi. Ayrıntı: `var/olcum-2026-10-03/fineweb2-hq/RAPOR.md` (git'te değil),
lisans: [haklar/hf-fineweb2-hq.md](haklar/hf-fineweb2-hq.md).

Etiketler: **ölçüldü** (örnekte ya da kaynağın üstverisinde sayıldı) · **kestirim** (örnekten
tamamına taşındı) · **hakem** (Sonnet + sıkı ölçüt; kurucuyla uyumu TASK-040'ta kappa 0,49).

## 1. Ne olduğu

| | | |
|---|---|---|
| Sabit sürüm | `c0c06e94fd3a44ae9e802b2b0fc533817601eb5e` | ölçüldü |
| Lisans | ODC-By 1.0 + Common Crawl kullanım şartları (FineWeb-2 ile aynı); erişim açık | ölçüldü |
| Belge | 8.578.808 (105 parquet dosyası) | ölçüldü |
| Dosya boyutu | 107,3 GB — **%74,7'si `embeddings`** (768 boyutlu vektör, sıkıştırılmamış) | ölçüldü (tek dosya) |
| Yalnız metin + üstveri | **≈ 27,3 GB** (HTTP Range ile seçici okuma tek dosyada denendi, çalışıyor) | kestirim |
| Metin | ≈ 25 GB → **≈ 4,6 – 4,7 milyar token** (5,405 bayt/token) | kestirim |
| Belge boyu | ortanca 1.155 karakter, ortalama 2.615 bayt (v5: 2.647) | ölçüldü |
| Paragraf yapısı | belgelerin %92,3'ünde satır sonu korunmuş (v5'te hiç yok) | ölçüldü |
| Belge üstverisi | `url`, `date`, `dump`, `language_score`, `quality_score`, `minhash_cluster_size`, … | ölçüldü |
| Seçim yöntemi | dil başına eğitilmiş XLM-R + MLP puanlayıcısının üst %10'u; pozitif örnekler soru-cevap/sınav türü veri setleri | kart + makale |

## 2. Kalite: aynı hakem, aynı ölçüt, iki korpus

İki korpustan 100'er belge karıştırıldı, biçim farkları giderildi (hangi belgenin hangi
korpustan geldiği görünmesin), **tek hakem aynı oturumda** okudu. "Çöp" = `cop` + `emin değilim`.

| Korpus | n | Çöp | %95 aralık |
|---|---:|---:|---|
| FineWeb2-HQ | 100 | **%43** | %33,7 – %52,8 |
| v5 | 100 | **%53** | %43,3 – %62,5 |

Ayrı ayrı okunan 200'er belgede: HQ %39,0 · v5 %48,5. Üç okumada da yön aynı ve fark ≈ 10 puan;
n = 100'de tek başına anlamlı değil (z = 1,42), birlikte tutarlı. Hakemin kendi tutarlılığı
(aynı belge, iki ayrı okuma): uyum %96 / %94, kappa 0,92 / 0,88.

**İki sonuç:**

1. **FineWeb2-HQ, v5'ten yaklaşık 10 puan daha temiz** — ama ikisi de kurucunun "sıkı korpus"
   ölçütünün çok uzağında. Korpus seçmek sorunu çözmüyor; asıl iş süzgeç.
2. **Çöpün türü farklı** (karma okumada çöp nedenleri):

   | Neden | FineWeb2-HQ | v5 |
   |---|---:|---:|
   | Makine çevirisi | **12** | 1 |
   | SEO / ticari / ürün | 12 | **18** |
   | Menü / manşet yığını | 1 | **12** |
   | Yetişkin / bahis | 1 | **7** |
   | Bozuk karakter | 4 | 5 |

   FineWeb-2'nin çıkarımı sayfa artıklarını ve yetişkin içeriği büyük ölçüde temizlemiş; kalan
   baskın çöp makine çevirisi. v5'te tersine menü yığınları ve yetişkin içerik duruyor, makine
   çevirisi neredeyse yok.

**Veri setinin kendi `quality_score`'u çöpü ayırmıyor.** Hakemin `cop` dediği belgelerin puan
ortancası 0,088, `kalsın` dediklerininki 0,075. Puan eşiğini yükseltmek işe yaramıyor: tamamında
çöp %39,0, puanı en yüksek yarıda %42,0, en yüksek çeyrekte %42,0. O puan "soru-cevap verisine
benzerliği" ölçüyor.

## 3. Makine çevirisi — bu veri setinin asıl kusuru

Gözle işaretleme (alt sınır; yalnız URL'si şüpheli 269 belgeye bakıldı):

| | Ana örnek (1.000) | Kontrol (200, tam rastgele) |
|---|---|---|
| Belge payı | %8,1 [6,6 – 10,0] | %13,0 [9,0 – 18,4] |
| **Bayt payı** | %15,7 | **%33,7** |
| ≤ 2019 dökümlerinde | %4,8 | %1,6 |
| ≥ 2022 dökümlerinde | %19,5 | %17,6 |
| `tr-web-v3` yakaladı | 0 / 81 | 1 / 26 |

İki bağımsız yöntem aynı yeri gösterdi: gözle "makine çevirisi" diye işaretlenip hakemin kör
dosyasına düşen 13 belgenin **13'üne** hakem de `cop` dedi.

Çeviri belgeleri uzun ve yeni dökümlerde yoğun; belgelerin %69'u 2020 sonrası dökümlerden.
İmzası çoğu zaman **adreste**: ana makine `tr.` ile başlıyor (`tr.topwar.ru`, `tr.eferrit.com`)
ya da yolda `/tr/` var ve alan adı Türkiye'ye ait değil; içerikte marka ve soyadları çevrilmiş
("Juliette Gordon **Düşük**"). Bu sinyal ancak `url` sütunu olduğu için kullanılabiliyor —
v5'te adres hiç yok.

## 4. Bizim hattımız bu veriye ne yapar

| | | |
|---|---|---|
| `tr-web-v3` atardı | 6 / 1.000 = %0,6 (baytın %3,8'i) | ölçüldü |
| Kişisel veri isabeti | 9 / 1.000; 8'i yayıncının yer tutucusu (`email@example.com`) | ölçüldü |
| Hattan geçince küçülme | belgelerin %1,5'i, baytın %6,3'ü | ölçüldü |

Yani bugünkü kurallarımız FineWeb2-HQ'nun çöpünü **görmüyor**: hakemin %40 dediği yerde %0,6
atıyor. Kurallar mC4'ün çöpüne (menü, anahtar kelime, bozuk kodlama) göre yazılmıştı. Bu
veriyle çalışacaksak gereken iki kural: **makine çevirisi** (TASK-042, 1. sınıf) ve **ticari/ürün
sayfası**.

## 5. Elimizdekiyle ilişkisi

| | | |
|---|---|---|
| Ana korpusla örtüşme (≥ 2 çapa aynı satırda) | 115 / 1.000 = %11,5 [9,7 – 13,6] | ölçüldü |
| Net-yeni | belge olarak ≈ %88 – 91, bayt olarak ≈ %93 – 96 | kestirim |
| **İdari-resmî Türkçe** (`gov.tr`, `bel.tr`, `tbmm`, `resmigazete`, `mevzuat`) | **3 / 1.000 = %0,3 [0,10 – 0,88]**; üçü de karar/mevzuat metni değil | ölçüldü + gözle |
| Ansiklopedi (hakemin tür etiketi, karma okuma) | HQ 4 / 100 · v5 10 / 100 | hakem |

**İdari-resmî damar bu veri setinde yok denecek kadar ince.** Karar motoru hedefi için gereken
metin türü buradan gelmeyecek; ayrı bir kaynak gerekir. Ansiklopedi ve sözlük payı da v5'te daha
yüksek: bizim ayırt edici kaynaklarımız (Vikipedi, TTK Belleten, DergiPark, TDK) FineWeb2-HQ'nun
**tamamlayıcısı**, rakibi değil.

## 6. Disk

Yalnız metin + üstveri ≈ 27,3 GB, bugünkü boş alana (57 GB) sığar. Bugünkü hattın "üç kopya"
düzeni (alım dosyası + depo nesnesi + temiz aday ≈ 75 – 80 GB) **sığmaz**. Çözümü mimaride:
aday bir **metin kopyası** değil, **seçim listesi** olursa üçüncü kopya hiç oluşmaz; alım
dosyası depoya sabit bağla verilirse ikinci kopya da oluşmaz.

## 7. Kurucunun önündeki kararlar

1. **Taban FineWeb2-HQ mi?** Ölçüm B kararını destekliyor (≈ 10 puan daha temiz, iki katı
   hacim, belge üstverisi ve paragraf yapısı var, %88 – 91'i net-yeni) — ama "temiz korpus"
   beklentisini değil: aynı ölçütle %40 civarı çöp.
2. **`embeddings` dahil mi?** Hariç: 27,3 GB, bütün satırlar ve bütün üstveri eksiksiz.
   Dahil: 107,3 GB, disk yetmiyor.
3. **Yeni iki kural** (makine çevirisi, ticari/ürün sayfası) alımdan önce mi, sonra mı?
4. **İdari-resmî Türkçe için ayrı kaynak** aranacak mı?
5. **İnceleme kapısı eşiği** (bugün tek ret kaynağı kilitliyor) — hâlâ açık.
6. **Mimari:** kaynak uyarlayıcısı + ortak belge kaydı + metinden ayrı kararlar (TASK-032'nin
   yeniden yazımı).

## Sınırlar

- Hakem bir dil modeli; sayıları kurucunun hükmü değil. Kurucu aynı karma dosyadan 20 – 30
  belgeye bakarsa çıpa olur.
- Karma okumada hakem, kendi hükümlerini verdikten sonra önceki bir oturumdan kalmış bir hüküm
  dosyasını yanlışlıkla gördüğünü bildirdi; hükümlerini değiştirmediğini söyledi. Test-tekrar
  uyumu bu yüzden üst sınır sayılmalı.
- Örnek 10 rastgele ofsetten 100'er satır (küme örneği) + 200 tam rastgele; aralıklar buna göre
  dar görünür. Makine çevirisi sayıları alt sınır.
- Seçici okuma tek dosyada denendi; 105 dosya için 27,3 GB bir ölçeklemedir.
