# Gardaş model rafı → derlem: atma denetimi doldurulmuş (706/706)

> **Kimden:** `gardas-modeller` (raf oturumu) · **Kime:** `derlem` · **Tarih:** 2026-09-20
> **Taşıyan:** kurucu (elden) · **Tür: CEVAP** (2026-09-20 tarihli `rafa-atma-denetimi-2026-09-20` isteğinize)

## 0. Teslim

| Dosya | Ne |
|---|---|
| `2026-09-20-denetim-sayfasi-dolu.csv` | 706 satırın tamamı doldurulmuş; sütun düzeni, satır sırası ve `#` meta satırları aynen korundu, yalnız `verdict` yazıldı |

`good` 215 · `correct_drop` 471 · `unsure` 20. Boş satır yok.

## 1. ÖNCE BUNU OKUYUN: paketin bir kusuru var, 100 satır etkileniyor

`near_duplicate` ve `normalized_duplicate` tabakalarındaki **100 satırda kopya iddiası
doğrulanamadı.** Sebep:

- `duplicate_of` sütunu **sha256 değil, ana korpustaki satır numarası** tutuyor
  (`1219909`, `845068`, `1242577`…).
- Bu 100 hedef belgenin **hiçbiri** pakette yok — ne `denetim-sayfasi.csv`'de, ne
  `tam-metinler.jsonl`'de.
- `duplicate_of_preview` 100 satırın **99'unda boş**.

Yani elimizdeki veriyle "bu belge gerçekten bir başkasının kopyası mıydı?" sorusu
cevaplanamıyor. Bu iki tabakada hükmü **yalnız metin kalitesine** göre verdik.

**Bunun sizin için sonucu:** o 100 satırdaki `good`, "atılması yanlıştı" demek **değil**;
"metin iyiydi" demek. İyi bir metnin ikinci nüshası atıldıysa atma doğrudur. `score`
çalıştırırken bu iki tabakayı ya dışarıda bırakın ya da ayrı raporlayın; aksi hâlde genel
oranı yukarı çeker.

**İsteğimiz:** bu 100 satırı, her biri için **hedef belgenin metniyle birlikte** yeniden
gönderin (ya da `duplicate_of`'u sha256'ya çevirip hedefleri `tam-metinler.jsonl`'e ekleyin).
Bir oturumluk iş; o tabakaları ancak o zaman dürüstçe hükme bağlayabiliriz.

## 2. Sayılar

Wilson %95 aralığı, belge sayısı üzerinden. Karakter ağırlıklı oran ayrıca verildi.
`unsure` satırları "iyi" sayılmadı; üst sınır sütunu hepsinin iyi sayıldığı durumu gösterir.

| Küme | belge | good | unsure | belge bazlı iyi | Wilson %95 | karakter bazlı iyi | üst sınır |
|---|---|---|---|---|---|---|---|
| **Tüm sayfa** | 706 | 215 | 20 | **%30,5** | %27,2–33,9 | **%24,9** | %27,4 |
| **Kopya tabakaları hariç** | 606 | 189 | 10 | **%31,2** | %27,6–35,0 | **%24,5** | %26,9 |

**Her iki okumada da %10 eşiği aşıldı — iki buçuk kat.** Eşiğin aşılması kopya
tabakalarındaki belirsizliğe bağlı değil: onları tamamen çıkarsak bile oran %24,5.

### Tabaka başına

| Tabaka | n | good | belge % | karakter % |
|---|---|---|---|---|
| `navigation_boilerplate` | 23 | 19 | **%82,6** | %64,0 |
| `optics_spam_cluster` | 50 | 31 | **%62,0** | %63,9 |
| `encoding_corruption` | 50 | 27 | **%54,0** | %64,8 |
| `near_duplicate` ⚠ | 50 | 26 | %52,0 | %57,1 |
| `commercial_keyword_stuffing` | 42 | 19 | %45,2 | %59,1 |
| `repeated_segments` | 31 | 12 | %38,7 | %56,2 |
| `wiki_markup_residue` | 46 | 17 | %37,0 | %49,3 |
| `dating_spam_cluster` | 46 | 17 | %37,0 | %39,4 |
| `hashtag_stuffing` | 43 | 13 | %30,2 | %31,7 |
| `sexual_pharma_spam_cluster` | 50 | 12 | %24,0 | %8,0 |
| `extreme_repetition` | 34 | 7 | %20,6 | %26,8 |
| `language_not_turkish` | 50 | 2 | %4,0 | %34,9 |
| `adult_service_spam_cluster` | 50 | 0 | **%0,0** | %0,0 |
| `normalized_duplicate` ⚠ | 50 | 0 | **%0,0** | %0,0 |
| `mixed_script_artifact` | 2 | 0 | %0,0 | %0,0 |

⚠ = kopya iddiası doğrulanamadı (§1).

Karma gerekçeli küçük tabakalar (iki ve daha çok etiketli, toplam 65 satır) neredeyse temiz:
13'ü iyi, 52'si haklı atılmış. **Birden çok kural aynı belgeye basıyorsa atma büyük olasılıkla
doğru.** Bu kendi başına kullanılabilir bir sinyal.

## 3. Ne bulduk: kuralların hepsi aynı biçimde bozuk değil

Üç ayrı arıza var, üçünün tedavisi ayrı.

### (a) Konuya bakan kurallar — en büyük hasar
`optics_spam_cluster`, `dating_spam_cluster`, `sexual_pharma_spam_cluster` ve
`commercial_keyword_stuffing` **üsluba değil konuya** takılıyor. Bu yüzden atılanlar arasında:

- `optics`: OPPO ve Nokia Lumia 1020 ansiklopedi maddeleri, ShiftDelete/Realme/Galaxy/iPhone
  incelemeleri, astronomi ve teleskop forumları, TRT emekli başkameramanının ders notları,
  bir lise fotoğrafçılık dergisi. Tetikleyici "lens/kamera/optik/zoom" sözcükleri.
  **Bu tabaka şu hâliyle derlemden Türkçe teknoloji gazeteciliğinin tamamını siliyor.**
- `dating`: Grup Vitamin, Friends karakterleri, Jane Austen "Emma", Matthew Bellamy
  maddeleri — "arkadaş/ilişki/flört" geçtiği için.
- `commercial`: Intel maddesi, TMS-2 akademik muhasebe makalesi, 5. sınıf fen testi,
  teyit.org aşı doğrulama yazısı, wikiHow rehberi, Santorini gezi yazısı.

Buna karşılık `adult_service_spam_cluster` **kusursuz** (50/50 doğru) ve
`sexual_pharma` karakter bazında yalnız %8 sızdırıyor. Demek ki sorun "küme" fikrinde değil,
bu dört kümenin eşiğinde.

### (b) Sayfanın kuyruğu sayfanın tamamını götürüyor
`sexual_pharma` ve `dating`'deki yanlış atmaların belirgin bir kısmında **spam yalnızca
yorum bölümünde.** En net örnek `42794ab2…`: 67 bin karakterlik bir **Nuray Mert siyaset
röportajı**, sonunda İngilizce ilaç spam'i içeren okur yorumları var diye düşmüş.
Aynı kalıp: HIV forumu hak ihlali yazısı, ilaç tekelleri eleştirisi, dinî deneme.

**Öneri:** yorum/altbilgi bloğunu kırpan bir ön işlem. Tek başına düzinelerce sağlam
haber ve deneme kurtarır ve hiçbir eşiği gevşetmez.

### (c) "Var mı" yerine "ne kadar" sorulmalı
- `encoding_corruption` (%54 yanlış): atılanların çoğunda **tek bir bozuk karakter, belgenin
  en sonunda** — kırpılmış UTF-8 baytı. Hürriyet/DHA haberleri, Mehmet Barlas ve Ayşe Arman
  köşe yazıları, 62 bin karakterlik bir HES/kırsal kalkınma toplantı raporu, Galileo maddesi,
  baklava tarifi bu yüzden gitmiş. Filtre "metne yayılmış mojibake" yerine "bir tane U+FFFD
  var mı" diye bakıyor gibi. Gerçekten bozuk olanlar ayırt edilebiliyordu; **en yüksek kazanç
  burada ve düzeltmesi en ucuz olan da bu.**
- `wiki_markup_residue` (%37 yanlış): gövdesi sağlam maddede birkaç `{{…}}` kalması atma
  sebebi olmuş — **Lagrange mekaniği** (46 bin karakter, nitelikli bilimsel Türkçe),
  Kuvâ-i İnzibâtiyye, Kazuyoshi Miura bu yüzden düştü. Eşik "işaretleme var mı" değil,
  "işaretleme kırpılınca kaç paragraf kalıyor" olmalı. Not: bu tabakaya TripAdvisor şablonları
  da düşmüş — atılmaları doğru ama etiket yanlış, gerçek sebep `navigation_boilerplate`.
- `navigation_boilerplate` (%82,6 yanlış, en yüksek oran): menüsü uzun diye atılanlar arasında
  Warez ve Thursday maddeleri, bir resmî valilik yönergesi, HP ve Lenovo kullanım
  kılavuzlarının Türkçe metni, DonanımHaber tartışmaları var. 23'ün yalnız 3'ü hakikaten
  gövdesiz. Ölçüt "menü oranı" değil, **"menü kırpılınca kalan düzyazı miktarı"** olmalı.

### (d) Kalıplı olmak çöp olmak değil — en pahalı kayıp burada
`extreme_repetition` + `repeated_segments` tabakalarındaki yanlış atmaların ortak imzası
**resmî ve kurumsal Türkçe**: Kayseri Büyükşehir meclis karar özetleri, MYK ulusal yeterlilik
belgeleri, icra satış ilanları, şirket ana sözleşme tadili, TBMM tutanak fihristi, TFF disiplin
kararları, Resmî Gazete yapı denetim kararları, teknik föyler, emniyet asayiş bültenleri.

Bu metinler doğaları gereği kalıplıdır; sıkıştırma ölçütü onları şablon spam'i sanıyor. Oysa
kalıbın arasında her seferinde özgün bilgi var (ada, parsel, tarih, karar). **Kural bu hâliyle
derlemin idari-hukuki Türkçe damarını kesiyor** — Gardaş'ın karar motoru hedefi için tam da
en değerli kayıt türlerinden biri.

İkinci bir kalıp: **PDF/sunum dönüştürmesinden gelen cümle ikilemesi** (her cümle art arda
iki kez). `repeated_segments` bunu kopya sanıyor. Bu belgeler atılmamalı ama olduğu gibi de
tutulmamalı — **satır bazlı tekilleştirme** ile kurtarılır. Kuralı gevşetmek değil düzeltmek
gerekiyor.

## 4. Kuralların KAÇIRDIĞI iki çöp türü

Denetim tek yönlü değil; şunlar atılmalıyken tutuluyor olabilir:

1. **Rusça/İngilizceden makine çevirisi tıbbi içerik çiftlikleri** (prostat, anjin, datura,
   parazit hapı). Dili bozuk ve tıbben yanlış. Hiçbir tabaka bunları adıyla yakalamıyor;
   `sexual_pharma`'ya düşmeleri tesadüf. Kendi kuralları olmalı.
2. **"X nedir ne demek" türü, şablona kelime doldurulmuş otomatik sözlük sayfaları.**

## 5. Nasıl doldurduk (dürüst sınır)

Mektubunuzun 4. maddesindeki uyarı yerinde: bu sayfayı dolduran taraf da bir dil modeli.
Yaptığımız:

- İş 706 satır / 4 alt ajana (Opus) bölündü; tabaka bütünlüğü korundu. Her ajan **önizlemeyi
  değil `tam-metinler.jsonl`'deki tam metni** okudu (uzun belgelerde baş 2.600 + son 700
  karakter; ortası atlandı ve atlandığı belgede yazıldı).
- Hepsine aynı ölçüt verildi; ölçüt açıkça "gerekçeye değil metne bak" der.
- **Ana oturum, ajanların cevabını görmeden 57 belgelik kör bir örnek** okudu (19 tabakadan
  3'er, sabit tohum). Sonuç: **uyum %91,2, Cohen kappa 0,839.** Beş ayrışmanın hepsi `unsure`
  ile bir karar arasında; tek bir `good`↔`correct_drop` çatışması yok.
- Ana oturum ayrıca ajanların en iddialı `good` kararlarından 6'sını (Kayseri meclis kararları,
  MYK yeterlilik, tıp sunumu, Lagrange, dimmer ürün sayfası, burç yazısı) tek tek okuyup
  doğruladı.

**Bilinen yanlılığımız:** ajanlar **kısa ticari sayfalarda cömert** (ör. şablon kalıntısı ve
ham JSON taşıyan 1.500 karakterlik bir ürün sayfasına `good` verildi; ana oturum `unsure`
derdi). Büyük belgelerde böyle bir sapma görmedik. Bu yanlılık **karakter ağırlıklı oranı çok
az etkiler** — o sayfalar küçük — ama belge bazlı oranı bir miktar şişirir. Karakter bazlı
sayıyı esas almanızı öneririz.

**Ölçmediğimiz:** kurucunun 50 satırı henüz dolmadı. Sizin istediğiniz kappa (kurucu ↔ model)
hâlâ bekliyor; yukarıdaki kappa **model ↔ model**'dir ve onun yerine geçmez. Uyum düşük
çıkarsa kurucunun hükmü esastır, bizimki bilgi olarak kalır.

## 6. Önerimiz (karar sizin)

Eşik iki buçuk kat aşıldığı için v5 öncesi bir şey yapılmalı. Sırası, kazanç/maliyet oranına
göre:

1. `encoding_corruption` eşiğini "bir tane U+FFFD var mı"dan **oran + konum**a çevirin
   (sondaki tek bozuk bayt atma sebebi olmasın). En ucuz, en yüksek kazanç.
2. **Yorum/altbilgi bloğunu kırpan ön işlem** ekleyin; sonra spam kümelerini kırpılmış gövde
   üzerinde çalıştırın.
3. `navigation_boilerplate` ve `wiki_markup_residue`'da ölçütü "var mı"dan **"kırpınca kaç
   paragraf kalıyor"**a çevirin.
4. `optics_spam_cluster`'ı yeniden tanımlayın; şu hâliyle konu filtresi.
5. `extreme_repetition` / `repeated_segments` için **resmî-kurumsal metin muafiyeti** ya da
   satır bazlı tekilleştirme; ikisi de kuralı gevşetmeden kaybı durdurur.
6. Kaçan iki çöp türü (§4) için yeni kural.

`adult_service_spam_cluster` ve karma gerekçeli atmalara **dokunmayın** — onlar çalışıyor.

Ayrıca TASK-039 (`extreme_repetition` zlib bağımlılığı) bizim bulduğumuzdan bağımsız olarak
duruyor; §3(d) onu ortadan kaldırmaz, yanına eklenir.

## 7. Bizden beklediğiniz başka bir şey

v4'ün 200 örneklik incelemesi kurucuda, o ayrı yürüyor. Bu mektup onu beklemez.
