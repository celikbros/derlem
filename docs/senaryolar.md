# Senaryolarla Derlem: Ekipler İçin Kullanım Kılavuzu

Bu belge, Derlem'i ilk kez kullanacak bir alan ekibine (hukuk, tıp, felsefe...)
verilmek üzere yazılmıştır. Mimari anlatmaz; "şu ekranda şunu yap" der.

## Önce Tek Cümlelik Çeviri

Siz **ekip ve konu** diye düşünürsünüz; Derlem **kaynak (dosya) ve amaç** diye
düşünür. Çeviri tablosu:

| Sizin dünyanız | Derlem'deki karşılığı |
|---|---|
| "Hukuk ekibi kurdum" | Kullanıcılar ekranından açılan 3-5 hesap (1 veri yöneticisi + 2-4 inceleyici) |
| "Hukuk alanında çalışıyorlar" | Kaynak kaydındaki `Alan` (domain) kutusuna `hukuk` yazılması — hepsi bu |
| "Veritabanı oluşturuyorlar" | Hayır — ekip **dosya getirir ve örnek inceler**; veritabanını program tutar |
| "Kitap/doküman yükleyeceğim" | Her kitap/derleme = katalogda bir **kaynak** kaydı + bir dosya |
| "Başka LLM'den distile edeceğim" | Üretilen çıktı = `synthetic_*` tipli bir kaynak dosyası; aynı kapılardan geçer |
| "Tıp, radyoloji, felsefe takımları" | Aynı katalogda `domain` etiketi farklı kaynaklar; ayrı sistem/kurulum GEREKMEZ |
| "Eğitim verisi hazır" | Amaç başına **frozen release + export dosyası** (mixture raporu alan dağılımını gösterir) |

Kritik nokta: konu başına ayrı Derlem, ayrı veritabanı, ayrı klasör yoktur.
**Tek katalog** vardır; ekipler kendi `domain` etiketli kaynaklarıyla ilgilenir.

## Senaryo 1 — Hukuk Ekibi: Doküman/Kitap Yükleme

Amaç: Yargıtay kararları derlemesini eğitim havuzuna sokmak.

**Adım 0 — Hesaplar (bir kere, admin yapar):**
Kullanıcılar ekranı → "Yeni kullanıcı" → `hukuk.yonetici@...` (rol:
`data_manager`), `hukuk.uzman1@...` ve `hukuk.uzman2@...` (rol: `moderator`
veya `expert_reviewer`).

**Adım 1 — Dosyayı hazırla:**
**PDF ve Word (DOCX) dosyaları artık doğrudan yüklenebilir** — program
metne çevirmeyi kendisi yapar (2026-07-12'den beri) ve ham belgeyi kanıt
olarak saklar. Elinizdeki veri düz metinse kural: **UTF-8 bir `.txt`,
satır başına bir belge** (bir karar = bir satır) veya JSONL
(`{"text": "..."}` satırları). Taranmış (görüntü) PDF'ler henüz
desteklenmez; OCR sıradaki sürümdedir.

**Adım 2 — Kaynak kaydı (hukuk.yonetici):**
Kaynaklar → "Yeni kaynak":

| Alan | Örnek değer |
|---|---|
| Kaynak adı | `yargitay_kararlari_2020_2024` |
| Kaynak tipi | `legal_corpus` |
| İçerik amacı | `Pretrain` (ham metin havuzu için) |
| Lisans | `kamu-karar-metni` (gerçek durum ne ise) |
| Hak durumu | Kanıtınız yoksa `Bilinmiyor` bırakın — sonra karar verilir |
| Dil | `tr` |
| Alan | `hukuk` ← ekibi "ekip" yapan etiket budur |
| Lisans kanıtı | Kararın dayandığı belge yolu/linki |
| Köken bilgisi | Dosyanın nereden derlendiği |

**Adım 3 — Yükle:** kaynağın satırına tıkla → sağ panelden dosyayı yükle.
Program otomatik olarak: SHA256 kimliği çıkarır, değişmez depoya kopyalar,
PII tarar, tekrarları arar, 200 örnek seçer. İlerleme **İşler** ekranındadır;
sizin yapacağınız bir şey yok, birkaç dakika bekleyin.

**Adım 4 — İnceleme (hukuk.uzman1/2):**
İnceleme ekranı → kaynak kuyruktadır → 200 örneği okuyup puanla (toplu karar
mümkün). Bu adım "bu derleme gerçekten temiz ve kaliteli hukuk metni mi"
sorusunun insan cevabıdır. Uzman kendi yüklediği kaynağı onaylayamaz.

**Adım 5 — Onay:** tüm kapılar temizse (satırdaki "Sıradaki kapı" sütunu söyler)
inceleyici kaynağı onaylar. Kaynak artık release'e girmeye hazırdır.

Tıp, radyoloji, felsefe ekipleri **aynı beş adımı** kendi domain etiketiyle
uygular. Radyoloji için `Alan: tip-radyoloji` yazmak yeterlidir; alt alan
ayrımı serbest metindir.

## Senaryo 2 — Başka LLM'den Distilasyon (Sentetik Veri)

Amaç: Güçlü bir modele tıp konularında ders-kitabı tarzı metin ürettirmek.

1. **Üretim Derlem dışında yapılır:** bir script model API'sini çağırır,
   çıktıları JSONL dosyasına yazar. Yanına bir **üretim manifesti** koyun:
   hangi model, hangi prompt şablonu, hangi tarih, kaç kayıt.
2. Kaynak kaydında farklı olanlar: Kaynak tipi `synthetic_textbook`,
   Lisans `kendi-uretimimiz` + üretici modelin kullanım şartları notu,
   Lisans kanıtı = üretim manifestinin yolu, Alan = `tip` (veya ilgili alan).
3. Gerisi Senaryo 1 ile aynıdır: yükle → kapılar → örnek incelemesi → onay.
   **Sentetik olmak kapı muafiyeti getirmez** — modelin ürettiği metinde de
   PII, tekrar veya çöp olabilir; 200 örneği yine insan okur.

## Senaryo 3 — Soru-Cevap Ekibi (Instruction Verisi)

Amaç: hukuk uzmanlarına soru-cevap çifti yazdırmak (fine-tuning verisi).

**Uygulama içi yol (2026-07-16'dan beri):** yazacak kişilere `contributor`
rolü verilir. Katkıcı **Katkılar** ekranından soru-cevap çiftini veya serbest
metnini yazar, kullanım şartını onaylar ve gönderir; katkılar havuzda birikir.
Veri yöneticisi havuzu **"Kaynağa demetle"** ile tek kaynağa dönüştürür
(soru-cevap → `Instruction`, serbest metin → `Pretrain`); demet normal
PII/tekrar/örneklem/insan inceleme kapılarından geçer. Katkı gönderme
inceleyici rollerine kapalıdır — kimse kendi metnini içeren kaynağı
inceleyemez.

Toplu dış üretim alternatifi: çiftler dışarıda kanonik JSONL olarak toplanır
(`derlem.canonical-sample.v1` formatında conversation kayıtları), tek dosya
halinde `İçerik amacı: Instruction` olan bir kaynak olarak yüklenir.
Eval seti hedefleniyorsa amaç `Eval` seçilir ve **asla** pretrain/instruction
havuzuyla karışmaz — program bunu zorla ayırır.

## Release: Ekiplerin Emeği Nasıl Birleşir?

Ayda bir (veya ihtiyaç oldukça) admin/veri yöneticisi:

1. **Sürümler** → yeni taslak: amaç `Pretrain` → onaylı TÜM kaynaklar listelenir
   (hukuk + tıp + felsefe...). Hepsini veya bir kısmını seç.
2. Freeze → kapılar yeniden koşar, eval sızıntısı denetlenir, SHA256 manifest'i
   donar. **Mixture raporu** alan dağılımını gösterir: "hukuk %22, tıp %31..."
3. Export → eğitim ekibine verilecek JSONL/TXT dosyası + manifest.

Alan-özel paket isterseniz (yalnız hukuk release'i), taslağı oluştururken
yalnız hukuk kaynaklarını seçersiniz. Yani "hukuk veritabanı" dediğiniz şey
pratikte: *hukuk domain'li onaylı kaynaklardan yapılmış bir release*tir.

## Ekip Liderine Verilecek Tek Paragraf

> "Alanınla ilgili metinleri UTF-8 satır-başına-belge dosyaları hâline getir.
> Her dosyayı Derlem'de bir kaynak olarak kaydet (alan etiketin sabit, amacı
> doğru seç), yükle, otomatik kontrolleri bekle. Ekibindeki uzmanlar İnceleme
> ekranındaki 200 örneği puanlayıp kaynağı onaylasın. Gerisi — depolama,
> temizlik, tekrar kontrolü, paketleme — programın işi. Takıldığın yerde
> arayüzdeki Rehber sekmesine ve [Hızlı Başlangıç](hizli_baslangic.md)'a bak."
