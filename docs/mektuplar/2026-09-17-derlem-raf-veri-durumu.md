# derlem → soruyu sorana: v2 verisinin bugünkü durumu, beş soruya ölçülmüş cevap

> **Kimden:** `derlem` (veri atölyesi) · **Kime:** beş soruyu soran taraf
> **Tarih:** 2026-09-17 · **Taşıyan:** kurucu (elden) · **Tür: DURUM RAPORU**
>
> Bu belgedeki her sayı 2026-09-17'de Derlem'in kendi veritabanı, nesne deposu ve
> üretim manifestleri üzerinde ölçülmüştür. Ölçülmemiş hiçbir yere tahmin
> yazılmadı; o satırlarda açıkça **"ölçülmedi"** yazıyor. Kaynaklar dipnotlarda.

## Özet (üç cümle)

Dondurulmuş bir `pretrain` sürümü **yok**; elimizdeki 12,85 GB'lık temiz aday
onaylı bir sürüm değil, incelemesi süren bir adaydır. Otomatik kapıların
(kişisel veri, birebir tekrar, normalize tekrar, örnekleme) tamamı geçti; tek
gerçek engel **insan incelemesi**: 200 örnekten 1'i incelendi, o da hassas
işaretlendi, onaylanan 0. Sınav kirliliği kanıtı bugün **üretilemez**, çünkü
sistemde `eval`/`holdout` amaçlı kaynak sayısı 0.

---

## 1. Bugünkü durum: v2'yi dondurmak için geriye tam olarak ne kaldı

Dondurma kapıları koda gömülüdür (`internal/repository/releases.go`, `QueueFreeze`).
Sürüme girecek her kaynak için istenen ile temiz adayda **ölçülen**:

| Kapı | İstenen | Ölçülen (2026-09-17) | Durum |
|---|---|---|---|
| Kişisel veri taraması | `clear` | `clear` | ✅ |
| Birebir dosya tekrarı | `unique` | `unique` | ✅ |
| Normalize belge tekrarı | `unique` | `unique` | ✅ |
| Örnekleme | `sampled` | `sampled`, 200 örnek | ✅ |
| Hak durumu | `cleared` | `cleared` | ⚠️ (bkz. uyarı) |
| Lisans kanıtı | dolu | dolu | ✅ |
| İncelenen örnek | 200 | **1** | ❌ |
| Onaylanan örnek | 200 | **0** | ❌ |
| Hassas işaretli örnek | 0 | **1** | ❌ |
| Kaynak onayı | `approved_source` | `sampled_for_review` | ❌ |

Ek olarak sürüm düzeyinde sözleşme anlık görüntüsü ve uygulama paketi SHA'sı
gerekir; bunlar sürüm oluşturulurken üretilir. `pretrain` amaçlı bir sürüm hiç
açılmadığı için bu akış bu amaçta **denenmedi (ölçülmedi)**. Veritabanındaki 7
dondurulmuş sürümün tamamı eski `instruction` deneme sürümleridir.

**⚠️ Hak tutarsızlığı (ölçüldü):** ana kaynak `gardash_faz2_tr_dedup_20260621`
hak durumu `unknown`, ondan türetilen temiz adayda `cleared` yazıyor. Bir türev,
girdisinden daha temiz bir hak durumuna sahip olamaz. Faz-2'nin yedi ham
kaynağının hak araştırması Derlem'de ayrı iş olarak açıktır (TASK-011) ve ürün
çıkmadan önce yapılacaktır.

### İşin kimde olduğu

**Kurucuda (insan kararı ve emeği):**
1. 199 örneğin incelenmesi ve hassas işaretli 1 örneğin çözülmesi.
2. İnceleme bitince kaynak onayı (kaynağı oluşturan hesap onaylayamaz).
3. Sınav setine karar verilmesi (bugün 0 kayıt).
4. Sıralama kararı: bugünkü temiz aday mı dondurulacak, yoksa önce kalite
   süzgeciyle yeniden mi üretilecek? **Yeniden üretim, 200 örneklik incelemeyi
   sıfırlar** (yeni nesne → yeni SHA → yeni örnek nesli), bu yüzden karar
   incelemeye başlamadan önce verilmelidir.
5. Hak tutarsızlığının kararı.

**Derlem'de (bu taraf):** taslak sürümü açmak, kaynağı bağlamak, dondurmayı
çalıştırmak, `txt` ve `jsonl` ihracatlarını üretmek, token sayısını ölçmek,
teslimat belgesini yazmak; sınav metinleri verilince onları `eval`/`holdout`
kaynağı olarak kaydetmek; karar öyleyse temiz adayı kalite süzgeciyle yeniden
üretip yeniden örneklemek.

**Başka projede:** eğitim ve model künyesine SHA'nın yazılması; kaynak etiketli
`gardash_tr_dedup.jsonl` gerekirse yeniden üretimi (betik `celikbros/Gardash`
deposunda; içindeki yollar geçersiz, ham kaynaklar artık Derlem'de).

---

## 2. Teslimat neye benzeyecek

### Teslim edilecek dosyalar

1. **Metin dosyası (artifact).** İki biçimden biri:
   - `txt` — belge başına tek UTF-8 satır; belge içindeki satır sonları tek
     boşluğa indirilir. Hızlı pretraining tüketimi için.
   - `jsonl` — her satır bir JSON kayıt: `id`, `text` ve `metadata` (dil, alan,
     lisans, kaynak kimliği, kaynak SHA256'sı, kaynak içindeki satır sırası,
     belge SHA256'sı). Köken izi gerekiyorsa bu biçim kullanılır.
2. **İhracat manifesti** (`derlem.export-manifest.v2`): metin dosyasının
   SHA256'sı, kayıt sayısı, bayt boyutu, token tahmini (yöntem
   `unicode-codepoint-range-v1`; tokenizer çıktısı **değildir**), kaynak bazlı
   köken bilgisi ve determinizm kuralları.
3. **Sürüm manifesti:** sürümün kimliği ve sürümü, içindeki kaynaklar (her biri
   için SHA256 + sürüm numarası), kapı sonuçları, `frozen_at` ve manifestin
   kendi SHA256'sı.
4. **Raporlar:** karışım raporu (dil/alan/kaynak payları), tekrar ve
   dekontaminasyon kapılarının sonuçları. Bunlar dondurulmuş sürümün anlık
   görüntüsüne bağlıdır, ayrıca gönderilmesi gerekmez.

Artifact ve manifest önce içerik adresli depoya yazılır; kayıt `ready` olduktan
sonra veritabanı tetikleyicisi güncellemeyi ve silmeyi reddeder.

### Metnin içindeki satırlar — 10 gerçek örnek

Aşağıdaki satırlar bugünkü temiz adayın (`ebe29279…0d989`, 12.850.383.067 bayt)
ilk 10 satırıdır; `txt` biçimi birebir böyle görünür:

```
 1|  679 karakter | İktisadi Analizde Zaman Cetvellerinin Kullanılması: 2006 Türkiye Zaman Kullanım Anket Verisi Üzerine Bir Değerlendirme . Bu yazıda Türkiye İstatistik Kurumu'nun…
 2|   60 karakter | Oyunlar Teorisi Çerçevesinde Türkiye-AB İlişkilerine Bakış .
 3|   85 karakter | Avrupa Birliği'nin Akdeniz Bölgesine Yönelik Yeni Politikasının Türkiye İçin Anlamı .
 4|  529 karakter | TOPLUMUN SİYASETİ . Toplumun siyasetle ilişkisinin görünen ve görünmeyen yönlerinin daha iyi anlaşılması ve toplumun geçirdiği değişim…
 5|   96 karakter | Özelleştirmede Uygulanmayan Yargı Kararları ve Avrupa İnsan Hakları Mahkemesi'ne Başvuru Hakkı .
 6|   77 karakter | Kamu Yönetimi Reformu ve Kamu Yöneticisi Davranışı: Recep Yazıcıoğlu Örneği .
 7|   59 karakter | "Emeğin Avrupa'sı" İşçi Sınıfını Birleştirir mi Böler mi? .
 8| 2396 karakter | BRÜKSEL MUHABİRLERİNİN GÖZÜNDEN TÜRKİYE'NİN "AVRUPALILAŞMA-MA-SI": MÜZAKERELERİN İLK 10 YILINDA AVRUPA HABERCİLİĞİNE DAİR DEĞERLENDİRMELER . Avrupa Birliği'nin…
 9|   54 karakter | Türklerin İnsanlığa Katkısı: Birlikte Yaşama Kültürü .
10|  117 karakter | Kitabiyat: David Harvey'e Göre Yeni Emperyalizm Gücün Ülkesel ve Kapitalist Mantıkları Arasındaki Diyalektik İlişki .
```

Bu örnekten iki olgu okunur: satırlar **başlık + gövde** biçiminde birleşiktir ve
gövdesiz, yalnız başlıktan oluşan satırlar azımsanmayacak orandadır (bu 10
satırın 6'sı 120 karakterin altında). Korpus genelinde bu oran **ölçülmedi**.

### Tüketici hangi dosyadan, hangi sırayla okur

1. **Sürüm manifesti** — hangi sürüm, hangi kaynaklar, hangi kapılar geçti.
2. **İhracat manifesti** — metin dosyasının SHA256'sı, kayıt sayısı, token tahmini.
3. **Metin dosyası** indirilir.
4. **Eğitime başlamadan önce** metin dosyasının SHA256'sı hesaplanır ve ihracat
   manifestindeki değerle karşılaştırılır. Eşleşmiyorsa eğitim başlamaz.

### Model künyesine hangi SHA yazılır

**Metnin (artifact) SHA256'sı.** Eğitilen tam baytların kimliği odur. Yanına
**sürüm manifestinin SHA256'sı** da yazılmalıdır; o da "hangi onaylı sürümdü"
sorusunun cevabıdır. Tek bir sayı yazılacaksa metnin SHA'sı yazılır.

---

## 3. Temizlik durumu: ne temizlendi, ne temizlenmedi

Kaynak: temiz aday üretim manifesti (`clean-candidate-v1`, üretim 2026-07-25).

**Girdi 6.027.968 satır → çıktı 5.922.891 satır (%98,26 kaldı).**

Atılan satırlar:

| Neden | Satır |
|---|---|
| Kişisel veri içeriyor | **104.853** |
| Birebir/normalize tekrar | **221** |
| Aşırı büyük (> 256 KB) | **3** |
| Boş | 0 |

Kişisel veri bulguları (toplam eşleşme / etkilenen satır):

| Tür | Eşleşme | Satır |
|---|---|---|
| Telefon | 114.437 | 52.727 |
| E-posta | 86.435 | 50.957 |
| Ödeme kartı | 13.830 | 10.520 |
| IBAN | 2.087 | 1.423 |
| TC kimlik no | 665 | 362 |

Parmak izi çıkarılan satır: 5.902.749. Kısa olduğu için parmak izi çıkarılmadan
tutulan satır: 20.142.

### Temizlenmeyenler

| Konu | Durum | Sayı |
|---|---|---|
| **Yakın kopyalar** (birebir olmayan) | Tam tarama **yapılmadı**. Bir kalibrasyon koşusu bu kaynak için 100 aday çift üretti (Hamming 15–25); bunların 2'si incelendi. | Korpus genelindeki oran **ölçülmedi** |
| **Çöp/şablon satırlar** (menü, reklam, site kalıbı) | Süzgeç kodu **var** (`tr-web-v1`: gezinme kalıbı, reklam, kelime çeşitliliği, URL/telefon yoğunluğu) ve temiz aday üreticisine bağlı; **ama bu temiz aday o süzgeçten geçmedi** (manifestte kalite politikası kaydı yok) | **ölçülmedi** |
| **OCR bozuklukları** | Böyle bir süzgeç **yok** | **ölçülmedi** |
| **Dil karışması** | Hiçbir aşamada dil tespiti **yok**; kaynağın dili elle `tr` girilmiş | **ölçülmedi** |

### Elimizdeki gerçek kullanılabilir metin

- Ölçülen: **12.850.383.067 bayt / 5.922.891 satır** (kişisel veri ayıklanmış,
  birebir tekrarı alınmış hâli).
- **Token sayısı: ölçülmedi.** İhracat işi hesaplıyor; ilk ihracatta ölçülecek.
- **Kalite olarak kullanılabilir oran: ölçülmedi.** Bugünkü örnek neslinde 200
  örnekten 1'i incelendi ve hassas işaretlendi; bu tek karardan oran çıkarılamaz.

---

## 4. Sınav kirliliği: kanıt nasıl üretilecek

Mekanizma iki katmanlı ve kodda hazır:

1. **Birebir dekontaminasyon — sert kapı.** Sürümün belgeleri, `eval`/`holdout`
   amaçlı kaynakların belgeleriyle belge hash'i düzeyinde karşılaştırılır.
   Eşleşme dondurmayı **bloke eder**. Ham metin ne rapora ne geçici indekse
   yazılır; indeks iş bitince silinir.
2. **Yaklaşık dekontaminasyon — rapor.** Yöntem
   `normalized-word-3gram-simhash64-v1-hamming10-bands8x8-v1`: sözcük
   3-gramlarından 64-bit SimHash, 8×8 bit bant indeksi, Hamming ≤ 10 potansiyel
   eşleşme. Tek başına freeze'i bloke etmez; insan incelemesine aday listesi
   üretir. Raporda en fazla 20 örnek eşleşmenin kaynak kimliği, satır sırası,
   Hamming mesafesi ve yaklaşık benzerlik oranı bulunur — **metin bulunmaz**.

**Bugünkü ölçüm: `eval`/`holdout` amaçlı kaynak sayısı 0.** Bu yüzden iki kapı da
"uygulanamaz" (`not_applicable`) döner ve **kirlilik kanıtı üretilemez**. Bu
hâlde dondurulan bir sürümün karnesi dayanaksızdır.

Kanıtın üretim sırası: sınav metinleri `eval`/`holdout` amacıyla kaynak olarak
kaydedilir → sürüm dondurulur → dondurulmuş sürümün kapı sonuçlarında
karşılaştırılan belge sayısı, birebir eşleşme sayısı ve yakın eşleşme adayları
sayıyla yer alır. Bu sayılar sürümün anlık görüntüsüne bağlı kalır, sonradan
değiştirilemez.

Sınav seti eğitim verisine yapısal olarak karışmaz: amaç alanı (`eval`/`holdout`)
ayrı olduğu için bu kaynaklar bir `pretrain` sürümüne dahil edilemez.

**Bu tarafın beklediği girdi:** sınav setinin ne olacağı kararı ve metinleri.

---

## 5. Takvim

Bloke eden tek iş insan incelemesidir: **199 örnek + 1 hassas örneğin çözümü.**

Ölçülü olanlar: paket boyutu 10/20/50/100/200 seçilebiliyor; paket inceleyiciye
15 dakikalık kirayla atanıyor ve açık arayüz kirayı 5 dakikada bir yeniliyor.
**İnceleme hızı ölçülmedi** — bu kaynakta bugüne kadar toplam 4 karar kaydı var,
bundan hız çıkarılamaz.

Derlem tarafındaki iş (taslak sürüm → dondurma → iki ihracat → teslimat belgesi)
incelemeden sonra gelir; 12,85 GB'lık dondurma ve ihracatın **süresi ölçülmedi**,
ilk koşuda ölçülecek.

Bu yüzden tarih koşullu verilir: **inceleme bitiminden bir gün sonra v2 donar.**
Kurucunun hızına dair iki senaryo (varsayım, ölçülmedi): 200 örnek iki oturumda
biterse **2026-09-19**; günde 50 örnekle **2026-09-22**.

Takvimi değiştirecek iki karar:

- **Sınav seti kararı dondurmadan önce gelmelidir.** Gelmezse sürüm donar ama
  kirlilik raporu "uygulanamaz" der.
- **"Önce kalite süzgeciyle yeniden üret" kararı incelemeyi sıfırlar:** yeni
  nesne, yeni SHA, yeni 200 örnek. Buna Derlem tarafında yeniden üretim ve
  yeniden örnekleme süresi eklenir (12,85 GB'lık geçiş; **ölçülmedi**). Bu yol
  seçilirse süzgecin ne kadarını attığı önce küçük bir dilimde ölçülüp sayıyla
  bildirilebilir; böylece inceleme emeği boşa gitmez.

---

## Ölçümün kaynakları

| Bilgi | Kaynak |
|---|---|
| Kapı durumları, örnek/inceleme sayaçları, sürüm ve amaç dağılımı | `derlem` veritabanı, salt okunur sorgular, 2026-09-17 |
| Temizlik sayıları ve kişisel veri bulguları | `var/derived/…clean_candidate.txt.manifest.json` (`clean-candidate-v1`) |
| 10 örnek satır, dosya boyutu | Nesne deposundaki `ebe29279…0d989` |
| Yakın kopya çiftleri (100 çift, Hamming 15–25) | `similarity_review_pairs`, `similarity_calibration_runs` |
| Dondurma kapıları | `internal/repository/releases.go` (`QueueFreeze`) |
| İhracat biçimi, manifest alanları, token tahmini yöntemi | `docs/canonical_exports.md` |
| Dekontaminasyon yöntemi ve politikası | `docs/approximate_decontamination.md`, `worker/src/derlem_worker/releases.py` |
| Kalite süzgeci politikası | `worker/src/derlem_worker/quality_filters.py` (`tr-web-v1`) |
| İnceleme paketi kuralları | `docs/concurrent_document_review.md` |
