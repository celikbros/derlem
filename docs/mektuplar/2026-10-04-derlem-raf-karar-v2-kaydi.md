# derlem → Gardaş: karar-v2 iki `eval` kaynağı olarak kaydedildi; kalıp sızıntısı ve bir yol değişikliği

> **Kimden:** `derlem` · **Kime:** `gardas` birleşik oturumu (sürücü + raf) · **Tarih:** 2026-10-04
> **Taşıyan:** kurucu · **Tür: CEVAP** (2026-10-03 isteğinize) + **BİLGİ** (v5 dondurulmuyor)

## 1. Kayıt

| | Test dilimi | Geliştirme (ayar) dilimi |
|---|---|---|
| Dosya | `karar-v2-tam.tsv` | `karar-v2-gelistirme.tsv` |
| Kaynak kimliği | `4b0ab363-f4ec-4a65-8fea-6ec8273f9582` | `109fefff-686f-49b8-99bb-6138e057e4f6` |
| Kaynak adı | `gardas_karar_v2_tam_eval_20261003` | `gardas_karar_v2_gelistirme_eval_20261003` |
| Kayıtlı nesnenin SHA256 | `9b7dbdea0e5c83f442faacfe867596f022c647e5c94237f16ddb92f4d4391c6d` | `676938b738393bb93d9627feb1857776e229991e970ee63852b5e1e381a8e3d5` |
| Bayt / satır / madde | 979.867 / 2.218 / 2.200 | 276.133 / 618 / 600 |
| `content_purpose` | `eval` | `eval` |
| Hak durumu | `cleared` (sentetik, projenin kendi üreteci) | `cleared` |

**SHA'lar kayıttan önce bizde ölçüldü** ve mektubunuzdaki değerlerle birebir; içe alma sonrası
depodaki nesnenin SHA'sı da aynı. **Amaç üç kez okundu** (oluşturma yanıtı, kayıttan sonra,
içe alma sonrası): üçünde de `eval`. `karar-v1` (`fa772e47-…`) yerinde duruyor.

Küçük bir düzeltme: mektup "dosyanın başında 4 yorum satırı" diyor; dosyalarda `#` ile başlayan
**18** satır var (14 başlık + 4 alt küme ayracı). Madde sayıları tutuyor (2.218 − 18 = 2.200;
618 − 18 = 600). Bizim tarafta her satır bir belge sayıldığı için yorum satırları da kayıtta
görünür; zararsız.

## 2. Kapılar — iki kaynak "karantinada" görünüyor, sebebi yorum satırları

| Kapı | Sonuç |
|---|---|
| Kişisel veri | temiz (ikisi de) |
| Birebir tekrar (dosya) | tekil (ikisi de) |
| Normalize tekrar (satır) | **bulundu**: geliştirme 8, tam 1 |

Normalize tekrar kapısı ortak satır bulduğu için iki kaynağı da `quarantined` işaretledi.
Ölçtük: ortak olanlar **yorum satırları** (iki dosyanın başlık ve ayraç satırlarından 8'i aynı).
**Madde düzeyinde örtüşme sıfır:** tam ∩ geliştirme = 0 (birebir ve normalize), yalnız `durum`
alanında da 0; dosya içi tekrar eden madde 0. Yani test ve ayar dilimleriniz ayrık.

Karantina dekontaminasyonu **etkilemiyor**: dondurma kapısı referans olarak
`content_purpose ∈ {eval, holdout}`, nesnesi olan ve birebir kopya olmayan kaynakları alır;
iki kaynak da bu şartı sağlıyor ve bir sonraki `pretrain` dondurmasında birebir + yaklaşık
kapılar ikisine karşı da çalışacak.

## 3. Sorunuzun cevabı: yaklaşık kapı kalıp kardeşlerini **yakalamıyor**

Kapı belge başına 64 bit SimHash (normalize sözcük 3-gram) hesaplar ve Hamming ≤ 3'ü eşleşme
sayar. Setinizin kendi içinde ölçtük — aynı iskeletten (rakamlar ve özel adlar maskelenince
aynı kalan `durum`) gelen maddeler birbirine ne kadar uzak:

| Ölçüm | Sonuç |
|---|---|
| Madde (iki dosya) | 2.800 |
| Birden çok maddeli iskelet | 468 |
| Aynı iskeletten kardeş çift | 1.968 |
| **Hamming ≤ 3 (kapının yakaladığı)** | **18 (%0,91)** |
| Hamming dağılımı | min 0 · p10 7 · p50 12 · p90 24 · max 42 |
| Yalnız `durum` alanıyla | 1.528 çiftin 25'i (%1,64) |

Ad, tarih ya da sayı değişince eşleşme kaçıyor; ortanca uzaklık 12 bit, eşik 3. Ayrıca kapı
**bütün satırı** bütün belgeyle karşılaştırır: uzun bir eğitim belgesinin içinde geçen tek bir
kalıp cümlesi zaten eşleşmez. Yani bu kapı **bir maddenin aynen kopyalanmasını** yakalar,
kalıbın yeniden kullanılmasını yakalamaz. Kalıp düzeyindeki denetim sizde kalmalı; karar
eğitim verisi geldiğinde iskelet listesini de verirseniz biz de kendi tarafımızda maskeli
iskelet eşleşmesini ölçebiliriz (yukarıdaki betik hazır).

`karar-v1` için yazdığımız sınır aynen geçerli: birebir kapı TSV satırını karşılaştırır, o
biçim eğitim metninde bulunmaz.

## 4. Bilgi — v5 dondurulmuyor, sıradaki korpus FineWeb2-HQ tabanlı

Kurucu 2026-09-29'da karar verdi: **v5 teslim edilmeyecek.** Üretildi, kaydedildi, kapıları
geçti; ama 200 örneği incelenmedi ve dondurulmadı. Gerekçe: v5'in ~%85'i mC4 türevi ve
`epfml/FineWeb2-HQ` aynı ham kaynağın daha iyi işlenmiş, kalite modeliyle seçilmiş dilimi.
Kurucunun inceleme oturumları yerine başkası geçecek bir korpusa harcanmayacak.

Sizin için sonucu: **pilot için beklediğiniz ~2 milyar tokenlık veri gecikiyor.** Şu an
ölçüyoruz (lisans notu yazıldı: ODC-By 1.0 + Common Crawl şartları, sabit sürüm `c0c06e94…`;
Türkçe dilim 8.578.808 belge, 107,3 GB parquet — büyük kısmı bize gerekmeyen gömme
vektörleri). 1.000 belgelik örnek ölçümü ve hakem okuması sürüyor; sayılar çıkınca ayrı
mektupla yazarız. v5 sigorta olarak kayıtta duruyor.

Bekleyen iki konunuz buna göre değişiyor: `wiki_markup_residue` +150 satırlık örneklem
(v5'in kurallarını ölçüyordu) öncelikten düştü; teslim mektubu FineWeb2-HQ tabanlı sürüm için
gelecek.
