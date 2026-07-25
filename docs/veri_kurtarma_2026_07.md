# Veri Kurtarma — depo (CAS) restorasyonu, 2026-07-25

**Olay:** 2026-07-16 22:44 civarında `var/` ağacı sıfırlanmış; içerik adresli depo
(`var/storage/objects`) **boşalmıştı** (742 kayıtlı nesnenin 742'si diskte yok, 26,42 GB).
Katalog (PostgreSQL) etkilenmemişti: 12 kaynak, 535 belge, 655 örneklem üyeliği,
**11.910.861 belge parmak izi**, denetim izi ve inceleme hazırlığı olduğu gibi duruyordu.

**Sonuç:** Faz-2 zinciri **bayt-bayt geri getirildi ve doğrulandı.** Hiçbir katalog kaydı
değiştirilmedi; yalnız eksik nesneler, kayıtlardaki SHA256 değerleriyle **kanıtlanarak**
depoya yeniden yerleştirildi. İçerik adresli depoda doğru baytı doğru yola koymak,
hash ile ispatlanabilir bir işlemdir; kimlik değişmediği için kayıtlar kendiliğinden tutarlıdır.

## Yapılan işlem (sırayla)

| # | Adım | Doğrulama |
|---|---|---|
| 1 | Ham seed dosyası, `gardash/scripts/rebuild_faz2_corpus.py` ile 7 ham kaynaktan deterministik yeniden üretildi (kurucu koştu) | `sha256 = 9826d58e…83aa07b5` · 6.027.968 satır · 13.569.773.056 bayt — **kaynak kaydıyla birebir** |
| 2 | Dosya CAS'a yerleştirildi (`objects/sha256/98/26/…`) | kopya sonrası SHA yeniden hesaplandı ✓ |
| 3 | Temiz aday, restore edilen seed'den `clean_candidate` ile yeniden türetildi | `sha256 = ebe29279…03c0d989` · 5.922.891 satır · 12.850.383.067 bayt — **kaynak kaydıyla birebir** |
| 4 | Temiz aday CAS'a yerleştirildi | SHA doğrulandı ✓ |
| 5 | Örneklenen 300 belge nesnesi (200 aktif + 100 superseded), temiz adaydan satır sırasıyla yeniden üretildi (`sample_jobs` tarifi: `strip → _document_from_line → text.encode("utf-8")`) | **300/300 SHA tuttu · 0 uyuşmazlık · 0 bulunamayan** |
| 6 | Depodan okunan belge metinleri denetlendi | karakter sayıları `documents.char_count` ile birebir; Türkçe metin sağlam |

**Bugünkü depo durumu:** 302/742 nesne yerinde (26,42 GB = kayıtlı hacmin ~%100'ü).
Eksik kalan 440 nesnenin tamamı **smoke/test verisidir** (Risk Sampling Smoke 200 belge,
Resample 20, distilasyon/extraction/UI smoke kayıtları). Faz-2 teslimatı için gerekli
nesnelerin **tamamı hazırdır**; smoke artıkları geri getirilmedi (kaynak dosyaları da yok,
üretim değeri yok). Bu bilinçli bir karardır, eksiklik değil.

## Yan bulgu — "224 satır farkı" AÇIKLANDI

`tamga/docs/v3_8_pii_clean_retokenize_readiness.md` ve devir raporunda **çözülmemiş** diye
kayıtlı olan fark bu koşuda ölçümle kapandı:

```
6.027.968 (ham)  −  104.853 (PII satırı)  =  5.923.115  beklenen
gerçek temiz aday                          =  5.922.891
fark                                       =        224
   ├─ removed_duplicate_lines              =        221
   └─ removed_oversized_lines              =          3   (>256 KiB belge)
```

Yani 224 = 221 + 3. Türetim raporu (`var/derived/…manifest.json`) bu üç sayacı ayrı ayrı
yazıyor; ilk koşuda toplanmadığı için açıklanamamış görünüyordu. **Varsayım değil, ölçüm.**

PII dağılımı (yeniden üretim, ilk koşuyla aynı): telefon 114.437 · e-posta 86.435 ·
kart 13.830 · IBAN 2.087 · TCKN 665 bulgu (satır bazında: 52.727 / 50.957 / 10.520 / 1.423 / 362).

## Öğrenilen ders (kayda geçer)

1. **Katalog tek başına yetmez, depo tek başına yetmez.** Yedekleme planı ikisini birlikte
   kapsamalı; bugünkü kurtarma yalnız ham kaynakların OneDrive'da durması sayesinde mümkün oldu.
2. **Determinizm sigortadır.** Zincirin her adımı (rebuild → clean_candidate → sampling)
   deterministik olduğu için kayıp veri "yeniden hesaplanabilir" hale geldi. Bu, tasarım
   tercihi olarak korunmalıdır.
3. `var/` **yedeklenmiyor** olabilir — `.gitignore`'da olması yedekten muaf olduğu anlamına
   gelmemeli. Ayrı bir yedek politikası önerilir (Faz 4 sıraya kayıt).

## Durum: teslimat kapısı

Faz 0'ın tek blokeri değişmedi ve artık **teknik olarak açıktır**:
**200 örneğin moderatör incelemesi (0/200)** — hesap `moderator@derlem.local`,
ön-inceleme raporu hazır (`docs/gardas_ornek_on_inceleme.md`, önerisi "Seçenek A —
pragmatik onay", ~20 dk). İnceleme için gereken 200 aktif belgenin **tam metni artık
erişilebilir** (önizlemeler ortalama 223 karakterle kırpık olduğundan bu şarttı).
