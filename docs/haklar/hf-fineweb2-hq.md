# `epfml/FineWeb2-HQ` (config `tur_Latn`) — lisans ve olgu notu

**Tarih:** 2026-10-03 · **Hazırlayan:** Derlem oturumu (Claude) · **Karar:** kurucu
Hukuki görüş değildir; şartlar okunduğu gibi kaydedilmiştir. Hiçbir veri indirilmedi (yalnız
veri kartı, HF API üstverisi, datasets-server özeti, makale ve lisans sayfaları okundu).
Doğrulanamayan her şey "doğrulanamadı" diye işaretlidir.

| Alan | Değer |
|---|---|
| Veri seti | https://huggingface.co/datasets/epfml/FineWeb2-HQ (yayıncı: EPFL / `epfml`; üst veri seti `HuggingFaceFW/fineweb-2` — yayıncı farklı) |
| Türkçe alt küme | config `tur_Latn` (yalnız `train` bölümü; `test` yok; `tur_Latn/*` altında 105 parquet) |
| Sabit sürüm | repo commit `c0c06e94fd3a44ae9e802b2b0fc533817601eb5e` (HF API `sha`; `lastModified` 2025-02-19T21:39:01Z; `createdAt` 2025-02-17T09:55:30Z) |
| Türediği FineWeb-2 sürümü | **Kart yazmıyor** (kart: *"Being a subset of FineWeb2, this data covers websites over the 2013-2024 time period."*). Tarih çıkarımı (kartta değil): HQ 2025-02-19'da son değişti; FineWeb-2'nin v2.0.0'ı 2024-12-08, v2.0.1'i 2025-01-08, v2.1.0'ı 2025-06-27 → HQ en çok v2.0.0/v2.0.1'den türemiş olabilir. **Doğrulanamadı.** |
| Veri kartı lisansı | `odc-by` (kart YAML ve API `cardData.license`) — ODC-By 1.0 |
| İçerik lisansı | Ayrı içerik lisansı **yok**; kart FineWeb-2 ile aynı ODC-By 1.0 + Common Crawl kullanım şartlarını söylüyor. Sayfa sahiplerinin telifi bu lisanstan bağımsız (aşağıda) |
| Erişim | açık (API `gated: false`, `private: false`) |
| Türkçe boyut | **8.578.808 belge** (kart tablosu ve datasets-server `num_rows` aynı); **105 parquet = 107.323.203.587 bayt** (HF ağaç API toplamı = datasets-server `num_bytes_parquet_files`; kart "Disk size": `100G`); datasets-server bellek tahmini `num_bytes_memory` = 191.356.231.817 bayt (embeddings dahil, float64). **Metin baytı ve kelime sayısı kartta ve datasets-server'da yok → doğrulanamadı** |
| Sütun sayısı | 13 (datasets-server `num_columns`; aşağıdaki liste) |
| Öneri `rights_status` | **`cleared` (ticari olmayan)** — koşullu; kurucu kararı gerekir (§8) |
| Ana korpusta zaten var mı? | **Doğrudan hayır.** Dolaylı: FineWeb-2'nin alt kümesi → aynı Common Crawl kökeni; `wiki_oscar` (mC4 %90,6 + Wikipedia %9,4) ile örtüşme **ölçülmedi** (§7) |

## 1. Lisans: kart ve içerik ayrı

- Kart YAML: `license: odc-by`.
- Kart "Licensing Information" (README, okundu 2026-10-03): *"Like FineWeb2, this dataset is
  released under Open Data Commons Attribution License (ODC-By) v1.0 license and is subject to
  CommonCrawl's Terms of Use."*
- Kart "Dataset summary": *"FineWeb2-HQ is a high-quality, model-filtered pretraining dataset
  derived as a subset of FineWeb2, spanning 20 languages."*
- Kartta ayrıca bir "içerik" lisansı, sayfa sahipleri için telif beyanı ya da kullanım amacı
  cümlesi **yok** (FineWeb-2 kartındaki "primarily intended to be used as a research artifact"
  cümlesi HQ kartında geçmiyor). Üst veri setinin içerik şartı olarak okunan: Common Crawl
  kullanım şartları (son güncelleme 2024-03-07; okundu 2026-10-03): *"BY USING THE CRAWLED
  CONTENT, YOU AGREE TO RESPECT THE COPYRIGHTS AND OTHER APPLICABLE RIGHTS OF THIRD PARTIES IN
  AND TO THE MATERIAL CONTAINED THEREIN."*; *"CC strongly recommends that you obtain the advice
  of legal counsel before making any use, including commercial use, of the Service and/or the
  Crawled Content."*; Tazmin (§9): kullanıcı, *"use of Crawled Content in connection with
  artificial intelligence, machine learning, or other similar technologies, including, without
  limitation, large language models and neural networks"* ile bağlantılı üçüncü taraf
  iddialarında Common Crawl'ı tazmin eder.
- ODC-BY 1.0 metin alıntıları (§4.2 lisans/URI, §4.3 bildirim; share-alike yok): bkz.
  [hf-allenai-c4.md](hf-allenai-c4.md); bu notta yeniden okunmadı.
- Makale (arXiv:2502.10361, HTML sürümü okundu; sayfa "v2 ... 19 Feb 2026", lisans CC BY 4.0),
  Ek H.1: sınıflandırıcı eğitim verilerinin lisansları — Aya Collection, Aya Dataset,
  OpenAssistant-2, Include-Base-44: Apache 2.0; çevrilmiş çok dilli MMLU: MIT; ön eğitim
  verisi FineWeb-2: ODC-By; XLM-RoBERTa: MIT. Bunlar yalnız **sınıflandırıcının** eğitim
  girdisidir; yayımlanan metin satırları FineWeb-2'den gelir, bu lisanslar satır içeriğine
  uygulanmaz (kart bu ayrımı açıkça yazmıyor; okuma budur).

## 2. Sürüm sabitleme

- Alım bu sha'ya sabitlenmeli: `c0c06e94fd3a44ae9e802b2b0fc533817601eb5e`.
- Kart sürüm/değişiklik günlüğü tutmuyor; FineWeb-2 sürümü (v2.0.0, v2.0.1 vb.) belirtilmemiş
  (yukarıda). Dump listesi: kart "2013-2024" diyor; tam dump listesi **doğrulanamadı** (kartın
  örnek satırı `CC-MAIN-2014-10`).
- Kaynak kodu: https://github.com/epfml/fineweb2-hq (kartın ve makalenin işaret ettiği);
  README'sinde yayımlanan veri için *"MLP MKC+ with a 10% retention rate"* yazıyor.

## 3. `tur_Latn` içeriği ve sütunlar

Türkçe: 8.578.808 belge, 105 parquet (`tur_Latn/000_00000.parquet` … `000_00104.parquet`;
ilk dosya 1.068.500.812 bayt, son 871.969.421 bayt; ortalama ≈ 1,02 GB). Belge başına parquet
≈ 12,5 KB.

Sütunlar (datasets-server `info` şeması; tanımlar kartlardan):

| Sütun | Tür | Tanım |
|---|---|---|
| `text` | string | FineWeb-2: *"the main text content"* |
| `id` | string | FineWeb-2: *"original unique identifier for this sample from CommonCrawl"* |
| `date` | string | FineWeb-2: *"crawl date (from CommonCrawl)"* |
| `dump` | string | FineWeb-2: *"the CommonCrawl dump this sample was a part of"* |
| `embeddings` | dizi(dizi(float64)) | **HQ'ya özgü.** Kart: *"array of float arrays containing 768-dimensional XLM-RoBERTa embeddings for every 512 token chunk of the tokenized text"* |
| `file_path` | string | FineWeb-2: *"s3 path for the individual CommonCrawl warc file containing this sample"* |
| `language` | string | FineWeb-2: *"ISO 639-3 code for the language of this sample"* |
| `language_score` | float64 | FineWeb-2: *"language prediction score as reported by the GlotLID classifier"* |
| `language_script` | string | FineWeb-2: *"script of the `text`, for example `Latn`"* |
| `minhash_cluster_size` | int64 | FineWeb-2: *"number of samples in the minhash cluster of this sample"* (tekilleştirme kümesi boyutu) |
| `top_langs` | string | FineWeb-2 kartında tanım cümlesi yarım kalmış (*"language-script pairs for which the language classifier"*); örnekte `{"deu_Latn_score": 0.998…}` biçiminde |
| `url` | string | FineWeb-2: *"url to the original page where `text` was present"* |
| `quality_score` | float64 | **HQ'ya özgü.** Kart: *"quality score obtained by the quality classifier"* |

HQ kartı: *"Each data entry includes the original FineWeb2 data fields with the addition of:"*
`quality_score` ve `embeddings`.

### `embeddings` ve indirme hacmi

- **Aynı parquet'in içinde** bir sütun (13 sütunun biri); ayrı dosya yok. Dolayısıyla
  `tur_Latn` indirmek embeddings'i de getirir. Kart, bütün FineWeb-2 için embeddings'i *ayrı*
  bir veri seti olarak da yayımlıyor: `epfml/FineWeb2-embedded` (burada okunmadı).
- Şema float64; belge başına en az bir 768 boyutlu vektör = **en az 6.144 bayt ham** (bellek
  ölçüsünde), uzun belgelerde 512 jeton parçası başına bir vektör daha. Parquet'te yüzen
  sayılar zor sıkışır.
- Ölçülemeyen kısım: parquet'te `text` ile `embeddings` baytlarının ayrı ayrı dağılımı
  (sütun boyutlarını görmek parquet dosya başlığını okumayı gerektirir; yapılmadı).
  **Kaba çıkarım:** belge başına parquet ≈ 12,5 KB; FineWeb-2 `tur_Latn`'da belge başına
  ≈ 1,3 KB sıkıştırılmış (125,53 GB / 95,1 M belge) olduğundan, indirilen baytların **büyük
  kısmı büyük olasılıkla embeddings'tir**. Bu, ölçüm değil çıkarımdır. **Doğrulanamadı.**
- Parquet sütunludur; yalnız `text` (+ üst veri) sütunlarını okumak teoride aralık istekleriyle
  mümkündür (`pyarrow` + `HfFileSystem`), ama bu denenmedi; "indirme hacmini embeddings olmadan
  düşürür" iddiası **doğrulanamadı** — alımdan önce tek dosyada TASK-032 tarzı bir denemeyle
  ölçülmeli.
- Kart/makale uyuşmazlığı: kart *"every 512 token chunk"* diyor; makale (§3.3) *"we considered
  only the first 512 tokens of each document"* ve belge başına tek 768 boyutlu vektör
  (ortalama havuzlama) anlatıyor. Yayımlanan sütunun gerçek şekli **doğrulanamadı**.

## 4. HQ nasıl seçilmiş

Kaynak: veri kartı, makale (Messmer, Sabolčec, Jaggi: *Enhancing Multilingual LLM Pretraining
with Model-Based Data Selection*, arXiv:2502.10361), kod deposu README'si.

- **Ne:** kart: *"the top 10% quality documents of FineWeb2 in each language, based on scores
  assigned by a deep learning classifier trained to identify structured and knowledge-rich
  samples using XLM-RoBERTa embeddings."*
- **Model:** makale §3.3: önceden eğitilmiş `xlm-roberta-base` (279 M parametre); belge
  gömmesi 768 boyutlu (ortalama havuzlama, en çok ilk 512 jeton). Üstüne **tek gizli katmanlı
  MLP**: boyut 256, ReLU, %20 dropout, sigmoid çıkış; 6 epoch, AdamW, ikili çapraz entropi.
  Belge puanı = MLP çıktısı (`quality_score`).
- **Eğitim verisi:** "MKC+": *"up to 80K positive samples"* — Include-Base-44, OpenAssistant-2,
  çevrilmiş MMLU, Aya Dataset ve (örneklenerek) Aya Collection — ve aynı sayıda **rastgele
  FineWeb-2 örneği negatif** olarak ("hedef: yapılandırılmış ve bilgi dolu örnekler"; olumsuz
  sınıfın çoğunun öyle olmadığı varsayılıyor). Makale: *"we created a training dataset for each
  language individually"* → **dile özgü** sınıflandırıcı. Türkçe için hangi pozitif kaynakların
  kaç örnekle kullanıldığı **doğrulanamadı** (makalede dil başına döküm okunmadı).
- **Neyi ödüllendirir:** pozitif örnekler soru-cevap/sınav/talimat verisi olduğu için
  "yapılandırılmış, bilgi yoğun, soru-cevaba benzer" metni; makalenin Ek F'si örnekle gösteriyor.
  (Kendi yorumum: bu, FineWeb-2'nin bilerek *kullanmadığı* türden "altın kaynağa benzerlik"
  süzgeci; FineWeb-2 kartı bunun lehçe/biçem önyargısı riskini anıyor — aşağıda.)
- **Eşik:** *"top 10%"* = belge puanına göre **en yüksek %10'luk dilim** (kod:
  `filter_mlp.py --retention-rate 0.1`; makale: *"we applied a score threshold based on the
  desired retention percentage of documents"*). Mutlak puan eşiği değil, **tutma oranı**.
  Makale ablasyonlarında en iyi eşiğin %10 olduğunu raporluyor (Arapça için %56, Danca için %65
  kullanılmış; yayımlanan 20 dil için kart %10 diyor).
- **Ölçüm notu:** Türkçe HQ 8.578.808 belge; bugünkü FineWeb-2 v2.1.x `tur_Latn` 95.129.129
  belge → oran %9,02, "tam %10" değil. Neden: HQ'nun türediği FineWeb-2 sürümünün belge sayısı
  farklı olabilir (v2.1.0 boyutu artırdı); **doğrulanamadı.**
- **Dile özgü mü:** sınıflandırıcı dil başına ayrı eğitilmiş; kartın dil tablosunda Türkçe
  var.
- **Kalite doğrulaması (kartın beyanı):** 1B parametreli modellerle Çince (CMMLU), Almanca ve
  Fransızca (MMLU) üzerinde ölçülmüş; kart: *"FineWeb2-HQ matches FineWeb2 performance when
  trained with 6x fewer tokens, and outperforms it when fully trained."* **Türkçe için ayrı bir
  değerlendirme kartta yok** → Türkçe kalitesi doğrulanamadı (Derlem kendi örneklem
  değerlendirmesini yapmalı).

## 5. Kartın kendi sınırlama/uyarı cümleleri (aynen)

HQ kartı, "Dataset origin":

> *"FineWeb2 is sourced from the internet at large, it is very likely that some personable
> identifiable information (PII) will be present, even if the FineWeb2 processing has already
> anonymized email addresses and public IP addresses. If you find your own PII and would like
> it removed, please fill out the FineWeb2 PII removal/opt out form."*
>
> *"CommonCrawl respects robots.txt at crawl time, but if you are a webmaster and find your
> website in FineWeb2 and would like to have it removed, you may also use the FineWeb2 PII
> removal/opt out form."*

HQ kartı, "Considerations for Using the Data":

> *"Before using this dataset for training models, we recommend performing additional filtering
> for sensitive content such as PII or harmful content. For the aspects of social impact,
> discussion of biases, and known limitations, we also refer to the FineWeb2 documentation."*

Atıf isteği: *"If you use this dataset in your research or applications, please use the
following citation:"* — `messmer2025multilingdatacomp` (Messmer, Sabolčec, Jaggi, arXiv 2025).

Üst kartın (FineWeb-2) ilgili cümleleri (HQ kartının işaret ettiği "documentation"):

> *"there are still a significant number of documents present in the final dataset that could
> be considered toxic or contain harmful content. As FineWeb2 was sourced from the web as a
> whole, any harmful biases typically present in it may be reproduced on our dataset."*
>
> *"We deliberately avoided using machine learning filtering methods that define text quality
> based on the similarity to a “gold” source such as wikipedia or toxicity classifiers as these
> methods have been known to disproportionately remove content in specific dialects and
> overclassify as toxic text related to specific social identities, respectively."* (Not:
> HQ'nun sınıflandırıcısı bu cümlenin tarif ettiği türden bir "örnek benzerliği" sınıflandırıcısı;
> kart bu gerilimi tartışmıyor.)

Doğruluk garantisi: HQ kartında içeriğin doğruluğu/yasallığı/telif durumu hakkında **garanti ya
da sorumluluk reddi cümlesi yok**; "doğruluk garantisi yok" ifadesi kartta açıkça **geçmiyor**.
Common Crawl şartları ise içeriğin doğruluğuna güvenilmemesini söylüyor (*"you may not rely on
any Crawled Content created or accumulated by CC"*).

## 6. Yükümlülükler (metinden)

| Yükümlülük | Durum |
|---|---|
| Atıf | **Zorunlu** (ODC-BY): lisans/URI ve "içerik epfml/FineWeb2-HQ'dan (FineWeb-2 türevi) alınmıştır" notu — veri kartında ve model künyesinde. Kart ayrıca makale atfı **istiyor** (`messmer2025multilingdatacomp`; yanında FineWeb-2 makalesi Penedo vd. 2025, arXiv:2506.20920 atfı da uygun olur — FineWeb-2 kartı ister). |
| Share-alike | Yok (ODC-By). |
| Yeniden dağıtım | ODC-BY izin verir (atıfla); Derlem ham metni yeniden dağıtmıyor. |
| Tazmin | **Var** — Common Crawl şartları §9; yapay zekâ/LLM eğitimi açıkça sayılmış. |
| Üçüncü taraf telifi | Common Crawl şartlarıyla **kullanıcıda**; sayfa sahiplerinin hakları saklı. |
| Kaldırma (takedown) | Yayıncı **FineWeb2** PII/site kaldırma formunu (https://forms.gle/VyNT3ZAUPZjPuWp39) gösteriyor; epfml'nin kendi ayrı bir kaldırma yolu kartta **yok**. Form kayıtlarının HQ'ya yansıyıp yansımadığı **doğrulanamadı** (HQ sha'sı 2025-02-19'dan beri değişmedi). Derlem, gelen talepleri kendi takedown yoluna bağlamalı. |
| Ticari kullanım | ODC-BY izin verir; Common Crawl hukuk danışmanı önerir. Derlem kapsamı ticari değil. |
| Erişim şartı | Yok (gated değil). |

## 7. Ana korpusumuzla örtüşme

- `wiki_oscar`: mC4-tr (%90,6) + Wikipedia-tr (%9,4). FineWeb-2/HQ: Common Crawl'dan yeni
  çıkarım (kendi metin çıkarma, dil tanıma — GlotLID — ve tekilleştirme hattı), mC4'ten
  türemiyor. İkisi aynı Common Crawl evreninden beslendiği için sayfa düzeyinde örtüşme
  **olası**; **ölçülmedi** (TASK-024 yöntemiyle net-yeni payı ölçülebilir).
- Kapsanan dump'lar: kart "2013-2024" diyor; HQ için tam dump listesi kartta yok
  (**doğrulanamadı**). FineWeb-2 kartı: *"96 CommonCrawl snapshots, spanning the summer of 2013
  to April 2024"*; HQ bunun %10 alt kümesi olduğundan bu aralığın içinde, ama her dump'ı
  kapsadığı **doğrulanamadı**. mC4'ün hangi dump'ları kapsadığı bu notta okunmadı; dönem
  çakışması **doğrulanamadı**.
- İçerik düzeyi: HQ, FineWeb-2'nin alt kümesi → **FineWeb-2'yi alırsak HQ zaten içindedir**
  (varsayım: aynı sürüm; sürüm farkı **doğrulanamadı**). Yani #1 FineWeb-2 ve #8 HQ ayrı
  hacimler değil, iç içe kümelerdir; ikisini birlikte almak çift sayım olur.

## 8. Öneri

**Öneri `rights_status`: `cleared` (ticari olmayan)**, gerekçe: (a) kart lisansı ODC-By 1.0 ve
içerik şartı FineWeb-2 ile **aynı** (ODC-By + Common Crawl ToU) — kurucunun `wiki_oscar` ve
FineWeb-2 için verdiği kabuller (atıf, Common Crawl tazmin maddesi, ticari olmayan kapsam)
sözcük sözcük aynı şartlara denk geliyor; (b) share-alike yok; (c) HQ yalnız bir **seçim**
(sınıflandırıcı puanı + gömme sütunu) ekliyor, yeni metin üretmiyor; sınıflandırıcıyı eğitmekte
kullanılan veri setleri Apache 2.0/MIT. Riskler: Common Crawl tazmini (FineWeb-2'deki ile aynı),
PII kalıntısı (kart "very likely" diyor), sayfa sahiplerinin telifi, kaldırma yolunun
yayıncıya bağlı olması.

**Kurucu kararı gerektiren nokta:** 2026-09-19 tarihli FineWeb-2 (`HuggingFaceFW`) kabulünün,
aynı şartları taşıyan fakat farklı yayıncının (`epfml`) türev alt kümesine ve tazmin/atıf
kabulleriyle birlikte HQ'ya da yazılı olarak genişletilip genişletilmeyeceği.

## Kaynaklar

- https://huggingface.co/datasets/epfml/FineWeb2-HQ
- https://huggingface.co/datasets/epfml/FineWeb2-HQ/raw/main/README.md
- https://huggingface.co/api/datasets/epfml/FineWeb2-HQ (sha, gated, cardData)
- https://huggingface.co/api/datasets/epfml/FineWeb2-HQ/tree/main/tur_Latn (105 parquet, boyutlar)
- https://datasets-server.huggingface.co/size?dataset=epfml/FineWeb2-HQ&config=tur_Latn
- https://datasets-server.huggingface.co/info?dataset=epfml/FineWeb2-HQ&config=tur_Latn (sütun şeması)
- https://arxiv.org/abs/2502.10361 ve https://arxiv.org/html/2502.10361 (makale)
- https://github.com/epfml/fineweb2-hq (README)
- https://huggingface.co/datasets/HuggingFaceFW/fineweb-2/raw/main/README.md (üst kart; sürüm günlüğü, sütun tanımları, önyargı/sınırlama)
- https://opendatacommons.org/licenses/by/1-0/ (bu notta yeniden okunmadı; bkz. hf-allenai-c4.md)
- https://commoncrawl.org/terms-of-use
- https://huggingface.co/datasets/epfml/FineWeb2-embedded (kartın anıştığı ayrı gömme veri seti; okunmadı)

Erişim tarihi: 2026-10-03
