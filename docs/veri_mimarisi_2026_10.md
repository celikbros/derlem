# Derlem veri mimarisi — çok kaynaklı alım, ortak belge kaydı, türetme

**Tarih:** 2026-10-13 · **Karar:** kurucu ("üçüne de evet", 2026-10-13) · **Durum:** plan; uygulama
TASK-032 (yeniden yazıldı), TASK-044, TASK-046, TASK-047, TASK-048
**Soru:** Her veri setinin sütunları farklı. Birçoğunu indirirsek kendi sistemimize nasıl alırız,
kalitesini nasıl otomatik ölçeriz, onlardan yeni veri setleri nasıl üretiriz?
**Cevap, tek cümle:** kaynak başına küçük bir **uyarlayıcı**, hepsinin aktığı **tek bir ortak belge
kaydı**, metinden ayrı tutulan **kararlar**, ve her çıktının yeni bir **kaynak** olarak kaydedildiği
türetme. Kurucunun tarif ettiği şey budur; yanlış değil, bugün yarısı var.

## 1. Bugün ne var, ne yok

| Katman | Bugün | Eksik |
|---|---|---|
| Alım | Yerel dosya, satır = belge; JSONL'de yalnız `text`/`content`/`body` ve `id` okunur; parquet okunamaz | Uyarlayıcı yok: tanınmayan sütunlar **atılır** (FineWeb2-HQ'nun `url`, `date`, `quality_score`'u kaybolur — Faz-2'deki kaybın aynısı) |
| Belge kaydı | Talimat verisi için gerçek şema var (`derlem.canonical-sample.v1`). Ön eğitim belgesi için **yok**: üstveri kaynak seviyesinde; belge başına yalnız SHA + satır numarası | Belge başına kaynak, adres, tarih, dil puanı, kalite sinyali, kopya kümesi |
| Kararlar | Atılacak-satır listeleri, atma raporları, manifestler, 200 örnek incelemesi — hepsi var ama dosya dosya | Belge kimliğine bağlı tek bir karar kaydı; "bu belge neden dışarıda" sorusu tek yerden cevaplanmıyor |
| Depolama | İçerik adresli nesne deposu (dosya = nesne); türevler yeni nesne | Sütunlu biçim yok: bir sütunu okumak için bütün dosya okunur; "puanı X'in üstü" süzmesi metne dokunmadan yapılamaz |
| Kalite kontrolü | Kapılar (PII, birebir/normalize tekrar, parmak izi), `tr-web-v3` kuralları, elle çalıştırılan hakem okuması | Hakem okuması bir iş olarak hatta değil; sonucu kaynağa yazılmıyor |
| Türetme | `clean_candidate` (süzgeç → yeni nesne, soy kaydıyla) | Ortak kayıttan seçim listesiyle türetme; talimat üretimi (distilasyon) ortak kayıttan beslenmiyor |
| İhracat | txt + jsonl (SHA'lı manifest) | Tokenize ihracat; belge üstverisi ihracatta yok |

## 2. Hedef mimari

```
  kaynak (HF / yerel / kazıma)
        │  uyarlayıcı (kaynak başına ~30 satırlık tanım)
        ▼
  ORTAK BELGE KAYDI  ──►  nesne deposu (Parquet parçaları, içerik adresli)
        │
        ├─ kapılar: PII · tekrar · dil · kural süzgeci      ─┐
        ├─ hakem örneklemesi (sıkı ölçüt, model jürisi)      ├─►  KARAR KAYDI (belge kimliğine bağlı)
        └─ insan incelemesi (200 örnek, kurucu)             ─┘
        │
        ▼
  TÜRETME = seçim listesi (+ dönüşüm)  ──►  yeni kaynak (soy kaydı, yeni SHA)
        │
        ▼
  DONDURULMUŞ SÜRÜM  ──►  ihracat: jsonl (üstveriyle) · txt · tokenize parçalar · manifest
```

### 2.1 Uyarlayıcı (kaynak başına)

Küçük bir tanım dosyası: "onların sütunu → bizim alanımız". Kod değil, veri.

```yaml
# adapters/epfml-fineweb2-hq.yaml
dataset: epfml/FineWeb2-HQ        revision: c0c06e94…        config: tur_Latn
format: parquet                   columns_read: [text, id, url, date, dump, language,
                                  language_score, quality_score, minhash_cluster_size, file_path]
columns_skipped: [embeddings]     # 768 boyutlu vektör, dosyanın %75'i; metin değil
map:
  text: text                      # paragraf sonları korunur
  provenance.external_id: id
  provenance.url: url
  provenance.crawl_date: date
  provenance.dump: dump
  language.declared: language
  language.score: language_score
  signals.quality_score: {value: quality_score, scorer: "fineweb2-hq-xlmr-mlp"}
  signals.minhash_cluster_size: minhash_cluster_size
extra: [file_path]                # eşlenmeyen her şey; atılmaz
document_boundary: record         # bir kayıt = bir belge, asla bölünmez
```

Her yeni veri seti = yeni bir yaml. Talimat setleri için de aynı: `messages` ya da
`instruction/output` alanları `derlem.canonical-sample.v1`'e eşlenir. Uyarlayıcı **doğrulama**
yapar: eşlenen sütun yoksa alım başlamaz; `text` boş kayıt sayılır ve raporlanır.

### 2.2 Ortak belge kaydı (`derlem.document.v1`)

| Alan | İçerik | Nereden |
|---|---|---|
| `doc_id` | metnin SHA256'sı (ham baytlar) | hesaplanır |
| `text` | belge metni, paragraf sonları korunur, **asla yeniden yazılmaz** | uyarlayıcı |
| `source_id`, `source_ordinal` | Derlem kaynağı ve kayıt sırası | alım |
| `provenance` | veri seti, sürüm SHA'sı, dosya, satır, onların kimliği, `url`, tarama tarihi, dump | uyarlayıcı |
| `language` | beyan edilen (`tr`), ölçülen (fastText, TASK-028) ve puanı | uyarlayıcı + kapı |
| `signals` | kalite puanları — **kimin puanı olduğuyla** (`fineweb2-hq`, `tr-web-v3`, `juri-sonnet-siki`), kopya kümesi büyüklüğü | kaynak + kapılar |
| `rights` | lisans kimliği, kanıt referansı, kapsam (ticari olmayan) | kaynak kaydı |
| `extra` | eşlenmeyen sütunlar, JSON | uyarlayıcı |

Belge **tek fiziksel satır değil, bir Parquet satırı**. Faz-2'nin "belge = satır, satır sonu yok"
sınırı yeni kaynaklara taşınmaz. Mevcut Faz-2 kaynakları aynı kayda **geriye dönük** alınır
(provenance = Derlem kaynak kimliği + satır numarası; adres yok, çünkü hiç olmadı).

### 2.3 Kararlar metinden ayrı (`derlem.decision.v1`)

Her hüküm bir satır: `doc_id · karar türü · hüküm · gerekçe · kim/ne verdi · sürüm · tarih`.

| Karar türü | Veren | Bugünkü karşılığı |
|---|---|---|
| `pii` | PII tarayıcısı | kaynak seviyesinde `pii_status` + atılan satırlar |
| `duplicate` / `near_duplicate` | tekrar kapıları | manifest sayıları, `duplicate_of` |
| `quality_rule` | `tr-web-vN` | atma raporu (`rejections.jsonl`) |
| `language` | fastText listesi | atılacak-satır listesi |
| `rights_scope` | S2 kapsam listesi | atılacak-satır listesi |
| `held_out` | hash kuralı | ayrı dosya |
| `jury` | model hakemi (sıkı ölçüt) | `hukumler-*.jsonl` (var/ altında, elle) |
| `human_review` | kurucu | `document_reviews` tablosu |

Metin hiç değişmez; bir sürüm "şu belgeler, şu kararlarla seçildi" listesidir. Bugünkü "hiçbir
metin yerinde temizlenmez" kuralı aynen korunur, hatta tek yerden zorlanır.

### 2.4 Depolama: ne nerede durur

| Veri | Yer | Neden |
|---|---|---|
| Belge metni + üstveri | Nesne deposunda **Parquet parçaları** (ör. 100.000 belge/parça), içerik adresli, sıkıştırılmış | Sütun bazlı okuma; "puanı > X" süzmesi metni okumadan; sıkıştırmayla ham boyutun ~%40'ı |
| Kaynaklar, sürümler, incelemeler, karar kayıtları | PostgreSQL | İlişki ve denetim izi; bugünkü tablolar |
| Belge kararları (milyonlarca satır) | PostgreSQL'de **değil** — Parquet karar parçaları + özet sayılar DB'de | 4 milyon belge × 8 karar türü DB'yi şişirir; dosya olarak hem ucuz hem sürümlenebilir |
| Örneklenen belgeler (200/kaynak) | PostgreSQL `documents` (bugünkü gibi) | İnceleme arayüzü buradan okur |
| Alım dosyası (ham indirme) | `var/import`, depoya **sabit bağ** | İkinci kopya oluşmaz |
| Türev | Seçim listesi (Parquet) + manifest; metin kopyalanmaz | Üçüncü kopya oluşmaz; disk sorunu burada çözülür |

Disk sonucu: FineWeb2-HQ için bugünkü düzen ≈ 75–80 GB isterdi; bu düzende ≈ 27 GB alım +
≈ 12–15 GB Parquet (sıkıştırılmış) ≈ **40 GB** — 57 GB boş alana sığar. (Kestirim; Parquet
sıkıştırma oranı Türkçe metinde ölçülmedi.)

### 2.5 Otomatik kalite kontrolü — her kaynak için aynı hat

Kaynak kaydedilince kendiliğinden koşar; sonuçları kaynak kartında ve karar kaydında:

1. **Kapılar** (bugün var): PII, birebir/normalize tekrar, parmak izi, dil.
2. **Kural süzgeci** (`tr-web-v3` + TASK-046'nın iki kuralı): atma raporu + gerekçe sayıları.
3. **Hakem örneklemesi** (yeni, TASK-047): kaynaktan tohumlu 200 belge, model jürisi, sıkı
   ölçüt → **çöp oranı ve aralığı** kaynak kartına yazılır. Hakem = Sonnet + sıkı ölçüt (ölçülmüş:
   kurucuyla kappa 0,49; test-tekrar 0,88–0,92). Kurucu yalnız 14–30 satırlık çıpaya bakar.
4. **İnsan incelemesi** (bugün var): 200 örnek, sürüm sözleşme kapısı için.

Böylece "bu veri seti iyi mi" sorusu her kaynak için aynı dört sayıyla cevaplanır: PII isabeti,
kural atma oranı, hakem çöp oranı, insan ret oranı. Bugün FineWeb2-HQ ve v5 için elle yapılan
karşılaştırma standart çıktı olur.

### 2.6 Türetme ve yeni veri seti üretimi

- **Süzme türevi:** seçim listesi = karar kaydından bir sorgu ("PII temiz ∧ kural geçti ∧ hakem
  çöp demedi ∧ hak kapsamında ∧ held-out değil"). Yeni kaynak, soy kaydı girdileri gösterir.
  `clean_candidate` bu hâle gelir: metin yazmaz, liste yazar.
- **Dönüşüm türevi:** metinden yeni metin üreten her şey (distilasyon ile soru-cevap, özet,
  çeviri, paragraf birleştirme) **yeni kaynak + yeni nesne**; girdi belgesinin `doc_id`'si
  provenance'ta. Talimat verisi `derlem.canonical-sample.v1` olarak doğar, aynı kapılardan geçer.
- **Karışım:** sürüm = birden çok kaynaktan seçim + ağırlık; karışım raporu kaynak ve lisans
  payını yazar (TASK-031).

### 2.7 İhracat

jsonl (belge üstverisiyle, bugünkü zarf genişletilir) · txt (satır = belge) · **tokenize parçalar**
(belge sınırı işaretli, karıştırılmış, parça SHA'ları ve token sayısıyla manifest — TASK-033'e bağlı).
Üstveri eğiticiye gitmez; neyin seçileceğine ve hangi ağırlıkla karışacağına karar vermek içindir.

## 3. Sıra

| # | İş | Kart | Model | Bağımlılık |
|---|---|---|---|---|
| 1 | Ortak belge kaydı + karar kaydı şeması, Parquet okuma/yazma, uyarlayıcı tanımı ve doğrulayıcı | TASK-044 | opus | — |
| 2 | HF alım işi: sabit sürüm, seçici sütun (Range), parça SHA'ları, kaldığı yerden devam, manifest; FineWeb2-HQ ilk koşu | TASK-032 (yeniden yazıldı) | opus | 1 |
| 3 | İki yeni kural: makine çevirisi, ticari/ürün sayfası — FineWeb2-HQ örneğinde ölçülerek | TASK-046 | opus | 2 (veri) |
| 4 | Hakem örneklemesi iş olarak + kaynak kartında dört sayı | TASK-047 | sonnet (hakem) / opus (hat) | 1 |
| 5 | Ön eğitim inceleme kapısı: sıfır tolerans yerine eşik (%10 önerisi), reddedilenler listeye, oran künyeye | TASK-048 | opus | kurucu kararı |
| 6 | Faz-2 kaynaklarının ortak kayda geriye dönük alınması; v5 seçim listesi olarak yeniden tanımlanır | TASK-044 içinde | sonnet | 1 |
| 7 | Mevzuat (idari-resmî damar) ve talimat setleri için uyarlayıcılar | TASK-032 içinde | sonnet | 1, lisans notları |
| 8 | Tokenize ihracat | TASK-033 | opus | raf tokenizer |

Planlama ve kararlar bu oturumda (Fable); kod/ölçüm işleri yukarıdaki modellere.

## 4. Kurucunun önündeki açık kararlar

- **İnceleme kapısı eşiği** (TASK-048): %10 mu? Konmadan FineWeb2-HQ tabanlı aday incelenemez.
- **Yeni ham veri yedek kapsamı:** 27 GB alım dosyası yedek dışı mı (sabit sürüm + manifest ile
  yeniden üretilebilir) — öneri: dışı; türev ve seçim listeleri içi.
- **İdari-resmî damar:** `muhammetakkurt/mevzuat-gov-dataset` ilk aday; lisans notu geliyor.
- **Talimat setleri** (`Turkce-Atlas-Instruct` vb.): kaynak sentetikse üreten modelin şartları.

## Sınırlar

Parquet sıkıştırma oranı, Range indirme hızı (tek bağlantı 1,9 MB/s ölçüldü; paralel denenmedi)
ve karar kaydının büyük korpusta sorgu süresi ölçülmedi. İlk alım bunları ölçer.
