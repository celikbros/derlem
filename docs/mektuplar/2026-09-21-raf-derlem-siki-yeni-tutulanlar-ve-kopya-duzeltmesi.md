# Gardaş model rafı → derlem: sıkı yeni-tutulanlar (293) + kopya eşleri düzeltmesi (100)

> **Kimden:** `gardas-modeller` (raf oturumu) · **Kime:** `derlem` · **Tarih:** 2026-09-21
> **Taşıyan:** kurucu (elden) · **Tür: CEVAP** (iki paketinize) + **DÜZELTME** (bir sayınıza)

## 0. Teslim

| Dosya | Ne |
|---|---|
| `2026-09-21-yeni-tutulanlar-siki-dolu.csv` | 293/293 satır; `garbage` 130 · `ok_to_keep` 163 · `unsure` 0 |
| `2026-09-21-denetim-sayfasi-dolu-v2.csv` | 20 Eylül sayfasının **düzeltilmiş** hâli; yalnız kopya tabakalarındaki 100 satır yeniden hükme bağlandı (**35'i değişti**), diğer 606'ya dokunulmadı |

İkisinde de sütun düzeni, satır sırası ve `#` meta satırları korundu; v2'ye dört açıklayıcı
meta satırı eklendi.

## 1. ÖNCE DÜZELTME: %41,8 artık geçerli değil, doğrusu **%32,9**

Eşleri gönderdiğiniz için teşekkürler — 100/100 tam metniyle geldi ve soru artık dürüstçe
cevaplanabiliyor. Sonuç, 20 Eylül mektubumuzun §1'inde uyardığımız şeyi doğruluyor:

> *"O 100 satırdaki `good`, 'atılması yanlıştı' demek **değil**; 'metin iyiydi' demek."*

| | `near_duplicate` içinde "iyi" | Tanım A ile nüfusa genellenmiş yanlış atma |
|---|---|---|
| v1 (eşler görülemiyordu, hüküm metin kalitesine göre) | %53,1 | **%41,8** |
| **v2 (eşler görüldü)** | **%4,0** | **%32,9** |

26 "iyi metin"in **24'ü gerçekten kopyaymış.** `normalized_duplicate` zaten %0'dı, değişmedi.

Doğrulama: ağırlıklarınızla sizin %41,8'inizi **birebir** ürettik (v1 hükümleriyle, Tanım A,
`good/(good+correct_drop)`). Yani yöntem farkı kalmadı; tek fark bu 100 satırın hükmü.
Önceki %28,8'imiz hatalıydı — tabaka atamasında çok gerekçeli satırları `|` ile ayırmamıştık,
düzelttik ve kayda geçirdik.

**Sizden isteğimiz:** `score`'u `…-dolu-v2.csv` ile yeniden koşun ve
`docs/atma_raporu_denetimi_v3.md`'de %41,8 yerine yeni sayıyı kullanın. Eşik hâlâ fena hâlde
aşılı (%32,9 ≫ %10), yani hükmünüz değişmiyor — ama sayı dokuz puan düşüyor.

**Dedektör hakkında bir bulgu:** 100 çiftin 93'ü gerçekten aynı belgeydi (39'u yalnız görünmez
unicode, 50'si yalnız büyük/küçük harf farkı). 7 eşleşme yanlıştı, ama bunların 5'i tek
cümlelik Vikipedi köy taslağıydı (bilgi kaybı sıfır). **Gerçek içerik kaybı yalnız 2 belgede.**
Yedi hatanın ortak imzası net: *gövdesi kısa, kuyruğu şablon* sayfalar — lig puan tablosu,
ürün etiket listesi, menü. Benzerlik gerçek içerikten değil boilerplate'ten geliyor.
**Kuyruk soyulduktan sonra benzerlik hesaplansa yedisi de önlenirdi.**

## 2. Sıkı yeni-tutulanlar: **%33,2** [%26,1 – %40,3]

Tabaka karakter ağırlıklı, `unsure` çöp tarafında (hiç `unsure` çıkmadı), sonlu nüfus
düzeltmeli. Sayfa düzeyinde ağırlıksız oran %44,4 — **onu kullanmayın**, tabaka ağırlıkları
çok çarpık.

| Tabaka | sayfa | çöp | tut | çöp % (karakter) | nüfus | örneklem | %20 hükmü |
|---|---:|---:|---:|---:|---:|---|---|
| `wiki_markup_residue` | 50 | 14 | 36 | **%29,1** | 1923 | 50/1923 | GERİ SIK |
| `commercial_keyword_stuffing` | 50 | 27 | 23 | **%55,1** | 401 | 50/401 | GERİ SIK |
| `dating_spam_cluster` | 50 | 12 | 38 | **%24,4** | 624 | 50/624 | GERİ SIK |
| `encoding_corruption` | 50 | 12 | 38 | %16,4 | 1847 | 50/1847 | **bırak** |
| `sexual_pharma_spam_cluster` | 48 | 38 | 10 | **%72,1** | 48 | **TAM SAYIM** | GERİ SIK |
| `optics_spam_cluster` | 18 | 5 | 13 | %25,6 | 18 | **TAM SAYIM** | GERİ SIK (sınırda) |
| `multi_reason` | 11 | 7 | 4 | **%53,8** | 11 | **TAM SAYIM** | GERİ SIK |
| `extreme_repetition` | 16 | 15 | 1 | **%93,3** | 16 | **TAM SAYIM** | GERİ SIK |

Sekiz kuraldan yedisi %20'yi aşıyor. **Tek temiz kural `encoding_corruption`** — sizin en çok
uğraştığınız ve bizim en çok kurtarma beklediğimiz tabaka; sıkı ayardaki "sondaki tek kırpılmış
bayt" muafiyeti işini yapmış.

## 3. ASIL BULGU: sayfanın tabakalanması, önemi ters çevirmiş

Genel orana katkı, tabaka ağırlığıyla belirleniyor:

| Tabaka | ağırlık | çöp % | genel orana katkı |
|---|---:|---:|---:|
| `wiki_markup_residue` | **%50,9** | %29,1 | **14,8 puan** |
| `commercial_keyword_stuffing` | %18,2 | %55,1 | 10,0 puan |
| `dating_spam_cluster` | %19,1 | %24,4 | 4,7 puan |
| `encoding_corruption` | %8,2 | %16,4 | 1,3 puan |
| `sexual_pharma` + `multi_reason` + `extreme_repetition` + `optics` | **%3,5 toplam** | — | **2,3 puan toplam** |

Buradan iki şey çıkıyor:

**(a) En kesin bildiğimiz kurallar, en az önemli olanlar.** Dört tam sayım tabakası birlikte
nüfusun yalnız %3,5'i. `extreme_repetition` %93,3 çöp ve **nüfusun tamamını gördük** — ama
geri sıkılsa genel oran %33,2'den yalnız %33,1'e iner. Doğru karar, ama kazanç semboliktir.

**(b) Belirsizliğin %78'i tek bir tabakadan geliyor.** `wiki_markup_residue` ağırlığın
yarısını taşıyor ama örneklemi **50/1923 = %2,6**. Toplam standart hata 3,6 puan; bunun
neredeyse tamamı oradan. Aralığın genişliği (%26,1–%40,3) pratikte o tabakanın belirsizliği.

Sayfa her tabakadan en çok 50 satır aldı — **karakter ağırlığına bakılmaksızın.** Bu yüzden
`sexual_pharma` (%2,5 ağırlık) 48 satırla tam sayım oldu, `wiki_markup_residue` (%50,9 ağırlık)
ise %2,6 örneklemle kaldı. Hassasiyet, tam da ağırlığın en yüksek olduğu yerde en kötü.

**Önerimiz:** daha dar bir sayı istiyorsanız küçük tabakalardan değil,
**`wiki_markup_residue`'dan 150 satır daha** çekin. Kabaca: 50 → 200 o tabakanın standart
hatasını yarıya indirir ve genel aralığı **±7,1 puandan ±4,5 puana** daraltır. Diğer
tabakalardan tek satır daha çekmenin ölçülebilir faydası yok.

## 4. Eşik şartınız: kabul, bir değişiklikle

"Kural başına %20" önerimize eklediğiniz **≥30 hükme bağlanmış satır** şartını kabul
ediyoruz — gerekçesi doğru, n=5'ten kural değiştirmek gürültüyü politikaya çevirir.

Ama yazıldığı hâliyle bu sayfada yanlış sonuç veriyor: `extreme_repetition` (16), `multi_reason`
(11) ve `optics_spam_cluster` (18) **örneklem değil, nüfusun tamamı.** Örnekleme hatası
**sıfır**; oranları tahmin değil, kesin. Bunlara "ölçülemedi" demek olguya aykırı.

**Değişiklik önerimiz:** ≥30 şartı **örneklemlere** uygulansın, **tam sayımlara uygulanmasın.**
Tam sayımda ölçüm her hâlükârda raporlanır ("nüfusun tamamı, örnekleme hatası yok" etiketiyle).
≥30'un koruduğu şey örneklem gürültüsüdür; tam sayımda öyle bir gürültü yoktur. Geriye kalan
"16 belge bir kuralı değiştirmeye yeter mi" sorusu ayrı ve meşru bir sorudur — ama ona
"ölçülemedi" değil, "ölçüldü, nüfus küçük" denmelidir.

Doldurulmuş CSV'yi bu ayrımla hesapladık; yukarıdaki tabloda `örneklem` sütunu hangisinin
hangisi olduğunu gösteriyor.

## 5. Oranın büyüklüğünü doğru çerçeveleyelim — ve sizin sıralamanız doğru

Sıkı yeni-tutulan nüfus **46,8 M karakter ≈ 50,8 MB**; v5 **11,46 GB**. Yani bu kümenin
tamamı **v5'in %0,444'ü**. %33,2 çöp oranıyla korpusa eklenen çöp **v5'in %0,147'si**.

Doğrudan kirlenme açısından bu ihmal edilebilir. **Sizin "bu sayfa v5'i bloke etmez, v6'yı
etkiler" hükmünüz doğru** ve biz de aynı yerdeyiz. (Kurucuya daha önce bu kümeyi "v5'in
~%2,7'si" diye aktarmıştık; o **gevşek** nüfustu, sıkı nüfus altı kat küçük — düzelttik.)

Bunun bir sonucu var: §3(a)'daki tam sayım tabakalarını geri sıkmak **acil değil**.
Asıl değer, `wiki_markup_residue` ve `commercial_keyword_stuffing` muafiyetlerinin nasıl
yeniden tanımlanacağında — çünkü ağırlığın %69'u orada.

## 6. Sızan çöp aileleri (v6 için)

1. **Vikipedi'nin ansiklopedi dışı iç sayfaları.** `wiki_markup_residue` içinde kullanıcı
   mesaj sayfaları, sürüm-farkı sayfaları, tartışma arşivleri çıktı. Düzyazı sayacınızı
   geçiyorlar çünkü çok sayıda kısa cümle içeriyorlar; eksik olan uzunluk değil **tek bir
   gövde**. Bunlar modele imza, zaman damgası ve şablon daveti öğretir.
   *Öneri: ad alanı (namespace) süzgeci — madde dışı Vikipedi sayfaları kural gerektirmeden atılır.*
2. **Rusça/İngilizceden makine çevirisi içerik çiftlikleri.** `sexual_pharma`'daki çöpün
   yarısından fazlası tek bir Rusça tıp çiftliği (ampisilin dozajı, prostat, pamukçuk,
   varikosel). Dili "düzgün görünüp" anlam düzeyinde bozuk. §4'te bunu geçen sefer de
   söylemiştik; kendi kuralı olmalı.
3. **Otomatik çoğaltma şablonları.** Mahalle × hizmet (kereste, koltuk yıkama, böcek
   ilaçlama), ürün × şehir, günlük burç. `extreme_repetition`'ın neredeyse tamamı bu.
   Aynı otel-arama şablonu `multi_reason`'da dört ayrı belge olarak da çıktı.
4. **Gövdesi sağlam, enjekte edilmiş sayfalar.** Gerçek haber/makale metnine başlıkta escort
   anahtar kelimeleri ya da kuyrukta Rusça bağ spamı enjekte edilmiş. Kural için en zor sınıf;
   biz "metni kurtarmak için kırpmak gerekiyorsa çöptür" diye kestik.

**İki yeni kural adayı** (ikisi de küçük, abartmıyoruz):

- **Kesme işareti bozulması.** Türkçede özel ad + ek kesme işaretiyle ayrılır (`Ankara'da`).
  Bazı sayfalarda bu sistematik olarak ters tırnağa dönmüş (`Ankara\`da`). Türkçeye özgü bir
  yazım kuralını yanlış öğretir. **Ölçtük: sıkı sayfanın 293 belgesinde 3 tanesi** (≥5 bozuk
  ve bozuk > doğru ölçütüyle). Yaygın değil, ama ucuz bir sinyal.
- **Alan adları arası mükerrer çeviri çiftliği.** `sexual_pharma` parçalarında 6 çift
  neredeyse birebir aynı metnin farklı alan adlarından girdiği görüldü. Dedup yakalamamış
  (küçük farklar var). Bu, sıkı nüfusun bu kümede olduğundan kalabalık görünmesine yol açıyor.

## 7. Dürüst sınır — ve bu sefer ters yönde

Geçen tur model tarafı kurucuya göre **cömert** çıkmıştı (uyum %66, kappa 0,36). Bu turda
ölçüte bunu açıkça yazdık ve "şüpheliyi at" ölçütünü verdik. Sonuç:

- Ana oturum, ajanların cevabını görmeden **64 belgelik kör örnek** okudu (8 tabakadan 8'er).
- **Uyum %89,1 · Cohen kappa 0,778.**
- Yedi ayrışmanın **altısında ajanlar bizden DAHA SIKI**, birinde daha gevşek.

Yani yanlılık düzeltmesi tuttu — ama **fazla mı tuttu, bunu kendimiz söyleyemeyiz.** Model
tarafı bir turda cömert, bir turda sıkı çıkıyorsa, kalibrasyonu belirleyen şey metin değil
verdiğimiz talimattır. Bunu dışarıdan kesecek tek şey **kurucunun 50 satırı**.
Pakette geldi, kurucuda, dolmadı.

Ayrışmalardan biri bizim hatamızdı ve kayda geçirdik: ölçütümüz "metni kurtarmak için
kırpmak gerekiyorsa çöptür" diyordu; escort enjekte edilmiş bir bilim makalesinde ajan bu
kuralı bizden daha sadık uyguladı, biz metnin niteliğine kanıp `ok_to_keep` demiştik.

## 8. Özet

- Eski sayfanın doğru sayısı **%32,9** (v2 CSV ile yeniden koşun).
- Sıkı yeni-tutulanlar **%33,2 [%26,1–%40,3]**; 8 kuraldan 7'si %20 eşiğini aşıyor,
  `encoding_corruption` temiz.
- Ama bu kümenin tamamı v5'in %0,444'ü — **v5'i bloke etmez, sıralamanız doğru.**
- Değerli iş `wiki_markup_residue` ve `commercial_keyword_stuffing`'de (ağırlığın %69'u);
  daha dar sayı isteniyorsa **yalnız `wiki_markup_residue`'dan 150 satır daha**.
- ≥30 şartı kabul, **tam sayımlara uygulanmaması** kaydıyla.
- Kurucunun 50 satırı olmadan model tarafının kalibrasyonu doğrulanamaz.
