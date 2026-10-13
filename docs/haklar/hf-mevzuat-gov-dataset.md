# `muhammetakkurt/mevzuat-gov-dataset` — lisans ve olgu notu

**Tarih:** 2026-10-13 · **Hazırlayan:** Derlem oturumu (Claude) · **Karar:** kurucu
Hukuki görüş değildir; şartlar okunduğu gibi kaydedilmiştir. Hiçbir veri indirilmedi (yalnız
veri kartı, HF API üstverisi, commit geçmişi, dosya ağacı, datasets-server `splits`/`size`/
`info`/`statistics`/`first-rows` uçları, kazıyıcı deposunun README'si ve mevzuat.gov.tr'nin
herkese açık sayfaları okundu). Doğrulanamayan her şey "doğrulanamadı" diye işaretlidir.

Bu not bir **idari/resmî Türkçe** damarı adayını anlatır: FineWeb2-HQ `tur_Latn` örnekleminde bu
türden metin 1.000 belgede 3 idi ([fineweb2_hq_degerlendirmesi_2026_10.md](../fineweb2_hq_degerlendirmesi_2026_10.md)).
Bu veri seti damarı doldurmaz, tohumlar: yalnız **kanun** (907 belge, kestirimen yaklaşık 20 milyon
karakter; §4).

| Alan | Değer |
|---|---|
| Veri seti | https://huggingface.co/datasets/muhammetakkurt/mevzuat-gov-dataset (yayıncı: tek kişi, `muhammetakkurt`; aynı kişinin kazıyıcı deposu `muhammetakkurtt/mevzuat-gov-scraper`, MIT) |
| Tür | Türkçe kanun metinleri; kanun başına bir kayıt, maddeler iç içe liste (§3) |
| Bölümler | yalnız `train` (config `default`) |
| Sabit sürüm | repo commit `3bf298d984aefe7154d89094ecb4c045de6f96e9` (HF API `sha`; `lastModified` 2024-10-01T10:08:39Z; `createdAt` 2024-09-09T07:59:17Z) |
| Veri dosyası sürümü | `mevzuat_parsed.json` blob oid `282bc6acf55965ae5de625fe968cf140297f5939`, LFS sha256 `4421eb596f45a1dce8de68b0239c3df1bf6f7c1041da961058512f1ac4312492`; 7 commit'in son ikisi yalnız `README.md` (2024-09-09 ve 2024-10-01) |
| Kart lisansı | `mit` (kart YAML ve API `cardData.license`) — **ama kartın kendi metni izinsiz ticari kullanımı yasaklıyor** (§1b) |
| İçeriğin asıl kaynağı | mevzuat.gov.tr (T.C. Cumhurbaşkanlığı Genel Sekreterliği Hukuk ve Mevzuat Genel Müdürlüğü'nün Mevzuat Bilgi Sistemi); kartın ve kazıyıcı README'sinin beyanı. Kayıtlardaki `url` alanı sitedeki kanun sayfasına işaret ediyor |
| Erişim | açık (`gated: false`, `private: false`, `disabled: false`); 221 indirme, 10 beğeni (API, 2026-10-13) |
| Boyut | **907 kayıt (kanun)**; 1 veri dosyası `mevzuat_parsed.json` = **37.314.203 bayt** (~37,3 MB); depo toplamı 37.318.962 bayt (3 dosya); datasets-server Parquet = 14.088.937 bayt, bellek = 33.346.057 bayt |
| Sütun sayısı | 7 (üçü iç içe: `resmi_gazete`, `dustur`, `maddeler`) |
| Öneri `rights_status` | **`cleared` (ticari olmayan)** — koşullu; kurucu kararı gerekir (§8) |
| Ana korpusta zaten var mı? | **Doğrudan hayır.** Dolaylı örtüşme (mC4'te kanun metni kopyaları) **ölçülmedi** (§7) |

## 1. Lisans: kart, kazıyıcı ve içeriğin kendisi ayrı katmanlar

**1a. Kart lisansı.** Kart YAML: `license: mit`. Depoda **LICENSE dosyası yok** (ağaç:
`.gitattributes`, `README.md`, `mevzuat_parsed.json`); MIT metnindeki telif sahibi/yıl satırı bu
yüzden hiçbir yerde yazılı değil. Kart ayrıca `language: [tr, ota, tur]` diyor (`ota` = Osmanlı
Türkçesi; örnek satırlar modern Latin yazılı Türkçe, §6) ve `task_categories: text-classification`.

**1b. Kartın kendi kısıtı (aynen, README "Source and Licensing", okundu 2026-10-13):**

> *"The dataset has been sourced from the Turkish Government Legislation Portal. Users are
> responsible for ensuring they comply with any legal usage terms when working with the data."*
>
> *"This dataset is provided for research and educational purposes. It may not be used for
> commercial purposes without obtaining proper permissions from the Turkish government or the
> original data source."*

Bu cümleler YAML'daki `mit` ile **çelişiyor** (MIT ticari kullanımı serbest bırakır; kart "izin
almadan ticari kullanılamaz" diyor). Hangisinin geçerli olduğu kartta çözülmemiş; **doğrulanamadı**.
Derlem'in kapsamı ticari değil; ama cümleyi bağlayıcı sayıp ticari olmayan kapsamla sınırlamak güvenli
okumadır. Kart ayrıca "yasal kullanım şartlarına uymak kullanıcının sorumluluğu" diyor — yani
yayıncı kaynak sitenin şartlarını **üstlenmiyor**.

**1c. Kazıyıcı deposu.** `muhammetakkurtt/mevzuat-gov-scraper`: GitHub API lisansı `MIT` (`LICENSE`:
"MIT License / Copyright (c) Muhammet…"), son push 2025-11-07. README: Scrapy + Selenium ile sitedeki
mevzuatı yıl aralığına göre çeker; `mevzuat_parser.py` regex ve spaCy (`tr_core_news_lg`) ile kanun
adı, numara, kabul tarihi, Resmî Gazete bilgisi ve maddeleri ayrıştırır. README: bu veri kümesi
*"2024 Eylül ayına kadar yayımlanan mevzuatları"* içerir ve *"Hatalı veya eksik kanun başlıkları ve
bazı kısımlar manuel olarak düzeltilmiştir."* README ayrıca "Geliştirme Alanları"nda: *"Mevzuat
metinlerinin bazı bölümlerinde ekstra karakterler ve hatalı biçimlendirmeler olabilir."* MIT,
kazıyıcı **kodunu** kapsar; çıktı verisi için ayrı bir beyan yok.

**1d. İçeriğin telif durumu (Türkiye).** 5846 sayılı Fikir ve Sanat Eserleri Kanunu **md. 31**
("II – Genel menfaat mülahazasiyle: 1. Mevzuat ve içtihatlar"), mevzuat.gov.tr'deki güncel
metinden (`https://www.mevzuat.gov.tr/MevzuatMetin/1.3.5846.pdf`, okundu 2026-10-13) aynen:

> *"Madde 31 – Resmen yayımlanan veya ilan olunan kanun, Cumhurbaşkanlığı kararnamesi,
> yönetmelik, tebliğ, genelge ve kazai kararların çoğaltılması, yayılması, işlenmesi veya her
> hangi bir suretle bunlardan faydalanma serbesttir."*

Dipnot 10: *"2/7/2018 tarihli ve 700 sayılı KHK'nin 24 üncü maddesiyle, bu maddede yer alan 'tüzük'
ibaresi 'Cumhurbaşkanlığı kararnamesi' şeklinde değiştirilmiştir."* (Eski metin "kanun, tüzük,
yönetmelik, …" idi; güncel metin yukarıdaki.) Yani resmen yayımlanan kanun metinleri çoğaltma/
işleme/yararlanma bakımından **serbest**; maddede amaç sınırı (ticari olmayan vb.) yok. Bu notun
yorumu: 907 kanunun maddelerinin kendisi için telif engeli beklenmez.

Açık kalan noktalar (hukuki görüş değil, ayrım): (i) md. 31 "resmen yayımlanan veya ilan olunan"
metinden söz eder; mevzuat.gov.tr'deki metin Resmî Gazete'deki ilk metin değil, **kodifiye (tek
metin haline getirilmiş, güncel)** metindir (site tanıtımı: *"Resmî Gazete'de yayımlanan kanunlar …
tek metin haline getirilir ve güncel olarak yayımlanır"*). Kodifiye metnin md. 31 kapsamında
sayılıp sayılmadığı **doğrulanamadı**. (ii) Sitenin bir derleme/veri tabanı olarak ayrı koruma
iddia edip etmediği **doğrulanamadı** (aşağıda). (iii) Ayrıştırma çıktısının (alan yapısı, madde
dizilişi) kazıyıcı yazarının emeği olduğu açık; telif niteliği taşıyıp taşımadığı **doğrulanamadı**
(alan yapısı olgusal, eşik düşük görünüyor).

**1e. mevzuat.gov.tr kullanım şartları — doğrulanamadı.** Okunanlar (2026-10-13):

- Ana sayfa ve her sayfanın alt bilgisi: *"2020 Tüm Hakları Saklıdır. Gizlilik, Kullanım ve Telif
  Hakları bildiriminde belirtilen kurallar çerçevesinde hizmet sunulmaktadır."* Bildirim var
  deniyor ama sayfa kaynağında ona giden bir bağlantı yok (JS ile açılan bir pencere olabilir);
  `/telifhaklari`, `/gizlilik`, `/kullanimsartlari`, `/iletisim` ve benzeri 12 yol denendi, hepsi
  sitenin 404 sayfasına düştü; `/Yardim` ve `/faydalilinkler` bildirim içermiyor. Bildirimin metni
  bu yüzden **okunamadı**; yeniden dağıtımı, makineyle okumayı ya da yapay zekâ eğitimini
  yasaklayıp yasaklamadığı **doğrulanamadı**.
- "Hakkımızda" (`/hakkimizda`, Tanıtım ve Tarihsel Süreç): hizmet *"ücretsiz ve koşulsuz olarak
  herkesin kullanımına sunulmuştur"* (abonelik sisteminin kalkışını anlatan cümle) ve *"Mevzuat Bilgi
  Sisteminden ücretsiz olarak yararlanabilirsiniz."* Bunlar **erişim** beyanıdır; yeniden kullanım/
  yeniden dağıtım lisansı değildir. Aynı sayfa Mevzuat Külliyatı'nın nasıl kurulduğunu anlatıyor:
  *"uygulama imkânı kalmamış olanlar ayıklanmış, hükümleri yürürlükte bulunanlar belirlenmiş"*
  (yani site yürürlükteki mevzuatı tutuyor; mülga mevzuat ayrı kategori, §4).
- `robots.txt` (64 satır, `Last-Modified` 2026-06-30): yalnız `User-agent: Googlebot` bloğu ve bir
  dizi `Noindex:` satırı (belli birkaç PDF/kanun sayfası); **`Disallow`, `Crawl-delay` ya da
  `Sitemap` satırı yok**, diğer ajanlar için kural yok. Kazıyıcının robots.txt'ye, oran sınırına ve
  (varsa) kullanım şartına uyup uymadığı **doğrulanamadı** (Selenium ile gerçek tarayıcı sürüyor;
  README oran sınırından söz etmiyor). Kazıma Eylül 2024'te yapılmış; Derlem sitenin kendisini
  kazımıyor, bu veri setini alıyor.
- Hizmetin sorumlusu: T.C. Cumhurbaşkanlığı Genel Sekreterliği Hukuk ve Mevzuat Genel Müdürlüğü.
  Metnin hukuken bağlayıcı/resmî olup olmadığına ilişkin bir feragat cümlesi bu sayfalarda
  **bulunamadı**.

## 2. Sürüm sabitleme

- Alım bu sha'ya sabitlenmeli: `3bf298d984aefe7154d89094ecb4c045de6f96e9`.
- Commit geçmişi (HF API, 7 commit): `e2b635c1` initial commit (2024-09-09T07:59:17Z); üç "Initial
  dataset upload" (08:06–08:11); `8b123ccc` ve `24ab8f92` "Update README.md" (2024-09-09);
  `3bf298d9` "update readme" (2024-10-01). datasets-server `info`'sunun indirme sağlaması
  `24ab8f92` commit'ine bağlı ve 37.314.203 bayt diyor; bugünkü ağaçtaki dosya boyutu aynı. Blob
  özeti eski commit için okunmadığından bayt eşitliği **doğrulanamadı** (yalnız boyut eşit).
- Kesme tarihi: kazıyıcı README'si "2024 Eylül ayına kadar"; ilk satır 7524 sayılı kanun (kabul
  28/07/2024, RG 02/08/2024). Sonrasındaki kanunlar yok; veri seti 2026-10-13'te ≈ 2 yıl eski.
- Kart sürüm/değişiklik günlüğü tutmuyor.
- Not: `.../raw/main/README.md` ilk istekte **başka bir veri setinin** (`AlicanKiraz0/Turkce-Atlas-Instruct`)
  kartını döndü; bu nottaki kart alıntıları `.../resolve/main/README.md`'den alındı (yanıt
  başlığında `X-Repo-Commit: 3bf298d…`; 2.238 bayt, `git hash-object` = ağaçtaki oid `9a4576d3…` —
  yani doğru kart).

## 3. Şema ve belge birimi

Dosya ağacı (HF API `tree/main`): `.gitattributes` (2.521 bayt), `README.md` (2.238 bayt),
`mevzuat_parsed.json` (37.314.203 bayt, LFS/Xet). **Biçim:** tek JSON dosyası (`format:json`); dizi
mi satır-JSON mu olduğu indirilmeden **doğrulanamadı**. Bu, TASK-032'nin "JSONL" alım yoluna doğrudan
oturmuyor (§5).

datasets-server: bölüm `train` (tek), `num_rows` = **907**, `num_columns` = 7; `splits`'te
`pending`/`failed` boş. `/info` şeması:

| Sütun | Tür | Anlam (kart) |
|---|---|---|
| `url` | string | sitedeki kanun sayfası (örn. `https://www.mevzuat.gov.tr/mevzuat?MevzuatNo=7524&MevzuatTur=1&MevzuatTertip=5`) |
| `Kanun Adı` | string | kanunun adı (büyük harfli; sütun adında **boşluk ve büyük harf** var) |
| `kanun_numarasi` | string | kanun numarası ("7524") |
| `kabul_tarihi` | string | kabul tarihi ("28/07/2024") |
| `resmi_gazete` | yapı {`sayi`: string, `tarih`: string} | Resmî Gazete sayısı ve tarihi |
| `dustur` | yapı {`cilt`, `sayfa`, `tertip`: string} | Düstur künyesi; kart: *"may be missing or incomplete"* |
| `maddeler` | liste(yapı {`madde_numarasi`: string, `text`: string}) | kanunun maddeleri |

**Belge birimi.** Bir kayıt = **bir kanunun tamamı**; metin `maddeler` listesinde **madde madde**
duruyor, düz bir `text` alanı **yok**. Madde sınırı korunmuş (`madde_numarasi` ayrı alan); fıkra ve
bent sınırı **korunmamış** (aşağıda).

**Üstveri.** Var: kanun adı, kanun numarası, kabul tarihi, Resmî Gazete sayı+tarih, Düstur (tertip/
cilt/sayfa), site URL'si. **Yok:** mevzuat türü sütunu (tür yalnız `url`'deki `MevzuatTur=1`'den
türetilir), yürürlük tarihi, yürürlük/mülga durumu, değişiklik geçmişi, madde başlığı alanı,
bölüm/kısım bilgisi.

**`/first-rows` örnekleri.** datasets-server `truncated: true`; yanıt boyut sınırı yüzünden yalnız
**ilk 11 satır** geldi (numaralar azalan: 7524, 7512, 7499, 7474, 7464, 7456, 7452, 7446, 7445, 7442,
7441; dosya sırası büyük olasılıkla kanun numarasına göre azalan, ama yalnız ilk 11 satır görüldü).
Üç örneğin alan yapısı (alan adları aynen, metinler özetlendi):

1. `{url: ".../mevzuat?MevzuatNo=7524&MevzuatTur=1&MevzuatTertip=5", "Kanun Adı": "VERGİ KANUNLARI İLE
   BAZI KANUNLARDA VE 375 SAYILI KANUN HÜKMÜNDE KARARNAMEDE DEĞİŞİKLİK YAPILMASINA DAİR KANUN",
   kanun_numarasi: "7524", kabul_tarihi: "28/07/2024", resmi_gazete: {sayi: "32620", tarih:
   "02/08/2024"}, dustur: {cilt: null, sayfa: null, tertip: null}, maddeler: [33 öğe]}`. İlk üç
   madde: `MADDE 1` = *"( 21/7/1953 tarihli ve 6183 sayılı … Kanun ile ilgili olup, yerine
   işlenmiştir.)"* (119 karakter); `MADDE 2` aynı kalıpta; `MADDE 3` = başka kanunun maddesini
   yeniden düzenleyen alıntı; ardından `MADDE 69` (1.573 karakter; **değiştirilen kanunun**
   maddesi, `MADDE 3` içinde alıntılanmış, ayrı öğe olarak çıkarılmış). Son madde: `MADDE 61`
   *"Bu Kanun hükümlerini Cumhurbaşkanı yürütür."*
2. `{… kanun_numarasi: "7512", "Kanun Adı": "DIŞİŞLERİ TEŞKİLATINI GÜÇLENDİRME VAKFI KANUNU",
   kabul_tarihi: "30/05/2024", resmi_gazete: {sayi: "32568", tarih: "06/06/2024"}, maddeler: [12 öğe]}`.
   Gerçek madde metni: `MADDE 1` = *"(1) Bu Kanunun amacı, … (2) Bu Kanun; … kapsar. Tanımlar"*
   (537 karakter; sondaki "Tanımlar" **bir sonraki maddenin başlığı**). `MADDE 2` sonunda *"İKİNCİ
   BÖLÜM Vakfın Faaliyetleri ve Organları Vakfın faaliyetleri"* eklenmiş.
3. `{… kanun_numarasi: "7499", "Kanun Adı": "CEZA MUHAKEMESİ KANUNU İLE BAZI KANUNLARDA DEĞİŞİKLİK
   YAPILMASINA DAİR KANUN", kabul_tarihi: "02/03/2024", resmi_gazete: {sayi: "32487", tarih:
   "12/03/2024"}, maddeler: [13 öğe]}`. Madde numaraları 1, 4, 5, 9, 12, 23, 33, 37, 38, 39,
   `GEÇİCİ MADDE 1`, 40, 41: aradaki numaralar (başka kanunları değiştiren maddeler) atlanmış;
   `MADDE 1` metni *"2- 3- ( 9/6/1932 tarihli ve 2004 sayılı İcra ve İflas Kanunu ile ilgili
   olup, yerine işlenmiştir.)"*.

Bu 11 satırda (yalnız bunlar görüldü): `maddeler` hiçbirinde boş/`null` değil; `dustur` 11'inde de
tümüyle `null` (modern kanunlar; Düstur yalnız eski kanunlarda dolu olmalı, görülmedi); 175 madde
metninde `\n` ve `\t` **0** (fıkra ve paragraf sonları kaybolmuş; "(1) … (2) …" işaretleri satır
içinde kalmış); `madde_numarasi` kalıpları: `MADDE N`, `Madde N`, `GEÇİCİ MADDE N`, `Geçici Madde N`
(büyük/küçük harf tutarsız). Tarih biçimi karışık: `28/07/2024`, `14/7/2023`, `2/11/2023` (kart:
"19.01.1990 veya 19/01/1990" — nokta ayırıcı da olabilir). `kabul_tarihi` uzunluğu 8–33 karakter
(33 karakterlik değerler tek tarih değil gibi; **doğrulanamadı**), 2 kayıtta `null` (`statistics`).

## 4. Boyut ve kapsam

| Ölçü | Değer | Kaynak |
|---|---|---|
| Kanun (belge) sayısı | **907** | datasets-server `size` ve `statistics` |
| Madde sayısı (toplam) | ≈ **40.850** (ortalama 45,04 × 907) | `statistics` ortalaması; kesin toplam **doğrulanamadı** |
| Madde/kanun | en az 0 (**en az bir kanunun `maddeler` listesi boş**), ortanca 19, ortalama 45,04, en çok 1.570 | `statistics` |
| Kanun başına madde histogramı (10 kutu, genişlik ≈ 157) | 868 kanun 0–158; 23: 158–316; 6: 316–474; 3: 474–632; 3: 632–790; 1: 790–948; 1: 948–1.106; 0: 1.106–1.264; 0: 1.264–1.422; 2: 1.422–1.570 | `statistics` |
| `Kanun Adı` uzunluğu | 9–783 karakter, ortalama 83,4, ortanca 66 | `statistics` |
| `kanun_numarasi` basamağı | 1 hane: 7; 2 hane: 9; 3 hane: 66; 4 hane: 825 | `statistics` |
| Metin boyutu | **≈ 20 milyon karakter** (11 satırlık örneklem: 175 maddede 85.671 karakter, madde başına ≈ 490; × 40.850); **üst sınır ≈ 33,3 MB** (datasets-server bellek tahmini, tüm sütunlar dahil) | **kestirim**; örneklem yanlı (yalnız 2023–2024 kanunları) |
| Kanun başına karakter (11 örnek) | en az 1.551 (7446), en çok 22.406 (7452), ortanca 6.934 (7474) | `/first-rows` |
| Madde başına karakter (175 örnek) | ortanca ≈ 124; %80'i ≤ 532; en uzunlar 1.100+ (maddelerin yarısından fazlası stub/kısa kalıp, §6) | `/first-rows` |
| Mevzuat türleri | Kart: *"various laws, regulations, and amendments"*; kazıyıcı README'si veri kümesine *"(Kanunlar)"* diyor; 11 örnek satırın tümü `MevzuatTur=1` (kanun). **Yönetmelik, tebliğ, KHK, Cumhurbaşkanlığı kararnamesi, tüzük, Cumhurbaşkanı kararı içeren hiçbir satır görülmedi; 907 satırın tamamı için "yalnız kanun" iddiası doğrulanamadı** | kart + `/first-rows` |
| Tarih aralığı | Kanun numarası 1 haneli (7), 2 haneli (9), 3 haneli (66), 4 haneli (825): düşük numaralı eski kanunlar var; en yeni 7524 (RG 02/08/2024). Eski kanunların kabul yıllarının dağılımı **doğrulanamadı** | `statistics` + `/first-rows` |
| Yürürlükten kalkmış (mülga) | Dahil olup olmadığı **doğrulanamadı**: yürürlük durumu sütunu yok; sitede "Mülga Mevzuat" ayrı bir kategori ve site yürürlükteki metni tutuyor; 907, numara aralığının (1–7524) ≈ %12'si → veri seti kanunların tamamı değil, **bir alt kümesi**; numaralar bitişik değil (7445, 7446, sonra 7452) ve seçim ölçütü kartta belgelenmemiş | kart + `/first-rows` |
| `statistics` kapsamı | yalnız `Kanun Adı`, `kabul_tarihi`, `kanun_numarasi`, `maddeler` (madde sayısı), `url`; iç içe yapılar (`resmi_gazete`, `dustur`) ve madde **metin uzunluğu** için istatistik yok → toplam karakter ve madde uzunluğu dağılımı resmî uçtan **ölçülemedi** | `statistics` |

Derlem'e ölçek: ≈ 20–33 MB metin, v3'ün 13,57 GB'ının binde birkaçı. Yani bu kaynak **korpus
hacmi** değil, **alan kapsamı** (idari-resmî damar, `hukuk-mevzuat`; [alan_taksonomisi.md](../alan_taksonomisi.md))
için değerli; ve bu kaynakta yalnız kanun var: kurucunun karar motoru için gereken yönetmelik,
tebliğ, genelge ve karar metinleri **bu veri setinde görülmedi**.

## 5. Derlem'e eşleme taslağı ve belge sınırı önerisi

Dayanak: [belge_sinirlari_politikasi.md](../belge_sinirlari_politikasi.md) §4 ("bir kayıt = bir belge,
asla bölünmez; belge metni manifestte adı yazan tek metin alanıdır; başlık metne eklenmez; paragraf
sonları saklanan nesnede korunur; kayıt sayısı, metin alanı, sabit sürüm SHA'sı manifeste yazılır")
ve [TASK-044](../gorevler/TASK-044-common-document-record-and-source-adapters.md)
(`derlem.document.v1`).

**Çakışma:** bu veri setinin kaydı (kanun) doğal belgedir, ama **tek metin alanı yok**; metin
`maddeler[].text` listesi. Politikanın "tek metin alanı" cümlesi bu kaynağa aynen uygulanamıyor.

| Seçenek | Belge | Sayı | Politikayla uyum |
|---|---|---|---|
| **(A) Kanun bütün** | bir kanun = bir belge; `text` = maddelerin sırayla deterministik birleşimi | 907 | Kayıt = belge kuralına uyar (kayıt bölünmüyor, başka kayıtla birleşmiyor); "tek metin alanı" cümlesi için **manifest istisnası** gerekir: `text_field` = `maddeler[*].text`, `text_assembly` kuralı yazılı |
| (B) Madde | bir madde = bir belge | ≈ 40.850 | Kuralı **bozar** ("asla bölünmez"); ayrıca maddelerin yarısından fazlası stub/kısa (§6) |
| (C) Fıkra | — | — | Olanaksız (fıkra alanı yok) |

**Öneri: (A).** Birleşim kuralı (manifeste kelimesi kelimesine yazılır, sürümlenir): her madde için
`madde_numarasi + "\n" + text`; maddeler `"\n\n"` ile ayrılır; **kaynak sırası korunur** (madde
numaraları artmayabilir, §6 — yeniden sıralanmaz); kayıt içinde hiçbir madde atılmaz, düzeltilmez,
kaynaklar arası birleştirilmez. `Kanun Adı` metne **eklenmez** (kural 2), `extra` alanında durur.
Düzleştirme yalnız txt ihracatında olur. `maddeler` listesi boş kanunlar sayılıp raporlanır,
sessizce atılmaz (TASK-044: "empty text → counted and reported"). Politika değişikliği önerisi:
kural 2'ye "birden çok alanın deterministik birleşimi manifestte kuralıyla birlikte yazılırsa tek
metin alanı sayılır" cümlesi — **kurucu kararı**.

`derlem.document.v1` taslağı:

| Derlem alanı | Kaynak |
|---|---|
| `text` | (A) birleşimi |
| `source_id` | `hf:muhammetakkurt/mevzuat-gov-dataset` |
| `source_ordinal` / `provenance.row` | kaynak dosyadaki sıra (0 tabanlı) |
| `provenance.dataset` | `muhammetakkurt/mevzuat-gov-dataset` |
| `provenance.revision` | `3bf298d984aefe7154d89094ecb4c045de6f96e9` |
| `provenance.file` | `mevzuat_parsed.json` (LFS sha256 `4421eb59…`) |
| `provenance.external_id` | `kanun:` + `kanun_numarasi` |
| `provenance.url` | `url` |
| `provenance.crawl_date` | **yok** (kazıma tarihi satırlarda yok; yaklaşık Eylül 2024) |
| `language` (bildirilen) | `tr` |
| `rights` | `license_id`: kart `mit` + kart kısıtı (§1b); `scope`: ticari olmayan; `evidence_ref`: bu not |
| `extra` (JSON) | `title` (`Kanun Adı`), `mevzuat_turu` (`kanun`, `url`'deki `MevzuatTur=1`'den türetilmiş, kaynakta sütun değil), `kanun_numarasi`, `kabul_tarihi` (ham dizi + ISO'ya normalize), `resmi_gazete.sayi`, `resmi_gazete.tarih` (ham + ISO), `dustur`, `madde_sayisi`, `alan`: `hukuk-mevzuat` |
| `signals` | `stub_ratio` (metni "yerine işlenmiştir" kalıbında olan maddelerin payı), `madde_sayisi`, `bos_madde_sayisi` |

Tarih normalizasyonu: `d/m/yyyy`, `dd/mm/yyyy`, `dd.mm.yyyy` biçimlerini kabul eden bir ayrıştırıcı
gerekir; ayrıştıramadığı değeri (33 karakterlik `kabul_tarihi` gibi) ham bırakıp saymalı. Alım:
tek 37 MB'lık JSON'dur; TASK-032'nin JSONL yoluna girmeden önce bir JSON → belge dönüştürücüsü
(adapter) gerekir. Bu not kod yazmıyor.

## 6. Kalite ipuçları (yalnız ilk 11 satırdan; 175 madde)

- **Kodlama:** Bozuk karakter (`U+FFFD`) **0**; Türkçe harfler (ç, ğ, ı, ö, ş, ü) 175 maddenin
  173'ünde doğru. Örnek yalnız 2023–2024 kanunlarından; **eski kanunlar için** kart: *"Especially in
  older laws, there may be different letters or signs"* — OCR/kodlama bozukluğu eski kısımda
  **doğrulanamadı**, alımdan önce rastgele bir kesitle ölçülmeli.
- **Stub (değiştirme) maddeleri:** 175 maddenin **94'ü (%53,7)** "… ile ilgili olup, yerine
  işlenmiştir." kalıbında (karakter olarak %14,1: 12.076/85.671). 11 kanunun **6'sı "… değişiklik
  yapılmasına dair" türü değiştirici kanun**; bunlarda madde gövdesi çoğunlukla yalnız yönlendirme
  cümlesi (7499: 13 maddenin 10'u; 7445: 21'in 18'i; 7456: 23'ün 18'i). Bu kanunlar mevzuat.gov.tr'de
  değiştirilen kanunun içine işlendiği için kendi metni boş bırakılmış. **Pretrain değeri düşük
  belge sınıfı**; çıkarma kararı alımın değil kalite süzgecinin işi (politika kural 4: kısa kayıt
  kısa belge olarak kalır) — `stub_ratio` sinyali bu yüzden önerildi.
- **Madde başlığı/bölüm yapışması:** bir sonraki maddenin kenar başlığı ("Tanımlar", "Yürürlük",
  "Yürütme") ve bölüm başlığı ("İKİNCİ BÖLÜM Vakfın Faaliyetleri …", 6/175 maddede) bir önceki
  maddenin **sonuna** yapışmış; madde başlığı ayrı alan değil. Metin akışı bozulmuyor ama başlıklar
  yanlış maddeye ait görünüyor.
- **Numaralandırma:** sıra monoton değil (`MADDE 3`'ten sonra `MADDE 69`, sonra `MADDE 4`:
  değiştirilen kanunun alıntı maddesi ayrı öğe olmuş); numaralar atlıyor (7499: 1, 4, 5, 9, 12, 23, …);
  175 maddenin 35'inin metni `N-` ("2- 3- 4-") kırıntısıyla başlıyor (silinen madde numaralarının
  artığı); `madde_numarasi` yazımı tutarsız (`MADDE`/`Madde`, `GEÇİCİ MADDE`/`Geçici Madde`).
- **Tablo/ek kalıntısı:** 175 maddelik örnekte görülmedi; kanun sonu ek tabloları ("(I) SAYILI
  LİSTE" vb.) için **doğrulanamadı** (uzun kanunlar örnekte yok).
- **Tekrar:** 175 maddede 14 madde birebir aynı metin (çoğu aynı kalıptaki stub cümleleri). Kanun
  içi tekrar normal; kanunlar arası aynı metin (değiştirici kanunlardaki ortak yürürlük/yürütme
  maddeleri) pretrain'de tekrar ağırlığı yaratabilir.
- **Düz metin:** `\n` yok, fıkra sonu yok; fıkralar `(1)`, `(2)` ile, bentler `a)`, `b)` ile satır
  içinde. Politikadaki "paragraf sonları saklanan nesnede korunur" kuralı bu kaynakta işe yaramaz:
  paragraf sonu Derlem'de değil, kazıyıcıda kaybolmuş.
- **Dil etiketi:** `ota` etiketi örneklerle doğrulanmıyor; sütunlarda dil alanı yok.

## 7. Ana korpusumuzla örtüşme

- `wiki_oscar`: mC4-tr (%90,6) + Wikipedia-tr (%9,4). Bu veri seti doğrudan site kazıması;
  `wiki_oscar`'ın hiçbir kaynağıyla ortak kayıt yok.
- **Dolaylı örtüşme ihtimali:** mevzuat.gov.tr sayfaları Common Crawl'da olabilir (site HTML döndürüyor;
  `robots.txt` yalnız Googlebot için birkaç sayfaya `Noindex` koyuyor, diğer ajanlara kural yok) ve
  kanun metinleri çok sayıda başka sitede (hukuk portalları, kurum siteleri, Resmî Gazete yansıları)
  kopyalı; bunlar mC4-tr'de olabilir. **Ölçülmedi.** Ölçüm yolu: TASK-024 yöntemiyle 907 kanundan
  rastgele örneklemin `wiki_oscar`/FineWeb-2'de bulunma payı (kısa kesit + yakın kopya).
- Kayıt biçimi (kanun başına `maddeler` listesi) mC4'teki sayfa biçiminden farklı olduğu için
  birebir belge eşleşmesi beklenmez; madde düzeyinde alt dizgi eşleşmesi mümkün.
- FineWeb2-HQ ile ilişki: HQ örnekleminde idari-resmî metin %0,3 idi; bu kaynak o açığa kısmi bir
  cevap, ama yalnız kanun için.

## 8. Yükümlülükler, öneri ve doğrulanamayanlar

| Yükümlülük | Durum |
|---|---|
| Atıf | MIT için telif sahibi satırı depoda **yok**. İyi niyet atfı öneriliyor: *"Mevzuat metinleri mevzuat.gov.tr'den; `muhammetakkurt/mevzuat-gov-dataset` @ `3bf298d`"* (veri kartında/model künyesinde) |
| Share-alike | Yok (MIT) |
| Ticari kullanım | Kart YAML (`mit`) serbest bırakır; kart metni (**"may not be used for commercial purposes without obtaining proper permissions"**) kısıtlar; FSEK md. 31 resmen yayımlanan metinler için serbestlik tanır ama kodifiye metin için yorum açık (§1d) → ticari kullanım **doğrulanamadı** |
| Yeniden dağıtım | Derlem ham metni yeniden dağıtmıyor; kullanım şartı bildirimi okunamadı (§1e) |
| Kaldırma (takedown) | Yayıncının kaldırma yolu kartta **yok**; mevzuat metni için kaldırma talebi beklenmez |
| Kişisel veri | Kanun metni; PII taraması **yapılmadı**; kanunlarda kişi adı beklenmez ama ölçülmedi |
| Erişim şartı | Yok (gated değil) |

**Öneri `rights_status`: `cleared` (ticari olmayan)**, gerekçe: (a) içerik, 5846 sayılı Kanun md. 31
kapsamındaki türden (kanun); resmen yayımlanan kanun metni için telif engeli beklenmez; (b) kart
YAML'ı `mit`, kart metni araştırma/eğitim amacına izin veriyor ve Derlem kapsamı ticari değil;
(c) kaynak açık erişimli, kazıma sitenin herkese açık sayfalarından yapılmış (`robots.txt` yalnız
Googlebot'a birkaç `Noindex` satırı koyuyor); (d) FineWeb2-HQ notundaki "ticari olmayan `cleared`"
kabulüyle aynı ölçek. `rights_status` sözlüğünde kapsam alanı yok (TASK-030); kapsam `rights.scope`
ve bu notla taşınır.

Karşı ağırlık (`unknown` demenin gerekçesi): sitenin "Gizlilik, Kullanım ve Telif Hakları
bildirimi"nin okunamaması ve kart içindeki MIT/ticari-yasak çelişkisi. Bu not, kanunlar için md. 31
serbestliği açık ve kapsam ticari olmadığı için `cleared (ticari olmayan)` diyor; bildirim metni
bulunursa ve yeniden dağıtım/eğitimi yasaklıyorsa yeniden bakılmalı; ticari kullanıma geçilirse
mutlaka yeniden bakılmalı.

**Kurucu kararı gerektiren noktalar:** (1) `cleared (ticari olmayan)` onayı ve ticari kullanım
sınırı; (2) belge sınırı politikasına "deterministik birleşim = tek metin alanı" istisnası (§5);
(3) yalnız-kanun kapsamının idari-resmî damar için yeterli sayılıp sayılmayacağı (yönetmelik,
tebliğ, genelge, CB kararı/kararnamesi için ayrı kaynak veya ayrı hak araştırması).

**Doğrulanamayanlar (özet):**

1. mevzuat.gov.tr "Gizlilik, Kullanım ve Telif Hakları bildirimi"nin metni (var deniyor, bağlantı bulunamadı).
2. Kazıyıcının robots.txt'ye, oran sınırına ve site şartlarına uyup uymadığı.
3. Kodifiye metnin FSEK md. 31 kapsamına girip girmediği; sitenin derleme/veri tabanı koruması iddiası.
4. Kart içindeki MIT (YAML) ile "ticari kullanım için izin gerekir" (metin) çelişkisinin çözümü; MIT telif sahibi satırı yok.
5. 907 satırın tamamı için "yalnız kanun" iddiası, mülga kanunların dahil olup olmadığı, 907'nin seçim ölçütü.
6. Gerçek toplam karakter/madde sayısı (yalnız kestirim: ≈ 20 M karakter, ≈ 40.850 madde; ham dosya indirilmedi).
7. Eski kanunlarda (Düstür dolu) kodlama/harf bozukluğu; ek tablo kalıntısı.
8. `kabul_tarihi` 33 karakterlik değerlerin yapısı; tarih biçimi çeşitliliğinin tamamı.
9. Dosyanın JSON dizisi mi satır-JSON mu olduğu.
10. Ana korpusla (mC4/Wikipedia) örtüşme payı.
11. İlk yükleme ile bugünkü blob'un bayt eşitliği (yalnız boyut eşit).

## Kaynaklar

- https://huggingface.co/datasets/muhammetakkurt/mevzuat-gov-dataset
- https://huggingface.co/datasets/muhammetakkurt/mevzuat-gov-dataset/resolve/main/README.md (kart; `raw/main` ilk istekte başka bir kartı döndürdü, §2)
- https://huggingface.co/api/datasets/muhammetakkurt/mevzuat-gov-dataset (sha, gated, cardData, siblings)
- https://huggingface.co/api/datasets/muhammetakkurt/mevzuat-gov-dataset/commits/main (commit geçmişi)
- https://huggingface.co/api/datasets/muhammetakkurt/mevzuat-gov-dataset/tree/main?recursive=true (dosya ağacı, LFS oid)
- https://datasets-server.huggingface.co/splits?dataset=muhammetakkurt/mevzuat-gov-dataset
- https://datasets-server.huggingface.co/size?dataset=muhammetakkurt/mevzuat-gov-dataset
- https://datasets-server.huggingface.co/info?dataset=muhammetakkurt/mevzuat-gov-dataset
- https://datasets-server.huggingface.co/statistics?dataset=muhammetakkurt/mevzuat-gov-dataset&config=default&split=train
- https://datasets-server.huggingface.co/first-rows?dataset=muhammetakkurt/mevzuat-gov-dataset&config=default&split=train (yalnız ilk 11 satır, `truncated: true`)
- https://github.com/muhammetakkurtt/mevzuat-gov-scraper (README ve LICENSE; GitHub API lisansı MIT)
- https://www.mevzuat.gov.tr/ ve https://www.mevzuat.gov.tr/hakkimizda (tanıtım, tarihsel süreç, alt bilgi)
- https://www.mevzuat.gov.tr/robots.txt
- https://www.mevzuat.gov.tr/MevzuatMetin/1.3.5846.pdf (5846 sayılı FSEK, md. 31 ve dipnot 10)
- https://huggingface.co/datasets/AlicanKiraz0/Turkce-Atlas-Instruct (yalnız `raw/main` karışıklığının kaynağı olarak anıldı)

Erişim tarihi: 2026-10-13
