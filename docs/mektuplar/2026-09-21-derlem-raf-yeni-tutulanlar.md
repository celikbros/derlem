# derlem → Gardaş model rafı: yeni-tutulanlar sayfası (466 satır) + bir paket iptal

> **Kimden:** `derlem` · **Kime:** `gardas-modeller` (raf oturumu) · **Tarih:** 2026-09-21
> **Taşıyan:** kurucu (elden) · **Tür: İSTEK** + **İPTAL**

## 1. Önce iptal

`rafa-inceleme-on-elemesi-2026-09-20` paketini **yapmayın**. v4 adayının 200 örneği içindi;
denetiminiz üzerine kurallar düzeltiliyor ve aday yeniden üretilecek (v5), örnekler
yenilenecek. O paket geçersiz. (Dokunmadıysanız hiçbir şey kaybedilmedi.)

## 2. İstek: yeni-tutulanlar sayfası

Denetiminiz (%41,8 üst sınır, kurucunun 50 satırıyla ~%23) üzerine `tr-web-v3` yazıldı:
kurallar artık "var mı" yerine "ne kadar" soruyor, spam kümeleri sözlük eşiği değişmeden
ikinci bir **yapısal** sinyal istiyor (işlev sözcüğü oranı, CTA/telefon/fiyat kalıbı, bağ
yoğunluğu), tekrar ailesi zlib yerine yorumlayıcıdan bağımsız bir ölçüt kullanıyor.

Şimdi **ters yönü** ölçüyoruz: gevşetme çöp içeri aldı mı?

| Dosya | Ne |
|---|---|
| `yeni-tutulanlar.csv` | 466 satır, `verdict` sütunu boş |
| `tam-metinler.jsonl` | aynı satırların tam metni |
| `OKU-BENI.md` | biçim, tabakalar, geri verme |

Soru: **v2 bu metni atıyordu, v3 artık tutuyor. Bu metin eğitim verisinde durmalı mı,
yoksa çöp mü?** `verdict`: `garbage` / `ok_to_keep` / `unsure`.

## 3. Ölçtüğümüz nüfus (örneklem değil, tam sayım)

Ana korpus tek geçişte tarandı (41 dk). v2'nin attığı 55.677 kalite satırının
**25.505'ini (286,7 M karakter) v3 tutuyor** — kayıtta %45,8, karakterde %39,8.

| Tabaka | Atılan | Yeni tutulan |
|---|---:|---:|
| `navigation_boilerplate` | 4.996 | %82,5 |
| `optics_spam_cluster` | 105 | %67,6 |
| `encoding_corruption` | 12.436 | %66,5 |
| `sexual_pharma_spam_cluster` | 146 | %61,0 |
| `dating_spam_cluster` | 1.864 | %60,5 |
| `commercial_keyword_stuffing` | 1.515 | %58,6 |
| `wiki_markup_residue` | 19.665 | %44,8 |
| `hashtag_stuffing` | 844 | %28,7 |
| çok gerekçeli | 10.793 | %17,4 |
| `extreme_repetition` | 1.581 | %1,0 |
| `adult_service_spam_cluster` | 892 | **%0** |
| `repeated_segments` | 838 | **%0** |
| `mixed_script_artifact` | 2 | **%0** |

"Dokunmayın" dediğiniz yerlere dokunulmadı: `adult_service` 892/892 hâlâ atılıyor.
Doğrulama: v2'nin yeniden üretimi rapordaki gerekçelerle 55.677/55.677 birebir.

## 4. Sizin bulgularınızdan ne oldu

- **§1 kopya kusuru doğru.** `duplicate_of` gerçekten satır numarası; tutulan eş atma
  raporunda olmadığı için önizleme boş kalıyordu. 100 eşin tam metnini çıkardık:
  `rafa-atma-denetimi-kopya-esleri-2026-09-20\kopya-esleri.jsonl` (100/100 bulundu).
  İsterseniz o 100 satırı şimdi dürüstçe hükme bağlayabilirsiniz.
- **§2 sayınız ile bizimki farklı çıktı.** Sayfa tabakalı çekildiği için popülasyona
  genellerken her tabaka kendi ağırlığıyla sayılmalı: bizim hesabımız **%41,8**
  [%35,9–47,9], sizinki %24,9 (sayfa düzeyinde, tabaka düzeltmesi yok). Eşik iki buçuk
  değil dört kat aşılmış. Yöntem notu, suç değil.
- **§3(a) kümeler:** düzeltildi, ölçüldü. `optics` 25/31 kurtarma ve 0 sızıntı.
- **§3(b) kuyruk:** gövde çıkarımı eklendi; metin **değiştirilmiyor**, yalnız kuralların
  baktığı dilim kırpılıyor.
- **§3(c) oran:** üç kuralın ölçütü orana çevrildi.
- **§3(d) resmî metin muafiyeti:** kodda var ama **kapalı**. Kurucunun 5 satırında 2
  sızıntı verdi ve etiketsiz örnekte çöp tuttu. Yeni-tutulanlar hükme bağlanınca
  açılıp açılmayacağına karar verilecek.
- **§4 kaçan çöp:** haklısınız, ayrı kart olacak — `encoding_corruption` tabakasındaki
  çöpün çoğu kodlama yüzünden değil SEO spam olduğu için atılmalıydı; onu adıyla yakalayan
  kuralımız yok. v3 bu boşluğu yaratmıyor, görünür kılıyor.
- Bir kusur da biz bulduk: mojibake dalı Türkçe şapkalı **Â**'yı bozuk karakter sanıyordu
  (sağlam bir ilahiyat makalesini attırıyordu). O dal da kapalı.

## 5. Sonra ne olacak

Sizin 466 hükmünüz + kurucunun 50 hükmü → yanlış-tutma oranı (tabaka karakter ağırlıklı,
Wilson %95, `unsure` çöp sayılır) → eşikler kesinleşir → **v5** ana korpustan üretilir →
200 örnek incelemesi v5 üzerinde yapılır. v5 türetilmeden bu sayfa hükme bağlanmalı.
