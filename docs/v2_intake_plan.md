# v2 Alım Planı: Web-Ölçekli TR Corpus ve Sentetik Ders Kitabı

**Tarih:** 2026-07-05
**Hedef:** 30-100B token Türkçe pretrain havuzu + sentetik TR ders-kitabı korpusu
**Başarı metriği:** Faz-4 sonrası TurkishMMLU (mevcut taban: %25,4, şans seviyesi)
**Kısıt:** GPU gerektirmez; Spark koşusu sürerken CPU/disk işi olarak paralel yürür.

Gerekçe ve tüketici geri bildirimi: [Gardash Feedback 2026-07](gardash_feedback_2026_07.md).
Derlem ilkeleri değişmez: her kaynak tek amaca bağlanır, hak kapısı
default-deny çalışır, ham metin veritabanına girmez, release'ler deterministik
ve frozen'dır.

## 1. Aday Kaynaklar ve Hak Ön Değerlendirmesi

| Kaynak | Lisans (ön değerlendirme) | Kayıtta beklenen hak durumu | Not |
|---|---|---|---|
| FineWeb-2 (TR alt kümesi) | ODC-By 1.0 + CommonCrawl kullanım şartları | `cleared` adayı; atıf kanıtıyla | HuggingFace'ten shard bazlı indirme; dil etiketi hazır |
| HPLT v2 (TR) | CC0 (public domain dedication) | `cleared` adayı | En temiz hak durumu; kalite filtresi bizde koşar |
| CulturaX (TR) | mC4 (ODC-By) + OSCAR bileşimi; sayfası araştırma kullanımını vurgular | `restricted` — hukuki inceleme şart | Egemen/ticari eğitim hedefi için kullanım kapsamı netleşmeden onaylanamaz |
| Sentetik TR ders kitabı | Kendi üretimimiz | `cleared`; üretim manifesti kanıt olur | Aşağıda ayrı bölüm |

Kesin boyut/token sayıları indirme anında ölçülür ve kaynak manifestine
yazılır; plan hedefi üç web kaynağının TR alt kümelerinin 30-100B token
bandını fazlasıyla karşılamasıdır. **Hiçbir sayı doğrulanmadan release
metadata'sına geçmez.**

Her indirme paketi için kayıt anında zorunlu: kaynak URL'si + sürüm/snapshot
kimliği, indirme tarihi, lisans metni kopyasının referansı
(`license_evidence_ref`), `lineage_ref` olarak orijinal shard listesi.

## 2. Boru Hattı: Filtreden Release'e

Mevcut Derlem kapıları aynen geçerlidir; v2 yalnızca ölçek ekler.

```text
indirme (shard'lar)
  -> ön filtre (CPU): dil doğrulama, boilerplate/çöp ayıklama, satır normalizasyonu
  -> Derlem kaynak kaydı (shard grubu = 1 kaynak, amaç: pretrain)
  -> resumable local ingest -> immutable depo
  -> PII taraması + exact/normalize dedup + fingerprint indeksi
  -> kaynaklar arası near-dedup raporu (SimHash; FineWeb2 x CulturaX x HPLT çakışması beklenir)
  -> risk puanlı örneklem -> insan incelemesi -> onay
  -> release draft -> freeze (eval/holdout dekontaminasyonu) -> export
```

Ön filtre Derlem'in DIŞINDA, ayrı bir hazırlık script'inde koşar (Derlem ham
kaynağı olduğu gibi kaydeder; filtre kararları lineage'a yazılır). Kaynaklar
arası near-dedup v2'de kritikleşir: aynı CommonCrawl kökeninden gelen üç
veri kümesi ciddi kesişim içerir; SimHash raporu + insan eşik kararı
(bkz. [similarity_calibration.md](similarity_calibration.md)) release öncesi zorunlu değerlendirmedir.

## 3. Derlem Kapasite Boşlukları (bu planın açtığı işler)

| Boşluk | Neden gerekiyor | Durum/Plan |
|---|---|---|
| Çok parçalı (multi-shard) kaynak desteği | 30-100B token tek dosya değil, yüzlerce shard | Kısa vadede: shard grubu başına kaynak (mevcut yapıyla çalışır). Orta vadede: kaynak-altı shard manifesti |
| Parquet/shard export paketleme | Eğitim ekipleri shard'lı tüketir | Yol haritasında mevcut (v0.4 sıradaki işler); v2 ile önceliklendi |
| Disk planı | 30-100B token ≈ yüzlerce GB-TB ham metin + immutable kopya | Alım öncesi kapasite hesabı zorunlu; S3/MinIO (v0.6) öne çekilebilir |
| Kota/disk headroom koruması | Büyük ingest'ler diski doldurabilir | `SEC-P0-07` ile birleşik ele alınır |
| Sentetik köken etiketi | İnsan/sentetik ayrımı release metadata'sında görünmeli | v0.5 şema işi; geçici çözüm: `source_type=synthetic_*` + üretim manifesti lineage'ı |

## 4. Sentetik TR Ders-Kitabı Korpusu

Amaç: TurkishMMLU'nun ölçtüğü bilgi tabanını doğrudan hedefleyen, müfredat
kapsamlı, temiz Türkçe eğitsel metin.

Yönetişim kuralları (Derlem ilkeleriyle uyum):

1. Üretici model, sürüm, prompt şablonu kimliği ve üretim tarihi bir "üretim
   manifesti" dosyasına yazılır; kaynak kaydında `license_evidence_ref` +
   `lineage_ref` bu manifesti gösterir.
2. `source_type` değeri `synthetic_textbook` olur; saf-insan havuzu isteyen
   release'ler bu kaynak tipini dışarıda bırakabilir.
3. Sentetik içerik de aynı kapılardan geçer: PII (üretici sızıntısına karşı),
   dedup, örneklem ve insan incelemesi. Sentetik olması kapı muafiyeti getirmez.
4. Üretimde başka modellerin çıktısını kullanmanın lisans/şart etkisi
   (ör. sağlayıcı kullanım şartları) hak kapısında değerlendirilir.

Konu kapsamı önerisi (ilk dilim): ortaokul-lise müfredat eksenli fen, tarih,
coğrafya, yurttaşlık ve dil bilgisi; her belge tek konu, kaynakça-vari tekrar
içermeyen anlatım. Hedef: birkaç yüz milyon - birkaç milyar token'lık ilk paket.

## 5. Fazlama ve Sorumluluk

| Faz | İş | Sorumlu | GPU? |
|---|---|---|---|
| 0 (şimdi) | Disk kapasite hesabı; FineWeb-2/HPLT TR shard listeleri + lisans kanıt dosyaları; CulturaX hukuki inceleme başlatma | Veri yöneticisi | Hayır |
| 1 | İlk pilot: HPLT TR'den 1-2 shard grubunu uçtan uca geçirme (kayıt→ingest→kapılar→örneklem) | Veri yöneticisi + moderatör | Hayır |
| 2 | FineWeb-2 TR ölçekli alım + kaynaklar arası near-dedup raporu + eşik kararı | Ekip | Hayır |
| 3 | Sentetik ders kitabı ilk paketi (üretim manifesti + kapılar) | Ekip | Üretim modeline bağlı |
| 4 | v2 release + export; Gardash Faz-4 sonrası TurkishMMLU ölçümü | Admin + Gardash | Ölçüm Gardash'ta |

Faz 1 pilotu, v2'nin tüm kapasite varsayımlarını küçük ölçekte doğrular;
ölçek büyütme ancak pilot temizse başlar ("ölçek ölçümle büyür" ilkesi).

## 6. Riskler

- **CulturaX hak belirsizliği:** plan CulturaX'siz de 30-100B bandını
  karşılayacak şekilde kurulur; CulturaX bonus kabul edilir.
- **Çapraz kaynak tekrarları:** near-dedup raporu olmadan üç kaynağın
  birleştirilmesi şişkin ve tekrarlı havuz üretir; rapor + insan eşiği zorunlu.
- **Disk yetersizliği:** faz 0 kapasite hesabı tamamlanmadan indirme başlamaz.
- **İnceleme darboğazı:** shard grubu başına 200 örnek kuralı v2 ölçeğinde
  inceleme yükü doğurur; bulk review mevcuttur, gerekirse örneklem
  yoğunlaştırma politikası ayrıca kararlaştırılır.
