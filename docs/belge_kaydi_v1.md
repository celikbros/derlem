# Ortak belge kaydı `derlem.document.v1`, karar kaydı `derlem.decision.v1`, seçim listesi, uyarlayıcı

**Tarih:** 2026-10-13 · **Kart:** [TASK-044](gorevler/TASK-044-common-document-record-and-source-adapters.md) ·
**Tasarım:** [veri_mimarisi_2026_10.md](veri_mimarisi_2026_10.md) §2.1–2.4, 2.6 ·
**Durum:** uygulandı; **alan listesi kurucunun tek satırlık "ok"unu bekliyor** (kartın "Owner actions" bölümü).
**Kod:** `worker/src/derlem_worker/document_record.py`, `adapters.py`, `selection.py`;
uyarlayıcılar `adapters/*.yaml`. Talimat verisi şeması (`derlem.canonical-sample.v1`,
`canonical.py`) değişmedi; bu kayıt onun yanındadır.

## Sürüm sabitleri

| Sabit | Değer | Nerede |
|---|---|---|
| Belge şeması | `derlem.document.v1` | `DOCUMENT_SCHEMA_VERSION`; Parquet altbilgisinde `derlem.schema` anahtarı |
| Karar şeması | `derlem.decision.v1` | `DECISION_SCHEMA_VERSION` |
| Seçim listesi şeması | `derlem.selection.v1` | `SELECTION_SCHEMA_VERSION` |
| Seçim manifesti | `derlem.selection-manifest.v1` | `selection.py` |
| Parça yazıcı | pyarrow **25.0.1** (`parquet-cpp-arrow version 25.0.1`), zstd seviye 9, Parquet 2.6 | `SHARD_WRITER_PYARROW_VERSION`, `worker/pyproject.toml` (tam sürüm) |

Şema değişikliği yeni sürüm adıdır (`…v2`); v1 dosyaları okunmaya devam eder.

## 1. `derlem.document.v1` — bir belge = bir Parquet satırı

| Alan | Arrow tipi | Boş olabilir | Anlam | Kim doldurur |
|---|---|---|---|---|
| `doc_id` | string | hayır | Metnin UTF-8 baytlarının SHA256'sı (64 küçük hex). Yazıcı ve ihracat yeniden hesaplar; tutmazsa reddeder | hesaplanır |
| `text` | large_string | hayır | Belge metni, **asla yeniden yazılmaz**: paragraf sonları (`\n`, `\n\n`), baş/son boşluk dahil. Boş ya da yalnız boşluk metin belge olmaz (uyarlayıcı sayar ve raporlar) | uyarlayıcı |
| `source_id` | string | evet | Derlem kaynak kimliği. Alımda (TASK-032) null bırakılabilir: içerik adresli parçanın SHA'sı kaynak kaydından bağımsız kalsın diye; kimlik manifestte ve veritabanında | alım |
| `source_ordinal` | int64 | hayır | Kaynak içindeki kayıt sırası, 1'den, parça dizisinde kesin artan. Boş/geçersiz kayıt da numara tüketir: boşluk raporda görünen kayıttır | alım |
| `provenance.dataset` | string | evet | Veri seti adı (`epfml/FineWeb2-HQ`; Faz-2'de kaynak adı) | uyarlayıcı (sabit) |
| `provenance.revision` | string | evet | Sabit sürüm (HF commit SHA'sı; yerel arşivde SHA256SUMS'un SHA'sı; Faz-2'de ana nesnenin SHA'sı) | uyarlayıcı (sabit) |
| `provenance.file` | string | evet | Kaynak dosya (veri setindeki yol) | alım |
| `provenance.row` | int64 | evet | Dosya içindeki satır (0'dan) | alım |
| `provenance.external_id` | string | evet | Onların kimliği (`<urn:uuid:…>`) | uyarlayıcı (`map`) |
| `provenance.url` | string | evet | Adres; Faz-2'de yok (hiç olmadı) | uyarlayıcı |
| `provenance.crawl_date` | string | evet | Tarama tarihi, kaynaktaki biçimiyle | uyarlayıcı |
| `provenance.dump` | string | evet | Döküm (`CC-MAIN-2017-47`) | uyarlayıcı |
| `language.declared` | string | evet | Kaynağın beyanı, olduğu gibi (`tur`, `tr`) | uyarlayıcı (`map` ya da `constants`) |
| `language.detected` | string | evet | Derlem'in ölçtüğü dil (fastText, TASK-028) | kapı (sonra) |
| `language.score` | float64 | evet | Dil puanı | uyarlayıcı / kapı |
| `signals` | map<string, float64> | hayır (boş olabilir) | **Puanlayıcı adı → değer.** Anahtar puanın kime ait olduğunu söyler (`fineweb2-hq-xlmr-mlp`, `minhash_cluster_size`). Değer yoksa anahtar yazılmaz (yokluk ≠ 0) ve raporda `missing_signal_values` sayılır | uyarlayıcı + kapılar |
| `rights.license_id` | string | evet | Lisans kimliği | kaynak kaydı / uyarlayıcı `constants` |
| `rights.evidence_ref` | string | evet | Kanıt referansı (`docs/haklar/…`) | kaynak kaydı |
| `rights.scope` | string | evet | Kapsam (ör. ticari olmayan) | kaynak kaydı |
| `extra` | string (JSON) | evet | Eşlenmeyen sütunlar: sıralı anahtarlı, kompakt JSON nesnesi; hiç yoksa null. **Atılmaz** | uyarlayıcı |

Gruplar (`provenance`, `language`, `rights`) her zaman vardır; alt alanları null olabilir.

**Örnek** (FineWeb2-HQ örneğinin ilk satırı, uyarlayıcıdan geçmiş; metin ve `extra` kısaltıldı):

```json
{
  "doc_id": "f20ed3b5dac1abc179f7ebf0d6e5c673076665f18dc0ce91d827f7513f8a88a4",
  "text": "Birçoğumuz buğday tenliyiz ve sarı tonlarından kaçınıyoruz oysa her ten rengine uygun bir sarı tonu mevcut. …",
  "source_id": null,
  "source_ordinal": 1,
  "provenance": {
    "dataset": "epfml/FineWeb2-HQ",
    "revision": "c0c06e94fd3a44ae9e802b2b0fc533817601eb5e",
    "file": "tur_Latn/000_00000.parquet",
    "row": 0,
    "external_id": "<urn:uuid:753318ff-5fa4-4358-93b1-2f59b74fdde5>",
    "url": "http://sacsirlari.com/yazi/her-cilt-tonuna-uygun-sari-saclar",
    "crawl_date": "2017-11-20T19:13:53Z",
    "dump": "CC-MAIN-2017-47"
  },
  "language": {"declared": "tur", "detected": null, "score": 0.9999247789382935},
  "signals": {"fineweb2-hq-xlmr-mlp": 0.03320292755961418, "minhash_cluster_size": 4.0},
  "rights": {"license_id": null, "evidence_ref": null, "scope": null},
  "extra": "{\"file_path\":\"s3://commoncrawl/crawl-data/CC-MAIN-2017-47/…\",\"language_script\":\"Latn\",\"top_langs\":\"{\\\"tur_Latn_score\\\": 0.99992…}\"}"
}
```

## 2. `derlem.decision.v1` — her hüküm bir satır, metinden ayrı

| Alan | Arrow tipi | Boş olabilir | Anlam |
|---|---|---|---|
| `doc_id` | string | hayır | Hükmün belgesi |
| `source_ordinal` | int64 | evet | **Kartta yoktu, eklendi:** aynı metin bir kaynakta birden çok kez geçebilir (birebir kopya). Hüküm o geçişe aitse sıra numarası; belge düzeyi hükümde null |
| `decision_type` | string | hayır | `pii`, `duplicate`, `near_duplicate`, `quality_rule`, `language`, `rights_scope`, `held_out`, `jury`, `human_review` + iki mekanik tür: `oversized`, `empty_text` |
| `verdict` | string | hayır | `pass` · `reject` (eğitim seçimine girmez) · `held_out` (değerlendirme bölmesine ayrıldı) · `flag` (hüküm değil işaret, ör. jüri "şüpheli") |
| `reason` | string | evet | Gerekçe kodu (`email`, `navigation_boilerplate,repeated_segments`, `source_not_in_scope_s2`, `normalized_duplicate_of=1234`) — kişisel veri taşımaz |
| `judge` | string | hayır | Kim/ne verdi: kural sürümü (`tr-web-v3`), yöntem (`normalized-word-3gram-simhash64-v1-hamming3`), model+ölçüt, kullanıcı |
| `run_id` | string | hayır | Koşu kimliği |
| `decided_at` | timestamp(µs, UTC) | hayır | Koşunun başlangıç zamanı (koşudaki bütün satırlar için tek değer) |

Bilinmeyen karar türü ya da hüküm yazıcıda reddedilir. Kararlar PostgreSQL'e girmez (Parquet;
özetler sonraki kartta).

## 3. Seçim listesi `derlem.selection.v1` ve manifesti

| Alan | Tip | Anlam |
|---|---|---|
| `source_ordinal` | int64 | Ana kaynaktaki (parent) satır/kayıt numarası, kesin artan |
| `doc_id` | string | O satırın SHA256'sı — materialize her satırda yeniden hesaplar |
| `partition` | string | `train` ya da `held_out` |

Manifest (`<ad>.selection.manifest.json`, `derlem.selection-manifest.v1`): ana kaynağın yolu, SHA'sı ve
boyutu; `max_document_bytes`; seçim dosyasının ve karar dosyasının SHA/boyut/satır sayısı; bölme
sayıları; karar türü sayıları; `run_id`, `decided_at`; sınırı aşan satırların sıra numaraları
(`oversized_ordinals` — metni okunmadığı için `doc_id`'leri yok); **`expected_materialization`**
(her bölme için metin-kopyanın SHA'sı, bayt ve satır sayısı) ve koşunun tam `clean_candidate`
raporu. Karar dosyası "seçilmeyen her belgeyi" kapsar: seçim ∪ kararlar ∪ `oversized_ordinals`
= ana kaynağın bütün satırları (test edilir).

## 4. Parquet parçaları

- **Yazıcı:** `DocumentShardWriter` — ~100.000 belge/parça (`DEFAULT_ROWS_PER_SHARD`), parça içinde
  10.000 satırlık satır grupları; `cut()` o anki parçayı kapatır (TASK-032: bir kaynak dosya = bir
  parça). Parçalar `part-00000.parquet` … sırasıyla, hedefin yanındaki geçici dosyaya yazılır,
  başarıda yerine konur; hata/iptalde yarım dosya kalmaz.
- **Ayarlar:** zstd seviye 9, Parquet 2.6, sayfa sağlama toplamı açık, Arrow şeması altbilgide;
  sözlük kodlaması yalnız düşük kardinaliteli sütunlarda (kaynak, döküm, dil, sinyal adları, haklar);
  istatistik yalnız sayısal/sıralanabilir üstveride (metin ve kimliklerde yok).
- **Belirlenimcilik:** aynı kayıtlar aynı sırayla → aynı bayt → aynı SHA. Parquet altbilgisinde zaman
  damgası yoktur; anahtar-değer üstverisi yalnız `ARROW:schema` ve `derlem.schema`'dır. Tek oynak
  alan yazıcı sürümünü taşıyan `created_by`'dır; bu yüzden pyarrow **tam sürümle** sabitlenmiştir
  (`pyarrow==25.0.1`) ve yazıcı başka sürümle yazmayı reddeder. `signals` haritası anahtara göre
  sıralı yazılır. **Ölçüldü:** 100k dilimin parçası Python 3.14.6 ve 3.13.15'te, her birinde iki
  ayrı koşuda aynı SHA (`2d7a6278…`); testte iki ayrı süreç + süreç içi aynı SHA.
- **Nesne deposu:** parça sıradan bir nesnedir — `publish_parquet(store, info)` →
  `ContentAddressedStore.ingest_raw_file` (ikili yol), `objects/sha256/aa/bb/<sha>`; yayımlanan SHA
  yazılanla karşılaştırılır.
- **Okuma:** `read_documents(path, columns=[…])` sütun projeksiyonuyla akıtır (yalnız istenen sütun
  okunur); `read_decisions`, `read_selection` aynı yol. Yanlış şemalı dosya (`derlem.schema` tutmaz)
  reddedilir.

## 5. Uyarlayıcı sözleşmesi (`adapters/<ad>.yaml`)

| Anahtar | Zorunlu | Anlam |
|---|---|---|
| `dataset`, `revision` | evet | Kaynak kimliği ve sabit sürümü (yaml'da tırnaklı dizge) |
| `config`, `split` | hayır | HF yapılandırması / bölmesi |
| `format` | evet | `parquet` · `jsonl` · `tsv` (başlık satırlı, `excel-tab`; boş hücre = null) |
| `target` | hayır | `derlem.document.v1` (varsayılan) ya da `derlem.canonical-sample.v1` (talimat setleri, geçiş) |
| `columns_read` | evet | Okunacak sütunlar = `map`'te eşlenenler + `extra`. Biri kaynakta yoksa **alım başlamaz** |
| `columns_skipped` | hayır | Bilerek okunmayan sütunlar (ör. `embeddings`); okunanlarla kesişemez |
| `map` | evet (belge) | Hedef alan → sütun. Hedefler: `text` (zorunlu), `provenance.{external_id,url,crawl_date,dump}`, `language.{declared,detected,score}`, `rights.*`, `signals.<ad>` (sütun adı ya da `{value: sütun, scorer: ad}`; harita anahtarı `scorer`) |
| `constants` | hayır | Kaynak düzeyi sabitler (ör. `language.declared: tr`, `rights.license_id`) |
| `extra` | hayır | Eşlenmeyip `extra` JSON'una giden sütunlar |
| `content_purpose` | yalnız canonical | Talimat kaydının beklenen amacı |
| `document_boundary` | evet | Yalnız `record`: bir kayıt = bir belge, asla bölünmez ([belge_sinirlari_politikasi.md](belge_sinirlari_politikasi.md) §4) |

Statik doğrulama (`load_adapter`): bilinmeyen anahtar, eşlenmeyen `text`, `columns_read` dışında
eşlenen sütun, okunup kullanılmayan sütun, hem eşlenen hem `extra` sütun, hem eşlenen hem sabit alan,
alımın doldurduğu alanı (`provenance.dataset/revision/file/row`) eşleme, `record` dışı sınır → ret.

Veri doğrulaması: Parquet ve TSV'de sütun kümesi okumadan önce (altbilgi / başlık) denetlenir;
JSONL'de kayıt başına (eksik sütunlu kayıt alımı durdurur). **Adı geçmeyen sütun atılmaz:** `extra`'ya
gider ve raporda `unlisted_columns` olarak listelenir; okumamak için `columns_skipped`'e açıkça
yazmak gerekir. Tip hatası (metin dizge değil, sinyal sayı değil) kaydı `invalid_records`'a yazar.

**Rapor** (`AdapterReport.to_dict()`): `records_seen`, `documents`, `blank_lines`, `empty_text` +
ilk 100 sıra numarası, `oversized` + sıra numaraları, `invalid_records` + örnekler, `skipped_columns`,
`unlisted_columns`, `missing_signal_values`, `ok`. Değişmez: `records_seen = documents + empty_text +
invalid_records (+ oversized)` — hiçbir şey sessizce düşmez.

**Üç uyarlayıcı:** `epfml-fineweb2-hq.yaml` (parquet; 12 sütun okunur, `embeddings` atlanır),
`faz2-raw-jsonl.yaml` (ham arşivin `{"text","source"}` kayıtları; `source` etiketi `extra`'da),
`derlem-canonical-sample.yaml` (talimat kaydı olduğu gibi: satır bayt bayt taşınır, her kayıt
`canonical.py` ile doğrulanır; geçersiz/canonical olmayan kayıt sayılır).

**TASK-032 bu arayüzü şöyle kullanır:** `load_adapter` → uzak Parquet altbilgisinden sütun adları →
`adapter.plan_columns(names)` (eksik sütunda ret; `plan.read` = Range ile okunacak sütunlar) →
satır grubu satırları `(satır_no, sözlük)` → `adapt_rows(adapter, rows, plan=…, report=…,
file_label=…, first_ordinal=…)` → `DocumentShardWriter.add` / `cut()` → `publish_parquet`.

## 6. Seçim listesiyle türetme

```text
python -m derlem_worker.clean_candidate --input-path P --output-path X.txt <v5 seçenekleri> --selection-list
    → X.selection.parquet + X.decisions.parquet + X.selection.manifest.json  (X.txt yazılmaz)
python -m derlem_worker.selection materialize --manifest X.selection.manifest.json [--output O.txt] [--held-out-output H.txt] [--verify-parent]
python -m derlem_worker.selection from-text-copy --parent P --train v5.txt --held-out v5_heldout.txt --output-dir D --name N --max-document-bytes 262144
```

- Seçim koşusunun karar mantığı metin-kopya koşusunun **aynı kodudur** (`derive_clean_candidate`);
  fark yalnız çıktı ucunda: metin diske yazılmaz, SHA'sı hesaplanır, her karar karar dosyasına
  gider. Metin-kopya modu (v1–v5) değişmedi.
- `materialize` korumaları: seçim dosyasının SHA'sı manifestle aynı; seçilen her satırın SHA256'sı
  `doc_id` ile aynı; sıra numaraları artan ve ana kaynakta var; üretilen metnin SHA'sı ve boyutu
  `expected_materialization` ile aynı. Biri tutmazsa çıktı yayımlanmaz (geçici dosya silinir).
  `--output` verilmezse yalnız SHA hesaplanır, diske metin yazılmaz.
- `from-text-copy`: var olan bir metin-kopya türevi ana kaynağın sıralı alt dizisidir; tek geçişte
  seçim listesine çevrilir. Karar anlık görüntüsü bu yolda yoktur (kararlar eski koşunun raporunda).

### 6.1 Parçalı kaynaktan (TASK-049)

Ana kaynak bir alım manifestiyse (`derlem.import-manifest.v1`; `--source-id` ile yapılandırılmış
depo, `--input-path` ile `--store-root`), `clean_candidate` belgeleri parça sırasında okur ve her
belgeyi **aday satırına** çevirir (`import_manifest.CANDIDATE_LINE_FORMAT` =
`derlem.candidate-line.v1`): `{"text": …, "url": provenance.url}`, sıralı anahtar, kompakt JSON,
UTF-8 kaçışsız, LF. Paragraf sonları JSON kaçışıyla korunur; satır okuyucuları `text`'i aynen
geri verir. `url` satırdadır çünkü `tr-web-v4` onu okur — aynı belgeler bu biçimde JSONL'e
yazılıp satır satır okununca seçim listesi, karar dosyası ve beklenen SHA'lar **bayt bayt
aynıdır** (test: `test_clean_candidate_shards.py`; 200k dilim ölçümü kartta). Common Crawl
kimliği satırda **yok**: PII kapısı satırın tamamını tarar ve uuid'nin rakam grupları
telefon/kart desenine uyuyor (ilk 30.000 belgede %0,46 yanlış isabet); kimlik sıra
numarasından bulunur.

- Karar yolu satır okuyucusunun aynı döngüsüdür; sıra numarası belgenin `source_ordinal`'ı;
  sınır aşımı satırın LF dahil baytına uygulanır (satır dosyasındaki gibi); `doc_id` aday
  satırının SHA256'sıdır (ortak kaydın metin-SHA'sı değil); held-out kuralı aday satırına uygulanır.
- PII: JSON kaydı satırlarında satırla birlikte **metin de** taranır (satırda `\n` kaçışlı;
  iki satıra bölünmüş bir numara yalnız metinde görünür). Düz metin satırında metin = satır:
  v1–v5 üretimleri değişmez (v5 ana nesnesinde metni satırdan farklı okunan satır: 0,
  `var/olcum-2026-10-13/task-049/olcum-v5-json-satir.json`).
- Seçim manifestinin `parent` bölümü `kind: import_manifest`, satır biçimi, depo kökü ve okunan
  parçaların listesini (SHA, boyut, satır, sıra aralığı) taşır; `materialize` aynı parçaları
  (her biri SHA256 ile doğrulanarak) okur, liste alım manifestiyle tutmazsa durur. Manifestte
  `policies` (yargıç kimlikleri) ve `report.machine_translation_target` (A/B) durur.
- `--decided-at` (saat dilimli ISO) ve `--run-id` birlikte verilirse karar dosyası yeniden
  üretilebilir; `--limit-lines` seçim kipinde yalnız parçalı kaynakta (ölçüm dilimi) kabul edilir
  ve manifestte `document_limit` olarak durur.

## 7. Ölçümler (2026-10-13; `var/olcum-2026-10-13/task-044/`)

| Ölçüm | Sonuç |
|---|---|
| 100k dilim → belge parçası (`dilim-100k_v3.txt`, 202.923.864 bayt, 99.007 satır) | zstd-9: **70.516.336 bayt = ham baytın %34,75'i**; yazma 17,0 s (11,9 MB/s, 5.810 belge/s). zstd-3: %38,6, 31 MB/s. zstd-19: %31,9, 1,4 MB/s |
| Okuma (zstd-9 parça) | bütün sütunlar 1,72 s (118 MB/s ham eşdeğeri, 57 bin belge/s); yalnız `text` 1,18 s; yalnız `doc_id`+sıra 0,086 s (1,16 milyon belge/s); Arrow tablosu olarak `text` 0,76 s |
| Gidiş-dönüş | 99.007 metnin 99.007'si dilimdeki satırla birebir |
| Ana korpus kestirimi (13.569.773.056 bayt, 6.027.968 satır) | ≈ **4,7 GB** Parquet (zstd-9), 61 parça, yazma ≈ 19 dk, tam okuma ≈ 2 dk, `doc_id` taraması ≈ 6 s. **Koşulmadı** |
| FineWeb2-HQ örneği (1.000 satır, 12 sütun) | 1.000/1.000 belge, 923 belgede `\n` — metin ve paragraf sonları birebir; parça **ham metin+üstverinin %31,2'si** (uncompressed 12 sütunlu Parquet'in %34,0'ı). Tam veri seti kestirimi ≈ 27,2 GB → ≈ **9,2 GB** (tasarımdaki 12–15 GB kestiriminden düşük; 1.000 belgelik küçük parçada ölçüldü) |
| Seçim listesi = metin kopyası, 100k dilim, v5 ayarları | metin kopyası `e69dd953…` (191.889.947 bayt, 73.230 satır) = materialize çıktısı, bayt bayt; seçim + karar dosyası metin kopyasının %1,9'u |
| Metin-kopya modu değişmedi | TASK-044 öncesi `clean_candidate.py` aynı dilim ve ayarlarla aynı SHA'yı verir (`e69dd953…`) |
| **v5 = ana nesne + seçim listesi** (tam korpus, yalnız hash) | materialize SHA **`9dc5d6f7…aefd33` = v5 nesnesi**, held-out `de48eabb…` = v5 held-out; 4.327.374 + 1.651 satır; seçim listesi 160.110.427 bayt (v5 metninin %1,40'ı); kurma 171 s, materialize 121 s |

## Sınırlar

- `decided_at` ve `run_id` koşuya özgüdür: karar dosyasının SHA'sı koşudan koşuya değişir (seçim
  dosyası değişmez). Aynı kararı yeniden üretmek gerekirse ikisi parametreyle verilir.
- Sınırı aşan satırın (`max_document_bytes`) `doc_id`'si yoktur; karar dosyasına değil manifeste girer.
- Seçim listesinden ihracat (`releases.py`'nin seçim listesini doğrudan okuması) bu kartta yok:
  bugün `materialize` metni üretir, sürüm o nesneden ihraç edilir.
- FineWeb2-HQ oranı 1.000 belgede ölçüldü; ilk gerçek alım (TASK-032) 100.000 belgelik parçalarda ölçer.
