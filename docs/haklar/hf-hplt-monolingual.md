# HPLT tek dilli Türkçe — `HPLT/hplt_monolingual_v1_2` (`tr`) ve `HPLT/HPLT2.0_cleaned` (`tur_Latn`) — lisans notu (TASK-023)

**Tarih:** 2026-09-19 · **Hazırlayan:** Derlem oturumu (Claude) · **Karar:** kurucu
Hukuki görüş değildir; şartlar okunduğu gibi kaydedilmiştir. Hiçbir veri indirilmedi.
İki sürüm aynı kullanım şartlarını taşıdığı için tek notta; sabit sürüm ve boyut ayrı ayrı.

| Alan | v1.2 | v2.0 cleaned |
|---|---|---|
| Veri seti | https://huggingface.co/datasets/HPLT/hplt_monolingual_v1_2 | https://huggingface.co/datasets/HPLT/HPLT2.0_cleaned |
| Türkçe alt küme | config `tr` (varyantlar: ham / `deduplicated` / `cleaned`) | config `tur_Latn` |
| Sabit sürüm | repo commit `dbe88820461dd953a4094e1bb32c88b55c325f1e` (son değişiklik 2026-07-08). **Dikkat:** HF deposunda yalnız yükleyici betik var; veri `https://data.hplt-project.org/one/monotext/{cleaned,deduplicated}/tr_map.txt` listesinden çekiliyor — veri dosyaları için ayrı bir sabitleme (dosya özetleri) gerekir. | repo commit `d1324a5283f762ee62c2a5c81de08fc6450ea540` (son değişiklik 2026-06-11); veri parquet olarak depoda |
| Veri kartı lisansı | `cc0-1.0` (kart YAML) — **yalnız paketleme** | `cc0-1.0` (kart YAML) — **yalnız paketleme** |
| Üst kaynak içerik lisansı | **Yok.** *"We do not own any of the text"*; kaynak Common Crawl + Internet Archive taramaları | **Yok.** Aynı beyan; kaynak *"mostly Internet Archive with some additions from Common Crawl"* |
| Erişim | açık | açık |
| Türkçe boyut (yayıncı beyanı) | hplt-project.org v1.2 tablosu: ham **154 GB / 215,38 M belge / 238,30 B kelime**; dedup 79 GB / 59,43 M / 64,92 B; **cleaned 47 GB / 27,05 M belge / 42,65 B kelime** | Kart tablosu (satır 173): segment 2,58e9, kelime **5,17e10**, karakter **3,90e11**, belge **1,17e8**. datasets-server: **116.566.047 satır, 262.225.005.184 bayt parquet** |
| Öneri `rights_status` | **`restricted`** — içerik için verilmiş hak yok; kullanım kurucu risk kabulüne dayanır (ticari olmayan araştırma), bildirim-kaldırma taahhüdüne uyulur | **`restricted`** — aynı |
| Ana korpusta zaten var mı? | **Hayır** (kaynak farklı: çoğu Internet Archive). Common Crawl kısmı mC4-tr ile içerik olarak örtüşebilir; ölçülmedi. | **Hayır**; aynı not. |

## Okunan lisans metni (alıntılar)

- v1.2 kartı "Terms of Use" (README, okundu 2026-09-19): *"HPLT states the following: These data
  are released under these Terms of Use: — We do not own any of the text from which these text
  data has been extracted. — We license the actual packaging of these text data under the
  Creative Commons CC0 license ("no rights reserved")."* "Data removal": *"Found data that you
  would like removed in the next release? Contact the data creators."*
  (hplt-datasets@ufal.mff.cuni.cz). Kart: *"These large-scale web-crawled corpora based on
  CommonCrawl and the Internet Archive are accessible in 75 languages."*
- v2.0 kartı "Terms of Use and Takedown" (README, okundu 2026-09-19): aynı iki madde; "Notice
  and take down policy": *"Should you consider that our data contains material that is owned by
  you and should therefore not be reproduced here, please: Clearly identify yourself … Clearly
  identify the work claimed to be infringed … Clearly identify the material that is claimed to
  be infringing …"* Kaynak: *"The source of the data is mostly Internet Archive with some
  additions from Common Crawl."*
- hplt-project.org v2.0 (okundu 2026-09-19): *"We will comply with legitimate requests by
  removing the affected sources from the next release of the corpora."* Kaynak: *"4.5 petabytes
  of compressed web data in total (mostly from Internet Archive, but also from Common Crawl)."*
  Sitenin `tur_Latn` satırı (dedup 32,11 M belge / 267,47 GB; cleaned 12,68 M / 178,05 GB) HF
  kartındaki sayılarla **uyuşmuyor**; hangi tablonun hangi varyantı gösterdiği sayfadan
  çıkarılamadı — bu notta HF kartı ve datasets-server sayıları esas alındı.
- CC0 1.0 özeti (creativecommons.org): hak sahibi feragat eder; CC0 *"rights that other persons
  may have in the work"* üzerinde etkisizdir — burada metnin sahipleri üçüncü taraflar.
- Internet Archive kısmı için kartlarda ayrı bir kullanım şartı **gösterilmiyor**; Common Crawl
  kısmı için Common Crawl kullanım şartları (bkz. [hf-allenai-c4.md](hf-allenai-c4.md)).

## Yükümlülükler (metinden)

| Yükümlülük | Durum |
|---|---|
| Atıf | Paketleme CC0 → zorunlu değil. Kart, akademik atıf ister (makale). |
| Share-alike | Yok. |
| Yeniden dağıtım | Paketleme için serbest; içerik hakkı verilmemiş. |
| Tazmin | Kartta yok; Common Crawl'dan gelen kısım için Common Crawl şartları. |
| Bildirim-kaldırma | Yayıncı taahhüt ediyor; kullanan tarafın da aynı takedown yoluna uyması makul (data_governance takedown kuralı). |
| Erişim şartı | Yok. |

## Ne demek

Hacim büyük (v2 `tur_Latn` 116,6 M satır / 262 GB parquet; kaba **~70 B token** raf çevrimiyle,
390 G karakter üzerinden) ve mC4/FineWeb-2'den **farklı kökenli** (Internet Archive), yani net
yeni token beklentisi yüksek. Hak konumu mC4/FineWeb-2'den daha zayıf: yayıncı yalnız
"paketleme CC0, metin bizim değil" diyor, ODC-BY gibi bir veritabanı hakkı bile vermiyor.
Kullanım, `academic`/`tdk` için yapılan türden bir **kurucu risk kabulü** (ticari olmayan
araştırma, yeniden dağıtım yok, takedown taahhüdü) gerektirir. OSCAR'dan farkı: erişim açık ve
yayıncı erişimi kısıtlamıyor.

## Kaynaklar

- https://huggingface.co/datasets/HPLT/hplt_monolingual_v1_2 ve `/raw/main/README.md`, `/raw/main/hplt_monolingual_v1_2.py`
- https://huggingface.co/datasets/HPLT/HPLT2.0_cleaned ve `/raw/main/README.md`
- https://huggingface.co/api/datasets/HPLT/hplt_monolingual_v1_2 , https://huggingface.co/api/datasets/HPLT/HPLT2.0_cleaned (commit sha)
- https://datasets-server.huggingface.co/size?dataset=HPLT/HPLT2.0_cleaned&config=tur_Latn
- https://hplt-project.org/datasets/v1.2 (Türkçe satırı, şartlar)
- https://hplt-project.org/datasets/v2.0
- https://creativecommons.org/publicdomain/zero/1.0/

Erişim tarihi: 2026-09-19
