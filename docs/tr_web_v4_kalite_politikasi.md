# `tr-web-v4` kalite politikası — makine çevirisi ve ticari sayfa

**Tarih:** 2026-10-13 · **Görev:** [TASK-046](gorevler/TASK-046-machine-translation-and-commercial-page-rules.md) ·
**Durum:** kodda ve testte; hedefler kurucu onayı bekliyor, hakem yeniden koşusu bekliyor ·
**Ölçüm:** `var/olcum-2026-10-13/task-046/RAPOR.md`

## 1. Ne değişti

`tr-web-v4` = `tr-web-v3` + iki yeni gerekçe:

| Gerekçe | Ne yakalar | Modül |
|---|---|---|
| `machine_translation` | makine çevirisi / çeviri çiftliği (Rusça, İngilizce, Almanca … kaynaktan otomatik Türkçe) | `worker/src/derlem_worker/machine_translation.py` |
| `commercial_page` | ürün kartı, fiyat listesi, satış çağrısı, sponsor etiketi, mağaza gezinti izi, mahalle × hizmet şablonu | `worker/src/derlem_worker/commercial_page.py` |

- **v3 hükümleri dondurulmuştur.** `quality_v4.py` v3'ün kod yolunu aynen çağırır, yalnız iki
  gerekçe ekler; gerekçe sırası v3'ün sırası + `machine_translation`, `commercial_page`. Aynı
  girdi için v4'ün v3'e ait gerekçeleri v3'ünkiyle birebir aynıdır: testle sabit
  (`worker/tests/test_quality_v4.py`), etiketli 1.400 metinde 0 fark, tam alımdan 210.000
  belgelik örneklemde 0 fark.
- **Kurallar yapısaldır, konusal değil.** Hangi konuda yazıldığına bakmaz; metnin *nasıl*
  yazıldığına (çeviri kalıpları, satış sayfası biçimi) ve *nereden* geldiğine (adres) bakar.
- **Tam metin üzerinde çalışır**, gövde (`body()`) üzerinde değil — rafın kuralı: "metin
  kurtarılmak için kırpılmak zorundaysa çöptür".
- **`url`** ortak belge kaydının (`derlem.document.v1`) `provenance.url`'sidir. Yalnız v4 okur;
  v1–v3 yok sayar. URL'si olmayan kaynakta (v5 gibi) çeviri kuralı yalnız içerik sinyalleriyle
  çalışır: zayıflar ama yanlış atma artmaz (v5'in `kalsın` satırlarında 1/103).
- Tüm eşikler **tamsayı karşılaştırmasıdır** (belirlenimcilik, TASK-039 ilkesi).

## 2. `machine_translation`

### 2.1 Sinyaller

| Sinyal | Tanım | Kaynak |
|---|---|---|
| URL: `host_tr` | ana makine `tr.` ile başlıyor (`tr.topwar.ru`, `tr.eferrit.com`) | adres |
| URL: `path_tr` | yolda `tr` dil kesimi (`/tr/`, `/tr-tr/`) ya da `?hl=tr`, `?lang=tr` | adres |
| URL: `foreign_cctld` | 2 harfli ülke uzantısı, `tr` değil ve genel kullanımlılar (`co io tv me cc ws fm ly gg tc az cy`) değil | adres |
| İşlev profili | (kopya kalıp − doğal bağlama) / sözcük, binde | metin |
| `"Bu,"` çalkası | cümle başında `Bu,` (İngilizce "This," kalıbı) | metin |
| Kiril kalıntısı | ≥ 3 Kiril harf ve harflerin %5'inden az | metin |

Wikimedia projeleri (`tr.wikipedia.org` …) URL imzasından muaftır: topluluk yazımı, dil alt alanı
çeviri imzası değil.

**İşlev profili sözlükleri etiketli satırlardan türetildi** (ana örneğin 1.000 belgesi,
MT-pozitif ile MT-olmayan belge frekansı log-oranı, büyük harfle yazılma payı ≥ %30 olan özel
adlar otomatik dışarıda). İki ucun en güçlü 60'ar öğesinden yalnız dilbilgisel olanlar tutuldu:

- **Kopya kalıplar (29):** `sahiptir`, `olacaktır`, `aşağıdaki`, `dahil`, `sağlar`, `içerir`,
  `onları`, `bunları`, `olduğundan`, `belirli`, `yalnızca`, `çeşitli`, `tamamen`, `gerçekten`,
  `anlamına`, `izin` … ("have", "will be", "the following", "including", "provides" …)
- **Doğal bağlama (20):** `ise`, `diye`, `kendisine`, `içerisinde`, `ederek`, `şöyle`, `adlı`,
  `yaptığı`, `üzerine`, `yönelik`, `yandan` … (çeviri bunları neredeyse hiç kullanmıyor)

Ad ve konu sözcükleri (`bahis`, `satış`, `istanbul`, `türkiye`) listeye bilerek alınmadı.

### 2.2 Karar

```
machine_translation =
      (URL imzası  VE  (profil ≥ −4‰  VEYA  "Bu,"  VEYA  Kiril kalıntısı))
  VEYA (profil ≥ 20‰)                       -- URL'siz, güçlü
  VEYA ("Bu,"  VE  profil ≥ 10‰)            -- URL'siz, çalka + profil
profil yalnız ≥ 75 sözcüklük belgede kullanılır
```

URL tek başına **yetmez**: etiketli satırlarda URL imzalı 195 belgenin 106'sı göz okumasında
çeviri sayılmadı (`tr.motorsport.com`, `dw.com/tr`, `support.microsoft.com/tr-tr` …). Teyit
eşiği düşüktür (−4‰): URL imzalı belgeyi yalnız açıkça doğal Türkçe bağlama kullanıyorsa tutar.

### 2.3 Ölçüm (etiketli satırlar)

Etiketler: göz işaretleri (1.200 FineWeb2-HQ belgesinde 107 — **yalnız URL'si şüpheli 269 aday
okundu**), hakem hükümleri (HQ 200 + karma 100; gerekçesinde "çeviri" geçen `çöp` = 25), v5
hakemi (200). Yanlış-atma kümesi: hakemin `kalsın` dediği satırlar.

| | göz MT (107) | hakem MT (25) | birleşik (119) | kontrol örneği MT (26)¹ | HQ `kalsın` (122) | v5 `kalsın` (103) |
|---|---:|---:|---:|---:|---:|---:|
| URL imzası (herhangi) | %83,2 | %44,0 | %74,8 | %80,8 | %9,8 | — |
| profil ≥ 20‰ | %17,8 | %24,0 | %17,6 | %11,5 | %0,0 | %1,0 |
| "Bu," ∧ profil ≥ 10‰ | %13,1 | %20,0 | %14,3 | %11,5 | %0,0 | %0,0 |
| Kiril kalıntısı | %2,8 | %4,0 | %2,5 | %3,8 | %0,0 | %0,0 |
| **Kural** | **%83,2** | **%64,0** | **%78,2** | **%73,1** | **%4,9** (6) | **%1,0** (1) |

¹ Profil sözlükleri ana örnekten türetildi; kontrol örneği türetmeye girmedi (bağımsız sınama).

**Geçici hedef (recall ≥ %80, `kalsın`'da yanlış atma ≤ %5) tam tutmuyor:** yanlış atma tavanı
tutuyor (%4,9); recall göz işaretlerinde %83, birleşik kümede %78, ama yansız kümelerde
(hakem-MT %64, kontrol %73) %80'in altında. Göz işaretlerinin recall'u **seçim yanlılığı** taşır
(işaretler zaten URL adaylarından seçildi), bu yüzden üst sınırdır. Yanlış atma tavanı
gevşetilirse cephe (yalnız ana örnekle seçilmiş): tavan %7,5 → birleşik recall %84, kontrol %81;
tavan %10 → %85 / %85.

### 2.4 Ölçülüp reddedilenler

| Sinyal | Sonuç |
|---|---|
| Harfi harfine çevrilmiş özel ad sözlüğü ("Düşük" = Low, "Hayalet" = Ghost) | Ana örnekten türetilen sözlük 7 sözcük (`açıklama`, `eksik`, `fiyatları` …), kontrol MT'de 1/26, kontrol MT-olmayanda 5/174 isabet — ezber, genellemiyor. Ayrıca cümle içi başlık harfli yaygın sözcük oranı MT'de daha *düşük* (AUC 0,37–0,45). |
| Cümle uzunluğu düzenliliği (CV) | AUC 0,50–0,59 |
| İngilizce sayı biçimi, `Bay/Sayın + ad` | çok seyrek, ayırmıyor |

## 3. `commercial_page`

### 3.1 Aileler

| Aile | Örnek |
|---|---|
| `price` | kuruş haneli tutar (`27,99 TL`), para simgesi (`199 ₺`, `$47.14`), `Fiyat: 120` — düz yazıdaki yuvarlak tutar ("100 lira") **sayılmaz** |
| `cta` | `sepete ekle`, `satın al`, `sipariş ver`, `hemen ara`, `ücretsiz kargo`, `stok durumu`, `indirim kodu` … |
| `spec` | `ürün kodu`, `marka:`, `model:`, `isbn`, `teknik özellikler`, `kdv dahil` … |
| `corp_we` | `firmamız`, `müşterilerimiz`, `hizmetlerimiz`, `sunuyoruz` … |
| `sponsor` | `sponsorlu`, `affiliate`, `reklam:`, `işbirliği ile hazırlanmıştır` … |
| `breadcrumb` | `Ana Sayfa > Ürünler > …` |
| `title_repeat` | baştaki 30 sözcüğün bir üçlüsü metinde ≥ 5 kez (mahalle × hizmet şablonu) |

### 3.2 Karar

```
commercial_page =  en az 2 farklı aile
              VEYA price ≥ 2  VEYA cta ≥ 2  VEYA spec ≥ 2  VEYA sponsor ≥ 1
```

"Ansiklopedi kalır, sponsorlu inceleme gider" — ama **biçim önce**: kural tür sözlüğü değil,
satış sayfasının biçim izlerini ve *aile* sayar. Aynı ailenin on isabeti tek kanıttır.

### 3.3 Ölçüm

| | HQ ticari `çöp` (26) | v5 ticari `çöp` (35) | HQ `kalsın` (122) | v5 `kalsın` (103) | ansiklopedi `kalsın` (29) | v5 başka `çöp` (62) |
|---|---:|---:|---:|---:|---:|---:|
| **Kural** | **%15,4** | **%34,3** | **%0,0** | **%0,0** | **%0,0** | %4,8 |

Ticari kural **temkinlidir**: hakemin HQ'da ticari dediği belgelerin çoğu düzyazı tanıtım
metnidir (kitap tanıtım spotu, firma tanıtımı) ve fiyat/satış/kart biçimi taşımaz — biçim
kuralı onları görmez. Daha cömert ayar (`title_repeat ≥ 3`) v5 recall'unu %45,7'ye çıkarır ama
v5 `kalsın`'da %3,9 yanlış atma getirir; çeviri kuralının %4,9'u ile birlikte bütçe aşılır.

## 4. Bütün olarak v4 (etiketli satırlar, hakem hükmü)

| | HQ-200 (hakem) | v5-200 (hakem) |
|---|---|---|
| Öncesi çöp (`emin değilim` dahil) | %39,0 [32,5 – 45,9] | %48,5 [41,7 – 55,4] |
| v3 sonrası | %39,2 (1 atma, o da `kalsın`) | %48,5 (0 atma) |
| **v4 sonrası** | **%31,4 [24,8 – 38,7]** — 31 atma: 25 çöp, 6 `kalsın` | **%44,3 [37,3 – 51,5]** — 17 atma: 16 çöp, 1 `kalsın` |

HQ satırı **örnek içi** kestirimdir (çeviri eşikleri bu etiketlerle seçildi); yansız sayı hakem
yeniden koşusundan gelecek (§6).

## 5. Tam alımda etkisi (FineWeb2-HQ `tur_Latn`, 8.578.808 belge)

Tek geçiş: 105 parça, her biri SHA256 ile doğrulandı; 8.578.808 belge, 25,2 GB metin.

| | belge | bayt |
|---|---:|---:|
| `machine_translation` | 1.474.546 = **%17,2** | 7,71 GB = **%30,6** |
| `commercial_page` (son kod; geçişteki kalıpla %2,54 / %8,1) | ≈ %2,4 | ≈ %7,6 |
| en az biri (v4'ün yeni atması, son kod) | ≈ **%18,4** (≈ 1,58 M) | ≈ **%33,7** (≈ 8,5 GB) |
| v4 toplam (v3 ∪ yeni; 210.000 belgelik örneklem) | %18,8 | %34,9 |
| yalnız v3 (örneklem) | %0,8 | %3,6 |

Döküm yılına göre çeviri atması: ≤ 2019 **%9,5** belge (%17 bayt), 2020 – 21 **%21,6**
(%40), ≥ 2022 **%22,9** (%35). Ticari: %1,7 / %2,7 / %3,4. 2026-10-03 göz okumasının
kestirimiyle (MT ≈ %13,8 belge, ≈ %33 bayt, yeni dökümlerde dört kat) aynı yeri gösteriyor.
Hacim etkisi: ≈ 25,2 GB'lık alımın ≈ 8,5 GB'ı yeni kurallarla düşer.

Ticari kuralın `sponsor` kalıbı tek geçişten **sonra** düzeltildi ("sponsorluğunu" haberi);
çeviri kuralı değişmedi. Son kodla ticari oran aynı 210.000 belgelik örneklemde iki kalıpla
birden ölçülüp tam geçişe oranlandı (RAPOR §5).

## 6. Hakem yeniden koşusu

`var/olcum-2026-10-13/task-046/juri-kor-200/` — tam alımdan tohumlu düzgün rastgele 200 belge,
kör (kaynak/adres/kural hükmü yok, boşluk normalize, karışık sıra), cevap anahtarı ayrı
(`ANAHTAR-acma.json`). Aynı okumadan üç sayı çıkar: **öncesi** (200'ün tamamı), **v3 sonrası**,
**v4 sonrası** (tutulan alt kümeler) ve kuralların isabeti (atılan alt kümede çöp payı).
Puanlama: `puanla.py` (Wilson %95; `emin değilim` çöp tarafında, ayrıca yalnız-çöp okuması).

## 7. Bilinen zayıflıklar

1. **Çeviri kuralının yarısı adrese dayanır.** URL'siz kaynakta (v5, eski mC4 türevleri) yalnız
   içerik yolları kalır: aynı etiketlerde URL'siz recall göz MT'de %26, hakem MT'de %36, kontrolde %19.
2. **Yerelleştirilmiş kurumsal sayfalar** (`support.microsoft.com/tr-tr`, `support.deezer.com/hc/tr`,
   `tr.motorsport.com`, `dw.com/tr`): profesyonel ya da insan çevirisi; kural bunları da atar.
   HQ `kalsın` satırlarındaki 6 yanlış atmanın 6'sı bu sınıftan. "Şüpheliyi at" kararına
   uygun, ama bir hacim bedeli var.
3. **Türk alan adlı çeviri haber çiftlikleri** (İngilizce haberin Türkçe sitede yayımı) URL
   imzası taşımaz; yalnız profil ve "Bu," yakalar — hakem-MT recall'unun %64'te kalmasının
   nedeni.
4. **İçerik yolu LLM/SEO metnine de basar.** Tam alım örneğinin göz okumasında URL'siz atılan
   20 belgenin 10'u çeviri, 6'sı çeviri değil ama SEO/üretilmiş metin, 4'ü iyi Türkçe (İncil
   çevirisi, köşe yazısı, halk bilgisi, magazin haberi). Kopya kalıplar ("sahiptir",
   "olacaktır") üretilmiş Türkçede de sık.
5. **Ticari kural düzyazı tanıtımı görmez** (HQ ticari çöpte recall %15). Bu bir biçim kuralının
   sınırıdır; tür sınıflandırması ayrı yöntem ister (hakem / sınıflandırıcı). Tersi de var:
   tam alımın göz okumasında ticari isabetlerin bir kısmı kuruşlu tutar taşıyan hukuk yazısı,
   "marka:/model:" sözcüklü haber ya da başlık tekrarlı haberdi (fiyat biçimi daraltıldıktan
   sonra 25 okumada 4 belge hâlâ yanlış atılıyor).
6. **Etiketler küçük ve yanlı.** Göz işaretleri yalnız URL adaylarına bakıldığı için URL
   sinyalini kayırır; HQ ana örneği eski dökümlere kaymış bir küme örneğidir; v5 metinleri ilk
   6.000 karakterdir (v5 nesnesi silindi).
7. **`clean_candidate` alım manifestini doğrudan okumuyor** (satır okuyucusu `_bounded_lines`);
   v4'ün URL'yi görmesi için girdinin JSONL satırında `url` ya da `provenance.url` bulunmalı.
   Alım manifesti + Parquet parçalarından türetme ayrı iş.

## 8. Karar kaydı

Seçim listesi kipinde (`--selection-list`) v4 her gerekçeyi **kendi** `derlem.decision.v1`
satırı olarak yazar: `decision_type=quality_rule`, `verdict=reject`,
`reason=machine_translation` / `commercial_page` / v3 gerekçesi, `judge=tr-web-v4@<sha12>`.
`<sha12>`, hükmü belirleyen altı kaynak dosyanın (LF'ye çevrilmiş) SHA256'sının ilk 12
hanesidir (`quality_v4.judge_id()`); kod değişirse yargıç kimliği değişir. Manifestte
`quality_judge` alanı aynı kimliği taşır. v1–v3'ün tek satırlık biçimi değişmedi.

## 9. Kullanım

```
python -m derlem_worker.clean_candidate --input-path aday.jsonl --quality-policy tr-web-v4 --selection-list ...
```

Kontrol koşuları: 30 bozma (her eşik, her koruma, her bağlantı) → 30 kırmızı; bozulmamış ve geri
alınmış ağaç yeşil (`var/olcum-2026-10-13/task-046/kontrol-kosulari.json`).
