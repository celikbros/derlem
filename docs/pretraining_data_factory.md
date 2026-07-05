# Pretraining Data Factory

Bu belge, Turkce Veri Atolyesi'nin LLM ve tokenizer ekiplerine buyuk, izlenebilir ve dondurulebilir corpus uretmesi icin teknik omurgayi tanimlar.

## Karar

Ham ve temizlenmis buyuk metin dosyalari PostgreSQL icine konmaz. Veri atolyeleri icin pratik ayrim:

- **Object storage / filesystem:** ham dosya, temiz JSONL, canonical TXT, release export paketleri.
- **PostgreSQL:** kaynak katalogu, lisans/izin, kalite sinyali, onay durumu, denetim izi, release manifest metadata'si.
- **Git:** kod, sema, kucuk manifest, runbook ve raporlar.

Tek makine/pilot icin local filesystem yeterli olabilir. Ekip ve veri buyuyunce MinIO/S3 uyumlu object storage'a gecilir. DVC kucuk/orta Git merkezli veri surumleme icin, lakeFS ise object storage uzerinde branch/commit/merge semantigi gerektiginde degerlendirilir.

Mevcut `C:\CELIKBROS PROJECTS\gardash` v3.8 Faz 2 corpus release'i degistirilmez. Yeni kaynaklar geldiginde mevcut manifest uzerine yazilmaz; `v3.9`, `v4` veya yeni tarihli bir frozen release uretilir.

## Iki Ayri Yasam Dongusu

Buyuk pretraining corpus'u ile insan katkisi ayni onay modelini kullanmaz.

Corpus factory hatti:

```text
source_registered
  -> license_review
  -> raw_ingested
  -> extracted
  -> auto_cleaned
  -> deduped
  -> audited_sampled
  -> approved_source_or_shard
  -> freeze_candidate
  -> frozen_release
```

Human data workshop hatti:

```text
submitted
  -> auto_filter
  -> human_review
  -> expert_review_or_sensitive
  -> approved
  -> export
```

Web-scale corpus'ta her dokumani insan incelemesinden gecirmek gercekci degildir. Burada kaynak veya shard bazli onay, stratified ornek denetimi ve otomatik kalite kapilari kullanilir. Insan katkisi, instruction, preference, answer review ve eval verisinde kayit bazli incelenir.

## Veri Katmanlari

1. `raw_sources`
   - Orijinal veri degismeden saklanir.
   - Lisans, kaynak, tarih, checksum, dil/domain tahmini ve PII riski kaydedilir.

2. `normalized_sources`
   - Encoding, satir sonu, bosluk, bozuk OCR/HTML temizligi ve format donusumu uygulanir.
   - Normalizasyon politikasi kayit altina alinir. Tokenizer ekibi onayi olmadan Unicode/agresif normalizasyon yapilmaz.

3. `clean_corpus_candidates`
   - Dil tespiti, kalite filtresi, PII tarama, exact dedup ve gerekirse near-dedup sonrasi aday veri.
   - Her aday parca kaynak ve islem gecmisiyle izlenebilir kalir.

4. `approved_corpus`
   - Otomatik gate'leri gecmis ve insan/uzman tarafindan onaylanmis veri.
   - LLM pretraining, tokenizer retrain veya eval/holdout ayrimi burada yapilir.

5. `pretraining_releases`
   - Dondurulmus corpus surumu.
   - `final_corpus_manifest.json`, canonical one-document-per-line text view, dedup raporu, mixture raporu, checksum ve gate raporlari birlikte saklanir.

## Release Yasam Dongusu

```text
source_registered
  -> license_review
  -> raw_ingested
  -> normalized
  -> auto_filtered
  -> pii_checked
  -> deduped
  -> sampled_for_human_review
  -> approved
  -> release_candidate
  -> frozen_release
```

Her gecis bir run id, arac surumu, zaman damgasi, operator ve rapor path'i uretmelidir.

## LLM ve Tokenizer Ekiplerine Teslim

Mevcut `C:\CELIKBROS PROJECTS\gardash` ve `C:\TURKCE-TOKENIZER` disiplininden devam edilmeli:

- Corpus release, `v3.8-final-corpus-manifest-1` benzeri makine-okunur manifest ile gelir.
- Manifest en az sunlari tasir: frozen path, format, line count, raw bytes, sha256, dedup status, mixture, normalization policy, tokenizer registry, document-boundary karari.
- Atolye LLM veya tokenizer pipeline'i calistirmaz; yalnizca veriyi ve raporlarini teslim eder.
- Tokenizer ekibi kendi tarafinda preflight/retrain kararini verir.
- LLM ekibi kendi tarafinda tokenization/training paketini uretir veya tokenizer ekibinden alir.
- Atolye kaynaklari mixture icinde ayri gorunur: `atolye_clean_tr_text`, `atolye_instruction`, `atolye_eval_holdout` gibi. Base pretraining'e yalnizca uygun havuzlar girer; preference, hidden eval ve post-training verisi ayridir.

## Kalite Kapilari

Minimum otomatik kapilar:

- Encoding/UTF-8 okunabilirlik
- Dil tespiti ve Turkce orani
- Exact duplicate oranlari
- Near-duplicate raporu. Kucuk/veri-dar release'lerde bilincli erteleme kabul edilebilir; buyuk yeni corpus release'lerinde MinHash/SimHash benzeri near-dedup gate varsayilan olmalidir.
- PII/sensitive tarama
- Kaynak/lisans uygunlugu
- Bozuk OCR, mojibake, HTML/artifact orani
- Uzunluk dagilimi ve cok kisa/cok uzun dokuman filtreleri
- Eval/holdout sizinti kontrolu
- LLM/tokenizer ekiplerinin kullanabilecegi canonical export ve checksum tutarliligi
- LF canonical export kontrolu: bir dokuman = bir satir, ic newline bosluk veya kontrollu ayiraca cevrilir.

## Metadata Alanlari

Her kaynak parcasi icin minimum alanlar:

- `source_id`, `source_name`, `source_type`
- `language`, `language_confidence`, `script`, `domain`, `genre`
- `license`, `rights_status`, `usage_permission`, `redistribution_allowed`
- `raw_path`, `normalized_path`, `approved_path`
- `raw_bytes`, `document_count`, `sha256`
- `pii_risk`, `copyright_risk`, `sensitive_domain`
- `dedup_group`, `dedup_method`, `dedup_report_path`
- `quality_score`, `review_status`, `reviewer`
- `train_allowed`, `eval_allowed`, `tokenizer_allowed`
- `split`: train, validation, hidden_eval, holdout veya post_training

## Pilot Uygulama

Ilk teknik MVP:

- Go core API
- Python data workers
- PostgreSQL metadata DB
- Local filesystem veya MinIO object store
- MVP'de PostgreSQL job queue; olculmus ihtiyacta Redis Streams
- JSONL/TXT export
- Basit admin/moderator UI
- `schemas/source_dataset.schema.json` ve `schemas/corpus_release.schema.json` validasyonu

Ilk is:

1. Mevcut Faz 2 corpus'u `pretraining_releases` kaydi olarak iceri almak.
2. Yeni kaynaklar icin `source_registered -> raw_ingested -> normalized -> deduped` akisini calistirmak.
3. 10-50 GB yeni veriyle release candidate uretmek.
4. LLM/tokenizer ekiplerine manifest, canonical text export ve kalite raporlari teslim etmek.
