# Hacim planı — sonraki tokenler nereden gelecek (TASK-013)

**Tarih:** 2026-09-19 · **Hazırlayan:** Derlem oturumu (Claude) · **Karar:** kurucu ·
**Kart:** [TASK-013](gorevler/TASK-013-hacim-plani.md) ·
**Dayanak:** [hak_kanit_paketi_2026_09.md](hak_kanit_paketi_2026_09.md) (S2 kararı),
[TASK-016](gorevler/TASK-016-parent-composition-by-raw-source-document.md) (kaynak başına bayt),
[TASK-023](gorevler/TASK-023-licence-notes-for-turkish-hugging-face.md) + `docs/haklar/hf-*.md`
(altı lisans notu), [belge_sinirlari_politikasi.md](belge_sinirlari_politikasi.md) (alım kuralı),
[plan_2026_09.md](plan_2026_09.md) (Faz 2/4), [backup_restore.md](backup_restore.md),
[ham_arsiv_faz2_kaynaklari.md](ham_arsiv_faz2_kaynaklari.md).

**Bu bir plandır. Hiçbir şey indirilmedi, hiçbir toplayıcı çalıştırılmadı, hiçbir servis
başlatılmadı.** Aşağıdaki her indirme, disk kullanımı ve alım işi ayrı bir kurucu
go/no-go'suna bağlıdır (§6). Token sayıları rafın bayt çevrimidir (5,405 bayt/token),
tamga ile ölçülmemiştir ve geçtikleri her yerde **kestirim** olarak işaretlidir.

---

## 1. Bugünkü hacim: v4 → token → açık

| Büyüklük | Sayı | Nasıl |
|---|---|---|
| Ana korpus (Faz-2, `9826d58e…`) | 13.569.773.056 bayt / 6.027.968 satır | ölçüldü |
| Temiz aday **v3** (`83dcac77…`) | **11.896.793.726 bayt** / 5.827.650 satır | ölçüldü, v3 manifesti |
| v3 token | ~2,20 milyar | **kestirim** (5,405 bayt/token; 2026-09-19 mektubu §1) |
| S2 atılacak satır listesi (v3 üzerinde) | 1.529.744 kayıt (`s2-droplist-v3-2026-09-19.jsonl`) | ölçüldü, dosya sayımı |
| Temiz aday **v4** (S2 süzgeci sonrası) | **≈ 11,26 GB beklenen** (v3 baytının %5,39'u düşer) | **beklenen — v4 manifesti henüz yok** |
| v4 token | **≈ 2,08 milyar** | **kestirim** (beklenen bayt ÷ 5,405) |

**v4 manifestinin durumu (2026-09-19 23:58'de kontrol edildi):** üretim sürüyor;
`var/derived/` altında yalnız geçici çıktı (`…_v4.txt.dv6fbr8d.tmp`, 2,91 GB, 23:56) ve
biten held-out parçası (`…_v4_heldout.txt`, 4.323.687 bayt / 1.641 satır; 598 satır S2
listesiyle atıldı) var. `…_clean_candidate_v4.txt.manifest.json` **yok**. Manifest çıkınca
bu bölümdeki iki satır (`output_byte_size` ve ondan türeyen token kestirimi) **ölçülmüş**
sayılarla değiştirilmeli; §3'teki dilim boyu da o sayıya göre bir kez yeniden hesaplanır.
Beklenen %5,39'un dayanağı: S2'nin ana korpus üzerinde **ölçülen** bedeli %5,33
(13.569.773.056 → 12.847.009.148 bayt, TASK-016) ve aynı listenin v3'e uygulanması.

### Açık (kestirim)

| Hedef | Token | v4'ten açık | Açığın temiz metin karşılığı |
|---|---|---|---|
| Raf tek koşu hedefi | 2,60 milyar | **0,52 milyar** | **≈ 2,80 GB** |
| **2× pay** (etiketli varsayım; raf onaylamadı) | 5,20 milyar | **3,12 milyar** | **≈ 16,85 GB** |

2× payı Derlem'in koyduğu bir tampondur, rafın istediği bir sayı değildir; gerekçesi
§5'teki üç sorunun cevabı (dil başına hedef, gerçek tamga, paketleme) gelene kadar
tek-koşu hedefine tam oturan bir dilim almanın riskli olmasıdır. Raf "2,6 yeter, tek
epoch" derse §3'ün küçük dilimi yeter.

**Ham metin karşılığı.** v3 üretiminde girdinin **%87,7'si** çıktıya kaldı
(13.569.773.056 → 11.896.793.726 + 4.630.115 held-out; ölçüldü). Yeni kaynaklarda bu oran
**ölçülmedi** — FineWeb-2 yayıncının kendi süzgecinden geçtiği için daha yüksek, mC4
kalanında daha düşük olabilir. Aynı oran kullanılırsa:

- 2,6 milyara ulaşmak için ≈ **3,19 GB net yeni ham metin**
- 2× pay için ≈ **19,21 GB net yeni ham metin**

**Hedef sayısının kendisi teyit ister.** "~2,6 milyar / 130 M model" rakamı TASK-013
kartına rafın 2026-09-17 mektubunun §5'inden aktarılmıştır; o mektubun kopyası bu depoda
yok (`docs/mektuplar/` altındakiler Derlem → raf yönünde). Teyidi §5'te isteniyor.

---

## 2. Aday kaynaklar — net yeni token / lisans riski sırası

Sıralama ve lisans durumları TASK-023 tablosundan ve kurucunun 2026-09-19 kararından gelir
(FineWeb-2 `cleared` ticari olmayan; HPLT için risk kabulü **verilmedi**; CulturaX
izlenmez; OSCAR `blocked`).

| # | Kaynak | Lisans (karar) | Beklenen net yeni token | İndirme | Örtüşme | Karar |
|---|---|---|---|---|---|---|
| 1 | `HuggingFaceFW/fineweb-2` `tur_Latn` `af9c133…` | **`cleared`** (ticari olmayan; `wiki_oscar` kabulleri genişletildi) | ~53 milyar (kestirim) | 134,79 GB parquet (30 parça) | doğrudan yok; CC kökeni ortak, **ölçülmedi** | **Aday #1** |
| 2 | `allenai/c4` mC4 `tr` kalanı `1588ec4…` | **`cleared`** (ticari olmayan; mevcut karar) | ~44 milyar (kestirim; ~50'nin %89'u) | 110,00 GB gzip (1.024 dosya) | ilk ~9,75 M belge elimizde (%11) | Aday #2 |
| 3 | `wikimedia/wikipedia` `20231101.tr` `b04c8d1…` | **`cleared`** (ticari olmayan) | **≈ 0** | 0,55 GB parquet | **tam** (aynı config `wiki_oscar`'da) | **Pilot** (yöntem ölçümü) |
| 4 | `HPLT/HPLT2.0_cleaned` `tur_Latn` `d1324a5…` | **`restricted`** — risk kabulü verilmedi | ~70 milyar (kestirim) | 262,23 GB parquet | farklı köken (Internet Archive) | **Hayır** (karar değişirse yeniden bakılır) |
| 5 | `uonlp/CulturaX` `tr` | `restricted`; izlenmez | ~64 milyar, çoğu #1/#2 ile aynı | gated (form) | mC4 payı doğrudan örtüşür | **Hayır** |
| 6 | `oscar-corpus/OSCAR-2301` `tr` | **`blocked`** (erişim askıda) | 0 (alınamaz) | — | — | **Hayır** |

### 2.1 FineWeb-2 `tur_Latn` — aday #1

- **Lisans (karar):** ODC-By 1.0 + Common Crawl kullanım şartları. Kurucu 2026-09-19'da
  `wiki_oscar` kabullerini (atıf, Common Crawl tazmin maddesi, ticari olmayan kapsam) bu
  veri setine **genişletti** → alındığında `cleared` (ticari olmayan). Ek yükümlülük:
  yayıncının PII / site kaldırma talepleri Derlem'in takedown yoluna bağlanır
  ([hf-fineweb-2.md](haklar/hf-fineweb-2.md)).
- **Beklenen net yeni (kestirim + dayanak):** kart `tur_Latn` için 284,52 GB UTF-8 /
  41,93 milyar kelime / 95,13 M belge diyor → 5,405 bayt/token ile ~53 milyar token. Dosya
  ölçümü (HF ağaç API, lisans notunda): train 30 parquet = 134.789.283.815 bayt → parça
  başına ortalama **4,49 GB parquet ≈ 9,48 GB metin** (284,52 / 134,79 = 2,11 metin/parquet).
- **Örtüşme:** ana korpusta FineWeb-2 kaydı yok; ama mC4-tr ile aynı Common Crawl kökenli.
  Oran **ölçülmedi**. Ölçüm yolu TASK-024'ün net yeni pay yöntemidir: alınan dilim kaynak
  olarak kaydedilir, normalize tekrar kapısı aile dışı kopyaları sayar, net yeni pay =
  1 − `external_duplicate_count` / belge sayısı. Pilotta yöntem doğrulandıktan sonra aynı
  ölçüm ilk FineWeb-2 parçasında tekrarlanır ve dilim boyu ona göre düzeltilir.
- **İndirme ve disk:** §4'teki tablo. Kural: her yeni ham bayt en az **üç kopya** tutar —
  (1) `IMPORT_ROOT` altındaki alım dosyası, (2) içerik adresli object store kopyası,
  (3) türetilen temiz aday. Sıkıştırılmış indirme (parquet) dördüncü kopyadır, dönüşümden
  sonra silinebilir.
- **Alım yolu:** TASK-032 (`import_hf_dataset`, onay ister): sabit sürüm `af9c133…`,
  parça bazında SHA + devam, **bir kayıt = bir belge**, paragraf sonları JSONL'de korunur,
  txt ihracında tek boşluğa iner
  ([belge_sinirlari_politikasi.md](belge_sinirlari_politikasi.md) §4). `mc4_scraper.py`
  yeniden kullanılmaz: sabit sürüm vermiyor ve toplayıcının `clean_and_normalize`'ı
  paragraf sonlarını siliyor.
- **Temizlik bedeli (ölçülen orandan):** 3,4 saat / 13,57 GB = **15,0 dk/GB**; fastText
  dil listesi 25 dk / 13,5 GB = **1,85 dk/GB**.

### 2.2 mC4-tr kalanı — aday #2

- **Lisans (karar):** ODC-BY + Common Crawl şartları; `wiki_oscar` için verilen S2
  kararının **aynısı**, yeni kabul gerekmiyor. `cleared` (ticari olmayan).
- **Beklenen net yeni:** akışın ilk ~9,75 M belgesi (`sources.json` `max_docs`)
  `wiki_oscar`'da; kartın `tr` alt kümesi tahminen 87,6 M satır. Net yeni ≈ **78 M belge**,
  ~44 milyar token (kestirim). Ölçülen dosya boyutu 110.002.674.567 bayt gzip / 1.024
  dosya → dosya başına ortalama **107 MB gzip ≈ 268 MB metin** (274 GB metin kestiriminden).
- **Örtüşme:** **kısmen ve bilinen kısmı**: akış sırası deterministik olduğu için elimizdeki
  parça "ilk N belge"dir. Ama hangi dosya numaralarının ilk 9,75 M belgeye denk geldiği
  **ölçülmedi**; güvenli yol yüksek numaralı dosyalardan başlamaktır. Kalan örtüşme
  (tekrarlayan sayfalar) yine TASK-024 yöntemiyle ölçülür.
- **Disk / alım / temizlik:** FineWeb-2 ile aynı kurallar, aynı 3× kuralı, aynı dk/GB
  oranları.
- **Neden #2:** aynı lisans sınıfı, ama dilim seçimi daha karışık (örtüşen başlangıcı
  atlamak gerekiyor) ve yayıncı süzgeci daha zayıf. Plan gereği mC4-tr, Vikipedi-tr'nin
  net yeni token'ı ölçülmeden kaydedilmez ([plan_2026_09.md](plan_2026_09.md), Faz 4 notu).

### 2.3 Vikipedi-tr — pilot; hacim değil yöntem

- **Lisans (karar):** CC BY-SA 3.0 + GFDL; atıf ve share-alike kabulü S2 kararında zaten
  var. `cleared` (ticari olmayan).
- **Beklenen net yeni:** **≈ 0.** Aynı config (`20231101.tr`) `wiki_oscar`'ın içinde
  (kayıtların %9,4'ü `source=wikipedia`). Kart: 534.988 makale / 997.254.242 bayt metin /
  552.923.659 bayt indirme (2 parquet).
- **Değeri:** küçük, sabit sürümlü, tamamen temiz bir referansla **örtüşme ölçüm yönteminin
  kendisini** ölçmek. Beklenen sonuç "net yeni ≈ %0"; yöntem bunu göstermiyorsa yöntem
  yanlıştır ve büyük dilime güvenilemez.
- **Disk:** 0,55 GB parquet + ≈ 1,05 GB JSONL alım nesnesi + ≈ 1,05 GB object store
  kopyası ≈ **2,7 GB** (pilot türev aday üretmiyor; 3× kuralının üçüncü ayağı yok).
- **Temizlik:** hat koşulursa 1,0 GB × 15,0 dk/GB ≈ **15 dk** (+ fastText ≈ 2 dk).
- **Alım yolu:** TASK-024 mevcut yerel dosya alımını kullanır (yeni kod yok) ama kaydı
  **txt değil JSONL** yazmalıdır, yoksa paragraf sonları boşluğa iner
  ([belge_sinirlari_politikasi.md](belge_sinirlari_politikasi.md) §3, (a) satırı).

### 2.4 HPLT — `restricted`, bugün hacim değil

En yüksek net yeni beklentisi (~70 milyar token, farklı köken: Internet Archive), ama
yayıncı içerik için hak vermiyor ("metin bizim değil; yalnız paketleme CC0"). Kurucu
2026-09-19'da risk kabulü **vermedi** → hacim planında **sıfır** sayılır. Karar değişirse
sıra #1'in önüne geçer; o durumda v1.2 değil v2.0 alınır (veri HF deposunda, sabit sürüm
`d1324a5…`; v1.2'nin dosyaları HF dışında).

### 2.5 CulturaX ve OSCAR — kapsam dışı

CulturaX'in kendi lisansı yok, iki üst kaynağa yönlendiriyor; hacminin büyük kısmı zaten
#1 + #2 ile daha temiz şartlarla alınabiliyor. OSCAR'ın erişimi askıda (`blocked`);
açılsa bile içerik lisansı yok. İkisi de izlenmiyor.

### 2.6 Arşivdeki toplayıcılar — hacim kaldıracı değil

TDK / TTK / DergiPark / TRT toplayıcılarının kendi README'lerindeki verim iddiası yüz MB
mertebesindedir (TDK ~50 MB, TTK ~200 MB); TRT zaten `blocked`. Hacim planında **kapsam
dışıdır**; yeniden toplama ancak belge sınırı kazanmak için gündeme gelir, o da ayrı bir
karardır.

---

## 3. Önerilen sıra

**Adım 1 — Vikipedi-tr pilotu (TASK-024).** Küçük (0,55 GB indirme, ≈ 2,7 GB tepe disk),
lisansı tamamen kapanmış, net yeni beklentisi ≈ 0. Ölçtüğü şey hacim değil, **örtüşme
ölçüm yöntemi** ile alım/PII/parmak izi süreleridir (ikincisi TASK-032'nin
boyutlandırmasına girer). Claude günü: 1 (kartta yazılı). Makine: indirme süresi
**ölçülmedi** (ağ hızı ölçülmedi); hat koşulursa ≈ 15 dk + 2 dk.

**Adım 2 — FineWeb-2 `tur_Latn`'den sınırlı ilk dilim.** Pilotun net yeni pay sayısı
geldikten sonra, TASK-032 ile sabit sürümden **parça bazında** alınır.

Dilim boyutlandırması (hepsi kestirim; varsayım: temizlikte %87,7 bayt kalır, net yeni pay
%100 — pilot ve ilk parça bu payı ölçünce düzeltilir):

| Dilim | parquet | Metin | Temiz | Yeni token | v4 ile toplam | Hedefin katı |
|---|---|---|---|---|---|---|
| 1 parça | 4,49 GB | 9,48 GB | 8,31 GB | ~1,54 milyar | ~3,62 milyar | 1,39× |
| **2 parça (önerilen)** | **8,99 GB** | **18,97 GB** | **16,63 GB** | **~3,08 milyar** | **~5,16 milyar** | **1,98×** |
| 3 parça | 13,48 GB | 28,45 GB | 24,95 GB | ~4,62 milyar | ~6,70 milyar | 2,58× |

**Öneri: 2 parça = 8,99 GB indirme.** 2,6 milyar hedefini 1 parça zaten geçiyor; 2 parça
2× payı (5,20 milyar) %99 oranında karşılıyor. 3 parça **diske sığmıyor** (§4).

Duyarlılık: net yeni pay %100 değil de %80 çıkarsa 2 parça ~2,46 milyar yeni token verir
(toplam ~4,55 milyar, 1,75×); o durumda ya 3. parça için disk kararı gerekir ya da 2× payı
düşürülür. Pilotun ilk sırada olmasının sebebi budur.

**Saat olarak (ölçülen oranlardan türetilmiş kestirim):**

| İş | Girdi | Süre |
|---|---|---|
| fastText dil listesi, yalnız yeni dilim | 18,97 GB | ≈ 35 dk |
| Temiz aday hattı, yalnız yeni dilim | 18,97 GB | ≈ 4,8 saat |
| **Temiz aday hattı, v4 + yeni dilim ortak geçiş** | 30,23 GB | **≈ 7,6 saat** |
| fastText, ortak geçiş | 30,23 GB | ≈ 56 dk |
| İndirme | 8,99 GB | **ölçülmedi** (ağ hızı ölçülmedi) |

Ortak geçiş şarttır: yeni kaynak v4 ile aynı adayda birleşecekse tekilleştirme iki akış
için ortak koşmalıdır (v3 üretiminde de öyleydi). Yani gerçek maliyet ≈ **7,6 saat makine +
~1 saat dil listesi**, ve sonucu **v5** adayıdır — 200 örnek incelemesi ve held-out
yeniden üretilir. Bu bedel v2 teslimatından **sonra** ödenmelidir; v4 teslimatını
geciktirmez.

**Adım 3 — mC4-tr kalanı.** Yalnız FineWeb-2 diliminin net yeni payı ve kalite süzgeci
atma oranı ölçüldükten sonra, ayrı go/no-go ile. Yüksek numaralı dosyalardan başlanır;
19 GB metin için ≈ 71 dosya ≈ 7,6 GB gzip.

---

## 4. Disk ve yedek — kurucu kararı gerekiyor

**Ölçüm:** `df -h /c` (Git Bash), **2026-09-19 23:55**: C: 933 GB, kullanılan 822 GB,
**boş 112 GB** (%89 dolu). 23:58'de aynı sayı. (Kartın notundaki "~115 GB / 23:30" ile
fark, v4 üretiminin o sırada yazdığı geçici dosyadır.)

**3× kuralı.** Her yeni ham bayt en az üç yerde durur: `IMPORT_ROOT` alım dosyası +
içerik adresli object store kopyası + türetilen temiz aday. `wiki_oscar`'da kullanılan
**sabit bağ** (hard link) hilesi ilk iki kopyayı tek dosyaya indirir (aynı disk; alım
yalnız okur); HF alımında da uygulanabilir, kazancı ≈ 20 GB.

Önerilen dilim (FineWeb-2, 2 parça) için tepe disk:

| Kalem | Bayt (kestirim) |
|---|---|
| parquet indirme (2 parça) | 8,99 GB |
| JSONL alım nesnesi (`IMPORT_ROOT`; metin + ~%5 JSON çerçevesi) | ≈ 19,9 GB |
| object store kopyası | ≈ 19,9 GB |
| birleşik aday v5 (v4 11,26 + yeni temiz 16,63) | ≈ 28,0 GB |
| **tepe toplam** | **≈ 76,8 GB** |
| parquet dönüşümden sonra silinirse | ≈ 67,8 GB |
| sabit bağ da kullanılırsa | ≈ 47,9 GB |

112 GB boş diske göre **2 parça sığar** (kalan ≈ 35–64 GB). **3 parça ≈ 109,6 GB ister,
yani sığmaz**: 3. parça ancak yeni disk ya da eski türevlerin (v3 çıktısı, v4 geçici
dosyaları, atma raporları) temizlenmesiyle mümkündür. Bu planda disk, lisanstan **daha
bağlayıcı** kısıttır.

### Yedek kararı (açık soru)

**Bugünkü durum ([backup_restore.md](backup_restore.md)):** son yedek **2026-08-30**,
şifresiz dump, nesne aynasına 0 yeni nesne. v3 nesneleri, 17 Eylül'de geri konan 422 nesne
ve beş ham kaynak **hiçbir yedekte yok**; hedef RPO 24 saat. OneDrive "Files On-Demand"
294 nesneyi (24,61 GB) yalnızca-buluta taşıdı — yerel ikinci kopya fiilen yok ve her
tatbikat 24,6 GB indiriyor. Ham arşiv (24,65 GB) **bilerek yedek dışı** (kurucu kararı
2026-09-17).

**Karar gereken:** onlarca GB'lık yeni HF ham verisi yedek **içinde** mi **dışında** mı?

| Yol | Bedeli | Notu |
|---|---|---|
| **Dışarıda** (ham arşiv gibi) | Kayıpta yeniden indirme (8,99 GB parquet) + dönüşüm + ≈ 7,6 saat hat | Ham arşivden farkı: **yeniden üretilebilir** — sabit sürüm SHA'sı ve manifest var, kaynak HF'de duruyor |
| **İçeride** | OneDrive aynası ≈ +20 GB; her tatbikat o baytları da indiriyor; kota ve süre artar | Tek kazanç: yayıncı sürümü kaldırırsa kopya elde kalır (olasılık **ölçülmedi**) |

**Derlem önerisi (karar kurucunun):** yeni HF **ham** nesneleri yedek **dışında** (sabit
sürümden yeniden üretilebilir; manifest bunu kanıtlar), ama dondurulmuş bir sürüme giren
**türev** nesneler (v5 adayı, ihracat dosyaları, sürüm manifesti) yedek **içinde** —
bunların yeniden üretimi 7,6 saat makine + yeni bir 200 örnek incelemesi demektir. Ayrıca
duran öneri: ilk ihracattan önce en az bir taze şifreli yedek (TASK-010a).

---

## 5. Rafa sorulacaklar (sonraki mektuba)

1. **Hedef token, dil başına.** Bugün elimizdeki tek sayı TASK-013 kartına aktarılmış
   "~2,6 milyar, 130 M model, tek koşu". (a) Bu sayı hâlâ geçerli mi? (b) Türkçe dışında
   bir dil hedefleniyorsa dil başına kaç token? (c) Tek epoch mu, birden çok epoch mu —
   yani 2,6 milyarın üstüne pay koyalım mı, koyacaksak kaç katı? Derlem bu planda etiketli
   bir **2× varsayımı** kullandı; onaylanmadıkça varsayımdır ve dilim boyu ona bağlı.
2. **Tamga (tokenizer).** 5,405 bayt/token rafın çevrimidir ve bu belgedeki her token
   sayısı ona dayanır. Eğitimde kullanılacak tamga dosyası/kimliği verilirse Derlem gerçek
   sayımı manifeste yazar (TASK-033). Ek soru: bu oran FineWeb-2 web metninde de geçerli
   mi, yoksa farklı mı düşüyor?
3. **Paketleme belge sınırını istiyor mu.** Soru zaten yazıldı ve burada tekrarlanmıyor:
   [belge_sinirlari_politikasi.md](belge_sinirlari_politikasi.md) **§6** ("Rafa soru"),
   olduğu gibi sonraki mektuba girer.

---

## 6. Kurucu go/no-go listesi

Hiçbiri onaysız başlamaz. Sıra yukarıdan aşağıdır.

| # | Karar | Ne için | Sayı |
|---|---|---|---|
| 1 | **Vikipedi-tr pilotu (TASK-024)**: indirme + disk + kaynak kaydı | Örtüşme ölçüm yöntemini ölçmek | 0,55 GB indirme; ≈ 2,7 GB disk; 1 Claude günü |
| 2 | **Yedek kapsamı**: yeni HF ham verisi yedek dışında mı? | §4 | dışarıda: 0 GB yedek; içeride: ≈ +20 GB ayna |
| 3 | **TASK-032 kartı** (`import_hf_dataset`) ve bağımlılıkları (TASK-030/031) | Alımın tek meşru yolu | 3 + 2 + 1,5 Claude günü |
| 4 | **FineWeb-2 `tur_Latn` ilk dilimi**: 2 parça, sabit sürüm `af9c133…` | Hacim açığı | 8,99 GB indirme; ≈ 76,8 GB tepe disk; ≈ 7,6 saat + ~1 saat makine |
| 5 | **v5 adayı üretilsin mi** (v4 + yeni dilim, ortak tekilleştirme) | Yeni hacmin teslimata girmesi | 200 örnek incelemesi ve held-out **yeniden** üretilir; v2 teslimatından sonra |
| 6 | **mC4-tr kalanı** — ayrı go/no-go, FineWeb-2 dilimi ölçüldükten sonra | Hacim açığı (yedek yol) | ≈ 7,6 GB gzip / ≈ 71 dosya (19 GB metin için) |
| 7 | **HPLT risk kabulü** — bugün **hayır** | Karar değişirse #1'in önüne geçer | ~70 milyar token (kestirim) |
| 8 | **3. parça için disk** (yeni disk ya da türev temizliği) | 2× payın güvenli tarafı | +32,8 GB ister; bugün yok |
| 9 | Bilgi için, kapsam dışı: CulturaX, OSCAR, arşiv toplayıcıları (TDK/TTK/DergiPark/TRT) | — | hacim kaldıracı değil |

---

## Kaynaklar

| Bilgi | Kaynak |
|---|---|
| v3 bayt/satır/SHA, atılanlar, 3,4 saat, fastText ~25 dk | `var/derived/…_v3.txt.manifest.json`; [2026-09-19 mektubu](mektuplar/2026-09-19-derlem-raf-v3-uretildi.md) §1; [2026-09-18 mektubu](mektuplar/2026-09-18-derlem-raf-kararlar-ve-v3.md) §3 |
| v4 durumu (manifest yok), held-out v4, S2 listesi | `var/derived/` dizin listesi 2026-09-19 23:58; `…_v4_heldout.txt.manifest.json`; `s2-droplist-v3-2026-09-19.jsonl` (1.529.744 satır) |
| S2 kararı, %94,67, kaynak başına hak durumu | [hak_kanit_paketi_2026_09.md](hak_kanit_paketi_2026_09.md) |
| Kaynak başına bayt, senaryo tablosu | [TASK-016](gorevler/TASK-016-parent-composition-by-raw-source-document.md) |
| Veri seti lisansları, sabit sürümler, boyutlar, dosya sayıları | `docs/haklar/hf-fineweb-2.md`, `hf-allenai-c4.md`, `hf-wikimedia-wikipedia.md`, `hf-hplt-monolingual.md`, `hf-culturax.md`, `hf-oscar-2301.md` |
| Bir kayıt = bir belge, JSONL'de paragraf sonu, §6 raf sorusu | [belge_sinirlari_politikasi.md](belge_sinirlari_politikasi.md) |
| Alım işi (sabit sürüm, devam, ölçütler); örtüşme yöntemi | [TASK-032](gorevler/TASK-032-in-app-import-hf-dataset-job.md); [TASK-024](gorevler/TASK-024-overlap-pilot-one-pinned-turkish-wikipedia.md) |
| Yedek durumu, OneDrive uyarıları, ham arşiv kararı | [backup_restore.md](backup_restore.md), [ham_arsiv_faz2_kaynaklari.md](ham_arsiv_faz2_kaynaklari.md) |
| Boş disk | `df -h /c`, 2026-09-19 23:55: 112 GB boş |
| Faz 2/4 sırası, "Vikipedi-tr ölçülmeden mC4-tr yok" | [plan_2026_09.md](plan_2026_09.md) |
