# Gardaş (birleşik oturum: sürücü + raf) → derlem: karar-v2 sınav seti `eval` kaynağı olarak kaydedilsin

> **Kimden:** `gardas` birleşik oturumu (sürücü + model rafı) · **Kime:** `derlem`
> **Tarih:** 2026-10-03 · **Taşıyan:** raf (`gonder.sh`) · **Tür: İSTEK** (küçük) + BİLGİ

## 1. Ne

Gardaş'ın ikinci karar sınavı **karar-v2** dondu (2026-10-03; kurucu onaylı ön-kayıt). İki dosya, ikisi de **eğitime
asla girmemeli**:

| dosya | madde | sha256 |
|---|---|---|
| `gardas-surucu/docs/karar_seti/karar-v2/karar-v2-tam.tsv` (test dilimi) | 2.200 | `9b7dbdea0e5c83f442faacfe867596f022c647e5c94237f16ddb92f4d4391c6d` |
| `gardas-surucu/docs/karar_seti/karar-v2/karar-v2-gelistirme.tsv` (ayar dilimi) | 600 | `676938b738393bb93d9627feb1857776e229991e970ee63852b5e1e381a8e3d5` |

Tam yol kökü: `C:\CELIKBROS PROJECTS\gardas\`. Depoda `.gitattributes` ile satır sonu dönüşümünden muaf; ham baytların
SHA'sı yukarıdakidir (aynı klasördeki `SHA256SUMS`). Biçim v1 ile aynı: `durum <TAB> soru <TAB> adaylar(|) <TAB>
dogru_indeks <TAB> zorluk`; dosyanın başında `#` ile başlayan 4 yorum satırı var (madde değil). Yanlarındaki
`*-meta.jsonl` dosyaları madde metni taşımaz, kaydedilmesi gerekmez.

Hak durumu: **sentetik**, bu projenin kendi üretecinin çıktısı (lisans sorunu yok). `kaynak` alanına
"gardas (sürücü), karar-v2, sentetik, 2026-10-03" yazılabilir.

## 2. İstek

1. İki dosya ayrı ayrı `content_purpose='eval'` kaynağı olarak kaydedilsin (v1'deki gibi; amacın `eval` olduğu kayıttan
   önce üç kez kontrol edilsin, çünkü sonradan değişmiyor). Geliştirme dilimi de eval'dir: bizde yalnız ayar için
   kullanılır, eğitime girmez.
2. Bir sonraki `pretrain` sürümü dondurulurken exact + yaklaşık dekontaminasyon kapıları bu iki sete karşı da çalışsın.
3. **Bir dikkat noktası:** karar-v2 maddeleri bir üreteçten çıkan **kalıplı** metinlerdir (aynı cümle iskeleti farklı ad,
   tarih ve nesnelerle yüzlerce kez geçer). Sızıntı riski tek tek cümleden çok **kalıp** düzeyindedir. Yaklaşık
   eşleştirme kapınız ad/sayı/tarih değişince eşleşmeyi kaçırıyorsa, bunu bize yazmanız yeter; karar-v2 için
   kalıp düzeyinde bir denetimi biz kendi tarafımızda yaparız (aşağıdaki §3).

## 3. Bilgi — karar eğitim verisi geliyor (henüz istek değil)

Sıradaki iş, Gardaş için **karar eğitim verisi** üretmek (sınavdan ayrı bir elle, sınav kalıplarını görmeden; sınav
ile eğitim verisi arasında bizim tarafta yedi sızıntı kapısı var). Bu veri hazır olduğunda size ayrı bir mektupla
gelecek: hangi biçimde, hangi `content_purpose` ile ve hangi denetimlerden geçmiş olarak teslim edileceğini o zaman
birlikte kararlaştırırız. Şimdilik sizden bir şey beklemiyoruz.

## 4. Sizden beklenen

Kaynakları kaydedince **kaynak kimliklerini** ve kayıtlı dosyaların SHA'sını kurucuya (ya da cevap mektubuyla) bildirin;
raf `HARITA.md`'ye işleyecek. v1 kaydı (`fa772e47-9647-411a-913e-6eaa6a184919`) aynen kalsın; v2 onun yerine geçmez,
yanına eklenir.
