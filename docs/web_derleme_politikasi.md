# Genel Web Derleme Hak Politikası (kalıcı, sınıf bazında karar)

**Tarih:** 2026-07-07
**Kapsam:** Ekibimizce crawl'lanmış **genel web metni** sınıfının tamamı.
**İlke:** Hak kararı kaynak başına değil, veri SINIFI başına bir kez verilir.
Bu politika bir kez onaylandıktan sonra, sınıfa giren her yeni kaynak için
ayrı hukuki değerlendirme YAPILMAZ; kaynak kaydında yalnız bu politikaya
referans verilir.

## Sınıf tanımı — bu politika neyi kapsar?

Kapsar:

- Ekibimizin kendi araçlarıyla crawl'ladığı, halka açık Türkçe (veya çok
  dilli) web sayfası metinleri.
- Bu sınıftan türetilmiş temizlenmiş/tekilleştirilmiş adaylar.
- FineWeb-2, HPLT gibi izinli lisanslı hazır web derlemeleri (kendi
  lisans kanıtlarıyla birlikte).

**Kapsamaz — bunlar her zaman ayrı, bireysel karar ister:**

- Kitaplar, gazete/dergi arşivleri, akademik yayınlar.
- Satın alınmış veya sözleşmeyle edinilmiş veri setleri.
- Login/paywall arkasından alınmış içerik.
- Kişisel mesajlaşma/e-posta benzeri özel iletişim verisi.
- CulturaX gibi lisans kapsamı belirsiz hazır derlemeler.

## Karar

Bu sınıftaki veri, aşağıdaki kalıcı koşullarla **eğitim kullanımı için
temizdir (`cleared`)**:

1. Yalnız kendi LLM/tokenizer eğitimimizde kullanılır; ham metin üçüncü
   taraflara yeniden dağıtılmaz (Derlem'in `consumer_team` sınırı bunu uygular).
2. Her kaynak Derlem'in PII kapısından geçer; PII bulgulu satırlar release'e
   giremez.
3. Takedown/silme talepleri v1.0 politikası uyarınca işlenir; düzeltme yeni
   release olarak çıkar.
4. Web verisiyle model eğitiminin Türk hukukunda açık istisnası olmadığı
   bilinir; bu karar sektör standardı pratiğe dayalı bilinçli bir risk
   kabulüdür.

## Kaynak kaydında uygulama (kaynak başına ~10 saniye)

| Alan | Değer |
|---|---|
| Hak durumu | `Temizlendi` |
| Lisans | `kendi-derleme-web-tr` (hazır derlemede kendi lisansı, ör. `odc-by-1.0`) |
| Lisans kanıtı | `docs/web_derleme_politikasi.md` |

Hepsi bu. Ayrı belge, ayrı değerlendirme, ayrı imza yok.

## Politika onayı (bir kez doldurulur)

- Onaylayan ad / rol: **Celikbros** (proje sahibi)
- Tarih: **2026-07-07**
- Teyit: "Sınıf tanımını ve karar koşullarını okudum; bu politika ekibimizin
  crawl'ladığı genel web verisi sınıfı için kalıcı hak kararımızdır."
  — Onay, 2026-07-07 tarihli yazılı "Onaylıyorum — Celikbros" beyanıyla verildi.

Politika değişirse yeni tarihli sürüm eklenir; eski kayıtlar dokunulmaz.
