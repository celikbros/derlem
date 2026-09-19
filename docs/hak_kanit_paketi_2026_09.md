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
