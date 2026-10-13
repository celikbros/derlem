# HF veri seti içe alımı (`import_hf_dataset`)

**Tarih:** 2026-10-13 · **Kart:** [TASK-032](gorevler/TASK-032-in-app-import-hf-dataset-job.md) ·
**Tasarım:** [veri_mimarisi_2026_10.md](veri_mimarisi_2026_10.md) §2.1–2.4 ·
**Kayıt ve uyarlayıcı:** [belge_kaydi_v1.md](belge_kaydi_v1.md) ·
**Kod:** `worker/src/derlem_worker/hf_import.py`, `import_manifest.py`, `jobs/hf_import_jobs.py`;
API `internal/httpapi/hf_import_handlers.go`, `internal/repository/hf_import.go`.

Bir Hugging Face veri setinin **sabit bir sürümünü**, uyarlayıcının (yaml) tanımladığı sütunlarla,
**yalnız gereken baytları indirerek** ortak belge kaydına (`derlem.document.v1`) alır ve sonucu
kayıtlı bir Derlem kaynağı yapar. İlk kullanım: FineWeb2-HQ `tur_Latn` (`adapters/epfml-fineweb2-hq.yaml`).

## 1. Nasıl çalışır

1. **Uyarlayıcı** yüklenir ve doğrulanır (TASK-044 sözleşmesi). `revision` 40 haneli commit SHA'sı
   olmak zorundadır: dal adı (`main`) sabit sürüm değildir, iş başlamaz.
2. **Veri kartı** (`README.md`) aynı sürümden okunur: `license` kimliği ve kartın SHA256'sı manifeste
   girer; kartın `configs` bölümünden config/split'in dosya kalıbı (`tur_Latn/*`) bulunur. Kartta
   `configs` yoksa `<config>/**` kullanılır.
3. **Dosya listesi** HF ağaç API'sinden sabit sürümde alınır (sayfalı; yol, boyut, git oid, LFS
   SHA256, xet hash) ve `import-manifest.draft.json`'a yazılır. datasets-server'ın satır sayısı
   yalnız bilgi amaçlı çapraz kontrol olarak iş sonucuna yazılır (ana dalı izlediği için manifeste
   girmez).
4. **Parquet yolu (seçici okuma):** her dosya için
   - indirme adresi bir kez çözülür (hub 302 → imzalı CDN adresi; `X-Repo-Commit`, `X-Linked-Size`,
     `X-Linked-ETag` = LFS SHA256 ağaçla karşılaştırılır; adresin süresi dolmadan yeniden çözülür),
   - altbilgi **tam iki Range isteğiyle** okunur (son 8 bayt, sonra altbilginin kendisi),
   - satır grubu başına yalnız okunan sütunların parça aralıkları birleştirilerek çekilir
     (FineWeb2-HQ'da 2 istek: `text…dump` ve `file_path…quality_score`),
   - atlanan sütunların (`columns_skipped`, ör. `embeddings`) bayt aralıkları **yasak** aralıktır:
     birleştirme o boşluğu asla köprülemez, okuyucu o aralığa düşen isteği göndermeden durur, dosya
     sonunda istek kaydı yasak aralıklara karşı bir kez daha denetlenir. Sunucu Range'i yok sayıp
     200 dönerse gövde okunmaz, iş durur (tam dosya inmesin diye).
   - 2–8 bağlantıyla satır grupları paralel çekilir; yazma sırası değişmez (belirlenimci).
5. **JSONL/TSV yolu** (küçük setler): dosyanın tamamı indirilir; boyut ve SHA (LFS'te SHA256,
   değilse git blob SHA1 = ağaçtaki `oid`) tutmazsa iş durur; sonra aynı uyarlayıcı sözleşmesi.
   Ham dosya parça yazılınca silinir.
6. Satırlar uyarlayıcıdan `derlem.document.v1` kaydına geçer (`adapt_rows`); **bir kaynak dosya =
   bir parça** (`DocumentShardWriter.cut()`); parça adı `shard-<dosya sırası>.parquet`. Boş/yalnız
   boşluk metin belge olmaz, sayılır (`empty_text`, sıra numaralarıyla). Sıra numarası
   (`source_ordinal`) dosyalar boyunca sürer; boş kayıt da numara tüketir.
7. Parça depoya yayımlanır (`publish_parquet`, içerik adresli); iş içinde yerel kopya silinir.
8. Bütün dosyalar bitince `import-manifest.json` yazılır ve depoya yayımlanır; **kaynağın nesnesi
   bu manifesttir**.

Eksik eşlenmiş sütun (`plan_columns`) → `AdapterError`, iş hata ile biter, parça yazılmaz.
HTTP 429/5xx ve bağlantı hataları üstel beklemeyle (1, 2, 4 … en çok 60 s; `Retry-After` varsa ona
uyulur) en çok 7 deneme. `HF_TOKEN` **yalnız ortam değişkeninden** okunur ve yalnız hub alan adına
gönderilir; CDN yönlendirmesine gönderilmez.

## 2. Defter (ledger) ve kaldığı yerden devam

`<çalışma dizini>/ledger.jsonl`: ilk satır başlık (alım kimliği: veri seti, sürüm, config, split,
uyarlayıcı SHA'sı, şema, yazıcı sürümü, kart SHA'sı, dosya listesi, satır grubu sınırı), sonra dosya
başına bir satır: parça SHA256, bayt, satır sayısı, sıra aralığı, metin baytı, **indirilen bayt**,
istek sayısı, altbilgi istek/bayt, sütun başına bayt, süre, dosyanın uyarlayıcı raporu.

- Her parçadan sonra defter **bütünüyle** geçici dosyaya yazılıp yerine konur (atomik; yarım satır
  olmaz).
- **Devam:** defterde olan ve parçası depoda (ya da kuru koşuda diskte) boyut + SHA256 ile tutan dosya
  atlanır; tutmayan dosya yeniden alınır. **Yarım dosya baştan alınır:** parça geçici dosyaya yazılır,
  hata/iptalde silinir; açılışta kalmış geçici dosyalar temizlenir.
- Başlığı farklı bir defterle (başka sürüm/uyarlayıcı/dosya listesi) devam edilmez: iş durur, yeni
  çalışma dizini gerekir.
- İş içinde çalışma dizini `IMPORT_ROOT/hf-import/<source_id>`: aynı işin yeniden denemesi defterden
  devam eder.

## 3. Manifest (`derlem.import-manifest.v1`)

Belirlenimci: zaman, süre, yerel yol, indirilen bayt **yoktur** (bunlar defterde ve iş sonucunda).
Aynı sürüm + uyarlayıcı + parametre → aynı bayt → aynı SHA (testte ve gerçek dosyada 1 ve 4
bağlantıyla doğrulandı). İçerik: `schema` (ilk anahtar — tanıma öneki), veri seti/sürüm/config/split,
dosya kalıpları, uyarlayıcı (ad, SHA, okunan/atlanan sütunlar), belge şeması, parça yazıcı ayarları,
lisans (`id`, kart SHA'sı), toplamlar (dosya, parça, kayıt, belge, boş metin, geçersiz, metin baytı,
**sütun sınıfına göre bayt**: `text` / `metadata` / `skipped`), kaynak dosyalar (boyut, LFS SHA256,
xet hash, satır, satır grubu, sütun baytları), parçalar (dosya, SHA256, bayt, satır, sıra aralığı),
birleşik uyarlayıcı raporu.

Kaynak kaydına giden özet (`lineage_ref`, tek satır JSON): `kind=hf_dataset`, manifest SHA'sı,
veri seti, sürüm, config, split, okunan/atlanan sütunlar, uyarlayıcı SHA'sı, kayıt/belge/parça
sayıları, sütun sınıfına göre bayt, lisans kimliği, kart SHA'sı, isteğe bağlı not.

## 4. Kaynak kaydı ve kapılar

`POST /api/v1/sources/import-hf` (yalnız `admin`; bilinmeyen alan → 400):

```json
{
  "adapter_path": "epfml-fineweb2-hq.yaml",
  "content_purpose": "pretrain",
  "rights_status": "unknown",
  "license_evidence_ref": "docs/haklar/hf-fineweb2-hq.md",
  "lineage_note": "FineWeb2-HQ tur_Latn ilk alim (TASK-032)",
  "name": "FineWeb2-HQ tur_Latn",
  "language": "tr",
  "domain": "web"
}
```

- `adapter_path`: göreli ise `ADAPTERS_ROOT`'a (varsayılan `./adapters`) göredir; mutlak ise
  `IMPORT_ROOT` ya da `ADAPTERS_ROOT` altında olmalıdır; `.yaml/.yml`, sembolik bağ yok, kökten
  çıkamaz (API'de ve işte iki kez denetlenir).
- `license_evidence_ref` `docs/haklar/…` olmalıdır; `cleared` için zorunludur. `name`, `language`
  (varsayılan `tr`), `domain` (varsayılan `general`) isteğe bağlı.
- Tek transaction: kaynak (`source_type=hf_dataset`, `license=hf-card:pending`, geçici
  `lineage_ref`) + `import_hf_dataset` işi + iki denetim olayı. Aynı uyarlayıcı yoluyla aktif bir alım
  varsa 409.
- **İlerleme:** `GET /api/v1/jobs?source_id=<id>` — iş kaydının `result.progress` alanı:
  `files_done/files_total`, `shards_done`, `rows_read`, `bytes_downloaded`, `mb_downloaded`,
  `mb_per_s`, `requests`, `retries`, `files_skipped_by_resume`.
- İş bitince tek transaction: parçalar (`application/vnd.apache.parquet`) ve manifest
  (`application/vnd.derlem.import-manifest+json`) `storage_objects`'e; kaynağın `object_sha256` =
  manifest, `lineage_ref` = özet, `license` = kartın lisansı (yer tutucuysa), durum `raw_ingested`;
  `scan_pii` ve `check_exact_duplicate` kuyruğa; parmak izi ve örnekleme bakım taramasıyla gelir.
- **Kapılar manifesti tanır:** PII, parmak izi (normalize tekrar) ve örnekleme nesne bir alım
  manifestiyse belgeleri depodaki parçalardan okur (her parça boyut + SHA256 ile doğrulanır; her belge
  satır okuyucularına tek satırlık `{"id","text"}` olarak verilir — paragraf sonları JSON kaçışıyla
  korunur, metin değişmez; sıra numarası `source_ordinal`). Birebir tekrar kapısı nesne SHA'sına
  bakar (değişiklik gerekmedi).
- **Sürüm freeze/ihracat bu kaynakları henüz kabul etmez:** yakın-kopya ve decontamination kapıları
  nesneyi satır satır okur; manifest satırlarını belge sanmamaları için açıkça
  `document_shards_source_not_supported` ile durdurulur (açık kalanlar).

Migration gerekmedi: `source_type` serbest metin, `lineage_ref` metin, parça listesi manifest nesnesinde,
iş tipi serbest metin. Eski işçi bu iş tipini görürse "Unsupported job type" ile işi başarısız yazar —
API ile işçi birlikte dağıtılmalıdır.

## 5. Komutlar

Kuru koşu (depoya yazmaz; parçalar çalışma dizininde kalır):

```powershell
$env:PYTHONPATH='worker/src'; $env:PYTHONIOENCODING='utf-8'
.\.venv\Scripts\python.exe var\olcum-2026-10-13\task-032\kuru_kosu.py rg1      # ilk satır grubu
.\.venv\Scripts\python.exe var\olcum-2026-10-13\task-032\kuru_kosu.py file-c4  # tek dosya, 4 bağlantı
```

Doğrudan fonksiyon:

```python
from pathlib import Path
from derlem_worker.hf_import import import_hf_dataset
r = import_hf_dataset(Path("adapters/epfml-fineweb2-hq.yaml"), Path("var/olcum/x"),
                      only_files=["tur_Latn/000_00000.parquet"], max_row_groups=1, connections=4)
print(r.manifest_sha256, r.run_stats)
```

Tam koşu (uygulama içinden; API ve işçi çalışırken, admin oturumuyla):

```powershell
$body = @{ adapter_path='epfml-fineweb2-hq.yaml'; content_purpose='pretrain'; rights_status='unknown';
           license_evidence_ref='docs/haklar/hf-fineweb2-hq.md'; name='FineWeb2-HQ tur_Latn';
           language='tr'; domain='web'; lineage_note='TASK-032 tam alim' } | ConvertTo-Json
Invoke-RestMethod -Method Post -Uri http://<api>/api/v1/sources/import-hf -WebSession $s `
  -ContentType 'application/json' -Body $body
# ilerleme: Invoke-RestMethod -Uri "http://<api>/api/v1/jobs?source_id=<id>" -WebSession $s
```

İşçi ortamı: `HF_IMPORT_CONNECTIONS` (varsayılan 4, en çok 8), `ADAPTERS_ROOT`, gerekirse `HF_TOKEN`.
`rights_status` kurucunun §8 kararından sonra `cleared` yapılır (lisans notu önerisi:
koşullu `cleared`, ticari olmayan).

## 6. Ölçümler (2026-10-13, gerçek ağ, `var/olcum-2026-10-13/task-032/`)

Dosya: `tur_Latn/000_00000.parquet` (1.068.500.812 bayt, 84.773 satır, 85 satır grubu, sıkıştırmasız).

| Koşu | Satır | İstek (dosya) | İndirilen bayt | Dosyanın payı | Süre | MB/s | Parça |
|---|---:|---:|---:|---:|---:|---:|---|
| İlk satır grubu, 1 bağlantı | 1.000 | 4 (2 altbilgi + 2) | 5.422.715 | %0,51 | 4,0 s | 1,36 | 1.649.858 bayt (`7254c444…`) |
| Tüm dosya, 1 bağlantı | 84.773 | 172 (2 + 2×85) | 270.825.687 | **%25,35** | 155 s | **1,74** | 90.623.172 bayt (`e449bdce…`) |
| Tüm dosya, 4 bağlantı | 84.773 | 172 | 270.825.687 | %25,35 | 41,7 s | **6,49** | aynı SHA (`e449bdce…`), aynı manifest (`6ee3a6b9…`) |
| Tüm dosya, 8 bağlantı | 84.773 | 172 | 270.825.687 | %25,35 | 23,2 s | **11,68** | aynı SHA, aynı manifest |

- **Embeddings indirilmedi:** indirilen bayt = okunan 12 sütunun altbilgideki parça boyutları toplamı
  (270.491.207) + altbilgi (334.480), fazladan bayt **0**. Atlanan `embeddings` 797.675.121 bayt
  (dosyanın %74,65'i). İlk satır grubunda: okunan 5.088.235, atlanan 13.274.178 bayt.
- İstekler (tüm koşu): kart 2 (yönlendirme), ağaç 1, datasets-server 1, çözümleme 1, altbilgi 2,
  satır grubu başına 2.
- Parça: indirilen baytın %33,5'i (zstd-9); metin 249.414.184 UTF-8 bayt; 84.773/84.773 belge, boş
  metin 0. datasets-server'dan 101 örnek satırla (önceki ölçüm, dosya 0'a düşenler) metin, `\n`
  sayısı (1.251), `url`, `dump`, `id`, sinyaller birebir aynı.
- **Paralel:** tek bağlantının 1,74 MB/s'si (önceki ölçüm 1,93) bağlantı başına sınır; 4 bağlantı 3,7×,
  8 bağlantı 6,7× — CDN bağlantı başına ≈ 1,5 MB/s veriyor, toplamda sınıra (429) rastlanmadı, yeniden
  deneme 0. Hub çözümlemesi dosya başına 1 istek (hub sınırı "resolvers" 3.000/5 dk; satır grubu
  istekleri CDN'e gider). 8 bağlantıda işlemci (zstd-9 yazma, ölçülmüş ≈ 12 MB/s) sınıra yakın olabilir;
  ölçülmedi. İşçi varsayılanı 4 (ofis hattını doldurmamak için); `HF_IMPORT_CONNECTIONS=8` ile 11,7 MB/s.

**Tam koşu kestirimi (105 dosya, koşulmadı):** ≈ 27,2 GB indirme (107,3 GB'ın %25,35'i), ≈ 17.400
Range isteği (105 × (2 + 2 × ~82)) + 105 çözümleme, 105 parça, ≈ 9,1 GB parça (indirilenin %33,5'i;
belge_kaydi_v1.md'deki 1.000 belgelik kestirim 9,2 GB), 8.578.808 kayıt. Süre: 1 bağlantıda
≈ 4,3 saat (1,74 MB/s); 4 bağlantıda ≈ 70 dk (6,49 MB/s); 8 bağlantıda ≈ 39 dk (11,68 MB/s) —
tek dosyadan ölçekleme, kestirim. Disk: depo ≈ 9,1 GB parça + manifest; çalışma
dizininde en çok bir parça (≈ 90 MB) + deponun geçici kopyası; ham indirme diske yazılmaz.

## 7. Sınırlar ve açık kalanlar

- Sürüm freeze/ihracatı parça kaynaklarını okumuyor (kapalı tutuldu); `releases.py`'nin
  `document_shards` ihracat yolu hazır, freeze kapılarının (yakın kopya, decontamination) parça
  okuyucusu ve `release_jobs`'un manifestten parça listesini vermesi ayrı iş.
- `derlem.canonical-sample.v1` hedefli uyarlayıcılar (talimat setleri) bu işte desteklenmiyor.
- Sıkıştırılmış JSONL (`.jsonl.gz`/`.zst`) desteklenmiyor.
- Veritabanına bağlı uçtan uca test (işçi tamamlama transaction'ı) yazılmadı; Go depo testi
  (`TestQueueHFImportCreatesSourceAndJobAtomically`) DB ile koşulmadı.
