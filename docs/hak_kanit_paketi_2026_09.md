# Faz-2 ham kaynakları — hak kanıt paketi (TASK-011)

**Tarih:** 2026-09-19 · **Hazırlayan:** Derlem oturumu (Claude) · **Karar:** kurucu
**Yöntem:** her kaynağın yayıncısının kendi lisans/kullanım şartı sayfası okundu
(alıntılar aşağıda, okunma tarihi 2026-09-19); toplayıcı kodundan (`corpus_builder/`)
kaynak adresleri alındı. Hukuki görüş değildir; kanıt ve öneridir.

Amacımız: ham metni **yeniden dağıtmadan**, yalnız **kendi modelimizi eğitmekte** kullanmak.
İki soru: (1) metni bu amaçla kullanabilir miyiz, (2) eğitilen modelin lisansına/ticari
kullanımına bir şart bulaşır mı.

## Özet tablo

| Kaynak | Boyut | Yayıncının beyanı (okundu) | Eğitimde kullanım | Modele bulaşan şart | Öneri `rights_status` |
|---|---|---|---|---|---|
| `wiki_oscar` (mC4 + Wikipedia, HF indirmesi) | 12,8 GB | C4/mC4: **ODC-BY** + Common Crawl kullanım şartları; Wikipedia: **CC BY-SA 3.0 + GFDL** | Evet, şartlı | Atıf zorunlu (ikisi); Wikipedia'da **share-alike**; Common Crawl: üçüncü taraf telifine saygı + **yapay zekâ/LLM kullanımında tazmin yükümlülüğü**, ticari kullanım için hukuk danışmanı önerisi | `restricted` (atıf + share-alike + tazmin kabulü yazılı olursa `cleared`) |
| `ttk` (Belleten) | 113 MB | **"CC BY-NC 4.0"** (site ana sayfası) | Evet, **ticari olmayan** | Ticari model eğitimi kapsam dışı; atıf | `restricted` (ticari amaçta `blocked`) |
| `academic` (DergiPark OAI-PMH özetleri) | 65 MB | Platform genelinde tek lisans **yok**; dergi bazında CC BY / CC BY-NC-ND vb. | Dergi bazında değişir | Dergi bazında; NC/ND olanlar ticari/türev kullanımı kapatır | `unknown` → dergi bazında ayrıştırılmadan `cleared` olamaz |
| `trt` (trthaber.com RSS) | 1,1 MB | Kullanım şartları: içerik **"kopyalanamaz… alıntı yapılamaz"**, ticari kullanım yasak, otomatik toplama yasak | **Hayır** | — | `blocked` (388 belge; çıkarılması korpusu etkilemez) |
| `tdk` (sozluk.gov.tr API) | 16 MB | Sitede lisans/kullanım şartı beyanı **bulunamadı** (ana sayfa ve kurum sitesi okundu) | Belirsiz; kamu kurumu içeriği, telif TDK'da | Belirsiz | `unknown` (TDK'dan yazılı izin ya da kurumun açık lisansı gerekir) |
| `celik_gold` | 13,0 GB | Toplayıcı yok, köken bilinmiyor | Bilinmiyor | Bilinmiyor | `unknown` (köken bulunmadıkça `cleared` olamaz) |
| `tr_corpus` | 458 MB | Toplayıcı yok, köken bilinmiyor | Bilinmiyor | Bilinmiyor | `unknown` |

## Kaynak notları (alıntılar)

### 1. `wiki_oscar` — Hugging Face `allenai/c4` (mC4) ve `wikimedia/wikipedia`

- **allenai/c4** veri kartı (okundu 2026-09-19): *"We are releasing this dataset under the
  terms of ODC-BY. By using this, you are also bound by the Common Crawl terms of use in
  respect of the content contained in the dataset."* mC4 alt kümesi 108 dil, `tr` dahil.
  https://huggingface.co/datasets/allenai/c4
- **Common Crawl kullanım şartları** (okundu 2026-09-19): *"BY USING THE CRAWLED CONTENT, YOU
  AGREE TO RESPECT THE COPYRIGHTS AND OTHER APPLICABLE RIGHTS OF THIRD PARTIES IN AND TO THE
  MATERIAL CONTAINED THEREIN."* Ticari kullanım için hukuk danışmanı önerilir; yapay
  zekâ/makine öğrenmesi/LLM kullanımından doğan üçüncü taraf iddialarında kullanıcı Common
  Crawl'ı **tazmin eder**. https://commoncrawl.org/terms-of-use
- **wikimedia/wikipedia** veri kartı: lisans **cc-by-sa-3.0** ve **gfdl**; döküm `20231101`,
  `20231101.tr` (535 bin satır). https://huggingface.co/datasets/wikimedia/wikipedia
- **Ne demek:** ODC-BY atıf ister (veri kartında ve model künyesinde kaynak gösterilir).
  CC BY-SA share-alike: metnin yeniden dağıtımında aynı lisans; model ağırlıklarının "türev
  eser" sayılıp sayılmadığı dünyada tartışmalı — risk kabulü kararı. Common Crawl tazmin
  yükümlülüğü hukuki risktir; kabul edilecekse yazılı kabul edilir.
- **Doğrulandı (2026-09-19):** `wiki_oscar_corpus.jsonl` kayıtlarında `source` alanı var;
  85.075 kayıtlık örneklemde değerler yalnız `mc4` (%90,6) ve `wikipedia` (%9,4).

### 2. `ttk` — Türk Tarih Kurumu Belleten

- Site ana sayfası (okundu 2026-09-19): *"Bu dergideki çalışmalar Creative Commons
  Atıf-GayriTicari 4.0 Uluslararası (CC BY-NC 4.0) ile lisanslanmıştır."* Açık erişim
  politikası sayfası menüde var; adresi doğrudan bulunamadı (404).
  https://www.belleten.gov.tr/
- **Ne demek:** ticari olmayan kullanımda atıfla serbest. Eğitilen model ticari amaçla
  kullanılacaksa bu kaynak dışarıda kalmalı ya da kurumdan yazılı izin alınmalı.

### 3. `academic` — DergiPark OAI-PMH özetleri

- DergiPark platform genelinde tek lisans beyan etmiyor; dergiler kendi politika sayfasında
  CC lisansı seçiyor (örnekler: CC BY 4.0, CC BY-NC-ND 4.0). OAI-PMH ile harmanlanan
  kayıtlar OpenAIRE'de görünür. Kaynaklar: https://cabim.ulakbim.gov.tr/dergipark-ve-uluslararasi-gorunurluk/ ,
  https://dergipark.org.tr/tr/pub/ap/page/17751 , https://dergipark.org.tr/tr/pub/uead/page/5414
- **Ne demek:** 45.208 özet hangi dergilerden geldiğine göre ayrışmalı; kayıtta dergi kimliği
  varsa (`academic_corpus.jsonl` alanları — TASK-016'da bakılacak) dergi başına lisans
  eşlenir; NC/ND lisanslı dergiler ticari/türev kullanımda dışarıda kalır.

### 4. `trt` — TRT Haber RSS

- Kullanım şartları (okundu 2026-09-19): *"İnternet Sitesi'nde yer alan hiçbir bir video,
  müzik, görsel, doküman, sayfa, grafik, tasarım vb. unsur veya içerik, kısmen veya
  tamamen… kopyalanamaz, başka yere taşınamaz, alıntı yapılamaz."* ve *"Aksi belirtilmedikçe
  ticari ya da kişisel amaçlarla ve kaynak göstermeden kullanılamaz."*; otomatik programlarla
  sunucuları zorlamak yasak. https://www.trthaber.com/kullanim-sartlari.html
- **Ne demek:** izin yok. 388 belge; çıkarmanın korpusa etkisi ihmal edilebilir. Öneri:
  `blocked`, ana korpustan bu kaynağa ait satırlar çıkarılır (bileşim ölçümü TASK-016).

### 5. `tdk` — sozluk.gov.tr

- Sözlük sitesinde ve kurum sitesinde lisans/kullanım şartı beyanı bulunamadı (2026-09-19;
  sayfalar okundu, arama yapıldı). "Türkçe Sözlük'ün kullanılmasıyla ilgili açıklamalar"
  belgesi kullanım kılavuzudur, lisans değildir.
- **Ne demek:** telif TDK'dadır; açık lisans yoksa kullanım için kurumdan yazılı izin gerekir.
  Kamu kurumu içeriğinin "kamuya açık" olması, model eğitiminde kullanım hakkı vermez.

### 6. `celik_gold` ve `tr_corpus`

- Toplayıcı yok; `sources.json`'da yok; köken bilinmiyor. `celik_gold` ana korpusun en büyük
  girdisi (13,0 GB). Köken, içerik bileşimi (TASK-016: bu iki dosyanın satırları diğer beş
  kaynakla ve birbirleriyle ne kadar örtüşüyor) ve kurucunun hafızasıyla aranır.

## Ölçüm: hak sorunu korpusun baytça %6,66'sı (TASK-016, 2026-09-19)

`wiki_oscar`'ın kaynağı içerikten doğrulandı: her kayıtta `source` alanı var; 85.075 kayıtlık
örneklemde yalnız `mc4` (%90,6) ve `wikipedia` (%9,4). Ana korpusun her satırı hangi ham
kaynaklarda geçiyor ölçüldü (baytla):

| Senaryo | Kullanılan kaynaklar | Korunan bayt | Pay |
|---|---|---|---|
| S0 bugünkü v3 | yedisi | 13,57 GB | %100 |
| S1 TRT çıkar | TRT hariç | 13,57 GB | %100,00 |
| S2 kökeni bilinmeyenler de çıkar | wiki_oscar, ttk, academic, tdk | 12,85 GB | %94,67 |
| S3 + TTK çıkar (ticari hedef) | wiki_oscar, academic, tdk | 12,74 GB | %93,87 |
| S4 + TDK çıkar (lisans yok) | wiki_oscar, academic | 12,73 GB | %93,80 |
| **S5 yalnız lisansı belgeli kaynak** | **wiki_oscar** | **12,67 GB** | **%93,34** |

`celik_gold` bağımsız kaynak değil (belgelerinin %99'u başka dosyalarda; kendine özgü payı
baytça %1,96); `tr_corpus` kısa parçalar (baytça %3,36, satırca %24,9).

## KURUCU KARARI (2026-09-19): S2, ticari olmayan kullanım

**Seçilen yol: S2.** v2, yalnız şu ham kaynaklarda geçen satırlardan oluşur: `wiki_oscar`
(mC4 + Wikipedia), `ttk` (Belleten), `academic` (DergiPark özetleri), `tdk` (sözlük).
**Çıkarılan:** kökeni bilinmeyen `tr_corpus` ve `celik_gold`'a özgü satırlar; kullanım
şartları kopyalamayı yasaklayan `trt`'de geçen her satır. Ölçülen bedel: baytın %5,33'ü
(S2 %94,67 korur; ana korpus üzerinde).

**Kullanım kapsamı:** araştırma ve kendi modelimizin eğitimi; **ticari kullanım yok**.
Ham metin yeniden dağıtılmaz. Ticari kullanım başlamadan bu karar yeniden değerlendirilir
(o durumda en az `ttk` — CC BY-NC — çıkar; Common Crawl şartları için hukuki danışma).

**Kaynak başına dayanak:**

| Kaynak | Dayanak | Hak durumu (kapsamlı) |
|---|---|---|
| `wiki_oscar` | Belgeli lisans: mC4 ODC-BY + Common Crawl şartları; Wikipedia CC BY-SA 3.0 + GFDL. Kabul edilen yükümlülükler: atıf (veri kartında ve model künyesinde), share-alike riskinin kabulü, Common Crawl'ın yapay zekâ kullanımındaki tazmin maddesinin kabulü. | `cleared` (ticari olmayan) |
| `ttk` | Belgeli lisans: CC BY-NC 4.0; kullanım ticari olmadığı için lisans kapsamında. Atıf. | `cleared` (ticari olmayan) |
| `academic` | Dergi bazında lisans (platform lisansı yok); **kurucu risk kabulü**, kapsam: ticari olmayan araştırma. Ticari kullanımdan önce dergi bazında ayrıştırılır. | `cleared` (kurucu risk kabulü, ticari olmayan) |
| `tdk` | Lisans beyanı yok; **kurucu risk kabulü**, kapsam: ticari olmayan araştırma. Ticari kullanımdan önce TDK'dan yazılı izin. | `cleared` (kurucu risk kabulü, ticari olmayan) |
| `trt` | Kullanım şartları yasaklıyor. | `blocked` |
| `tr_corpus`, `celik_gold` (özgü kısmı) | Köken bilinmiyor; v2'ye girmez. | `unknown` |

**Türev kuralıyla ilişkisi:** "türev, girdisinden temiz olamaz" kuralı aklama yasağıdır.
v4, v3'ten **kaynak bazlı süzülerek** üretilir: içeriği yalnız yukarıdaki dört kaynaktan
gelir, dolayısıyla hak durumu o dört kaynağın en kısıtlısıdır (ticari olmayan `cleared`).
Süzmenin kanıtı (atılacak satır listesinin SHA256'sı, ölçüm) v4 manifestinde durur.

**Kaydeden:** Derlem oturumu, kurucunun 2026-09-19 tarihli cevabı üzerine ("S2:
bilinmeyenleri çıkar, TTK/TDK/akademik kalsın"; ticari hedef: "Hayır, şimdilik
araştırma/kendi kullanım").

**Uygulandı (2026-09-19, kurucu onayı "ok onay veriyorum"):** tablodaki hak durumları
`sources` kayıtlarına API üzerinden (denetim izli) işlendi — `ttk`, `academic`, `tdk`
`cleared` (lisans kanıtı: bu belge), `trt` `blocked`; `tr_corpus` `unknown` kaldı.
`wiki_oscar` ham dosyası kaynak olarak kaydedildi (`faz2_ham_wiki_oscar_20260919`,
`e6f3b29b-d2e6-4f89-bdee-cd1e3c52703e`, `cleared`, lisans kanıtı bu belge) ve ana
korpusun girdilerine eklendi (6 girdi; `celik_gold` hâlâ kayıtsız, S2'de dışarıda).
Ticari olmayan kapsam `license_evidence_ref` ve `lineage_ref` metinlerinde yazılıdır;
`rights_status` sözlüğünde kapsam alanı yoktur (bkz. TASK-030, makine okunur lisans defteri).

## Kurucunun önündeki seçenekler (TASK-011 kararı, 2. inceleme oturumundan önce)

- **A) Kaynak bazlı temizlik + v4:** `trt` çıkarılır; `ttk` ticari amaçta çıkarılır;
  `academic` dergi bazında ayrışır; `tdk`, `celik_gold`, `tr_corpus` köken/izin gelene kadar
  çıkarılır; `wiki_oscar` için atıf + share-alike + tazmin kabulü yazılır. Aday **v4** olarak
  yeniden üretilir; 200 örnek incelemesi yenilenir. En temiz; ölçüme göre **bedeli baytın
  %6,66'sı** (S5; TTK/TDK/akademik izinleri sonradan gelirse geri eklenir).
- **B) Risk kabulü memosu:** kurucu, kapsamı ve tarihi yazılı bir memoyla `celik_gold`,
  `tr_corpus`, `tdk` için riski üstlenir; memo bu kaynakların lisans kanıtı olur; ana korpus,
  aday ve held-out `cleared`'ı miras alır. `trt` (388 belge) yine de çıkarılmalı (açık yasak).
  Hızlı; hukuki risk kurucuda; `data_governance.md`'ye belgelenmiş istisna.
- **C) Erteleme:** v2 donmaz; önce izinler (TDK, TTK ticari) ve köken araştırması.

**Önerim:** ne olursa olsun `trt` çıkar (açık yasak, ihmal edilebilir boyut). Ticari model
hedefleniyorsa `ttk` da çıkar. Kalan karar B ile A arasında hız/risk dengesidir; B seçilirse
memo şunları açıkça söylemeli: hangi kaynaklar, hangi kullanım (yalnız kendi eğitimimiz,
yeniden dağıtım yok), tazmin ve share-alike risklerinin kabulü, takedown taahhüdü.

## TASK-038 — `tr_corpus` kökeni (ölçüm, 2026-09-19)

TASK-011 `tr_corpus` için "toplayıcı bulunamadı" yazmıştı; TASK-022 ilk 500 satırın 366'sını
`wiki_oscar` kayıtlarının içinde bulmuştu. Bu kez **1.502.165 satırın tamamı** 12,8 GB'lik
`wiki_oscar`'ın **4.253.739 kaydının tamamına** karşı ölçüldü (salt okunur; hak durumu
değiştirilmedi).

**Yöntem.** İki taraf da aynı kodla normalize edildi (TASK-016 kuralı: boşluk dizileri tek
boşluğa, kırpma, `casefold`, utf-8). Normalize satırların en kısası 50 bayt, bu yüzden kısa
satır istisnası gerekmedi. Her satırdan, satıra eşit aralıkla yayılmış **8 adet 32 baytlık
pencere** ("çıpa") alınıp 64 bit'e özetlendi (numpy `cumsum` ile yuvarlanan polinom karma +
splitmix64) — 12.017.320 çıpa. `wiki_oscar` 8 MB'lik öbeklerle akıtıldı, **her kaydın bütün
32 baytlık pencereleri** karmalanıp çıpa dizininde arandı. Bir satır bir kaydın içinde
geçiyorsa satırın *her* penceresi, dolayısıyla 8 çıpanın hepsi o kayıtta vardır; bu yüzden
tarama hiçbir içerme'yi kaçıramaz. En az 2 çıpa tutunca (kayıt, satır) çifti aday sayıldı ve
her aday **tam `bytes in bytes` denetimiyle** doğrulandı — yani sonuç sezgisel değil, tam
alt dizgi içermesi. Karma çakışması yalnız fazladan aday üretir, doğrulama eler. Wikipedia
içinde bulunan satırlar dizinden budandı (12,0M → 2,1M çıpa); ölçümü doğrusal tutan budur.
Ayrıca istenen **yaklaşık kural** da hesaplandı: aday çiftlerde satırın 8 kelimelik
gölgelerinin (shingle) **≥ %95'i** kayıtta geçiyorsa "yakın içerme".

**Sonuç** (bayt = ham satır, satır sonu dahil; toplam 457.814.564 bayt):

| Sınıf | Satır | Satır payı | Bayt | Bayt payı | uzunluk p10/p50/p90 |
|---|---:|---:|---:|---:|---|
| (a) bir `wikipedia` kaydının içinde | 1.243.012 | %82,748 | 369.389.846 | %80,685 | 64 / 188 / 660 |
| (b) yalnız bir `mc4` kaydının içinde | 1.452 | %0,097 | 208.600 | %0,046 | 58 / 75 / 288 |
| (c) hiçbiri | 257.701 | %17,155 | 88.216.118 | %19,269 | 61 / 192 / 793 |

≥ %95 gölge kuralı eklenince (a)'ya 5.384 satır daha girer (+0,36 puan).

**Kalıntı aslında da Wikipedia.** Eşleşmeyen satırların **%40,5'i** tipografik kesme
işareti (U+2019) taşıyor; eşleşen satırların **%0,00'ı** taşıyor — yani kalıntı `wiki_oscar`'dan
kelimelerde değil, noktalama biçiminde ayrılıyor (toplayıcı `download_tr_corpus.py`
`20220301.tr` dökümünü okuyor, `wiki_oscar` ise `20231101.tr`). Kalıntı, kıvrık tırnak/kesme,
tireler ve üç nokta iki tarafta da ASCII'ye indirgenerek **aynı tam yöntemle** yeniden
tarandı; 114.972 satır daha Wikipedia kayıtlarının içinde çıktı:

| Sınıf | Satır | Satır payı | Bayt | Bayt payı | uzunluk p10/p50/p90 |
|---|---:|---:|---:|---:|---|
| (a) Wikipedia | 1.357.984 | **%90,402** | 430.400.365 | **%94,012** | 65 / 205 / 699 |
| (b) yalnız mC4 | 1.504 | %0,100 | 223.365 | %0,049 | 58 / 76 / 295 |
| (c) hiçbiri | 142.677 | %9,498 | 27.190.834 | %5,939 | 57 / 82 / 378 |

Kalan %5,9: 142.677 kısa satır (ortanca 82 bayt) — kategori listeleri, oyuncu/künye
listeleri, taslak cümleler, kaynakça satırları; tipi yine Wikipedia, ama bu dökümde yok.

**Doğrulama.** Rastgele **2.000 satır** (tohum 20260919), aynı geçişte bağımsız bir
Aho-Corasick otomatıyla **her kayda** karşı tam alt dizgi olarak da arandı. Gerçek değer:
1.651 wikipedia, 1 yalnız mC4, 348 hiçbiri. Çıpa yöntemi: kesinlik **1,0000**, duyarlılık
**1,0000** (kaba kuvvetle birebir aynı). ≥ %95 gölge kuralı tam içermeye karşı: kesinlik
**0,9952**, duyarlılık **1,0000** — 8 yanlış pozitifin hepsi gerçek yakın kopya (toplayıcının
`clean_wiki_text`'i `'''kalın'''`, `[[bağ|metin]]`, `<ref>` temizliyor), gürültü değil.

**Süre.** Tek süreç, tepe bellek ~1,6 GB: satır hazırlığı 29 sn · ana tarama **1.611 sn**
(26,9 dk) · kalıntının tipografi taraması 2.187 sn (36,5 dk) · raporlar ~60 sn →
**toplam ≈ 64 dk** (12,81 GB + 458 MB). Betikler ve çıktılar:
`var/olcum-2026-09-19/task-038/`.

**Kurucuya öneri (karar kurucunun).** `tr_corpus` "kökeni bilinmiyor" değil: baytının
**%94,0'ı** harfi harfine, `wiki_oscar`'ın zaten taşıdığı Türkçe Wikipedia metni
(CC BY-SA 3.0 + GFDL, ticari olmayan kullanımda `cleared`). Önerim: kaynak kaydını
**`unknown` bırakmak** — v4 bu satırları zaten atıyor ve aynı metin `wiki_oscar`'da bütün
madde olarak duruyor, dolayısıyla durumu değiştirmenin kazancı yok — ama bu belgeye şu
yazılsın: `tr_corpus`'un %94'ünde hak sorusu Wikipedia sorusudur; ileride `tr_corpus` geri
istenirse Wikipedia'da geçen pay `wiki_oscar` şartları altında kabul edilebilir, %5,9'luk
kalıntı dışarıda kalır.
