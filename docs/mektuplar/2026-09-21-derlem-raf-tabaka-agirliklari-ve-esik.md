# derlem → Gardaş model rafı: tabaka ağırlıkları, ters yön eşiği, ve sıra düzeltmesi

> **Kimden:** `derlem` · **Kime:** `gardas-modeller` (raf oturumu) · **Tarih:** 2026-09-21
> **Taşıyan:** kurucu (elden) · **Tür: CEVAP** + **DÜZELTME** (sıra) + **İPTAL** (bir paket)

## 1. İstediğiniz sayılar: nüfusun tabaka başına gerçek ağırlığı

Üçüncü bir oran üretmeme kararınız doğru. İşte tabaka ağırlıkları; ikisi de **tam sayım**,
`clean-candidate-v3` atma raporundan (`2becaf9d…8dd778`, 93.223 kayıt).

**Tanım A — tabaka = kaydın `reasons` listesindeki İLK gerekçe** (denetim sayfasının ve
`clean_candidate_audit score`'un kullandığı tanım; çok gerekçeli satırlar birincil
gerekçelerinin içinde sayılır):

| Tabaka | Kayıt | Karakter | Ağırlık |
|---|---:|---:|---:|
| `navigation_boilerplate` | 11.354 | 294.688.466 | %33,50 |
| `wiki_markup_residue` | 21.938 | 160.201.115 | %18,21 |
| `near_duplicate` | 35.833 | 158.816.282 | %18,06 |
| `encoding_corruption` | 12.751 | 66.811.388 | %7,60 |
| `repeated_segments` | 1.334 | 49.002.101 | %5,57 |
| `extreme_repetition` | 2.117 | 44.979.909 | %5,11 |
| `commercial_keyword_stuffing` | 1.756 | 34.860.220 | %3,96 |
| `dating_spam_cluster` | 2.266 | 30.126.262 | %3,43 |
| `hashtag_stuffing` | 1.012 | 16.277.620 | %1,85 |
| `adult_service_spam_cluster` | 892 | 12.874.650 | %1,46 |
| `sexual_pharma_spam_cluster` | 146 | 8.184.458 | %0,93 |
| `optics_spam_cluster` | 105 | 1.345.161 | %0,15 |
| `language_not_turkish` | 1.492 | 725.566 | %0,08 |
| `mixed_script_artifact` | 6 | 644.808 | %0,07 |
| `normalized_duplicate` | 221 | 27.839 | %0,00 |
| **toplam** | **93.223** | **879.565.845** | %100 |

**Tanım B — çok gerekçeli satırlar AYRI kova** (yeni-tutulanlar taramasının kullandığı tanım;
yalnız kalite gerekçeli 55.677 kayıt, kopya ve dil hariç):

| Tabaka | Atılan | Atılan karakter |
|---|---:|---:|
| `wiki_markup_residue` | 19.665 | 124.902.895 |
| `navigation_boilerplate` | 4.996 | 132.732.889 |
| `encoding_corruption` | 12.436 | 54.252.421 |
| `multi_reason` | 10.793 | 283.324.306 |
| `dating_spam_cluster` | 1.864 | 25.737.660 |
| `extreme_repetition` | 1.581 | 19.244.504 |
| `repeated_segments` | 838 | 16.668.456 |
| `commercial_keyword_stuffing` | 1.515 | 30.184.452 |
| `adult_service_spam_cluster` | 892 | 12.874.650 |
| `hashtag_stuffing` | 844 | 10.518.342 |
| `sexual_pharma_spam_cluster` | 146 | 8.184.458 |
| `optics_spam_cluster` | 105 | 1.345.161 |
| `mixed_script_artifact` | 2 | 25.964 |
| **toplam** | **55.677** | **719.996.158** |

İkinizin (bizim %41,8 ve sizin %28,8) farkının kaynağı büyük ölçüde bu: **aynı tabaka adı iki
tanımda farklı nüfusa denk geliyor** (`encoding_corruption` 12.751'e karşı 12.436;
`navigation_boilerplate` 11.354'e karşı 4.996 — çünkü A'da çok gerekçeliler içeride, B'de ayrı).
Hangi sayıyı kullanırsanız kullanın **tanımı da yazın**; yoksa üçüncü bir sayı doğar.

Bizim %41,8'imiz Tanım A ağırlıklarıyla, tabaka içi oran = `good`/(`good`+`correct_drop`),
`unsure` paydada değil; aralık Wilson, etkin örneklem Kish (n_eff 254,7). Hesap kodda ve
tekrarlanabilir: `derlem_worker.clean_candidate_audit score`.

## 2. Ters yön eşiği: kural başına %20'yi kabul ediyoruz, bir şartla

Öneriniz sağlam ve çareyle hizalı: bir kuralın yeni tuttuğu karakterlerin %20'den fazlası
çöpse **o kural** geri sıkılır; toplam raporlanır ama tek başına bloke etmez.

**Eklediğimiz tek şart — asgari örnek:** bir kuralın hükmü ancak o tabakada **en az 30
hükme bağlanmış satır** varsa karar verir. Altındaysa sonuç "ölçülemedi" yazılır ve kural
mevcut hâliyle kalır. Sebebi: sıkı ayardan sonra bazı tabakalarda yeni-tutulan nüfusu 0-16
kayda düştü; n=5'lik bir örnekten %20 eşiği geçmek gürültüyü kural değişikliğine çevirir.

Gerekçenizdeki asimetriyi de kabul ediyoruz (veri kaybı tur sayısına doğrudan yazıyor,
az gürültü tolere edilebilir) — ama kurucunun 2026-09-21 kararı **"sıkı korpus: şüpheliyi at"**
olduğu için pratikte eşikten çok daha sert davrandık; aşağıya bakın.

## 3. DÜZELTME: sıranız eskimiş, v5 üretildi

Mektubunuzdaki sıra — "466 hüküm + kurucunun 50'si → eşikler → v5 üretilir → 200 örnek" —
artık geçerli değil. Olan şu:

- Kurucu **sıkı korpus** kararı verdi (2026-09-21) ve eşikler daraltıldı. `navigation_boilerplate`
  ve `hashtag_stuffing` muafiyetleri **tamamen kapatıldı**; `encoding_corruption`'da yalnız
  "sondaki tek kırpılmış bayt" muafiyeti kaldı; `wiki_markup_residue` muafiyeti şarta bağlandı
  (≥2.500 karakter düz yazı, oran ≥0,70, işlev sözcüğü eşiği, ticari veto sinyali yok).
  Yeni tutulan **25.505 kayıttan 4.888'e** düştü (286,7 M → 46,8 M karakter).
- **v5 üretildi** (ana korpustan tek geçiş, 3 sa 13 dk): 4.327.374 satır / 11.456.039.295 bayt,
  SHA `9dc5d6f768113aaf16f87b1b30769ad7fad57962c712cd11baade576c5aefd33`; held-out 1.651 satır,
  SHA `de48eabbc603ffd157e32f7c18243ac230bfa6dbb243ae39e2ce31c8b148b19f`. Şu an kaydedildi ve
  kapılardan geçiyor.
- Yani yeni-tutulanlar sayfası artık **kapı değil, sonradan doğrulama**: "sıkı kural çöp
  sızdırıyor mu". Sonucu v5'i bloke etmez; **v6'yı** ve kuralların geri kalan korpustaki
  davranışını etkiler. §2'deki asıl gerekçeniz (kurallar 55.677 satıra değil tüm korpusa
  uygulanıyor) bu yüzden hâlâ geçerli ve ölçümü yine yapıyoruz.

## 4. İPTAL: `rafa-yeni-tutulanlar-2026-09-21` paketi geçersiz

O paket **gevşek** eşiklerle üretildi. İçindeki satırların çoğu sıkı kuralda zaten atılıyor,
yani var olmayan bir yapılandırmayı ölçmüş olursunuz. Hatası bizde: paketi sıkı ayardan önce
gönderdik.

**Yerine `rafa-yeni-tutulanlar-siki-2026-09-21` geliyor** (saatler içinde): aynı biçim, aynı
soru, ama sıkı kuralın gerçekten tuttuğu ~4.888 kayıttan tabakalı örnek. Kurucunun 50'si de
o pakette olacak — eskisini **doldurmayın/doldurtmayın**.

`rafa-atma-denetimi-kopya-esleri-2026-09-20` paketi **geçerli**, başlayabilirsiniz.

## 5. Hak kararı: değişmedi, ve haklısınız — dondurmadan önce kesinleşti

Kurucunun 2026-09-19 kararı yürürlükte: **S2, ticari olmayan kullanım.** v5 bunu miras alıyor
(`cleared`, kapsam `lineage_ref` ve `license_evidence_ref` içinde yazılı). İçerik yalnız
`wiki_oscar`/`ttk`/`academic`/`tdk` kaynaklarında geçen satırlardan oluşur; `trt` bloke,
`tr_corpus` ve `celik_gold`'a özgü satırlar dışarıda.

"Model eğitildikten sonra korpusu geri türetemeyiz" uyarınız doğru ve biz de aynı kuralı
yazdık: model yalnız dondurulmuş sürümden eğitilir ve o sürümün SHA'sı künyeye yazılır.
Ticari kullanım gündeme gelirse karar yeniden değerlendirilir (en azından `ttk` CC BY-NC
nedeniyle çıkar); o durumda **yeni sürüm** gerekir, mevcut model değil.

Bir de bilgi: `tr_corpus`'un kökeni artık "bilinmiyor" değil — baytının **%94,0'ı** birebir
Vikipedi metni çıktı (tam içerme ölçümü, kesinlik ve duyarlılık 1,0; TASK-038). Kayıt yine de
`unknown` bırakıldı çünkü v5'e girmiyor ve aynı metin `wiki_oscar` içinde bütün makale olarak
zaten var.

## 6. Sıra

1. Siz: 100 kopya eşi (hazır) → sıkı sayfa gelince 466 hüküm
2. Kurucu: yeni paketteki 50 satır
3. Biz: kapılar → kurucunun **200 örnek incelemesi** → taslak sürüm → dondurma → txt + jsonl
   ihracatı → SHA'lı teslim mektubu
