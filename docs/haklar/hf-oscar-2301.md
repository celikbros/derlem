# `oscar-corpus/OSCAR-2301` (config `tr`) — lisans notu (TASK-023)

**Tarih:** 2026-09-19 · **Hazırlayan:** Derlem oturumu (Claude) · **Karar:** kurucu
Hukuki görüş değildir; şartlar okunduğu gibi kaydedilmiştir. Hiçbir veri indirilmedi.

| Alan | Değer |
|---|---|
| Veri seti | https://huggingface.co/datasets/oscar-corpus/OSCAR-2301 |
| Türkçe alt küme | config `tr` |
| Sabit sürüm | repo commit `c2930464071faebadfb5491e2b4f99666da7a1e6` (son değişiklik 2025-08-06, HF API) |
| Veri kartı lisansı | `cc0-1.0` (kart YAML) — **yalnız paketleme, üstveri ve ek açıklamalar için** |
| Üst kaynak içerik lisansı | **Yok.** İçerik Common Crawl Kasım/Aralık 2022 anlık görüntüsü; OSCAR yazarları *"do not hold any copyright whatsoever"*. Common Crawl kullanım şartları ve yerel telif istisnaları (kartta "TDM"/"research" örneği) geçerli. |
| Erişim | **Gated (manuel onay) ve askıda.** Kart: *"we will not grant any access until the situation has been clarified."* README bile 401 döndürüyor. |
| Türkçe boyut (kart/proje belgesi beyanı) | **26.654.330 belge, 8.290.890.087 kelime, 73,7 GB** (OSCAR 23.01 tablosu) |
| Öneri `rights_status` | **`blocked`** (erişim yok; erişim açılsa bile içerik lisansı yok → en iyi hâlde `restricted`, kurucu risk kabulüyle) |
| Ana korpusta zaten var mı? | **Hayır.** `wiki_oscar` adına rağmen OSCAR kaydı içermiyor (`source` yalnız `mc4`/`wikipedia`). Dolaylı örtüşme: aynı Common Crawl kökeni, ölçülmedi. |

## Okunan lisans metni (alıntılar)

- Kart YAML: `license: cc0-1.0`; `gated: manual` (HF API).
- Kart erişim metni (`extra_gated_prompt`, HF API, okundu 2026-09-19): *"[IMPORTANT: We are
  forced to temporarily suspend access to OSCAR. The temporary nature of this suspension has led
  us to choose to implement it as gated access with manual control, and we will not grant any
  access until the situation has been clarified. … we remind you that we have always prohibited
  access to or use of OSCAR that violates the legislation in force where you are located. In
  France, for example, any use of OSCAR that does not fall within the framework of the so-called
  'TDM' or the so-called 'research' exceptions to copyright has always been prohibited.] By
  filling the form below, you understand that only the metadata and the annotations of OSCAR
  23.01 have a cc0-1.0 license, and that the rest of the content is crawled data derived from
  the November/December 2022 snapshot of Common Crawl, for which the authors of OSCAR do not hold
  any copyright whatsoever."* Form alanları: ad, e-posta, kurum, ülke, kullanım amacı ve onay
  kutusu: *"I have explicitly check with my jurisdiction and I confirm that downloading OSCAR
  2301 is legal in the country/region where I am located right now, and for the use case that I
  have described above."*
- OSCAR proje sitesi "Corpus License" (oscar-project.org, okundu 2026-09-19): *"We do not own
  any of the text from which these data has been extracted. We license the actual packaging and
  annotations of these data under the Creative Commons CC0 license ('no rights reserved')."*
  Bildirim-kaldırma: *"We will comply to legitimate requests by removing the affected sources
  from the next release of the corpus."*
- CC0 1.0 özeti (creativecommons.org): hak sahibi telifinden feragat eder; ancak CC0 *"rights
  that other persons may have in the work or in how the work is used"* üzerinde etkisizdir.
- Common Crawl kullanım şartları: bkz. [hf-allenai-c4.md](hf-allenai-c4.md) (üçüncü taraf
  telifine saygı; yapay zekâ kullanımında tazmin).

## Yükümlülükler (metinden)

| Yükümlülük | Durum |
|---|---|
| Atıf | Paketleme CC0 → zorunlu değil; içerik için lisans yok, dolayısıyla atıf sorunu değil, **hak** sorunu. |
| Share-alike | Yok. |
| Yeniden dağıtım | Paketleme için serbest; içerik için hak yok. |
| Tazmin | Common Crawl şartları üzerinden **var**. |
| Erişim şartı | **Var**: form + yargı alanı onayı + kullanım amacı; şu an hiç onay verilmiyor. |
| Yasal dayanak | Kart, kullanımı yerel telif istisnasına (TDM/araştırma) bırakıyor; Türkiye için böyle bir istisnanın kapsamı bu notta değerlendirilmez. |

## Ne demek

Bugün alınamaz; alınabilse bile içerik için yayıncının verdiği hak yoktur (yalnız "sahibi biz
değiliz" beyanı). Bu, `wiki_oscar`'daki mC4'ten daha zayıf bir konum: mC4 hiç değilse ODC-BY ile
veritabanı hakkını veriyor. Hacim büyük (Türkçe 73,7 GB, kaba **~13–14 B token** raf çevrimiyle)
ama erişim askıda olduğu sürece hacim planında sıfır sayılır. Erişim açılırsa yeniden bakılır;
o durumda öneri `restricted` (kurucu risk kabulü, ticari olmayan araştırma).

## Kaynaklar

- https://huggingface.co/datasets/oscar-corpus/OSCAR-2301 (kart; dosyalar ve README gated — 401)
- https://huggingface.co/api/datasets/oscar-corpus/OSCAR-2301 (`extra_gated_prompt`, `gated: manual`, commit sha)
- https://oscar-project.github.io/documentation/versions/oscar-2301/ (Türkçe satırı, Common Crawl Kas/Ara 2022)
- https://oscar-project.org/ ("Corpus License", bildirim-kaldırma)
- https://creativecommons.org/publicdomain/zero/1.0/
- https://commoncrawl.org/terms-of-use

Erişim tarihi: 2026-09-19
