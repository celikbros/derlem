# Hakem örneklemesi — standart kaynak kapısı (TASK-047)

Her kaynak kartında dört kalite sayısı:

| Sayı | Tanım | Kapsam | Aralık |
|---|---|---|---|
| **PII isabeti** | en az bir PII bulgusu (`basic-tr-v2`: TCKN, IBAN, e-posta, telefon, kart) olan örnek belge payı | hakem örneklemi | Wilson %95 |
| **Kural atma** | kalite politikasının (`tr-web-v3`, değiştirilebilir) atacağı örnek belge payı | hakem örneklemi | Wilson %95 |
| **Hakem çöp** | (`cop` + `emin degilim`) / hüküm verilen satır | hakem örneklemi | Wilson %95 |
| **İnsan ret** | (ret + sensitive_review) / incelenen örnek (TASK-048 formülü) | insan inceleme örneği | Wilson %95, web canlı hesaplar |

`emin degilim` çöp tarafında sayılır: 2026-10-04 elle ölçümü (FineWeb2-HQ %43 = 39 `cop` +
4 `emin degilim`; v5 %53 = 49 + 4) bu kuralla hesaplanmıştı. Ayrıca yalnız-`cop` oranı da
yazılır. PII ve kural sayıları örneklem üzerindedir; kaynakta tam PII taraması varsa
(`pii_scans`) nüfus bulguları ek olarak `pii.population` altında durur (bulgu / 1.000 belge —
tarayıcı belge değil bulgu sayar, iki sayı aynı şey değildir).

## Saklama (migration yok)

Sayılar `sources.source_metadata.quality_numbers` altına yazılır
(`derlem.quality-numbers.v1`): sayılar ve aralıklar, `judge_id`, `judge_model`, `run_id`,
kılavuz kimliği ve SHA'sı, örneklem (yöntem, tohum, n, nüfus), karar dosyasının SHA'sı ve satır
sayısı, kör dosya ve cevap anahtarının SHA'ları, maliyet (çağrı, jeton, tahmini USD, fiyat
tablosu sürümü), `computed_at`, `artifacts` (depoya giren her dosyanın SHA'sı). Go API bu alanı
kaynak cevabında zaten döndürüyor; web doğrudan okur. Depodaki nesneler `storage_objects`'e
kaydedilir; kaynak silme aracı (`purge_sources`) `source_metadata` içindeki SHA'ları referans
sayar.

Kararlar `derlem.decision.v1` Parquet satırıdır: `decision_type = jury`, `verdict`
(`kalsin → pass`, `cop → reject`, `emin degilim → flag`), `reason = tur/cop_nedeni`
(ör. `urun-ticari/seo-ticari`, `haber/`), `judge`, `run_id` (ikinci geçiş `run_id + "/retest"`),
`source_ordinal`. Jüri satırları **filtre değildir**: kurallara ve seçim listelerine bilgi verir,
kurucu karar vermedikçe belge atmaz.

## Örneklem

`jury-uniform-sha256-v1`, risk ağırlıksız (risk ağırlıklı olan insan incelemesinin örnekleyicisi):

- **Parça kaynağı** (`derlem.import-manifest.v1`): belge anahtarı
  `sha256(yöntem ‖ tohum ‖ doc_id)`, en küçük `n` anahtar. Seçim yalnız (tohum, doc_id)
  kümesine bağlıdır: parça sınırı, sıra numarası, yeniden alım değiştirmez. Birebir kopya
  metinde en küçük sıra numaralı geçiş alınır, kopya sayısı yazılır. Her parçanın boyutu ve
  SHA256'sı okunurken doğrulanır; seçilen belgelerde `doc_id == sha256(text)` doğrulanır.
- **Satır kaynağı** (txt/jsonl): anahtar `sha256(yöntem ‖ tohum ‖ satır_no)`; boş ve sınır aşan
  satırlar nüfusa girmez (sayılır). JSONL'de metin `text/content/body` alanından gelir.
- Kör dosyadaki sıra anahtar sırasıdır (kaynak sırası değil).

Ölçülen süre (paylaşımlı CPU, PII taraması sürerken): FineWeb2-HQ 8.578.808 belge / 105 parça
**61 sn**; ana korpus 13,57 GB / 6.027.968 satır **26 sn**. Aynı tohumla ikinci koşu bayt bayt
aynı kör dosyayı üretti.

## Kör dosya ve cevap anahtarı

`juri-kor.jsonl` satırı yalnız `no`, `metin`, `kesildi`, `char_count` taşır — url, dump,
kimlik, sıra no, sinyal, kaynak adı yok. Metindeki her boşluk dizisi tek boşluğa indirilir
(FineWeb2-HQ satır sonu taşır, v5 taşımaz; biçim kaynağı ele vermesin), ilk 6.000 karakter
verilir. Yazarken bir koruma (`assert_blind_row_clean`) fazladan alanı ve ham boşluğu
reddeder. `juri-anahtar.json` eşlemeyi tutar: `doc_id`, `source_ordinal`, url/dump/kimlik,
kural gerekçeleri, PII sayıları. Hakeme verilmez.

## Kılavuz ve hakem kimliği

Kılavuz `worker/src/derlem_worker/rubrics/juri-siki-v1.md` (LF, paketle gelir). Hakem
kimliği `sonnet+juri-siki-v1@<sha8>`; bugünkü SHA `50e993d6…` (test sabitler). Kılavuz
değişirse test kırmızı olur ve kimlik bilinçli olarak yeni sürüme (`juri-siki-v2`) taşınır;
koşu hazırlandığı kılavuzdan farklı bir kılavuzla puanlanamaz.

**Kaynak notu:** TASK-040 / 2026-10-04 koşularında modele verilen talimatın birebir metni
depoda saklanmamıştı (yalnız kör dosyalar, hüküm dosyaları ve hazırlama betikleri var). v1
metni depodaki kanıttan yeniden kuruldu: kurucunun 14 satırlık sayfasındaki soru ve "sıkı
korpus, şüpheliyi at / mahcup olur musunuz" ölçütü, hüküm dosyalarındaki sözlük (`hukum`,
13 `tur`, 10 `cop_nedeni`), kurucunun "ansiklopedi kalır, sponsorlu inceleme gider; önce biçim"
çizgisi (TASK-041). Bu yüzden kabul ölçütü olan "FineWeb2-HQ ve v5 elle ölçülen sayıları
aralık içinde yeniden üretir" aynı zamanda bu yeniden kurulumun sınavıdır.

## Model çağrısı ve bütçe

Çağrı distilasyonun sağlayıcı kaydından geçer (`PROVIDERS['anthropic']`, stdlib HTTP).
Anahtar **yalnız** worker ortamından (`ANTHROPIC_API_KEY`); iş yükünden ya da veritabanından
okunmaz, hiçbir dosyaya yazılmaz. Model `DERLEM_JURY_MODEL` (varsayılan `claude-sonnet-5-5`),
düşük çaba, kılavuz önbellekli sistem isteminde, belge başına bir çağrı. Ret (`refusal`) ya da
ayrıştırılamayan cevap o satırda hüküm yok demektir; yedek model kullanılmaz (hakemi sessizce
değiştirir, judge id yalan olur). Art arda 5 hata koşuyu durdurur.

Üst sınırlar (kurucu onayı bekliyor; ortamdan değişir):

| Değişken | Varsayılan |
|---|---|
| `DERLEM_JURY_MAX_CALLS_PER_RUN` | 450 |
| `DERLEM_JURY_MAX_TOKENS_PER_RUN` | 3.000.000 |
| `DERLEM_JURY_MAX_CALLS_PER_DAY` | 1.000 |
| `DERLEM_JURY_MAX_TOKENS_PER_DAY` | 6.000.000 |

- **Ön kontrol:** plan (satır × geçiş çağrı, kötümser jeton tahmini) sınıra sığmıyorsa hiç
  çağrı yapılmadan durur (`judge_budget_exceeded`).
- **Dayanıklı günlük sayaç:** `DERLEM_JURY_LEDGER_DIR` (varsayılan `var/state/jury-budget/`),
  UTC gün başına `jury-budget-YYYY-MM-DD.json`. Her çağrı ÖNCE ayrılır ve diske yazılır (fsync +
  atomik değiştirme, kilit dosyası); sonra tahmin gerçek jetonla düzeltilir. Çağrı sırasında
  çöken süreç sayılmış kalır — sayaç eksik saymaz.
- İşte koşu sayacı **işe** bağlıdır (`job-<id>`): yeniden deneme aynı sınırı paylaşır,
  ücretli çağrıları ikinci kez yapamaz. Bütçe aşımı ve hakem hatası kalıcı hatadır (yeniden
  denenmez).
- Tahmini maliyet (Sonnet 5.5 fiyat tablosu `anthropic-2026-10-06`, gerçek kör dosyalardan):
  geçiş başına ≈ $0,8–1,4; 200 belge × 2 geçiş ≈ **$1,6–2,8**. Ölçülen maliyet ilk gerçek
  koşudan sonra yazılır (`quality_numbers.cost`).

## İş: `jury_sample`

Yük: `source_id`, `seed` (zorunlu tamsayı), `n` (200), `retest` (true), `rule_policy`
(`tr-web-v3`), `object_sha256` (verilirse değişmemiş olmalı). Akış: örneklem → kör dosya +
anahtar → hakem (anahtar varsa) → karar Parquet'i → nesne deposu → `quality_numbers` + denetim
olayı (`source.quality_numbers_recorded`) + iş sonucu, tek işlemde. Anahtar yoksa durum
`judge_unavailable`: kör dosya ve anahtar yine depoya girer, PII ve kural sayıları yazılır.

Kuyruğa ekleme bugün elle (API ucu yok):

```sql
INSERT INTO background_jobs(job_type, payload, created_by)
SELECT 'jury_sample', jsonb_build_object('source_id', id::text, 'seed', 20261013, 'n', 200), created_by
FROM sources WHERE id = '<kaynak>';
```

Dağıtım sırası: eski worker bu iş tipini tanımaz ve işi başarısız sayar; önce worker güncellenir.

## Hükümleri dışarıdan vermek (`--verdicts`)

Hüküm dosyası JSONL, satır başına bir nesne (2026-10-04 `hukumler-sonnet-siki.jsonl` biçimi,
`sha256` alanı artık yok):

```json
{"no": 17, "hukum": "cop", "tur": "urun-ticari", "cop_nedeni": "seo-ticari", "gerekce": "ürün tanıtımı"}
```

`hukum`: `kalsin` / `cop` / `emin degilim` (Türkçe harfli yazım da kabul). Bilinmeyen ya da iki
kez gelen `no` hatadır; eksik satır raporlanır.

```powershell
$env:PYTHONPATH='worker/src'; $env:PYTHONIOENCODING='utf-8'
# tek kaynak, iki okuma
& .venv/Scripts/python.exe -m derlem_worker.jury score --run-dir <kosu> --verdicts p1.jsonl --retest p2.jsonl --source-id-context
# iki kaynak tek oturumda (karma): böl, sonra her koşuyu puanla
& .venv/Scripts/python.exe -m derlem_worker.jury split --mix-dir <karma> --verdicts karma-p1.jsonl --output-name hukumler-karma-p1.jsonl
# sayıları karta yaz (VERİTABANINA YAZAR; kurucu kararı)
& .venv/Scripts/python.exe -m derlem_worker.jury score --run-dir <kosu> --verdicts ... --apply-db
```

`score` koşu dizinine `kararlar.parquet` ve `kalite-sayilari.json` yazar; `--source-id-context`
insan ret ve nüfus PII'yi veritabanından yalnız okur.

## Kurucu çapası

`anchor` 14–30 (varsayılan 20) "zor satır" sayfası üretir (rafın biçimi): önce iki geçişin
ayrıştığı satırlar, sonra `emin degilim`, sonra kural–hakem çelişkileri, kalan yer iki hüküm
sınıfından en uzun belgelerle. Sayfada hakem hükmü, kural ve kaynak yazmaz. Kurucu `Hukum:`
satırlarını doldurur; `anchor-score` hakem–kurucu uyumunu ve kappa'yı (ikili ve üç sınıflı)
verir. Satırlar kasıtlı olarak zor yerlerden seçildiği için bu uyum nüfusun uyumundan düşüktür;
yön göstergesidir.

## Web

Kaynak kartında "Kalite sayıları" bölümü (dört sayı, aralık, ölçüm kaydı: örneklem, hakem,
test-tekrar, koşu, kararlar, maliyet); Kaynaklar görünümünün altında açılır "Kalite
karşılaştırması": bütün pretrain kaynakları yan yana.

## Ölçüm (2026-10-13, `var/olcum-2026-10-13/task-047/`)

Karma 400'lük kör dosya (200 FineWeb2-HQ + 200 Faz-2 ana korpus, karışık sıra) iki bağımsız geçişte
dörder sonnet oturumuna okutuldu (oturum başına 100 satır; yalnız kılavuz; cevap anahtarı yasak).
`jury split` ile koşulara bölündü, `jury score … --retest` ile puanlandı.

| | FineWeb2-HQ `tur_Latn` | Faz-2 ana korpus |
|---|---:|---:|
| Hakem çöp (çöp + emin değilim) | **%46,5** [39,7–53,4] | **%48,0** [41,2–54,9] |
| Yalnız çöp | %44,0 | %47,5 |
| Test-tekrar κ (üç sınıf / ikili) | 0,91 / 0,92 | 0,84 / 0,86 |
| Kural atma (`tr-web-v3`) | %0,5 | %1,5 |
| PII isabeti | %0,5 | %3,5 |
| Başlıca çöp nedenleri | makine çevirisi 42, SEO/ticari 25 | diğer 23, SEO/ticari 21, menü-spot 20, liste-katalog 17 |

10-04 elle ölçümü (FineWeb2-HQ %43) aralığın içinde; v5 silindiği için karşılaştırma ebeveyniyle
yapıldı. Kararlar `derlem.decision.v1` Parquet olarak koşu dizinlerinde; kartlara yazım
(`--apply-db`) kurucuda.

## Sınırlar

- PII ve kural oranları n=200 örneklem üzerindedir; seyrek olaylarda aralık geniştir
  (FineWeb2-HQ kural atma 1/200 = %0,5 [0,1–2,8]). Nüfus düzeyi kural oranı türetme manifestinden
  gelir, bu kapı onu ölçmez.
- Hakem sayısı kılavuza bağlıdır; kılavuz değişince eski sayılar yeni kimlikle karşılaştırılmaz.
- İnsan 200 örnek incelemesinin (sözleşme kapısı) yerine geçmez.
