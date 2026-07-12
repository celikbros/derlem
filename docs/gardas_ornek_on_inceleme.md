# Gardas Temiz Adayı — 200 Örnek Ön-İnceleme Raporu (Claude)

**Tarih:** 2026-07-12
**Kaynak:** `gardash_faz2_tr_dedup_20260621_clean_candidate_20260625` (f63352dd)
**Nitelik:** Bu bir ÖN-inceleme raporudur; makine analizi + Claude okuması.
Nihai karar insanındır (moderator). Bu rapor, insan incelemesini 1-2 saatten
~20 dakikaya indirmek için hazırlanmıştır.

## Yöntem

1. 200 örneğin **tamamının tam metni** API'den çekildi.
2. Otomatik analiz (200/200): uzunluk, kontrol karakteri, Türkçe karakter
   varlığı, tekrar deseni, büyük harf/rakam/sembol oranları.
3. **Claude okuması (66/200):** bayraklanan 46 belge + temsili 20 belge
   bizzat okundu ve kalite değerlendirmesi yapıldı.

## Otomatik bulgular (200/200) — çok temiz

| Kontrol | Sonuç |
|---|---|
| Encoding / kontrol karakteri | **0 sorun** |
| Yabancı dilde belge | **0** (hepsinde Türkçe karakter var) |
| Uzunluk | min 53, medyan 5.363, maks 159.396 karakter |
| Aykırılık | 10 çok kısa (<80 kr), 34 çok uzun (>20K kr) — kusur değil, uyarı |

## Okuma bulguları (66 belge) — gerçek sorunlar burada

**İyi haber:** Okunan belgelerin çoğunluğu kaliteli Türkçe: ansiklopedik
madde (Messi, Mısır mitolojisi, Asur kolonileri), ders özeti (infaz hukuku,
biyel mekaniği, bilgisayar aritmetiği), haber metni, köşe yazısı, mevzuat,
forum konuşması (doğal dil değeri var). 10 "çok kısa" belgenin hepsi temiz
tek cümleler (köy/ansiklopedi tanımları) — kusurlu değil.

**Kötü haber — sorunlu belgeler (~15 adet, okunanların ~%23'ü):**

| Tür | Ordinal örnekleri | Sorun |
|---|---|---|
| SEO/keyword spam | 951612, 4370196, 4376871, 4377120, 4377565, 4378486, 4379804, 4382098, 4395538 | "arkadaşlık sitesi / sohbet / dürbün kamera" tarzı anahtar-kelime yığını; cümle bütünlüğü yok |
| Yetişkin içerik + spam | **4369906** (İzmir escort, 133K kr), **645741** (cinsel sağlık ilaç spam'i, 157K kr) | 645741 ayrıca **bozuk karakter** içeriyor: Kiril "з" harfi ("ilaзlari") ve soft-hyphen kalıntıları |
| Örneklem İÇİ tekrar | **1040293 ≈ 4369844** | Aynı Instagram hashtag spam'i iki ayrı belge olarak (near-duplicate; exact-dedup yakalayamaz çünkü birebir aynı değil) |
| Site navigasyon dökümü | 4382863, 4387794, 4388325 | Facebook istatistik/haber portal menü dökümleri; düşük bilgi değeri |

**Önemli istatistik dürüstlüğü:** Bu örneklem **risk-ağırlıklıdır** (200'ün
115'i bilinçli olarak riskli belgelerden seçildi). Yani ~%23'lük sorun oranı
corpus genelini DEĞİL, en şüpheli dilimi temsil eder; corpus genelinde oran
belirgin şekilde düşüktür. Ayrıca Gardash'ın 130M koşusu bu veriyle "sıfır
overfit + akıcı sözdizimi" ölçmüştü — veri pratik olarak işe yaramıştır.

## Karar seçenekleri (moderatöre)

**Seçenek A — Pragmatik onay (önerilen):** 200 örneğin tamamını toplu onayla,
kaynak onayını ver; karar gerekçesine bu raporu referans göster. Gerekçe:
web-ölçekli pretrain corpus'unda bu gürültü payı sektör normalidir (FineWeb
ham hâli daha kirlidir); örneklem risk-ağırlıklıdır; spam filtresi v2 alım
hattının işidir (plan hazır). Süre: ~20 dk.

**Seçenek B — Titiz yol:** ~15 sorunlu belgeyi belge düzeyinde reddet. Bu,
kaynak onayını bloklar (kural: tüm örnekler onaylı olmalı) → spam/URL
filtreli `clean_candidate v2` türetmesi → yeni kaynak → yeni örneklem →
yeniden inceleme. Süre: günler. DGX geciktiği için zaman var; ama v2 web
alımında zaten daha güçlü filtre kurulacağından emek kısmen mükerrer olur.

## Moderatörün 20 dakikalık akışı (Seçenek A)

1. Bu raporu oku (5 dk).
2. Arayüzde şu belgelere göz at (ordinal ile ara): 645741, 951612, 4369906,
   1040293 — sorun tespitimi kendi gözünle doğrula (10 dk).
3. İnceleme ekranı → tümünü seç → toplu onay; gerekçe alanına:
   "Ön-inceleme raporu (docs/gardas_ornek_on_inceleme.md) okundu; spot
   kontrol yapıldı; web-corpus gürültü payı kabul edildi" (5 dk).
4. Kaynak onayını ver.

Sonrası otomatik: draft → freeze → export → teslim paketi (Claude koşturur).
