# Gardas/Faz 2 Temiz Adayı — Hak/Lisans Kararı ve Kanıt Kaydı

> **DURUM: TASLAK DOLDURULDU — ONAY BEKLİYOR.**
> Köken beyanı 2026-07-07'de veri sahibi tarafından verildi ("kendi
> crawl'ladığımız Türkçe sitelerden geldi"); değerlendirme bu beyana göre
> hazırlandı. Karar, 4. bölümdeki karar sahibi alanları doldurulup teyit
> edilene kadar geçersizdir. Onay sonrası bu dosyanın yolu kaynağın
> `license_evidence_ref` alanına yazılır.

**Kaynak:** `gardash_faz2_tr_dedup_20260621_clean_candidate_20260625`
**Source ID:** `f63352dd-fdd1-4e4b-a8d2-b167b3c856cf`
**SHA256:** `ebe292793d87ec067076bbb86f39801e6ed5fae18761dfcfa3506c4503c0d989`
**Satır:** 5.922.891 · **Byte:** 12.850.383.067 · **Amaç:** `pretrain`

## 1. Verinin kökeni

- Corpus'u derleyen: **Gardash proje ekibi (kendi ekibimiz)** — üçüncü
  taraftan satın alınmış/indirilmiş hazır veri seti değildir.
- Derleme yöntemi: **Türkçe web sitelerinin ekibimizce crawl'lanması**;
  Gardash Faz 2 hattında temizlik ve tekilleştirme sonrası 2026-06-21 tarihli
  final dedup corpus üretildi, 2026-06-25'te Derlem'e alındı.
- Kaynak türü: web taraması (çok siteli, çok konulu → alan etiketi `mixed`).
- Ham kaynakların lisans durumu: web sayfası içerikleri; **telif hakları ilgili
  site/yazar sahiplerindedir**, tek tek lisans beyanı toplanmamıştır.
- Üçüncü taraf içerik oranı: tamamına yakını üçüncü taraf web metnidir.

## 2. Kullanım hakkı değerlendirmesi

**Dayanak:** Kendi araçlarımızla derlenmiş web metninin, ham metni yeniden
yayımlamaksızın, **yalnız kendi LLM/tokenizer eğitimimizde** kullanılması.
Bu, dünyada LLM pretrain pratiğinin standardıdır (CommonCrawl türevleri,
FineWeb vb. aynı nitelikte veridir).

**Bilinen kısıtlar ve dürüst risk notu:**

- Türk hukukunda (FSEK) metin-veri madenciliği için açık bir istisna yoktur;
  web verisiyle model eğitimi dünyada da hukuken gri alandır. Karar bir risk
  kabulüdür, mutlak temizlik beyanı değildir.
- Ham metin üçüncü taraflara yeniden dağıtılamaz; Derlem export'ları yalnız
  kendi eğitim hattımıza verilir (`consumer_team` erişim sınırı bunu destekler).
- Crawl sırasında site kullanım şartları/robots yönergelerine uyum, derleme
  ekibinin beyanına dayanır.

**Riski azaltan uygulanmış önlemler:**

- KVKK yönü: 104.853 PII bulgulu satır temiz adaydan **çıkarıldı**; kalan
  corpus PII taramasından `clear` geçti; ham değer hiçbir kayda yazılmadı.
- 221 iç tekrar ve 3 aşırı boyutlu belge ayıklandı; içerik SHA256 zinciriyle
  izlenebilir.
- Takedown/silme politikası v1.0 hukuk çalışmasına bağlandı; talep gelirse
  düzeltme yeni release olarak çıkarılır (immutable model).

## 3. Karar

- [x] **`cleared` — şu kapsamla:** yalnız kendi LLM/tokenizer eğitimimizde
  kullanım; ham metin yeniden dağıtılmaz; takedown talepleri v1.0 politikasına
  göre işlenir. *(Öneri: yukarıdaki köken beyanı ve risk kabulüne dayanır;
  karar sahibinin teyidiyle geçerlilik kazanır.)*
- [ ] `restricted`
- [ ] `blocked`

`license` alanına yazılacak değer: `kendi-derleme-web-tr`

## 4. Karar sahibi (doldurulacak)

- Ad / rol: `.......`
- Tarih: `.......`
- Teyit: "1. bölümdeki köken beyanı doğrudur; 2. bölümdeki risk
  değerlendirmesini okudum; 3. bölümdeki kararı onaylıyorum."

## 5. Karar sonrası üç adım (operasyon)

1. Web arayüzü → Kaynaklar → bu kaynak → "Hak bilgisini düzenle":
   Hak durumu = `Temizlendi`, Lisans = `kendi-derleme-web-tr`,
   Lisans kanıtı = `docs/gardash_faz2_rights_decision.md`.
2. Moderatör: İnceleme → 200 örneği toplu inceleme ile puanla → kaynak onayı.
3. Admin: Sürümler → pretrain draft → freeze → JSONL/TXT export → manifest
   SHA256 zinciriyle Gardash'a teslim.
