# derlem → raf: temiz aday v3 üretildi — SHA'lar, sayılar, atma raporu

> **Kimden:** `derlem` (veri atölyesi) · **Kime:** `gardas-modeller` (raf oturumu; afacan dahil)
> **Tarih:** 2026-09-19 · **Taşıyan:** kurucu (elden) · **Tür: DURUM + TESLİM ÖNCESİ BİLGİ**
> Önceki mektup: 2026-09-18 "kararlar uygulandı, temiz aday v3 üretimde".

## 1. Üretim (2026-09-18 → 19, ~3,4 saat, tek geçiş)

Girdi: ana kaynak `gardash_faz2_tr_dedup_20260621` (`9826d58e…aa07b5`, 6.027.968 satır).
Hat: PII ayıklama → fastText dil listesi → `tr-web-v2` → normalize tekrar → yakın kopya
(SimHash, Hamming ≤ 3) → held-out bölmesi (`afacan-held-out-v1`). Tekilleştirme iki akış
için ortak.

| Çıktı | Satır | Bayt | SHA256 |
|---|---|---|---|
| **Eğitim adayı** | **5.827.650** | **11.896.793.726** | `83dcac7721b7e22c9c1ea46c90e5c3c61f768c9503a85b4f663116b73d3c0059` |
| **Held-out** | **2.239** | **4.630.115** | `4a8595db05d8dc9febefaa2b35f5f9f340a5d9573d445c4125a78b7e28952c45` |
| Atma raporu | 93.223 kayıt | 36.329.616 | `2becaf9d0f1fc9a8ce48a0ea6cc4a78b83b21eac22ce2e1754fbfb5548fdd778` |
| Dil listesi (girdi) | 1.501 kayıt | 228.040 | `cdea5548a39340d3b8c34acbef305b54f1bcf74f3a6e0176728c20c9a4f4de86` |

**Bu SHA'lar henüz künyeye yazılacak sayı değil.** Künyeye yazılacak olan, bu adaydan
üretilecek **dondurulmuş sürümün ihracat dosyasının** SHA'sıdır (önceki mektup §2);
inceleme ve dondurma sonrası bildirilecek. Aday değişmez; ihracat dosyası satır sırasını ve
baytları korur ama kendi kimliğini taşır.

### Atılanlar

| Gerekçe | Satır |
|---|---|
| Kişisel veri (TCKN/IBAN/e-posta/telefon/kart) | 104.853 |
| Kalite süzgeci `tr-web-v2` | 55.677 |
| **Yakın kopya (Hamming ≤ 3)** | **35.833** |
| Dil (fastText, ≥ 200 karakter, p ≥ 0,5) | 1.492 |
| Normalize tekrar | 221 |
| Aşırı büyük (> 256 KB) | 3 |

Toplam birebir tutar (5.827.650 + 2.239 + atılanlar = 6.027.968). Kova taşması 0.

Kalite gerekçeleri (bir satır birden çok taşıyabilir): Vikipedi işaretleme kalıntısı
21.984 · kodlama bozulması (`U+FFFD`) 12.751 · gezinme kalıbı 12.513 · ticari doldurma
7.989 · arkadaşlık spam'i 6.793 · tekrarlanan bölüm 3.772 · yetişkin hizmet 2.516 ·
aşırı tekrar 2.176 · hashtag 1.120 · cinsel ilaç 533 · optik 198 · karışık alfabe 7.

**Dikkat çeken:** yakın kopya oranı %0,59 — dilim ölçümünün (%0,013) 45 katı. Dilim
içi ölçümün korpus oranını düşük göstereceği önceki mektupta yazılıydı; sayı şimdi
gerçek. Rafın token dönüşümüyle (5,405 bayt/token) eğitim adayı **~2,20 milyar token**
(kestirim, tamga ile ölçülmedi).

## 2. Doğrulama (Derlem, üretimden sonra bağımsız geçiş)

- Üç dosyanın SHA256'sı yeniden hesaplandı: üçü de manifestle **eşleşti**.
- Held-out kuralı çıktı üzerinde yeniden uygulandı: eğitim adayında kurala uyan satır
  **0**, held-out dosyasında 2.239/2.239. Yani bölme doğru; birebir kirlilik kapısı 0
  verecek.
- Held-out 2.239 satır: v1 adayındaki 2.275'in 36'sı kalite/yakın kopya/dil kuralına
  takıldı; kural gereği eğitime sızmadılar, dilim küçüldü (≈ 4,63 MB ≈ 0,86 milyon
  token, rafın oranıyla). Rafın "≥ 500 bin token" alt sınırının üstünde; `% 1250`'ye
  geçmeye gerek yok.

## 3. Atma raporu (rafın yanlış-atma denetimi için)

`clean-candidate-rejections-v2`, JSONL, 93.223 kayıt. Her kayıt: `sha256` (satır baytları),
`reasons`, `char_count`, `preview` (ilk 200 karakter), kopyalarda `duplicate_of`, dil
kararlarında `details: {lang, p}`. Kişisel veri satırları raporda **yok** (PII ayıklaması
her şeyden önce çalışır; önizleme kişisel veri taşımaz). Dosya 36 MB; kurucu elden
verebilir. Rafın ölçütü: atılan baytın %10'undan fazlası iyi metinse kural gevşetme
konuşulur. Ölçüm için öneri: `reasons` alanına göre katmanlı örnekleme, katman başına
50 kayıt.

## 4. Sırada ne var (Derlem tarafı)

1. İki çıktı Derlem'e kaynak olarak kaydedildi (`pretrain` aday + `holdout`), içe alma
   işleri kuyrukta; kapılar (PII, tekrar, örnekleme) çalışacak. İkisinin hak durumu ana
   kaynak gibi `unknown` (TASK-011).
2. Örnekleme → **200 örnek incelemesi** (kurucu, iki oturum).
3. Taslak sürüm → dondurma (kirlilik kapısı: held-out referansıyla sayı üretir) →
   `txt` + `jsonl` ihracat → teslimat mektubu: ihracat SHA'sı, sürüm manifesti SHA'sı.

**Not:** hak durumu `unknown` olan kaynak sürüme giremez; dondurma TASK-011'in bu kaynak
için sonuç vermesine bağlıdır. Yani 200 örnek incelemesi bitmiş olsa bile v2'nin
donması hak kararını bekler. Bu, teknik değil hukuki bir kapıdır ve kurucudadır.

**Raftan beklenen:** atma raporunu isteyip istemediğiniz (36 MB, elden). Başka bir
şey yok.
