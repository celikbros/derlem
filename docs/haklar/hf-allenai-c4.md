# `allenai/c4` (mC4, config `tr`) — lisans notu (TASK-023)

**Tarih:** 2026-09-19 · **Hazırlayan:** Derlem oturumu (Claude) · **Karar:** kurucu
Hukuki görüş değildir; şartlar okunduğu gibi kaydedilmiştir. Hiçbir veri indirilmedi.

| Alan | Değer |
|---|---|
| Veri seti | https://huggingface.co/datasets/allenai/c4 |
| Türkçe alt küme | config `tr` (mC4, `multilingual/c4-tr.tfrecord-XXXXX-of-01024.json.gz`) |
| Sabit sürüm | repo commit `1588ec454efa1a09f29cd18ddd04fe05fc8653a2` (son değişiklik 2024-01-09, HF API) |
| Veri kartı lisansı | `odc-by` (kart YAML) |
| Üst kaynak içerik lisansı | Common Crawl kullanım şartları (kart: *"you are also bound by the Common Crawl terms of use"*); sayfa sahiplerinin telifi saklı |
| Erişim | açık (gated değil) |
| Türkçe boyut | Kartta dil başına boyut **yok** (yalnız mC4 toplamı 9,7 TB / 108 dil). Ölçüldü (HF ağaç API, 2026-09-19): `tr` train **1.024 dosya, 110.002.674.567 bayt gzip**. datasets-server: önizleme 1.683.640 satır = 5.275.297.705 bayt bellek; tahmini train satırı **87.587.373**. |
| Öneri `rights_status` | **`cleared` (ticari olmayan)** — `wiki_oscar` kararındaki kabullerle (atıf, Common Crawl tazmin maddesi) aynı; kabuller yazılı kalmalı |
| Ana korpusta zaten var mı? | **Kısmen, büyük parça.** `wiki_oscar` aynı `allenai/c4` `tr` akışını **baştan** okuyup en çok 9,75 M belge yazmış (`sources.json`, `max_docs: 9750000`; `mc4_scraper.py` satır 94, `streaming=True`, sabit sürüm yok). Kayıtların %90,6'sı `source=mc4`. Yani akışın **ilk ~%11'i** (süzülmüş) elimizde; kalan ~78 M belge net yeni aday. |

## Okunan lisans metni (alıntılar)

- Kart YAML: `license: [odc-by]`.
- Kart "Licensing Information" (README, okundu 2026-09-19): *"We are releasing this dataset under
  the terms of ODC-BY. By using this, you are also bound by the Common Crawl terms of use in
  respect of the content contained in the dataset."*
- Kart: *"To build mC4, the authors used CLD3 to identify over 100 languages."*; mC4 = 9,7 TB,
  108 alt küme.
- ODC-BY 1.0 (opendatacommons.org, okundu 2026-09-19): §4.2 *"Include a copy of this License or
  its Uniform Resource Identifier (URI) with the Database or Derivative Database"*; §4.3 Produced
  Work için *"a notice … reasonably calculated to make any Person … aware that Content was
  obtained from the Database"* — örnek: *"Contains information from DATABASE NAME which is made
  available under the ODC Attribution License."* Share-alike yok; §3.1 haklar *"explicitly
  include commercial use"*.
- Common Crawl kullanım şartları (son güncelleme 2024-03-07, okundu 2026-09-19): *"BY USING THE
  CRAWLED CONTENT, YOU AGREE TO RESPECT THE COPYRIGHTS AND OTHER APPLICABLE RIGHTS OF THIRD
  PARTIES IN AND TO THE MATERIAL CONTAINED THEREIN."* Ticari kullanım için hukuk danışmanı
  önerisi. Tazmin: kullanıcı, *"use of Crawled Content in connection with artificial
  intelligence, machine learning, or other similar technologies, including, without limitation,
  large language models and neural networks"* ile bağlantılı üçüncü taraf iddialarında Common
  Crawl'ı tazmin eder.

## Yükümlülükler (metinden)

| Yükümlülük | Durum |
|---|---|
| Atıf | **Zorunlu** (ODC-BY §4.2/4.3): lisans/URI ve "içerik allenai/c4'ten alınmıştır" notu — veri kartında ve model künyesinde. |
| Share-alike | Yok. |
| Yeniden dağıtım | ODC-BY izin verir (atıfla); Derlem ham metni yeniden dağıtmıyor. |
| Tazmin | **Var** — Common Crawl şartları, yapay zekâ/LLM kullanımı açıkça sayılmış. |
| Üçüncü taraf telifi | Common Crawl şartlarıyla **kullanıcıda**; sayfa sahiplerinin hakları saklı. |
| Ticari kullanım | ODC-BY izin verir; Common Crawl hukuk danışmanı önerir. Derlem kapsamı ticari değil. |
| Erişim şartı | Yok. |

## Ne demek

Hak sorusu yeni değil: `wiki_oscar`'ın %90,6'sı bu kaynaktan ve kurucu 2026-09-19'da S2 kararıyla
aynı şartları (atıf + tazmin maddesi kabulü, ticari olmayan) kabul etti. Yeni olan şey hacim:
toplayıcı akışın yalnız ilk ~9,75 M belgesini (süzerek) almış; kartın `tr` alt kümesi tahminen
87,6 M satır / 110 GB gzip. Kaba token tahmini (raf çevrimi 5,405 bayt/token; önizlemenin
bellek ölçüsüyle ~3,1 KB/satır → ~274 GB metin): **~50 B token**, bunun ~%11'i eldeki
`wiki_oscar` ile örtüşür (akış sırası deterministik olduğu için örtüşen kısım "ilk N belge"
olarak ayrılabilir; TASK-024 pilotu bunu ölçebilir). Sabit sürüm sorunu: toplayıcı `revision`
vermemiş; repo 2024-01-09'dan beri değişmediği için (`1588ec4…`) fiilen aynı sürümdür — yeni
indirme bu SHA'ya sabitlenmeli.

## Kaynaklar

- https://huggingface.co/datasets/allenai/c4
- https://huggingface.co/datasets/allenai/c4/raw/main/README.md
- https://huggingface.co/api/datasets/allenai/c4 (commit sha)
- https://huggingface.co/api/datasets/allenai/c4/tree/main/multilingual (c4-tr dosya boyutları, sayfalı)
- https://datasets-server.huggingface.co/size?dataset=allenai/c4&config=tr
- https://opendatacommons.org/licenses/by/1-0/
- https://commoncrawl.org/terms-of-use
- `var/raw-derlem/celik_ai-kod/CELIK_AI/corpus_builder/sources.json` (`tr.max_docs = 9750000`), `scrapers/mc4_scraper.py`

Erişim tarihi: 2026-09-19
