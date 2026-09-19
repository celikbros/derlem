# `wikimedia/wikipedia` (`20231101.tr`) — lisans notu (TASK-023)

**Tarih:** 2026-09-19 · **Hazırlayan:** Derlem oturumu (Claude) · **Karar:** kurucu
Hukuki görüş değildir; şartlar okunduğu gibi kaydedilmiştir. Hiçbir veri indirilmedi.

| Alan | Değer |
|---|---|
| Veri seti | https://huggingface.co/datasets/wikimedia/wikipedia |
| Türkçe alt küme | config `20231101.tr` (döküm 2023-11-01) |
| Sabit sürüm | repo commit `b04c8d1ceb2f5cd4588862100d08de323dccfbaa` (son değişiklik 2024-01-09, HF API) |
| Veri kartı lisansı | `cc-by-sa-3.0`, `gfdl` (kart YAML `license` alanı) |
| Üst kaynak içerik lisansı | Wikimedia dökümleri: GFDL + CC BY-SA 3.0 (kart); Wikimedia Vakfı Kullanım Şartları §7: katkılar CC BY-SA **4.0** + GFDL |
| Erişim | açık (gated değil) |
| Türkçe boyut (kart beyanı) | `num_examples` **534.988**, `num_bytes` **997.254.242** (~0,93 GiB metin); `download_size` 552.923.659 (2 parquet dosyası, ağaç listesiyle doğrulandı) |
| Öneri `rights_status` | **`cleared` (ticari olmayan)** — atıf + share-alike kabulü yazılı; `wiki_oscar` kararındaki kabullerle aynı |
| Ana korpusta zaten var mı? | **Evet, büyük ölçüde.** `wiki_oscar` toplayıcısı (`corpus_builder/scrapers/mc4_scraper.py`) aynı `20231101.{lang}` config'ini yükler; `wiki_oscar_corpus.jsonl` kayıtlarının %9,4'ü `source=wikipedia`. Net yeni token beklentisi **≈ 0**. |

## Okunan lisans metni (alıntılar)

- Kart YAML: `license: [cc-by-sa-3.0, gfdl]`.
- Kart "Licensing Information" (README, okundu 2026-09-19): *"Copyright licensing information:
  https://dumps.wikimedia.org/legal.html — All original textual content is licensed under the
  GNU Free Documentation License (GFDL) and the Creative Commons Attribution-Share-Alike 3.0
  License. Some text may be available only under the Creative Commons license; see their Terms
  of Use for details. Text written by some authors may be released under additional licenses or
  into the public domain."*
- Kart "Source Data": *"The dataset is built from the Wikipedia dumps: https://dumps.wikimedia.org
  … The articles have been parsed using the mwparserfromhell tool."*
- CC BY-SA 3.0 özeti (creativecommons.org, okundu 2026-09-19): *"Share — copy and redistribute
  the material in any medium or format for any purpose, even commercially"*; *"Attribution — You
  must give appropriate credit, provide a link to the license, and indicate if changes were
  made"*; *"ShareAlike — If you remix, transform, or build upon the material, you must distribute
  your contributions under the same license as the original."*
- Wikimedia Vakfı Kullanım Şartları §7 (okundu 2026-09-19): metin katkıları *"Creative Commons
  Attribution-ShareAlike 4.0 International License ("CC BY-SA 4.0"), and GNU Free Documentation
  License ("GFDL")"* altında; yeniden kullanımda atıf *"through hyperlink (where possible) or URL
  to the article"* ya da yazar listesiyle; değiştirilen metin *"under CC BY-SA 4.0 or later"*.

## Yükümlülükler (metinden)

| Yükümlülük | Durum |
|---|---|
| Atıf | **Zorunlu** (CC BY-SA ve GFDL). Kaynak: Wikimedia/Wikipedia, döküm tarihi, lisans bağlantısı; veri kartında ve model künyesinde. |
| Share-alike | **Var.** Metnin yeniden dağıtımında aynı lisans. Model ağırlıklarının "türev" sayılıp sayılmadığı metinde tanımlı değil — `wiki_oscar` kararında risk kabul edildi. |
| Yeniden dağıtım | Serbest, aynı lisans + atıf şartıyla. Derlem ham metni yeniden dağıtmıyor. |
| Tazmin | Yok (CC lisansları tazmin şartı içermez). |
| Ticari kullanım | Lisans izin verir; Derlem kapsamı ticari değil. |
| Erişim şartı | Yok. |

## Ne demek

Terimler `wiki_oscar` için zaten okunmuş ve kabul edilmiş terimlerin aynısı (bkz.
[hak_kanit_paketi_2026_09.md](../hak_kanit_paketi_2026_09.md)). Yeni bir hak sorusu açmıyor,
ama yeni hacim de getirmiyor: aynı döküm zaten ana korpusun içinde. Bu veri setinin değeri
hacim değil, TASK-024'teki **örtüşme pilotu** için sabit sürümlü, küçük, temiz bir referans olması.
Daha yeni bir döküm (kartta `20231101` son sabit döküm; başka tarih görülmedi) gelirse fark
küçüktür (Türkçe Wikipedia'nın 2023-11 sonrası büyümesi).

## Kaynaklar

- https://huggingface.co/datasets/wikimedia/wikipedia
- https://huggingface.co/datasets/wikimedia/wikipedia/raw/main/README.md
- https://huggingface.co/api/datasets/wikimedia/wikipedia (commit sha, son değişiklik)
- https://datasets-server.huggingface.co/size?dataset=wikimedia/wikipedia&config=20231101.tr
- https://dumps.wikimedia.org/legal.html (kartın yönlendirdiği adres; ayrıca okunmadı)
- https://creativecommons.org/licenses/by-sa/3.0/
- https://foundation.wikimedia.org/wiki/Policy:Terms_of_Use
- `var/raw-derlem/celik_ai-kod/CELIK_AI/corpus_builder/scrapers/mc4_scraper.py` (satır 94–97: `allenai/c4` `tr` akışı; `wikimedia/wikipedia` `20231101.{lang}`)

Erişim tarihi: 2026-09-19
