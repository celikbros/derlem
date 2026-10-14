# 200 Örnek İncelemesi Yönergesi

**Kimin için:** kurucu (teknik bilgi gerekmez).
**Tarih:** 2026-10-15.
**İncelenecek kaynak:** `fineweb2_hq_tur_latn_clean_candidate_trweb4B_xdedup_20261014`
(kimlik: `07a2b7e0-853b-4ce2-8a8c-653c1f31d921`, 6.601.402 belge).
**Adresler:** arayüz http://localhost:18400, API http://localhost:18401.

Bu yönerge tek bir iş içindir: 6,6 milyon belgenin içinden sistemin seçtiği **200
belgeye tek tek bakıp** her biri için "kalsın / gitsin" demek. Ne yapacağınız, hangi
düğmeye basacağınız ve sonucun ne anlama geldiği aşağıda adım adım yazıyor.

İşaret: **[DOĞRULANACAK]**, koddan veya belgelerden kesin okuyamadığım ayrıntıdır;
ilk gerçek oturumda ekrandan teyit edilmelidir. Hepsi en sonda (Bölüm 13) tek listede
toplandı.

---

## 1. Önce şunu bilin: bu bir ölçüm, temizlik değil

200 belgeye bakmak 6,6 milyonluk veriyi temizlemez. Amaç şudur: "Bu kaynakta çöp oranı
kabul edilebilir bir düzeyde mi?" sorusuna **sayıyla** cevap vermek. 200 belge bir
"termometre"dir; veriyi iyileştirmez, ne kadar kirli olduğunu söyler.

Kural şu:

- Reddettiğiniz belge sayısı ile "Hassas" dediğiniz belge sayısı **toplam en çok 20**
  olursa (200'ün %10'u), kaynak **onaylanabilir**.
- Toplam **21 veya daha fazla** olursa kaynak **onaylanamaz**. Bu bir arıza değildir;
  ölçümün "henüz yeterince temiz değil" demesidir. O durumda kurallar güçlendirilip
  kaynak yeniden türetilir, yeni bir 200'lük örnek çıkar (bkz. Bölüm 10).

%10 eşiği sizin kararınızdır (2026-10-13) ve bu kaynak için inceleme başlamadan önce
sisteme yazılmıştır. İnceleme başladıktan sonra değiştirilemez; "önce çıtayı koy,
sonra ölç" kuralı budur.

---

## 2. Ölçütünüz: tek soru

Her belgede sorulacak soru **tek** ve hakem kılavuzundakiyle aynıdır:

> **Bu sayfayı birine gösterip "bunu modelimize okutacağız" desem, mahcup olur muyum?**

- **Mahcup olmam** (akıcı, doğal Türkçe, tutarlı bir gövdesi var) ise: **Onayla**.
  Konu ne olursa olsun; biçim ve dil temizse belge kalır.
- **Mahcup olurum** ise: **Reddet**.
- Metin düzgün ama kişisel veri ya da zarar riski taşıyorsa: **Hassas işaretle**
  (Bölüm 6.3).
- **Kararsızsanız: Reddet.** Ölçüt "sıkı korpus"tur: şüpheliyi at, daha az ama daha
  temiz veri. Ekranda "emin değilim" düğmesi yoktur; şüphe = ret.

Sayıyı yapay olarak düşük tutmak için hafif davranmayın. Ölçümün işe yaraması için
kendi gerçek kararınızı verin. Eşik aşılırsa bu zaten doğru bilgidir.

---

## 3. Başlamadan önce: hazırlık (5 dakika)

### 3.1 Servisler çalışıyor mu?

İnceleme için üç şey ayakta olmalı: **web** (18400), **API** (18401) ve **PostgreSQL**.
Worker servisi inceleme kararları için gerekmez; ama sistemin arka plan işleri için
açık dursun. **[DOĞRULANACAK: worker'ın inceleme sırasında gerçekten gerekmediği; kod
yolu yalnız API ve veritabanını kullanıyor.]**

Hızlı kontrol: tarayıcıda http://localhost:18400 açılıp giriş ekranı geliyorsa web
ayaktadır. http://localhost:18401/health/ready bir "hazır" cevabı veriyorsa API ayaktadır.
**[DOĞRULANACAK: cevabın tam metni.]**

Kapalıysa üç ayrı terminal penceresinde, depo klasöründe (`C:\CELIKBROS PROJECTS\derlem`):

```powershell
go run ./cmd/api
```

```powershell
.\.venv\Scripts\python.exe -m derlem_worker
```

```powershell
Set-Location web
npm run dev
```

**Önemli:** bu pencerelerin her biri bir servistir. Pencereyi veya terminali kapatırsanız
servis de kapanır ve incelemede hata alırsınız (Bölüm 11). Pencereleri açık bırakın;
küçültebilirsiniz, kapatmayın.

PostgreSQL ayrı bir Windows hizmetidir; normalde kendiliğinden çalışır. **[DOĞRULANACAK:
bu makinedeki hizmetin adı ve otomatik başlatmada olduğu.]**

### 3.2 Hangi hesapla?

İncelemeyi **moderatör hesabıyla** yapın:

| Alan | Değer |
|---|---|
| E-posta | `moderator@derlem.local` |
| Parola | `DerlemTest123!` |

Neden admin değil? Kaynağı sisteme alan hesap kendi kaynağının örneklerini inceliyorsa bu
"bağımsız inceleme" olmaz. Sistem teknik olarak admin'e kendi kaynağını incelemeye izin
veriyor (kod bunu açıkça tanıyor); ama moderatör hesabı hem ayrı bir göz sağlar hem de
ekranı yalnız inceleme işine sadeleştirir. Moderatör, kaynağı oluşturan hesap **değilse**
sorun çıkmaz. Kaynağı bu hesap oluşturduysa "Kendi kaynağınızdaki belge örneklerini
üstlenemezsiniz" uyarısı gelir; o zaman başka bir inceleyici hesabı (örneğin
`expert@derlem.local`, parola aynı) kullanın. **[DOĞRULANACAK: kaynağı hangi hesabın
oluşturduğu. Görev notunda "kaynağı oluşturan admin kendi kaynağını inceleyemez"
yazıyordu; kod admin'e bu izni veriyor. Pratikte sonuç aynı: moderatörle girin.]**

### 3.3 Eşik gerçekten yazılı mı? (en önemli ön kontrol)

Giriş yaptıktan sonra (Bölüm 4) kaynağın satırında **"Sıradaki kapı"** sütununa bakın.

- `Ret oranı %0,00 / eşik %10,00` yazıyorsa eşik yazılı, **devam edin**.
- `Örnek 0/200` yazıyorsa eşik **yazılmamış**, eski "sıfır tolerans" kuralı geçerli: tek
  bir ret kaynağı kilitler. **Durun, incelemeye başlamayın.** Eşiği yalnız admin yazabilir
  ve ilk incelemeden sonra artık yazılamaz. (2026-10-14 kaydına göre eşik alım sırasında
  yazıldı; yine de gözle doğrulayın.)

---

## 4. Giriş ve kaynağı bulma

1. Tarayıcıda **http://localhost:18400** açın.
2. Giriş ekranında e-posta ve parolayı yazın (ekranda "Yerel test hesapları" kartları
   görünüyorsa **moderator** kartına tıklamak alanları doldurur). **Giriş yap**.
3. Moderatörle girince doğrudan **İnceleme** ekranı açılır. Değilse sol menüden
   **İnceleme**'ye tıklayın (yanındaki sayı, kuyruktaki kaynak sayısıdır).
4. Tablonun üstündeki **Kaynak ara** kutusuna `clean_candidate` yazın.
5. Doğru satır: `fineweb2_hq_tur_latn_clean_candidate_trweb4B_xdedup_20261014`.
   Kaynak adının üzerinde fareyi bekletirseniz kimliği görürsünüz; **`07a2b7e0`** ile
   başlamalı.

**Benzer isimli kaynaklara dikkat:**

| Ad (kısaltılmış) | Kimlik | Ne yapacaksınız |
|---|---|---|
| `…clean_candidate_trweb4B_xdedup_20261014` | `07a2b7e0…` | **Bu**, inceleyeceğiniz |
| `…heldout_trweb4B_20261014` | `ffde0f72…` | dokunmayın (ayrı tutulan test kümesi) |
| `FineWeb2-HQ tur_Latn` | `ba80dc1c…` | dokunmayın (üst kaynak) |

6. Satıra (kaynak adına) tıklayın. Ekran **odaklı inceleme** görünümüne geçer: üstte
   "Odaklı belge inceleme", altında "N bekleyen örnek · N riskli · N tamamlandı".

Satırda "Örnekleme" yazıyorsa 200 örnek henüz çekilmemiş demektir; "Paketi al" düğmesi
çalışmaz. Bitmesini bekleyin (Bölüm 11). Satırda "Hak incelemesi" veya "Lisans kanıtı"
yazıyorsa incelemeyi yine yapabilirsiniz; yalnız en sondaki onay düğmesi bundan etkilenir
(Bölüm 9).

---

## 5. İncelemeye başlama: paketi alma

Sistem 200 belgeyi size tek seferde vermez; küçük **paketler** halinde verir. Bu sayede
aynı anda birden fazla kişi çalışsa bile aynı belgeye iki kişi bakmaz.

1. Sayfada **"Yeni inceleme paketi"** bölümünü bulun.
2. **Paketteki belge** kutusunda **20** seçin (10 da seçilebilir; bu ekranda başka seçenek
   yok). 200 belge = 10 paket.
3. **"Paketi al ve incelemeye başla"** düğmesine basın.
4. "20 belgeli güvenli iş paketi alındı" bildirimi çıkar ve **ilk belge ayrı bir pencerede
   kendiliğinden açılır**.

Paket sırası: sistem en **riskli** belgeyi önce verir (risk puanı yüksekten düşüğe, eşit
puanda satır numarası küçük olan önce). Yani ilk paketlerde zor belgeler çıkması
normaldir; son paketler daha kolay olabilir. Belgenin üzerinde "Otomatik uyarılar" kutusu
çıkarsa bunlar yardımcı ipucudur (örneğin "Çok uzun", "Aşırı sembol"); **tek başına karar
değildir**.

Paket sizindir: **15 dakika boyunca** bu belgeler yalnız size ayrılır, başkasına verilmez
(Bölüm 8).

---

## 6. Belge başına karar: "3 saniyelik soru"

Belge penceresi iki yarıdan oluşur: solda **Okuma görünümü** (metin), sağda **Belge kararı**.
Pencerenin üstünde "Satır N · sürüm 1" yazar.

### 6.1 Önce bakın (çoğu belgede yaklaşık 3 saniye)

Metnin ilk birkaç satırına bakıp kaydırın. Soru: **mahcup olur muyum?**

- İlk bakışta bariz çöp (menü yığını, reklam, kırık karakter, anlamsız yığın): hemen
  **Reddet**.
- İlk bakışta düzgün: **kısaca bir de ortadan ve sondan** bakın. Uygulamanın kendi uyarısı
  da böyle der: *ret için baş, orta ve sondan en az iki bölgeyi doğrulayın; onay için metni
  daha geniş okuyun.* Düzgün başlayıp ortasında spam, bahis veya escort metni barındıran
  belgeler vardır; sonu başka bir belgeyle karışmış olabilir.
- Uzun belgeler (ilk paketlerde çoktur) 3 saniyeden fazla sürer; bu normaldir. "3 saniye"
  ilk izlenim içindir, okumayı atlamak için değil.

Metnin kesilmiş olması tek başına neden değildir. Satır sonlarının ve boşlukların düzeni
de tek başına ret nedeni sayılmaz (hakem kılavuzu böyle der); dile ve içeriğe bakın.

### 6.2 Üç karar ve ne anlama geldikleri

Sağ tarafta üç büyük düğme vardır:

| Düğme | Ne zaman | Ne olur |
|---|---|---|
| **Onayla** | Mahcup olmam. Düzeltme yapmadan eğitime girebilir. | Belge kalır. |
| **Reddet** | Biçim, dil veya içerik açısından çöp ya da şüpheli. | Belge **düşer**; 20'lik sayıya girer. |
| **Hassas işaretle** | Metin düzgün olabilir ama kişisel/mahrem veri ya da zarar riski var (Bölüm 6.3). | Belge **düşer**; 20'lik sayıya girer. |

**Önemli:** Reddet ile Hassas, kapıda ve dondurmada **aynı sonucu** verir: ikisi de belgeyi
eğitimden çıkarır ve ikisi de 20'lik toplama girer. Fark yalnız kayıttaki etikettir
("neden düştü?"). Hangisini seçeceğinizden emin değilseniz sonuç değişmez; zorlanmayın,
**Reddet** deyin.

### 6.3 "Hassas" ne zaman?

Hassas, "metin kötü yazılmış" demek değildir; "bu metin eğitim verisinde **bulunursa zarar
verebilir**" demektir. Konuyla değil, **metnin ne yaptığıyla** ilgilidir.

Aşağıdaki liste bu yönergenin önerdiği tanımdır; kurucu onayı bekler **[DOĞRULANACAK]**.
Kodda yalnız ilk madde ("kişisel/mahrem veri şüphesi") açıkça yazılıdır; diğerleri sizin
sorduğunuz sorunun ("tıp/hukuk/finans tavsiyesi, nefret, kişisel veri") karşılığıdır.

| Durum | Karar | Örnek |
|---|---|---|
| **Kişisel veri.** Tanınabilir özel bir kişiye ait mahrem bilgi: ad-soyadla birlikte adres, doğum tarihi, sağlık durumu, aile/özel hayat ayrıntısı, kimlik bilgisi. | **Hassas** | Bir forum mesajında kişinin adı, adresi ve hastalığı yazıyor. |
| **Tıp, hukuk, finans tavsiyesi.** Okuyucuya doğrudan "şunu yapın" diyen kesin tavsiye: ilaç ve doz, tedavi, "davayı kazanırsınız", "şu hisseye ya da kripto paraya yatırın". | **Hassas** | "Bu ilaçtan günde üç tane için, doktora gerek yok." |
| **Nefret, aşağılama, şiddete çağrı.** Bir grubu aşağılayan, şiddeti ya da ayrımcılığı öven veya özendiren metin. | **Hassas** | Bir etnik grubu aşağılayan yazı. |
| **Konuyu anlatan düzgün metin.** İlaç, dava, borsa, nefret suçu hakkında bilgilendiren haber, ansiklopedi maddesi, akademik ya da teknik anlatım. | **Onayla** | Bir ilacın yan etkilerini anlatan ansiklopedi maddesi. |
| **Hassas konulu ama aynı zamanda çöp** (spam, makine çevirisi vb.). | **Reddet** | Sahte "mucize ilaç" reklamı. |

Kısa kural: **konu bir neden değildir** (hakem kılavuzu: fotoğraf makinesi, ilaç, flört
konusunu anlatan düzgün bir haber kalır). Metin okuyucuyu bir şeye **yönlendiriyorsa** ya
da bir kişiyi **tanınır biçimde** açığa çıkarıyorsa Hassas; yalnız bilgi veriyorsa ve
düzgünse Onayla. Hâlâ emin değilseniz "şüpheliyi at" gereği Reddet veya Hassas deyin.

Veri yönetimi politikası da tıp, hukuk, finans, din, siyaset gibi konular için "güvenilir
inceleme olmadan eğitime alınmaz" der. Bu kaynak için anlamı: bu alanlarda tavsiye veren
veya iddia ileri süren bir metni onaylayacaksanız gerçekten güvenmelisiniz; güvenmiyorsanız
Hassas deyin.

Kişisel veriyi (telefon, e-posta, IBAN, TC kimlik no, kart) otomatik tarama zaten
kaynaktan temizlemiştir ("PII temiz"); yine de gözünüzden kaçmayan bir örnek görürseniz
Hassas deyin. **Gerekçe kutusuna o değeri kopyalamayın**, yalnız "kişisel veri var" yazın.

### 6.4 Reddet'te neden seçmek

Karar vermeden önce **"Bu belge neden uygun değil?"** altında altı hazır neden düğmesi
vardır. Birine tıklayınca beş puan ve gerekçe kutusu otomatik dolar. Hakem kılavuzundaki
çöp nedenlerinin ekrandaki en yakın karşılığı (bu eşleştirme yönergenin önerisidir):

| Gördüğünüz sorun | Ekrandaki düğme |
|---|---|
| Reklam, ürün/fiyat sayfası, "en iyi X" listesi, anahtar kelime yığını, bahis/eskort tanıtımı | **Reklam / ilan / SEO** |
| Menü, başlık yığını, gezinme metni | **Menü / navigasyon artığı** |
| Kırık karakter, bozuk kodlama | **OCR / kodlama bozuk** |
| Sözcük veya hashtag tekrarı metni bastırmış | **Aşırı tekrar / hashtag** |
| Birbirinden kopuk metinler birleşmiş; düzgün metne sonradan spam sokulmuş | **İlgisiz içerikler birleşmiş** |
| Anlamsız, otomatik üretilmiş, salt liste/katalog, imza ve tek satırlık forum yığını | **Anlamsız / yetersiz içerik** |
| **Makine çevirisi** (kelime kelime çevrilmiş, doğal olmayan Türkçe) | Ayrı düğme **yok** (aşağıya bakın) |

**Makine çevirisi** bu kaynakta en sık karşılaşılabilecek çöp türüdür ve düğmesi yoktur.
Yakın bir düğmeye (örneğin "Anlamsız / yetersiz içerik") tıklayın, sonra **Karar
gerekçesi** kutusundaki hazır cümleyi silip kendiniz yazın: "Makine çevirisi; doğal
olmayan Türkçe." Düğmenin etiketi kararı değiştirmez; gerekçe yazısı kayda geçer.
**[DOĞRULANACAK: kurucu ek bir "makine çevirisi" düğmesi istiyor mu?]**

Hazır neden düğmesi seçiliyken **Onayla düğmesi kapanır** ("Ret şablonu seçili; Onayla
kapatıldı"). Fikrinizi değiştirdiyseniz **"Şablonu temizle"** deyin (kutular da boşalır),
sonra yeniden puan girip Onayla'ya basın.

### 6.5 Beş puan (kararı belirlemez, ama boş bırakılamaz)

Sistem **beş puanın hepsini** ister (1 ile 5 arası; Onayla, Reddet ve Hassas için de):
Genel, Dil, Tutarlılık, Bilgi, Temizlik. 1 çok kötü, 2 sorunlu, 3 sınırda, 4 iyi, 5 çok iyi.

- Puanlar karar değildir; karar ayrı bir etikettir. Kaynağın geçip geçmediği yalnız
  Onayla/Reddet/Hassas sayısına bağlıdır, puanlara değil.
- Öneri: onayladığınız belgelere 4-5 verin. 3 yazıyorsanız büyük ihtimalle Reddet demeniz
  gerekir ("sınırda" = şüpheli). Bu bir öneridir, sistem kuralı değildir.
- Hazır ret düğmesi puanları sizin yerinize doldurur. Hassas'ta puanları siz girin.
- Hızlı girmek için ilk kutuya tıklayıp rakamı yazın, **Tab** ile sonrakine geçin.
  (Enter tuşu karar göndermez; bilerek kapalıdır.)

### 6.6 Gerekçe

- **Onayla:** gerekçe zorunlu değil.
- **Reddet ve Hassas:** gerekçe **zorunlu**. Kısa tek cümle yeter: "Menü yığını", "Makine
  çevirisi", "Kişisel adres ve sağlık bilgisi".
- Gerekçeye telefon, e-posta, IBAN veya başka kişisel değer kopyalamayın; yalnız sorunun
  türünü yazın.

---

## 7. Kararı kaydetme

Her belge için aynı sıra:

1. Metni okuyun, kararı verin.
2. (Reddet ise) uygun neden düğmesine tıklayın; gerekçeyi gerekirse düzenleyin.
3. Beş puanı girin (hazır düğme doldurmadıysa).
4. **Onayla**, **Hassas işaretle** veya **Reddet** düğmesine basın.
5. Tarayıcı bir onay penceresi açar: "… kararı kaydedilsin mi? Bu karar denetim geçmişine
   yazılır." **Tamam**'a basın.
6. "Belge inceleme kararı kaydedildi. Sıradaki örnek açılıyor." bildirimi çıkar ve **sıradaki
   belge kendiliğinden açılır**.

Paketteki son belge de bitince pencere kapanır ve "Bekleyen örnek kalmadı" bildirimi çıkar.
Sonraki paket için tekrar **"Paketi al ve incelemeye başla"** deyin (Bölüm 5). 200 belge
bitene kadar bu 10 kez tekrarlanır.

**Her belgeyi ayrı ayrı inceleyin.** İnceleme ekranında toplu karar yoktur; ama
**Kaynaklar** ekranında paketteki belgeleri işaretleyip tek seferde "Onayla" demek
mümkündür. Bu inceleme için o yolu **kullanmayın**: ölçümün değeri, her belgeye gerçekten
bakılmış olmasındadır.

**İlerlemeyi nereden görürsünüz:** "Yeni inceleme paketi" bölümünde "N / 200 İncelenen
örnek", "Onaylı" ve **"İşaretli"** sayıları ve bir ilerleme çubuğu vardır. İşaretli =
Reddet + Hassas toplamıdır, yani 20 ile karşılaştıracağınız sayı budur. Sayfanın altındaki
"İncelediklerim" bölümü verdiğiniz kararları listeler.

**Süre tahmini:** belge başına ortalama 1-2 dakika (beş puan ve onay penceresi dahil)
varsayılırsa toplam 3-5 saat, üç-dört oturum. **[DOĞRULANACAK: ölçülmedi.]**

### Yanlış karar verdim

Silinmez ama **geri alınır**. Belgeyi "İncelediklerim" listesinden açın, sağdaki **Geçmiş**
bölümünde **"Kararı geri al"** düğmesine basın, gerekçe yazın. Belge yeniden **Bekleyen**
olur ve sonraki bir pakette size (ya da başka inceleyiciye) yeniden atanır. Eski kayıt
silinmez, geri alma kaydı eklenir.

---

## 8. Ara verme ve devam etme (kilit süresi)

Aldığınız paket **15 dakikalık bir kilit** (kiralama) ile sizin adınıza tutulur. Sayfa
açık kaldıkça sistem bu süreyi **her 5 dakikada** kendiliğinden uzatır.

| Durum | Ne olur |
|---|---|
| Kısa mola (sekme açık, bilgisayar uyanık) | Hiçbir şey olmaz; süre uzamaya devam eder. |
| Uzun ara verecekseniz | **"Paketi bırak"** deyin. Kalan belgeler hemen havuza döner. Önerilen yol. |
| Sekmeyi/tarayıcıyı kapattınız ya da bilgisayar uyku moduna girdi | Süre uzatılamaz; belgeler en geç **15 dakika** sonra havuza döner. |
| Sayfayı yenilediniz (F5) | Ekrandaki paket görünümü kaybolur, ama paket sistemde sürer (bir sonraki bölüme bakın). |

**Geri dönünce:** **İnceleme, kaynak, "Paketi al ve incelemeye başla"**.

- Hâlâ 15 dakika içindeyseniz sistem **aynı paketi sürdürür** ("Mevcut N belgeli iş
  paketiniz sürdürüldü").
- Süre dolmuşsa **yeni bir paket** verilir (yine en riskli bekleyen belgelerden başlayarak).

**Verdiğiniz kararlar hiçbir durumda kaybolmaz.** Yalnız karar verilmemiş belgeler havuza
döner. Kilidi kaybettiğinizi şuradan anlarsınız: ekranda bir hata bildirimi çıkar ve paket
görünümünden kaybolur. Bir belgeyi okurken süre dolduysa karar gönderirken hata alabilirsiniz;
paketi yeniden alıp devam edin (Bölüm 11).

**Oturum:** 30 dakika hiç işlem yapmazsanız sistem sizi çıkarabilir; giriş ekranı gelirse
yeniden giriş yapın ve yukarıdaki yolla devam edin. Mutlak üst sınır 8 saattir.
**[DOĞRULANACAK: açık sekmenin her 5 dakikada yaptığı yenilemenin "hareketsizlik" sayacını
sıfırlayıp sıfırlamadığı.]**

---

## 9. Bitirme ve kaynak onayı

200 belgenin hepsi karara bağlanınca (ilerleme "200 / 200"):

1. Sayfanın ortasındaki **"Onay kapısı"** listesine bakın. Sekiz satır vardır; her biri yeşil
   işaret (geçti) ya da kırmızı çarpı (engelli) taşır:

   1. Dosya alındı
   2. Haklar temiz
   3. Lisans kanıtı
   4. PII temiz
   5. Exact tekrar yok
   6. Normalize tekrar yok
   7. Belge örnekleri hazır
   8. **Ret oranı %x / eşik %10,00** (sizin 200'lük sonucunuz)

2. Sekizinci satır yeşil ise (işaretli sayısı en çok 20) ve diğer yedisi de yeşilse, sayfanın
   **en altındaki "Moderasyon"** bölümüne inin ("İncelediklerim"in altında).
3. **"Onayla"** düğmesi artık aktiftir. Karar gerekçesi yazmak zorunlu değil. Basın, açılan
   pencerede **Tamam** deyin. "İnceleme kararı kaydedildi" bildirimi çıkar; kaynak satırı
   **"Onaylı · Ret oranı %x / eşik %10,00"** olur.

**DİKKAT, iki ayrı düğme seti vardır:**

- Belge penceresindeki Onayla/Hassas/Reddet **tek bir belge** içindir.
- Sayfanın altındaki "Moderasyon" bölümündeki Onayla/Hassas/Reddet **bütün kaynak**
  (6,6 milyon belge) içindir. Orada **Reddet'e veya Hassas'a basmayın**; kaynağın tamamı
  reddedilir. Kaynak seviyesinde yalnız onay için "Onayla" kullanılır.

**Onayla pasif kalırsa** kırmızı çarpılı satıra bakın:

| Kırmızı satır | Anlamı | Kim çözer |
|---|---|---|
| Ret oranı %x / eşik %10,00 | 21 veya daha fazla belgeyi Reddet/Hassas yaptınız | Bölüm 10 |
| Belge örnekleri hazır | Hâlâ karar verilmemiş belge var; "bekleyen örnek" sayısına bakın | Siz |
| Haklar temiz / Lisans kanıtı | Kaynağın hak durumu "Bilinmiyor" ya da lisans kanıtı boş. İncelemeyle ilgisiz bir eksik | admin: kaynak ayrıntısında "Metadata düzenle"; kanıtsız "Temizlendi" yapmayın |
| PII / tekrar satırları | Bu kaynakta normalde yeşil olmalı (2026-10-14 kaydına göre geçti) | geliştirici |

**[DOĞRULANACAK: bu kaynağın "Hak durumu" ve "Lisans kanıtı" alanlarının şu anki hâli. Üst
kaynakta hak durumu "Bilinmiyor" kalmıştı (kurucu kararı bekleniyordu); yeni kaynakta da
öyleyse inceleme bitse bile onay bu yüzden kilitli kalır.]**

Kaynak onaylandıktan sonraki adım (dondurma/release) bu yönergenin konusu değildir; o
adımı **admin** yapar (Sürümler ekranı).

---

## 10. Sonuç ne anlama gelir?

### 10.1 En çok 20 (200'ün %10'u veya altı)

- Kaynak **onaylanabilir**.
- Reddettiğiniz ve Hassas dediğiniz belgeler **dondurmada eğitim verisinden düşer**. Sistem
  bu belgelerin metnini bulur ve **aynı metin kaynakta başka yerde de geçiyorsa o kopyaları
  da** çıkarır. Çıkarılanların listesi ve kaydı sürümün manifestine yazılır.
- Dondurulan sürümün model kartı satırına şuna benzer bir satır üretilir: *"Human sample
  review: 18 rejected + 2 flagged of 200 sampled documents = 10.00% (threshold 10.00%, set
  before review; 1 reviewer(s))…"*

**Bu ne demek değildir:** yalnız sizin gördüğünüz 200 belgeden reddedilenler düşer.
Kaynaktaki geri kalan ~6,6 milyon belge tek tek incelenmedi; onlardaki benzer çöp yerinde
kalır. Ret oranı bir **ölçüdür**: "kural temizliği bu kadar iş görmüş, kalan kirlilik
tahminen şu kadar". Örnek riskli (uzun, kural sınırındaki) belgelere ağırlıklı çekildiği
için gerçek oran büyük ihtimalle sizin bulduğunuzdan düşüktür **[DOĞRULANACAK: bu yönün
istatistiksel olarak doğrulanması]**.

### 10.2 21 veya daha fazla

- Kaynak **onaylanmaz** ("Onayla" pasif kalır; denenirse sistem "örnek ret oranı eşiği
  aşıyor" der).
- Bu kötü haber değil, doğru haberdir: kaynak hâlâ çok kirli. Sonraki adım:
  1. Reddettiğiniz belgelerin **nedenlerine** bakılır (hangi çöp türü kaçmış: makine
     çevirisi mi, reklam mı, menü mü).
  2. Bu nedenlere göre **kurallar güçlendirilir** (daha sıkı bir kalite politikası).
  3. Kaynak **yeniden türetilir** (yeni bir aday) ve **yeni bir 200'lük örnek** çıkar.
  4. Yeni örnekte bu yönerge yeniden uygulanır.
- Eski 200'ün kararları yeni adaya taşınmaz. Yaptığınız iş **ölçümdür**; belgeleri tek tek
  temizlemek gibi bir adım yoktur.
- Toplam 21'e ulaştığında sonuç artık değişmez. İsterseniz orada durabilirsiniz; ama 200'ü
  bitirirseniz hangi çöp türünün kaç kez çıktığını tam görürsünüz, bu da kuralları yazarken
  işe yarar. Karar sizindir.

### 10.3 "Red verilenler eğitimden çıkmalı"

Evet; sistem tam olarak bunu yapar. Dondurma, Reddet ve Hassas belgelerin hepsini sürümden
çıkarır ve çıkardıklarını sayar. Çıkarılmayan tek şey, **hiç incelenmemiş** belgelerdir;
o yüzden kaynak ancak ret oranı eşiğin altındaysa kabul edilir.

---

## 11. Sık hatalar ve çözümleri

| Belirti | Neden | Çözüm |
|---|---|---|
| Giriş olmuyor | Yanlış hesap ya da parola | `moderator@derlem.local` / `DerlemTest123!` (Bölüm 3.2). 5 yanlış denemeden sonra hesap 15 dakika kilitlenir; bekleyin. |
| Kaynak listede yok | Yanlış menü ya da arama kutusunda başka bir yazı | **İnceleme** menüsü, arama `clean_candidate`; kutuyu temizleyip yenileme düğmesine basın. |
| Kaynak listesi boş, "İşlem tamamlanamadı" ya da **ECONNREFUSED** | **API servisi (18401) kapalı.** Web çalışıyor ama arkasındaki API'ye ulaşamıyor. | API terminalini bulun (Bölüm 3.1). Kapanmışsa `go run ./cmd/api` ile yeniden başlatın, sayfayı yenileyin. |
| Sayfa hiç açılmıyor ("bu siteye ulaşılamıyor") | **Web servisi (18400) kapalı** | `web` klasöründe `npm run dev`. |
| İnceleme ortasında her şey bir anda hata veriyor | **Terminal penceresi kapatıldı ya da bilgisayar yeniden başlatıldı; servisler gitti.** Terminali kapatmak servisi durdurur. | Servisleri yeniden başlatın (Bölüm 3.1). Verdiğiniz kararlar veritabanında olduğu için kaybolmaz. |
| Giriş ekranına döndüm | Oturum süresi doldu ya da 30 dakika hareketsizlik | Yeniden girin, "Paketi al…" ile devam edin. |
| "Paketi al ve incelemeye başla" gri | Örnekleme bitmedi ya da 200 belge zaten incelendi | Satırdaki "Sıradaki kapı"ya bakın; "Örnekleme" yazıyorsa bekleyin. |
| "Dağıtılabilecek bekleyen belge kalmadı veya tüm belgeler başka inceleyicilerde" | Kalan belgeler başka bir hesapta kilitli ya da hepsini bitirdiniz | Birkaç dakika bekleyip tekrar deneyin; başka hesapta kilitliyse en geç 15 dakikada serbest kalır. |
| "Kendi kaynağınızdaki belge örneklerini üstlenemezsiniz" | Bu hesap kaynağı oluşturan hesap | Başka bir inceleyici hesabı kullanın (Bölüm 3.2). |
| "Bu belge size atanmış geçerli bir iş paketinde değil" | Paketin kilidi bitmiş | Pencereyi kapatın, "Paketi al ve incelemeye başla"ya basın. |
| Hazır neden seçtim, **Onayla kapalı** | Tasarım gereği: ret şablonu seçiliyken onay kapanır | "Şablonu temizle" (Bölüm 6.4). |
| "Tüm kalite boyutları 1 ile 5 arasında olmalıdır" | Beş puandan biri boş | Beşini de doldurun. |
| "Ret veya hassas inceleme kararında gerekçe zorunludur" | Gerekçe kutusu boş | Bir cümle yazın. |
| Kaynak seviyesindeki Onayla pasif | Bölüm 9 tablosu | Bölüm 9 |
| Yanlışlıkla sayfa altındaki kaynak seviyesi Reddet/Hassas'a bastım | Tüm kaynak için karar verilmeye çalışılıyor | Önce çıkan onay penceresinde **İptal** deyin. **Tamam** dediyseniz hemen durup geliştiriciye bildirin; kaynak durumu kontrol edilmeli. **[DOĞRULANACAK: bu kararın geri alınıp alınamadığı.]** |

Not: ekrandaki hata cümleleri yukarıdakilere birebir uymayabilir; anlamları aynıdır.

---

## 12. Tek sayfalık özet (yanınızda tutun)

1. http://localhost:18400, `moderator@derlem.local` / `DerlemTest123!`.
2. Üç servis açık mı (web, API, PostgreSQL)? Terminal pencerelerini **kapatmayın**.
3. **İnceleme**, `clean_candidate` ara, `07a2b7e0…` satırı. "Ret oranı … / eşik %10,00"
   yazmalı (`Örnek 0/200` yazıyorsa durun).
4. Paket: **20**, sonra **Paketi al ve incelemeye başla**.
5. Her belgede: *mahcup olur muyum?*
   - Hayır, düzgün: **Onayla** (puanlar 4-5).
   - Evet, çöp ya da şüpheli: neden düğmesi, sonra **Reddet**.
   - Düzgün ama kişisel veri, tavsiye ya da nefret: **Hassas işaretle**.
   - Kararsız: **Reddet**.
6. Beş puan + (Reddet/Hassas'ta) gerekçe, karar düğmesi, onay penceresinde **Tamam**.
7. Mola: **Paketi bırak**. Dönünce: **Paketi al**.
8. 200/200 bitince "Onay kapısı"na bakın. **Reddet + Hassas en çok 20** ise sayfanın
   altındaki **Moderasyon, Onayla**. Orada Reddet/Hassas'a **basmayın**.
9. 21 veya fazlaysa: kaynak onaylanmaz; kurallar güçlendirilip yeniden türetilir (bir
   ölçüm, temizlik değil).

---

## 13. Doğrulanacaklar listesi

Bu yönergeyi kodu ve belgeleri okuyarak yazdım; çalışan arayüzde denemedim. Aşağıdakiler ilk
gerçek oturumda teyit edilmeli:

1. **"Hassas" tanımı (Bölüm 6.3).** Kodda yalnız "kişisel/mahrem veri şüphesi" yazıyor; tıp,
   hukuk, finans tavsiyesi ve nefret maddeleri bu yönergenin önerisi. Kurucu onaylamalı.
2. **Makine çevirisi için ayrı ret düğmesi yok (Bölüm 6.4).** Önerilen çözüm gerekçeyi elle
   yazmak; ek düğme istenip istenmediği kurucuya sorulmalı.
3. **Admin ve kendi kaynağı (Bölüm 3.2).** Görevde "admin kendi kaynağını inceleyemez"
   deniyordu; kodda admin'e açıkça izin var. Kaynağı hangi hesabın oluşturduğu da teyit
   edilmeli.
4. **Eşiğin yazılı olduğu (Bölüm 3.3).** 2026-10-14 kaydı yazıldığını söylüyor; satırda
   "Ret oranı … / eşik %10,00" görülmeli.
5. **Hak durumu ve lisans kanıtı (Bölüm 9).** Yeni kaynakta "Temizlendi" ve kanıt yoksa onay
   düğmesi inceleme bittikten sonra da kilitli kalır.
6. **Süre tahmini (Bölüm 7)** ölçülmedi.
7. **Oturum hareketsizlik sayacı (Bölüm 8).** Açık sekmenin 5 dakikalık yenilemesinin 30
   dakikalık sayacı sıfırlayıp sıfırlamadığı.
8. **Worker'ın gerekliliği (Bölüm 3.1)** ve **PostgreSQL hizmet adı / otomatik başlatma**.
9. **API sağlık adresinin tam cevabı** (`/health/ready`, Bölüm 3.1).
10. **Risk ağırlıklı örneğin ret oranını şişirdiği yönü (Bölüm 10.1)** doğrulanmadı.
11. **Hata iletilerinin tam metinleri (Bölüm 11)** kodda yazdığı biçimde değil, yaklaşık
    verildi; ekrandaki asıl yazı farklı olabilir.
12. **Kaynak seviyesinde yanlışlıkla Reddet/Hassas (Bölüm 11)** geri alınabilir mi.
13. **Dondurma çıktısı (Bölüm 10.1).** "Atılanlar listesi" ve model kartı satırı TASK-048'de
    uygulandı diye geçiyor; ama o görevin "k ≤ eşik ret ile dondurma başarılı olur ve tam o k
    belgeyi çıkarır" kabul ölçütü henüz işaretlenmemişti. İlk gerçek dondurmada teyit
    edilecek.
