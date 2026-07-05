# Gardash LLM Ekibi Geri Bildirimi ve Derlem Yanıtı

**Tarih:** 2026-07-05
**Kaynak:** Gardash LLM ekibi → Derlem veri ekibi (3 madde)
**Durum:** Yanıtlandı; taahhütler aşağıda.

Bu belge, Derlem'in ilk gerçek tüketici geri bildirimini denetlenebilir kayda
alır. Ölçülmüş sonuçlar release değerlendirmelerinde kanıt olarak kullanılır.

## 1. PII bulgusu ve release kapanış sorusu

**Gardash bildirimi:** Ham seed'deki 104.853 satırlık PII bulguları Gardash
tarafında "Spark öncesi re-tokenize" kararına dönüştü; egemen model vatandaş
PII'siyle eğitilmeyecek. Kritik soru: review kapıları + frozen release +
manifest ne zaman kapanır? Spark takvimi buna kilitli.

**Derlem yanıtı — kapanış kritik yolu:**

Teknik hat hazır ve doğrulanmış durumda; kalan işlerin tamamı insan kararıdır.
Hedef kaynak: `gardash_faz2_tr_dedup_20260621_clean_candidate_20260625`
(`f63352dd-...`, 5.922.891 belge; PII `clear`, exact/normalize dedup `unique`,
200 örnek hazır).

| # | Adım | Sorumlu | Süre | Not |
|---|---|---|---|---|
| 1 | Hak/lisans kararı + kanıt referansı girişi | Veri yöneticisi | ~30 dk | Corpus'un derlenme kaynağına göre `cleared/restricted` kararı; kanıt dosyası referansı zorunlu |
| 2 | 200 örneğin incelenmesi (bulk review destekli) | Moderatör/uzman | 0,5-1 gün | Tek oturumda 200'e kadar atomik toplu karar; self-review engeli geçerli |
| 3 | Kaynak onayı | Moderatör | dakikalar | Tüm kapılar temizse tek karar |
| 4 | Release draft + freeze | Admin | dakikalar | Freeze kapıları yeniden koşar + eval/holdout dekontaminasyonu |
| 5 | JSONL/TXT export + manifest | Otomatik | dosya boyutuna bağlı saatler | Deterministik; SHA256 manifest'le teslim |

**Taahhüt:** 1. adımdaki hak kararı verildiği gün, kapanış toplamda **1-2 iş
günüdür**. Bloklayan tek şey takvim değil karardır; Spark planlaması bu
varsayımla yapılabilir. Adım adım operatör kılavuzu:
[Hızlı Başlangıç](hizli_baslangic.md).

## 2. Ölçülmüş kalite sinyali (kayda alındı)

**Gardash bildirimi:** 130M parametre koşusunda Derlem corpus'uyla sıfır
overfit + akıcı sözdizimi gözlendi; "kalite > hacim" kapıları çalışıyor.
Dürüst zayıflık: bilgi tabanı şans seviyesinde (TurkishMMLU %25,4) — sebep
veri azlığı, kalitesizlik değil.

**Derlem kaydı:**

- Bu, Derlem çıktısının ilk ölçülmüş tüketici doğrulamasıdır: kalite kapıları
  (PII, dedup, örneklem incelemesi, dekontaminasyon) eğitim tarafında
  gözlemlenebilir fayda üretti.
- TurkishMMLU %25,4 bulgusu bir kalite regresyonu değil **hacim sinyalidir**;
  doğrudan v2 alım planının gerekçesidir (madde 3).
- Faz-4 sonrası TurkishMMLU ölçümü, v2 release'lerinin başarı metriği olarak
  [v2 alım planına](v2_intake_plan.md) hedef diye işlenmiştir.

## 3. v2 hazırlığı paralel başlıyor

**Gardash bildirimi:** Spark GPU'yu meşgul ederken CPU/disk işi olan
FineWeb-2 / CulturaX / HPLT TR (30-100B token) filtreleme + sentetik TR
ders-kitabı korpusu planı Derlem'le birlikte kurgulanmalı.

**Derlem yanıtı:** Plan yazıldı ve yürürlükte: [v2 Alım Planı](v2_intake_plan.md).
Özet: üç web-ölçekli aday kaynağın lisans/hak ön değerlendirmesi yapıldı,
Derlem kapılarına eşlenmesi ve kapasite boşlukları (çok parçalı kaynak,
Parquet paketleme, disk planı) belirlendi; sentetik korpus için köken
etiketleme tasarımı v0.5 kapsamına bağlandı. TurkishMMLU, v2 release'lerinin
kabul metriğidir.

## İzleme

- Kapanış kritik yolu adım 1 kararı: bekliyor (veri yöneticisi).
- v2 planındaki faz 0 işleri: başlatılabilir; GPU gerektirmez.
- Bu belge append-only kültürle uyumludur: sonraki gelişmeler yeni tarihli
  bölüm olarak eklenir, mevcut kayıt değiştirilmez.
