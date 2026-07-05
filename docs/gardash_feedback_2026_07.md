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

## Ek (2026-07-05): Gardash ön koşul sorularına kanıtlı yanıtlar

Gardash'ın frozen release ile istediği dört madde; tüm değerler bugün
artifact'ler üzerinde yeniden doğrulanmıştır.

### 1. 224 satır farkının tam hesabı

Fark tek kaynaktan değil iki ayrı kapıdan gelir; denklem birebir tutar:

| Kalem | Satır |
|---|---:|
| Ham corpus (`gardash_faz2_tr_dedup_20260621`) | 6.027.968 |
| − PII bulgulu satırlar | 104.853 |
| − Normalize document dedup iç tekrarları (NFKC + casefold + whitespace collapse parmak izi eşleşmesi) | 221 |
| − Boyut aşımı belgeler (> `MAX_DOCUMENT_BYTES` = 262.144 byte) | 3 |
| **= Temiz aday** | **5.922.891** |

221 + 3 = 224. İki bağımsız hesap aynı sonucu verir: türetme manifesti
(`clean-candidate-v1`, `removed_duplicate_lines: 221`,
`removed_oversized_lines: 3`) ve ham kaynak üzerindeki fingerprint işi
(`internal_duplicate_count: 221`, `skipped_oversized: 3`).

### 2. Tam SHA256 ve kesin sayılar

- **SHA256 (tam):** `ebe292793d87ec067076bbb86f39801e6ed5fae18761dfcfa3506c4503c0d989`
- **Satır sayısı:** `5.922.891`
- **Byte boyutu:** `12.850.383.067`
- 2026-07-05'te dosya üzerinden yeniden hesaplandı; türetme manifesti ve
  katalogdaki kaynak kaydı (`f63352dd-...`) ile birebir aynı. Dosya içerik
  adresli depoda bu hash anahtarıyla salt-okunur durur; hash aynı zamanda depo
  anahtarı olduğu için sessiz değişim yapısal olarak imkânsızdır.

### 3. LF politikası teyidi

Temiz aday **%100 LF**'dir:

- Türetici her satırı binary modda `UTF-8 + b"\n"` olarak yazar
  (`clean_candidate.py`, satır sonu üretimi tek noktadadır).
- 2026-07-05'te 12,8 GB'lık dosyanın tamamı tarandı: **0 adet CR (`\r`) byte**;
  dosya LF ile biter. Ham Faz 2 zincirindeki CRLF, Derlem'e alınan
  `gardash_tr_dedup.lf.txt` aşamasında zaten normalize edilmişti; türetme bu
  durumu korur.

### 4. ETA ve manifest zinciri

Kritik yol (bu belgenin 1. bölümü): hak/lisans kararı + kanıt girişi (~30 dk,
insan) → 200 örnek toplu inceleme (0,5-1 gün, insan) → kaynak onayı → freeze →
export. **Hak kararının verildiği günden itibaren 1-2 iş günü**; freeze/export
otomatik kısmı saatler mertebesindedir. Frozen release manifest'i
(`derlem.release-manifest.v1`) kaynak snapshot'ında yukarıdaki SHA256'yı ve
gate sonuçlarını zincirler; 224 satırının hesabı türetme manifesti + bu belge
ile lineage'da kalıcıdır. Bekletme Derlem'in otomasyon tarafında olmayacaktır;
tek değişken insan kapısının takvimidir.

## Döngü Durumu (2026-07-05, Gardash bilançosu)

Gardash mühendislerinin teyidiyle üç ekip döngüsünün iletişim ayağı kapandı:

- Gardash → Tamga: saha teyidi gönderildi ✓
- Tamga → Gardash: re-tokenize hazır + 224 satır yakalaması ✓
- Gardash → Derlem: 4 ön koşul soruldu ✓
- Derlem → Gardash: 4/4 kanıtlı cevap ✓

Kalan tek iş iki insan adımıdır: veri yöneticisinin hak/lisans kararı
(+ kanıt referansı) ve moderatörün 200 örnek incelemesi. Sonrası otomatiktir:
freeze → re-tokenize → DGX Spark v1 girdisi (1-2 iş günü). Hak kararını
hızlandırmak için doldurulmaya hazır karar/kanıt şablonu:
[gardash_faz2_rights_decision.md](gardash_faz2_rights_decision.md).
