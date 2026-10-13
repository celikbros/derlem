# İTÜ Doğal Dil İşleme Grubu — Araç ve Kaynak Sayfası: Veri Seti Envanteri

Kapsam: İTÜ DDİ (Doğal Dil İşleme) grubunun "Araçlar ve Kaynaklar" sayfasındaki veri setlerinin envanteri. Hiçbir şey indirilmedi; yalnızca sayfalar okundu. Derlem'in kapsamı kurucu kararıyla ticari olmayan araştırmadır.

## 0. Kaynak sayfa ve okuma durumu

- Sayfa okundu, JavaScript ile doldurulmuyor: `https://nlp.itu.edu.tr/araclarkaynaklar` düz metin olarak geldi. Başlığı "Language Resources and Tools for Turkic Languages"; yani yalnız Türkçe değil, Azerbaycan, Kazak, Kırgız, Özbek, Tatar, Türkmen ve Uygur dillerini de kapsıyor.
- İngilizce sürüm: `https://nlp.itu.edu.tr/en/tools-resources` 404 verdi. Doğru adres `https://nlp.itu.edu.tr/en/toolsandresources` (arama sonucundan bulundu, okundu). Aynı içerik `ddi.itu.edu.tr` altında da yansıtılıyor.
- **Sayfa hiçbir kayıt için lisans, erişim yöntemi (indirme/form/e-posta) veya dosya biçimi yazmıyor.** Kayıtlar yalnız bağlantı veriyor; kimi kayıtta boyut var. Bu yüzden aşağıdaki "lisans/erişim/biçim" sütunlarında sayfanın kendisinden gelen bilgi "belirtilmemiş" olarak kalır; ek bilgi yalnız bağlantı verilen sayfa okunabildiyse eklenmiştir ve "(hedef)" diye işaretlenmiştir.
- Sayfanın kapanış notu: "Eğer siz de veri kümelerinizin bu sayfada yer almasını istiyorsanız lütfen bize bildirin" — yani sayfa bir dizindir, İTÜ'nün tek tek lisans verdiği bir dağıtım noktası değildir.
- **Erişilemeyenler:** İTÜ'nün kendi veri sayfası `http://tools.nlp.itu.edu.tr/Datasets` (treebank, PropBank, normalizasyon, NER kaynaklarının asıl adresi) hem http hem https ile bağlantı reddetti (ECONNREFUSED, 160.75.159.5:443). Bu yüzden bu 8 İTÜ-DDİ kaydının lisansı ve erişim biçimi **doğrulanamadı**.
- Tutarsızlık: ITU Web Treebank boyutu Türkçe sayfa okumasında 5.099, İngilizce sürüm okumasında 5.009 cümle çıktı. Sayfalar özetleme aracıyla okunduğu için hangisinin doğru olduğu **doğrulanamadı**; tabloda Türkçe sayfadaki değer (5.099) kullanıldı.
- Sayfadaki iç hata: Kırgızca web derlemesi "kkWaC" etiketiyle yazılmış (kkWaC Kazakça korpusun kısaltmasıdır); bağlantı kywac'a gidiyor.

Kısaltmalar: "hedef" = bağlantı verilen sayfanın kendisinden okunan bilgi. "Belirtilmemiş" = ne İTÜ sayfasında ne okunabilen hedef sayfada yazıyor.

## 1. Türkçe veri setleri (sayfada 30 kayıt)

Sütunlar: ad · tür · boyut (sayfa) · lisans · erişim · biçim · bağlantı.

### 1.1 İTÜ DDİ grubunun kendi setleri

| # | Ad | Tür | Boyut | Lisans | Erişim | Biçim | Bağlantı |
|---|---|---|---|---|---|---|---|
| 1 | IMST Treebank v1.4.1 | treebank (METU-Sabancı'nın yeniden etiketlenmiş hali) | 5.635 cümle | belirtilmemiş; asıl sayfa erişilemedi, doğrulanamadı. Kök METU-Sabancı treebank'in araştırma amaçlı, imzalı sözleşmeyle ve yeniden dağıtım yasağıyla verildiği arama sonucunda geçiyor (ikincil kaynak, doğrulanamadı) | sayfa belirtmiyor | belirtilmemiş | http://tools.nlp.itu.edu.tr/Datasets |
| 2 | ITU Web Treebank (IWT) v1.5.1 | treebank (web metinleri) | 5.099 cümle (EN sayfa: 5.009) | belirtilmemiş | belirtilmemiş | belirtilmemiş | http://tools.nlp.itu.edu.tr/Datasets |
| 3 | IMST-UD Treebank (UD v2.1) | treebank (Universal Dependencies) | sayfada yok; UD sayfası (hedef): 5.635 cümle, 56.422 token | **CC BY-NC-SA 4.0** (hedef: UD IMST sayfası) | UD üzerinden açık (indirme adımı denenmedi) | CoNLL-U (UD standardı; sayfadan doğrulanmadı) | http://tools.nlp.itu.edu.tr/Datasets ; https://universaldependencies.org/treebanks/tr_imst/index.html |
| 4 | IWT-UD Treebank (TBD) | treebank (UD) | belirtilmemiş; sayfada "TBD" | belirtilmemiş; UD sayfası 404 verdi, doğrulanamadı | belirtilmemiş | belirtilmemiş | http://tools.nlp.itu.edu.tr/Datasets |
| 5 | Turkish PropBank | anlamsal rol etiketleme | 5.635 cümle | belirtilmemiş | belirtilmemiş | belirtilmemiş | http://tools.nlp.itu.edu.tr/Datasets |
| 6 | Turkish PropBank-UD | anlamsal rol (UD sürümü) | belirtilmemiş | belirtilmemiş | belirtilmemiş | belirtilmemiş | http://tools.nlp.itu.edu.tr/Datasets |
| 7 | Normalization Resources | normalizasyon (gürültülü metin) kaynakları | belirtilmemiş | belirtilmemiş | belirtilmemiş | belirtilmemiş | http://tools.nlp.itu.edu.tr/Datasets |
| 8 | Named Entity Recognition Resources | NER | belirtilmemiş | belirtilmemiş | belirtilmemiş | belirtilmemiş | http://tools.nlp.itu.edu.tr/Datasets |
| 9 | Turkish Sign Language Dictionary | sözlük (işaret dili) | belirtilmemiş | belirtilmemiş | web sitesi | belirtilmemiş | http://tid.itu.edu.tr/ |
| 10 | Turkish Sign Language Treebank | treebank (işaret dili) | belirtilmemiş | belirtilmemiş | sayfa yalnız makale DOI'sini veriyor; veri bağlantısı değil | belirtilmemiş | https://doi.org/10.1007/s10579-019-09465-5 |
| 11 | Turkish Aspect Based Sentiment Analysis Dataset | duygu (SemEval-2016 ABSA, restoran yorumları, Türkçe, subtask 1 eğitim) | belirtilmemiş | belirtilmemiş | META-SHARE deposu; erişim denenmedi | belirtilmemiş | bkz. §8 URL listesi (metashare.ilsp.gr) |

### 1.2 Diğer araştırmacı/gruplara ait Türkçe setler

| # | Ad | Tür | Boyut | Lisans | Erişim | Biçim | Bağlantı |
|---|---|---|---|---|---|---|---|
| 12 | TS Corpus | korpus (sosyal medya + çok kaynaklı web) | 491 milyon etiketli token (sayfa); hedef: 25+ korpus, 1,8 milyar+ token | belirtilmemiş. Hedef: "akademik çalışma ve araştırma için kısıtlamasız, açık" diyor ama lisans adı yok | sorgu arayüzünde sorgu, sonuç kaydetme ve veri indirme (hedef); tam metin toplu indirme koşulu doğrulanamadı | belirtilmemiş | https://tscorpus.com/ |
| 13 | Turkish National Corpus (TNC) | yazılı korpus (1990-2013; %2 konuşma dökümü) | 50 milyon sözcük | "ticari olmayan kullanım için ücretsiz kaynak" (hedef); lisans adı yok | yalnız çevrimiçi sorgu arayüzü (v3.tnc.org.tr); toplu indirme olduğu yazmıyor | belirtilmemiş | https://www.tnc.org.tr/ |
| 14 | Bilkent Turkish Writings Dataset | yaratıcı yazı korpusu (Bilkent Türkçe 101/102 dersleri) | sayfa: ~7.000 metin (2014-2018); hedef güncel sürüm v2: 9.119 yazı, ~45 MB CSV | "Academic Use License": ticari kullanım yasak, kâr amaçlı yeniden dağıtım yasak (hedef; tam LICENSE metni okunmadı) | doğrudan GitHub (açık depo) | CSV (text, course, semester, author, title, metadata, url, file_id); ayrıca Hugging Face ve ham metin | https://github.com/selimfirat/bilkent-turkish-writings-dataset |
| 15 | Sentiment Lexicons for 81 Languages | duygu sözlüğü (Türkçe dahil) | 81 dil | belirtilmemiş; Kaggle sayfası okunamadı | Kaggle | belirtilmemiş | https://www.kaggle.com/rtatman/sentiment-lexicons-for-81-languages |
| 16 | Old Newspapers | eski gazete cümleleri (çok dilli) | toplam ~17 milyon cümle, 67 dil; Türkçe payı ölçülmedi | belirtilmemiş; Kaggle sayfası içerik vermedi, doğrulanamadı | Kaggle | belirtilmemiş | https://www.kaggle.com/alvations/old-newspapers |
| 17 | English/Turkish Wikipedia NER and Text Categorization Dataset (TWNERTC) | NER + metin sınıflandırma (Wikipedia'dan otomatik etiketli) | hedef: Türkçe sürüm başına ~700 bin cümle; Türkçe gazetteer ~300 bin varlık | **CC BY 4.0** (hedef: Mendeley sayfası) | Mendeley Data, "Download All" düğmesi (hedef); dosya listesi görülemedi | belirtilmemiş (hedef de yazmıyor) | https://data.mendeley.com/datasets/cdcztymf4k/1 |
| 18 | Turkish UD | treebank (UD, Türkçe genel sayfa; alt treebank'ler) | belirtilmemiş | alt treebank'e göre değişir; yalnız IMST için CC BY-NC-SA 4.0 doğrulandı | açık | CoNLL-U (UD standardı) | https://universaldependencies.org/tr/index.html |
| 19 | Turkish WordNet | sözlük / sözcüksel veritabanı (Starlang) | belirtilmemiş | belirtilmemiş; GitHub deposu okunmadı | GitHub | belirtilmemiş | https://github.com/StarlangSoftware/TurkishWordNet-CPP |
| 20 | trTenTen20 | web korpusu | sayfa: 4,9 milyar sözcük; hedef: 6,15 milyar token, 368 milyon cümle, 20,8 milyon web sayfası | belirtilmemiş (Sketch Engine koşullarına bağlı; koşul sayfası okunmadı) | Sketch Engine uygulaması; ücretli abonelik, 30 gün deneme (hedef). Ham metin indirme yazmıyor | belirtilmemiş | https://www.sketchengine.eu/trtenten-turkish-corpus/ |
| 21 | trWaC | web korpusu | 32 milyon sözcük | belirtilmemiş | Sketch Engine; sayfa okunmadı, doğrulanamadı | belirtilmemiş | https://www.sketchengine.eu/trwac-turkish-corpus/ |
| 22 | CHILDES | çocuk dili korpusları (Türkçe alt kümesi) | 24 dil; Türkçe payı belirtilmemiş | belirtilmemiş | Sketch Engine | belirtilmemiş | https://www.sketchengine.eu/childes-corpora/ |
| 23 | ParlaMint 2.1 | parlamento tutanakları | 17 dil; Türkçe payı belirtilmemiş | belirtilmemiş | Sketch Engine | belirtilmemiş | https://www.sketchengine.eu/parlamint-corpora-of-parliamentary-debates/ |

### 1.3 Paralel derlemler

| # | Ad | Tür | Boyut | Lisans | Erişim | Biçim | Bağlantı |
|---|---|---|---|---|---|---|---|
| 24 | The English-Swedish-Turkish Corpus | paralel (özgün + çeviri) | belirtilmemiş | belirtilmemiş | web sitesi; okunmadı | belirtilmemiş | https://cl.lingfil.uu.se/~bea/turkiska/home-en.html |
| 25 | Bianet Corpus | paralel (Türkçe + Kürtçe veya İngilizce haber) | 3.000+ makale | belirtilmemiş; OPUS sayfası 404 verdi, doğrulanamadı | OPUS (sayfa adresi eski, güncel adres bulunamadı) | belirtilmemiş | http://opus.nlpl.eu/Bianet.php |
| 26 | OPUS Parallel Corpora | paralel (hizalı cümleler) | 40 dil; Türkçe payı belirtilmemiş | belirtilmemiş | Sketch Engine sayfası | belirtilmemiş | https://www.sketchengine.eu/opus-parallel-corpora/ |
| 27 | OpenSubtitles Parallel Corpora 2018 | paralel (altyazı) | 58 dil; Türkçe payı belirtilmemiş | belirtilmemiş | Sketch Engine sayfası | belirtilmemiş | https://www.sketchengine.eu/opensubtitles-parallel-corpora/ |

### 1.4 Konuşma korpusları

| # | Ad | Tür | Boyut | Lisans | Erişim | Biçim | Bağlantı |
|---|---|---|---|---|---|---|---|
| 28 | Spoken Turkish Corpus (METU) | konuşma (radyo kayıtları) | 18 radyo istasyonu | belirtilmemiş | web sitesi; okunmadı | belirtilmemiş | http://std.metu.edu.tr/en/ |
| 29 | METU Turkish Microphone Speech (LDC2006S33) | konuşma + hizalı döküm | 120 konuşmacı, ~500 dakika | belirtilmemiş; LDC kataloğu okunmadı | LDC kataloğu (ücret/üyelik durumu bu sayfadan doğrulanamadı) | belirtilmemiş | https://catalog.ldc.upenn.edu/LDC2006S33 |
| 30 | Turkish Broadcast News Speech and Transcripts (LDC2012S06) | konuşma + döküm | 130 saat | belirtilmemiş; LDC kataloğu okunmadı | LDC kataloğu (aynı not) | belirtilmemiş | https://catalog.ldc.upenn.edu/LDC2012S06 |

## 2. Diğer Türk dilleri (Türkçe dışı; Derlem Türkçe odaklıysa kapsam dışı)

Sayfa bu kayıtlar için de lisans/erişim/biçim vermiyor; hepsinin lisansı "belirtilmemiş" (bağlantılar okunmadı). Derlem notu: Türkçe ön eğitim hedefine doğrudan katkıları yok; ürün vizyonundaki çok dilli genişleme (moratoryum sonrası) için aday havuzu.

| Dil | Ad (tür; boyut) | Bağlantı |
|---|---|---|
| Azerbaycan | en-az-parallel-corpus (paralel EN-AZ; boyut yok) | https://github.com/derintelligence/en-az-parallel-corpus |
| Azerbaycan | az-corpus-nlp (korpus; boyut yok) | https://github.com/raminrahimzada/az-corpus-nlp |
| Azerbaycan | azWaC (web; 94 milyon sözcük) | https://www.sketchengine.eu/azwac-azerbaijani-corpus/ |
| Azerbaycan | Leipzig korpus koleksiyonu (karşılaştırılabilir; boyut yok) | https://cls.corpora.uni-leipzig.de/en?corpusLanguage=aze#tblselect |
| Azerbaycan | Helsinki Üniversitesi korpusu (Yeni Ahit çevirisi) | http://www.ling.helsinki.fi/uhlcs/readme-all/README-turkic-lgs.html#C21 |
| Azerbaycan | azwiki dump (Wikipedia) | https://dumps.wikimedia.org/azwiki/latest/ |
| Azerbaycan | Azeri at An Crúbadán (korpus; 8 milyon+ sözcük) | http://crubadan.org/languages/az |
| Azerbaycan | Domrachyov-Sudoplatova kazınmış korpus (2.189.398 sözcük; 100.560 cümle) | https://github.com/svetlana21/Nutch_parser/ |
| Azerbaycan | AZ summarization (makale + başlık; boyut yok) | https://github.com/derintelligence/az-summarization |
| Kazak | Almaty Corpus of Kazakh (NCKL; 40 milyon sözcük) | http://web-corpora.net/KazakhCorpus/search/ |
| Kazak | Open Source Kazakh Language Corpus (Kazak Wikipedia; 21 milyon sözcük; Google Drive) | https://drive.google.com/drive/folders/1A5xfmSaf3JW4b9F8dTNKkao090SUwPJ6?usp=sharing |
| Kazak | Kazakh UD Treebank (boyut yok) | https://universaldependencies.org/treebanks/kk_ktb/index.html |
| Kazak | kkWaC (web; 139 milyon sözcük) | https://www.sketchengine.eu/kkwac-kazakh-corpus/ |
| Kırgız | Kyrgyz web korpusu (19 milyon sözcük) | https://www.sketchengine.eu/kywac-kyrgyz-corpus/ |
| Kırgız | Kyrgyz UD (sayfa: "henüz açılmamıştır"; yayımlanmamış, sayıma dahil değil) | yok |
| Özbek | Uzbek Corpus 2017 (Leipzig; 663.119 cümle, 9.256.001 token) | https://corpora.uni-leipzig.de/en?corpusId=uzb_community_2017 |
| Özbek | uzWaC (web; 18 milyon sözcük) | https://www.sketchengine.eu/uzwac-uzbek-corpus/ |
| Tatar | Corpus of Written Tatar (500 milyon sözcük, 620 milyon+ token) | https://www.corpus.tatar/en |
| Tatar | Tatar National Corpus (180 milyon token, Aralık 2018) | http://tugantel.tatar/?lang=en |
| Tatar | Tatar Belletristic Literature Corpus (edebiyat; boyut yok) | http://litcorpus.antat.ru/index_en.htm |
| Türkmen | tkWaC (web; 2 milyon sözcük) | https://www.sketchengine.eu/tkwac-turkmen-corpus/ |
| Uygur | UyNeRel (NER; boyut yok) | https://github.com/kaharjan/UyNeRel |
| Uygur | Uyghur UD (treebank; boyut yok) | https://universaldependencies.org/treebanks/ug_udt/index.html |

Sayfada ayrıca veri olmayan: "Awesome Azeri NLP" (derleme liste, https://github.com/alexeyev/awesome-azeri-nlp) ve Apertium notu (yayımlanmamış küçük Tuva ve Kırım Tatarcası veri setlerinden söz ediyor; erişim yok).

Toplam: 30 Türkçe + 22 diğer Türk dili = **52 veri seti kaydı** (Kırgız UD yayımlanmadığı için ve Awesome listesi veri olmadığı için sayılmadı).

## 3. Araçlar ve modeller (veri değil)

- ITU DDİ Turkish NLP toolchain / pipeline (normalizasyon, morfolojik analiz vb.; web servisi): http://tools.nlp.itu.edu.tr/ (erişilemedi).
- kaznlp (Kazak NLP araçları): https://github.com/makazhan/kaznlp
- Apertium Turkic languages (morfolojik çözümleyiciler): https://wiki.apertium.org/wiki/Turkic_languages
- Türkçe dil modelleri: ELMo (https://github.com/ericxsun/ELMoForManyLangs), BERT (https://github.com/stefan-it/turkish-bert), fastText vektörleri (https://fasttext.cc/docs/en/crawl-vectors.html)
- Azerbaycan modelleri: Polyglot morfessor (https://github.com/aboSamoor/polyglot/blob/master/docs/MorphologicalAnalysis.rst), fastText AZ vektörleri (aynı fastText adresi)

## 4. Derlem'e uygunluk (Türkçe kayıtlar, tek cümle)

1. IMST: eval verisi (morfoloji/sözdizimi), pretrain değil; ~56 bin token, yaklaşık 1 MB altı.
2. IWT: eval verisi; IMST'ye benzer ölçek (~5 bin cümle), bayt ölçülmedi.
3. IMST-UD: eval verisi (UD morfoloji/dependency), pretrain metni değil; 56.422 token.
4. IWT-UD: eval verisi; "TBD" olduğu için şimdilik katkı yok, ölçülmedi.
5. Turkish PropBank: yalnız eval/etiketli veri; 5.635 cümle, pretrain'e uygun değil.
6. PropBank-UD: aynı, eval; ölçülmedi.
7. Normalization Resources: normalleştirme eval veya talimat verisi için aday; ölçülmedi.
8. NER Resources: NER eval verisi; pretrain metni değil; ölçülmedi.
9. TİD sözlüğü: uygun değil (işaret dili, metin korpusu değil).
10. TİD treebank: uygun değil; veri bağlantısı bile yok.
11. Turkish ABSA: duygu eval verisi (küçük, restoran yorumu); pretrain için ihmal edilebilir, ölçülmedi.
12. TS Corpus: pretrain adayı (491 milyon token, kabaca birkaç GB metin tahmini), ama toplu indirme ve yeniden dağıtım koşulu doğrulanamadı; ölçülmedi.
13. TNC: dengeli, kaliteli korpus; yalnız sorgu arayüzü olduğundan pretrain için kullanılamaz, olsa olsa kalite/denge referansı (eval); 50 milyon sözcük için yaklaşık 400 MB tahmini, ölçülmedi.
14. Bilkent Writings: pretrain için küçük ama özgün ve temiz metin (~45 MB CSV); akademik lisansı kapsama uyar, eval olarak da kullanılabilir.
15. Sentiment Lexicons 81: uygun değil (sözlük, metin yok); en fazla duygu eval yardımcısı.
16. Old Newspapers: pretrain adayı (eski gazete cümleleri; OCR kalitesi ve Türkçe payı ölçülmedi); lisans bilinmediği için riskli.
17. TWNERTC: hem pretrain (Wikipedia kaynaklı ~700 bin Türkçe cümle, kabaca onlarca MB; Wikipedia ile tekrar riski var) hem NER eval; CC BY 4.0 olduğu için en temiz aday.
18. Turkish UD: eval verisi; alt treebank'e göre değişir, ölçülmedi.
19. Turkish WordNet: pretrain değil; anlamsal eval/sözlük kaynağı olarak kullanılabilir; ölçülmedi.
20. trTenTen20: pretrain için çok büyük aday (6,15 milyar token) ama Sketch Engine içinde ücretli/sorgu erişimli; ham indirme yoksa pratikte kapalı sayılmalı.
21. trWaC: aynı durum, 32 milyon sözcük; küçük ve eski, FineWeb2-HQ'ya göre değeri düşük.
22. CHILDES (Türkçe): pretrain değil; çocuk dili ve konuşma verisi, çok küçük; ölçülmedi.
23. ParlaMint 2.1 (Türkçe): pretrain adayı (resmî dil, temiz); Türkçe payı sayfada yazmıyor, ölçülmedi; kendi lisansı doğrulanamadı.
24. English-Swedish-Turkish: paralel çeviri eval verisi; pretrain için küçük, ölçülmedi.
25. Bianet: paralel haber; pretrain için küçük (3.000+ makale, birkaç MB tahmini), çeviri talimat/eval verisi olarak kullanılabilir.
26. OPUS: çok büyük koleksiyon; Türkçe kısmı pretrain'e değil çeviri talimat verisine uygun; ölçülmedi.
27. OpenSubtitles 2018: Türkçe konuşma dili altyazısı; pretrain'de kalite/telif riski var, çeviri talimat verisi için daha uygun; ölçülmedi.
28. Spoken Turkish Corpus: ses/döküm; Derlem metin korpusu olduğu için uygun değil.
29. METU Microphone Speech: uygun değil (ses).
30. Turkish Broadcast News: uygun değil (ses); dökümleri küçük bir katkı olabilir ama erişim koşulu doğrulanamadı, ölçülmedi.

## 5. Özet: lisans/erişim sınıfları

Sınıflandırma yalnız doğrulanan bilgiye dayanır. Doğrulanamayan her şey (c) sayılmıştır; bu "kapalı" demek değil, "bilinmiyor" demektir. Sayım Türkçe 30 kayıt üzerinedir.

**(a) Açık lisanslı ve doğrudan indirilebilir: 1 kayıt**
- TWNERTC (#17): CC BY 4.0, Mendeley Data. Ticari olmayan kapsama uyar. Dosya listesi ve biçim doğrulanamadı.

**(b) Akademik kullanıma açık, ticari değil: 2 kesin + 2 sınır durumu**
- Kesin: IMST-UD (#3, CC BY-NC-SA 4.0; ShareAlike türev lisans yükü getirir) ve Bilkent Turkish Writings (#14, Academic Use License). İkisi de kurucu kapsamına uyar.
- Sınır: TS Corpus (#12) "akademik çalışma ve araştırma için kısıtlamasız" diyor ama lisans adı ve toplu indirme koşulu yok; TNC (#13) "ticari olmayan kullanım için ücretsiz" ama yalnız sorgu arayüzü, indirme yok.
- Turkish UD (#18) kendi başına sayılmadı: alt treebank'e bağlı, yalnız IMST için doğrulandı (= #3).

**(c) Lisansı belirsiz / doğrulanamadı: 25 kayıt** (#1, 2, 4-11, 15, 16, 18, 19-30; #18 dahil, genel sayfa)
- İTÜ DDİ'nin kendi kayıtlarının çoğu (asıl sayfa erişilemedi) ve diğer Türk dilleri kayıtlarının tamamı (22 kayıt).
- Ücretli veya üyelik gerektirebilecekler: Sketch Engine korpusları (#20-23, 26, 27) ve LDC kayıtları (#29, 30); koşulları doğrulanamadı.

Dağılım (Türkçe 30): (a) 1, (b) 2 kesin + 2 sınır, (c) 25.

## 6. Tuzak: "yalnız araştırma" ve "yeniden dağıtılamaz" şartları

Derlem dondurulmuş sürümleri (ör. v5) model rafına teslim ediyor. Bu teslim, kaynak verinin kopyasını ya da ondan türetilmiş metni kurum dışına vermek anlamına gelir. Akademik setlerin şartları bununla çelişebilir:

- **Bilkent Turkish Writings:** "kâr amaçlı yeniden dağıtım yasak" + "ticari kullanım yasak". Kâr amacı gütmeyen paylaşım gri alandır; tam LICENSE metni okunmadı. Teslim edilen sürüme metin girerse şartın kapsamı kontrol edilmeli.
- **IMST-UD (ve büyük olasılıkla diğer UD treebank'leri):** CC BY-NC-SA 4.0: ticari olmayan, atıf zorunlu ve **ShareAlike**; türev ürün aynı lisansla verilmek zorunda. Rafa giden bir korpusa karıştırılırsa tüm sürümü bağlayabilir; eval olarak ayrı tutmak daha güvenli.
- **IMST (METU-Sabancı kökü):** arama sonucuna göre araştırma amaçlı, imzalı sözleşmeyle veriliyor ve yeniden dağıtım yasak (ikincil kaynak, İTÜ'nün güncel koşulu doğrulanamadı). Doğruysa rafa teslim doğrudan çelişir.
- **TNC:** "ticari olmayan kullanım" ve yalnız sorgu; kopyasının dondurulmuş sürüme girmesi koşullara aykırı olabilir.
- **TS Corpus:** "akademik çalışma ve araştırma" ifadesi var; yeniden dağıtımı da türev modeli de açıkça düzenlemiyor. Yazılı izin gerekir.
- **Sketch Engine kaynaklı korpuslar** (trTenTen20, trWaC, azWaC, kkWaC, uzWaC, kywac, tkWaC, ParlaMint, OPUS, OpenSubtitles, CHILDES): abonelik koşulları geçerli; sorgu/konkordans erişimi ham metin indirmeyi veya model eğitimini kapsamayabilir. Koşul sayfası okunmadı, doğrulanamadı.
- **LDC (#29, #30):** LDC verisi genellikle lisans sözleşmesi altındadır ve yeniden dağıtımı kısıtlar (genel bilgi, bu çalışmada doğrulanamadı).
- **Çok sayıda "belirtilmemiş":** İTÜ sayfası lisans yazmadığı için "lisans yok" serbest anlamına gelmez; yazarın açık izni olmadan telif hakkı geçerlidir. "Çıktı her modele verilebilir" ilkesi (Gardas bağımsızlığı kaydı) yalnız (a) sınıfı veya yazılı izni olan kaynaklar için güvenle ileri sürülebilir.
- **Model ağırlıkları:** CC BY-NC-SA ve "academic use" şartlarının eğitilen modele geçip geçmediği hukuken tartışmalıdır; bu doküman hukuki görüş değildir.

Öneri: (a) dışındaki her kaynak için rafa girmeden önce yazılı izin ya da açık lisans metni kaydı alınmalı; bu olana kadar eval-only ve ayrı-sürüm yaklaşımı (veri rafa girmez, yalnız ölçüm sonucu girer).

## 7. Derlem için en değerli adaylar

1. **TWNERTC (#17)**: doğrulanmış tek CC BY 4.0; ~700 bin Türkçe cümle + NER etiketleri. Hem eval hem küçük pretrain katkısı. Wikipedia kaynaklı olduğundan tekrar riski var.
2. **Bilkent Turkish Writings (#14)**: doğrudan GitHub'da, 9.119 yazı/~45 MB, özgün temiz metin, akademik lisans kurucu kapsamına uyar; yeniden dağıtım şartı §6'da.
3. **IMST-UD (#3)**: doğrulanmış lisans (CC BY-NC-SA), eval için; morfoloji/dependency kalite ölçümü.
4. **TS Corpus (#12)**: 1,8 milyar+ token (hedef sayfa), potansiyel en büyük açık-akademik pretrain kaynağı; indirme ve yeniden dağıtım koşulu için yazılı yazışma şart.
5. **Bianet (#25)**: küçük paralel haber verisi, çeviri/talimat verisi olarak; lisansı doğrulanamadı, OPUS'tan güncel adres bulunmalı.

İTÜ'nün kendi veri setleri (treebank, PropBank, NER, normalizasyon) küçük ve etiketli; pretrain metni olarak değer taşımaz, eval olarak ilginç. Asıl erişim sayfası ulaşılamadığı için lisans yazışması gerekiyor.

## 8. Doğrulanamayanlar (özet)

- `tools.nlp.itu.edu.tr/Datasets` erişilemedi: İTÜ-DDİ'nin 8 kaydında lisans, erişim yöntemi, biçim.
- ITU Web Treebank boyutu: 5.099 mu 5.009 mu.
- IWT-UD lisansı (UD sayfası 404), Bianet/OPUS sayfaları (404).
- Kaggle sayfaları (Old Newspapers, Sentiment Lexicons) içerik vermedi.
- Sketch Engine kullanım koşulları, LDC koşulları, Mendeley dosya listesi, Bilkent LICENSE tam metni, ParlaMint lisansı okunmadı.
- Sayfanın son güncelleme tarihi görülmedi.

Erişim tarihi: 2026-10-13

URL listesi (bakılanlar):
- https://nlp.itu.edu.tr/araclarkaynaklar (okundu)
- https://nlp.itu.edu.tr/en/toolsandresources (okundu)
- https://nlp.itu.edu.tr/en/tools-resources (404)
- http://tools.nlp.itu.edu.tr/Datasets ve https://tools.nlp.itu.edu.tr/Datasets (ECONNREFUSED)
- https://universaldependencies.org/treebanks/tr_imst/index.html (okundu)
- https://universaldependencies.org/treebanks/tr_iwt/index.html (404)
- https://github.com/selimfirat/bilkent-turkish-writings-dataset (okundu)
- https://data.mendeley.com/datasets/cdcztymf4k/1 (okundu)
- https://tscorpus.com/ (okundu)
- https://www.tnc.org.tr/ (okundu)
- https://www.sketchengine.eu/trtenten-turkish-corpus/ (okundu)
- https://www.kaggle.com/alvations/old-newspapers (içerik alınamadı)
- https://opus.nlpl.eu/Bianet.php ve https://opus.nlpl.eu/Bianet/corpus/version/Bianet (404)
- WebSearch: "ITU NLP Turkish dataset nlp.itu.edu.tr resources"; "ITU Turkish treebank IMST ITU Web Treebank PropBank license request form research use tools.nlp.itu.edu.tr Datasets"
- META-SHARE ABSA (okunmadı): http://metashare.ilsp.gr:8080/repository/browse/semeval-2016-absa-restaurant-reviews-turkish-train-data-subtask-1/ff5dad70676311e5bf9c842b2b6a04d71fa7fa3ba4504a228dafe0c24560585b/
