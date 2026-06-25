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
| Yerel path | `C:\TURKCE-VERI-ATOLYESI\var\storage\objects\sha256\98\26\9826d58e8e11713ab99fb3690fff75bbfa2d533490c81b1b78f5ebdd83aa07b5` |
| Immutable flag | `true` |

## Gate Durumu

Son bilinen durum:

| Gate | Durum | Not |
|---|---|---|
| Ingest | `succeeded` | Dosya kopyalandi, SHA256 dogrulandi. |
| Exact file dedup | `unique` | Ayni SHA256 ile daha eski canonical kaynak bulunmadi. |
| PII scan | `running` | 13.6 GB dosya uzerinde satir satir tarama devam ediyor. |
| Normalized document dedup | `running` | Belge parmak izi indeksleme devam ediyor. |
| Document sampling | `not_sampled` | Normalized dedup tamamlanmadan calismaz. |
| Rights/license | `license_review` | Hukuk/hak kaniti netlesmeden release'e giremez. |

## Karar

Bu import bir onay veya release karari degildir. Gardas corpus Derlem tarafina
yonetilen, checksum'li ve yeniden izlenebilir bir seed olarak alindi. Release'e
girmesi icin PII, normalized dedup, belge ornekleme, hak/lisans ve insan onay
kapilarinin tamamlanmasi gerekir.
