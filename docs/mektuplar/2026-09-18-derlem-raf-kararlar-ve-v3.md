# derlem → raf: kararlar uygulandı, temiz aday v3 üretimde

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
| §3 fastText | **Kabul** | 3.14'te derlenemedi, 3.13'te kuruldu; ölçüm ve kural aşağıda §3. |
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

## 3. Dil tespiti: fastText ile uygulanıyor (güncellendi, aynı gün)

İlk denemede `fasttext-predict` Python 3.14'te derlenemedi; **Python 3.13 ile kuruldu ve
çalışıyor.** Aynı 82.239 uzun satırda (≥ 200 karakter) ölçüm:

| Araç | Süre | "Türkçe değil" (güven ≥ 0,5) | Bunların Türkçe olanı |
|---|---|---|---|
| lingua 2.2.0 (tüm diller) | 323 sn | 121 (%0,147) | 77 (%64) — yabancı adlı futbolcu biyografileri "Tagalog 1.0" |
| langdetect 1.0.9 | 291 sn | 84 (%0,102) | ölçülmedi |
| **fastText lid.176.ftz** | **23 sn** | **30 (%0,036)** | ~7 (%23), çoğu gerçekten karışık dilli |

Rafın kuralı (≥ 200 karakter, p ≥ 0,5) fastText ile **kabul edildi ve bu üretime girdi.**
Proje ortamı Python 3.14 olduğu için dil kararı dışarıda (3.13) hesaplanır ve üretime
atılacak-satır listesi olarak verilir; listenin SHA256'sı ve yöntemi manifeste yazılır,
atılan satırlar raporda `language_not_turkish` + `{lang, p}` ile görünür. Dil kuralsız
başlamış olan ilk üretim durduruldu, listeyle yeniden başlatıldı.

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

1. **Tam üretim** (`gardash_faz2_tr_dedup_20260621`, 13,57 GB): 2026-09-18'de
   başlatıldı, kestirim ~4 saat. Girdi v1 adayı değil **ana kaynak**; PII ayıklaması
   geçişin parçası olarak yeniden koşar. Dil listesi (fastText, ~25 dk) üretimden önce
   ana kaynak üzerinde hesaplandı.
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
