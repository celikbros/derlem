# `HuggingFaceFW/fineweb-2` (config `tur_Latn`) — lisans notu (TASK-023)

**Tarih:** 2026-09-19 · **Hazırlayan:** Derlem oturumu (Claude) · **Karar:** kurucu
Hukuki görüş değildir; şartlar okunduğu gibi kaydedilmiştir. Hiçbir veri indirilmedi.

| Alan | Değer |
|---|---|
| Veri seti | https://huggingface.co/datasets/HuggingFaceFW/fineweb-2 |
| Türkçe alt küme | config `tur_Latn` (`data/tur_Latn/train`, küçük `test`); süzülüp atılanlar ayrıca `tur_Latn_removed` |
| Sabit sürüm | repo commit `af9c13333eb981300149d5ca60a8e9d659b276b9` (son değişiklik 2025-10-27, HF API) |
| Veri kartı lisansı | `odc-by` (kart YAML) — ODC-By 1.0 |
| Üst kaynak içerik lisansı | Common Crawl kullanım şartları (kart: *"also subject to CommonCrawl's Terms of Use"*); 96 Common Crawl anlık görüntüsü, 2013 yazı – Nisan 2024 |
| Erişim | açık (gated değil) |
| Türkçe boyut (kart beyanı) | `tur_Latn`: **41.933.799.420 kelime, 95.129.129 belge, 284,52 GB UTF-8, 125,53 GB disk**. Ölçüldü (HF ağaç API): train 30 parquet = **134.789.283.815 bayt**, test 1 parquet = 52.871.101 bayt; `tur_Latn_removed` train 32 parquet = 147.301.785.437 bayt |
| Öneri `rights_status` | **`cleared` (ticari olmayan)** — mC4 ile aynı lisans sınıfı; `wiki_oscar` kararındaki kabuller (atıf + Common Crawl tazmin maddesi) buraya da yazılı olarak uygulanmalı |
| Ana korpusta zaten var mı? | **Hayır (doğrudan).** Ana korpusta FineWeb-2 kaydı yok. Dolaylı: aynı Common Crawl kökeni; mC4-tr'deki sayfalarla içerik örtüşmesi olası, oranı ölçülmedi (TASK-024 pilotu). |

## Okunan lisans metni (alıntılar)

- Kart YAML: `license: odc-by`.
- Kart "Licensing Information" (README, okundu 2026-09-19): *"The dataset is released under the
  Open Data Commons Attribution License (ODC-By) v1.0 license. The use of this dataset is also
  subject to CommonCrawl's Terms of Use."*
- Kart: *"The data was sourced from 96 CommonCrawl snapshots, spanning the summer of 2013 to
  April 2024, and processed using datatrove"*; *"primarily intended to be used as a research
  artifact on public data in the context of pretraining datasets for large language models."*
- Kart "Personal and Sensitive Information and opt-out": *"We anonymize email addresses and
  public IP addresses."* … *"If you find your own PII in FineWeb2 and would like it removed,
  please fill out our PII removal/opt out form."* … *"CommonCrawl respects robots.txt at crawl
  time, but if you are a webmaster and find your website in FineWeb2 and would like to have it
  removed, you may also use the PII removal/opt out form."*
- Kart tablosu başlığı: `ISO 639-3 | Script | Name | Language Family | Subset | Words |
  Documents | UTF-8 Bytes | Disk size`; Türkçe satırı: `tur | Latn | Turkish | Turkic |
  tur_Latn | 41,933,799,420 | 95,129,129 | 284.52GB | 125.53GB`.
- ODC-BY 1.0 ve Common Crawl kullanım şartları: alıntılar [hf-allenai-c4.md](hf-allenai-c4.md)
  notunda (atıf notu §4.2/4.3; share-alike yok; Common Crawl: üçüncü taraf telifine saygı,
  yapay zekâ/LLM kullanımında tazmin, ticari kullanımda hukuk danışmanı önerisi).

## Yükümlülükler (metinden)

| Yükümlülük | Durum |
|---|---|
| Atıf | **Zorunlu** (ODC-BY): lisans/URI ve "içerik HuggingFaceFW/fineweb-2'den alınmıştır" notu — veri kartında ve model künyesinde; kart ayrıca makale atfı ister (Penedo vd. 2025, arXiv:2506.20920). |
| Share-alike | Yok. |
| Yeniden dağıtım | ODC-BY izin verir (atıfla); Derlem ham metni yeniden dağıtmıyor. |
| Tazmin | **Var** — Common Crawl şartları. |
| Üçüncü taraf telifi / opt-out | Common Crawl şartlarıyla kullanıcıda; yayıncı PII/site kaldırma formu işletiyor — Derlem aynı kaldırma taleplerini kendi takedown yoluna bağlamalı. |
| Ticari kullanım | ODC-BY izin verir; Common Crawl hukuk danışmanı önerir. Derlem kapsamı ticari değil. |
| Erişim şartı | Yok. |

## Ne demek

Hak konumu mC4 ile **aynı sınıfta** (ODC-BY + Common Crawl şartları), yani kurucunun
`wiki_oscar` için verdiği S2 kararı bir kalemle buraya genişletilebilir. Hacim: 284,52 GB UTF-8
Türkçe metin — raf çevrimiyle (5,405 bayt/token) kaba **~53 B token**; kart 41,9 B kelime diyor.
Ana korpusun tamamı ~2,3 B token; yani tek başına hedefin çok üstünde. Kart, veri setinin Türkçe
dâhil 9 dilde mC4, CulturaX ve HPLT'ye karşı ablasyonlarla sınandığını söylüyor; süzme kriterleri
kamuya açık ve yeniden üretilebilir (pipeline GitHub'da). Sabit sürüm net (`af9c133…`, parquet
depoda). Beklenen net yeni token / lisans riski oranı listede **en yüksek**.

## Kaynaklar

- https://huggingface.co/datasets/HuggingFaceFW/fineweb-2
- https://huggingface.co/datasets/HuggingFaceFW/fineweb-2/raw/main/README.md
- https://huggingface.co/api/datasets/HuggingFaceFW/fineweb-2 (commit sha)
- https://huggingface.co/api/datasets/HuggingFaceFW/fineweb-2/tree/main/data/tur_Latn/train (parquet boyutları)
- https://datasets-server.huggingface.co/size?dataset=HuggingFaceFW/fineweb-2&config=tur_Latn (2026-09-19'da zaman aşımı; kart ve ağaç sayıları kullanıldı)
- https://opendatacommons.org/licenses/by/1-0/
- https://commoncrawl.org/terms-of-use
- https://github.com/huggingface/fineweb-2/blob/main/fineweb2-language-distribution.csv (kartın yönlendirdiği tam liste; ayrıca okunmadı)

Erişim tarihi: 2026-09-19
