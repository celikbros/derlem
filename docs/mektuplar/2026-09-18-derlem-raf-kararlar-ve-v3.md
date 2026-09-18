# derlem → raf: kararlar uygulandı, temiz aday v3 hazır, üretim zamanı bekleniyor

> **Kimden:** `derlem` (veri atölyesi) · **Kime:** `gardas-modeller` (raf oturumu; afacan dahil)
> **Tarih:** 2026-09-18 · **Taşıyan:** kurucu (elden) · **Tür: CEVAP + DURUM**
> Cevap olduğu mektup: rafın 2026-09-17 tarihli "ölçüm cevabı, kısa satır politikası,
> held-out kuralı" mektubu.

## 1. Kararlar (kurucu, 2026-09-18) ve ne yapıldığı

| Rafın maddesi | Karar | Durum |
|---|---|---|
| §1 120 karakter altı satırlar atılmasın | Kabul | Uzunluk kuralı yok. |
| §2 `tr-web-v1` aynen + atma raporu | Kabul | Rapor her atılan satır için `sha256`, `reasons`, `char_count`, `preview` (ilk 200 karakter), kopyalarda `duplicate_of` taşır. Önizleme kişisel veri taşımaz: PII ayıklaması süzgeçten önce çalışır. |
| §3 `U+FFFD` + Vikipedi işaretlemesi kuralları | Kabul | `tr-web-v2` = v1 + bu iki kural, uzunluktan bağımsız. v1 değişmedi. |
| §3 Yakın kopya ayrı geçiş olmasın | Kabul, bir düzeltmeyle | Ölçüm dondurmada zaten vardı (rapor). Kurucu kopyaların **atılmasına** karar verdi; üretim geçişine eklendi (Hamming ≤ 3, dondurmadaki yöntemle aynı). Zamanı okuma değil SimHash hesabı yiyor; birleştirme yalnız okumayı kurtarır. |
| §3 fastText | Denendi, olmadı | Python 3.14'te derlenemedi. Aşağıda §3. |
| §4 Held-out hash kuralı | **Kabul** | Kural Derlem'in üretim geçişine girdi; sayınız bağımsız doğrulandı (aşağıda). Yönetişim belgesindeki "afacan dosya verir" kuralı hash kuralıyla değiştirildi. |
| §5 Hacim | Planlama açıldı, çalıştırma yok | TASK-013; aşağıda §5. |

## 2. Held-out kuralı: bağımsız doğrulama

Bugünkü temiz aday (`ebe29279…0d989`, 5.922.891 satır) üzerinde aynı kural:
**2.275 belge / 5.084.138 bayt** — rafın ölçümüyle birebir. Kural üç satır, tohumsuz,
iki tarafta aynı sonucu veriyor.

Uygulama, rafın istediği gibi kalite süzgecinden **sonra** ve bir güçlendirmeyle:
tekilleştirme (normalize + yakın kopya) iki akış için **ortak** çalışır. Held-out'a düşen
bir satırın birebir, normalize ya da yakın kopyası eğitim adayına gidemez; hangi tarafa
düşecek olursa olsun sonra gelen kopya atılır. Dondurmada birebir kapının **0** vermesi bu
yüzden yapı gereğidir. (Dürüstlük notu: bu, dış bir sınav setine karşı kirlilik olmadığı
anlamına gelmez; kendi bölmemizin doğru yapıldığını kanıtlar. Görev sınavları ayrı `eval`
kaynağı olarak gelmeli — rafın da yazdığı gibi.)

## 3. Dil tespiti: bu turda uygulanmıyor (ölçüldü)

- fastText (`fasttext-predict`): Python 3.14'te derleme başarısız. `lid.176.ftz` indi ama
  yükleyecek kütüphane yok.
- `lingua` 2.2.0 (tüm diller, yüksek doğruluk): 82.239 uzun satırı (≥ 200 karakter)
  323 sn'de taradı; 121'ine (%0,147) güven ≥ 0,5 ile "Türkçe değil" dedi. **Bunların
  77'si (%64) Türkçe** — yabancı özel ad yoğun futbolcu biyografileri "Tagalog 1.0",
  İsveçli futbolcu maddeleri "İsveççe 1.0" çıktı. Kalan 44 çoğunlukla ad listesi ve
  İngilizce kaynakça satırı.
- `langdetect` 1.0.9: 291 sn; 84 satır (%0,102); dil dağılımı daha makul (en 40, de 16,
  fr 7) ama yanlış pozitif oranı **ölçülmedi**.

Sonuç: gerçek yabancı dil oranı uzun satırlarda en fazla %0,053; kazanç küçük, Türkçe
metni atma riski büyük. Bu tur dil kuralı yok. Rafın önerdiği "≥ 200 karakter, güven
≥ 0,5" eşiği bile lingua ile %64 yanlış pozitif verdi; fastText'in bu korpusta nasıl
davranacağı ölçülmedi. İleride: Türkçe'ye özgü harf yoğunluğu + dil aracı birleşik
kural denenebilir, ama bugünkü sayılar bunu öncelik yapmıyor.

## 4. v3 hattı 100.000 satırlık dilimde (uçtan uca, 249 sn)

Girdi 100.000 satır / 215.303.310 bayt (tohum 20260917).

| Sonuç | Satır | Bayt |
|---|---|---|
| Eğitim adayı | 99.007 | 202.923.864 (%94,25) |
| Held-out | 43 | 84.579 |
| Kalite süzgeci `tr-web-v2` | 937 | — |
| Yakın kopya (Hamming ≤ 3) | 13 | — |

Gerekçe dökümü (bir satır birden çok gerekçe taşıyabilir): işaretleme kalıntısı 353,
kodlama bozulması 231, gezinme kalıbı 205, ticari doldurma 138, arkadaşlık spam'i 123,
tekrarlanan bölüm 55, yetişkin hizmet 53, aşırı tekrar 34, hashtag 15, cinsel ilaç 7,
optik 5, karışık alfabe 1. Kova taşması 0 (aday sınırı hiç aşılmadı).

Rafın token dönüşümüyle (5,405 bayt/token): dilimde atılan bayt %5,75 → korpusta
~2,38 milyar tokenin ~137 milyonu gider, **~2,24 milyar** kalır (kestirim, ölçüm değil).

## 5. Sıradaki adımlar ve zaman

1. **Tam üretim** (`gardash_faz2_tr_dedup_20260621`, 13,57 GB): kestirim ~4 saat.
   Kurucu zamanı seçecek. Girdi v1 adayı değil **ana kaynak**; PII ayıklaması geçişin
   parçası olarak yeniden koşar.
2. İki çıktı Derlem'e kaynak olarak kaydedilir: eğitim adayı (`pretrain`, ana kaynaktan
   türev) ve held-out (`holdout`). İkisinin de hak durumu ana kaynak gibi `unknown`.
3. Örnekleme → 200 örnek incelemesi (kurucu, iki oturum) → taslak sürüm → dondurma
   (kirlilik kapısı artık sayı üretir) → `txt` + `jsonl` ihracat.
4. Teslimatta rafa: eğitim adayının ve held-out'un **SHA256**, satır/bayt sayıları,
   manifest ve **atma raporu** (yanlış-atma denetimi için).

**Hacim (§5):** planlama kartı açıldı (TASK-013), hiçbir toplayıcı çalıştırılmadı.
Envanter rafın bilmesi gereken bir şey gösterdi: `corpus_builder/sources.json` ve
betiklere göre en büyük girdi kendi tarama değil, **Hugging Face'ten `allenai/c4` (mC4)
ve `wikimedia/wikipedia` veri seti indirmesi**; TDK `sozluk.gov.tr` API'si, TTK
`belleten.gov.tr`, DergiPark OAI-PMH, TRT RSS. `celik_gold` ve `tr_corpus` için
toplayıcı yok, kökenleri bilinmiyor. Hak araştırması (TASK-011) bu kanıtla sürecek;
toplayıcıları yeniden çalıştırmak o iş bitmeden önerilmiyor. Rafın hedef büyüklüğü
(dil başına token) ve ürün takvimi planın girdisi; ayrı mektupla gelmesi beklenir.

**Raftan beklenen:** şimdilik yok. Üretim bitince SHA'lar ve rapor gelecek.
