# Gardas Seed Import

**Tarih:** 2026-06-25  
**Kaynak adi:** `gardash_faz2_tr_dedup_20260621`  
**Derlem source id:** `06ac330e-350f-45f0-b596-3dd4aa1dbc57`

## Ozet

Gardas projesindeki Turkce merkezli final dedup corpus, Derlem'in yonetilen
deposuna seed veri olarak kopyalandi. Ham veri PostgreSQL icine gomulmedi;
PostgreSQL yalnizca metadata, checksum, gate durumu ve audit kayitlarini
tutuyor. Kanonik metin dosyasi icerik adresli object store altinda saklaniyor.

## Kaynak

| Alan | Deger |
|---|---|
| Orijinal path | `C:\CELIK-GARDASH\datasets\faz2_corpus\gardash_tr_dedup.lf.txt` |
| Manifest | `C:\CELIK-GARDASH\docs\TOKENIZER_V3_8_FINAL_CORPUS_MANIFEST_FAZ2.json` |
| SHA256 | `9826d58e8e11713ab99fb3690fff75bbfa2d533490c81b1b78f5ebdd83aa07b5` |
| Boyut | `13,569,773,056` byte |
| Satir sayisi | `6,027,968` |
| Encoding | `UTF-8` |
| Content purpose | `pretrain` |

## Derlem Deposu

| Alan | Deger |
|---|---|
| Object key | `objects/sha256/98/26/9826d58e8e11713ab99fb3690fff75bbfa2d533490c81b1b78f5ebdd83aa07b5` |
| Yerel path | `C:\CELIK- DERLEM\var\storage\objects\sha256\98\26\9826d58e8e11713ab99fb3690fff75bbfa2d533490c81b1b78f5ebdd83aa07b5` |
| Immutable flag | `true` |

## Gate Durumu

Son bilinen durum:

| Gate | Durum | Not |
|---|---|---|
| Ingest | `succeeded` | Dosya kopyalandi, SHA256 dogrulandi. |
| Exact file dedup | `unique` | Ayni SHA256 ile daha eski canonical kaynak bulunmadi. |
| PII scan | `flagged` | `email=86435`, `phone=114437`, `payment_card=13830`, `iban=2087`, `tckn=665`. |
| Normalized document dedup | `duplicates_found` | `6,027,968` dokuman tarandi; `221` internal duplicate bulundu, external duplicate yok. |
| Document sampling | `not_sampled` | Normalized dedup ve PII temizlenmeden review orneklemesine gecilmez. |
| Rights/license | `license_review` | Hukuk/hak kaniti netlesmeden release'e giremez. |

Yerel, Git disi triage raporu:

- `C:\CELIK- DERLEM\var\reports\gardash_faz2_tr_dedup_20260621_06ac330e_triage.md`
- `C:\CELIK- DERLEM\var\reports\gardash_faz2_tr_dedup_20260621_06ac330e_triage.json`

## Clean Candidate Hazirligi

Ham seed degistirilmez. Temiz aday dosya, PII iceren satirlari, oversized
satirlari ve normalize fingerprint fazlaliklarini cikaran ayri bir turev olarak
uretilir.

Hizli duman testi calisti:

```powershell
.\.venv\Scripts\python.exe -m derlem_worker.clean_candidate --source-id 06ac330e-350f-45f0-b596-3dd4aa1dbc57 --output-dir .\var\derived --limit-lines 10000 --force
```

10K duman testi sonucu:

| Alan | Deger |
|---|---|
| Okunan satir | `10,000` |
| Yazilan satir | `9,995` |
| Cikarilan PII satiri | `5` |
| Cikarilan duplicate satiri | `0` |
| Cikarilan oversized satir | `0` |
| Cikti SHA256 | `f6d1e4bd17f852b887429a2684fb46b9f6b3d176ba3e23e54dac7f001ab6aa83` |

Tam corpus clean candidate komutu:

```powershell
.\.venv\Scripts\python.exe -m derlem_worker.clean_candidate --source-id 06ac330e-350f-45f0-b596-3dd4aa1dbc57 --output-dir .\var\derived
```

Tam corpus clean candidate uretildi:

| Alan | Deger |
|---|---|
| Clean candidate source id | `f63352dd-fdd1-4e4b-a8d2-b167b3c856cf` |
| Cikti dosyasi | `C:\CELIK- DERLEM\var\derived\gardash_faz2_tr_dedup_20260621_06ac330e_clean_candidate.txt` |
| Manifest | `C:\CELIK- DERLEM\var\derived\gardash_faz2_tr_dedup_20260621_06ac330e_clean_candidate.txt.manifest.json` |
| Okunan satir | `6,027,968` |
| Yazilan satir | `5,922,891` |
| Cikarilan PII satiri | `104,853` |
| Cikarilan duplicate satiri | `221` |
| Cikarilan oversized satir | `3` |
| Cikti SHA256 | `ebe292793d87ec067076bbb86f39801e6ed5fae18761dfcfa3506c4503c0d989` |
| Cikti boyutu | `12,850,383,067` byte |

Clean candidate Derlem'e ayri kaynak olarak kaydedildi ve immutable store'a
ingest edildi. Son gate durumu:

| Gate | Durum |
|---|---|
| Ingest | `succeeded` |
| PII scan | `clear` |
| Exact file dedup | `unique` |
| Normalized document dedup | `unique` |
| Document sampling | `sampled` (`200` ornek) |
| Approval status | `sampled_for_review` |

Not: Clean candidate'in parent ham Gardas kaynagiyla icerik cakismasi beklenen
bir lineage iliskisidir. Bu nedenle normalized dedup kapisi, `derived_from_source_id`
ile isaretlenen parent kaynagi external duplicate sayimindan haric tutar.
Kalan zorunlu kapilar: hak/lisans kaniti ve 200 ornegin insan review onayi.

## Karar

Bu import bir onay veya release karari degildir. Gardas corpus Derlem tarafina
yonetilen, checksum'li ve yeniden izlenebilir bir seed olarak alindi. Mevcut ham
kaynak karantinadadir; release'e girmesi icin PII bulgularinin ve internal
duplicate satirlarin temiz bir turev kaynakta cozulmesi, ardindan belge
ornekleme, hak/lisans ve insan onay kapilarinin tamamlanmasi gerekir.
