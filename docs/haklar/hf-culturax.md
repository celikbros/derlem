# `uonlp/CulturaX` (config `tr`) — lisans notu (TASK-023, isteğe bağlı aday)

**Tarih:** 2026-09-19 · **Hazırlayan:** Derlem oturumu (Claude) · **Karar:** kurucu
Hukuki görüş değildir; şartlar okunduğu gibi kaydedilmiştir. Hiçbir veri indirilmedi.

| Alan | Değer |
|---|---|
| Veri seti | https://huggingface.co/datasets/uonlp/CulturaX |
| Türkçe alt küme | config `tr` |
| Sabit sürüm | repo commit `6a8734bc69fefcbb7735f4f9250f43e4cd7a442e` (son değişiklik 2024-12-16, HF API) |
| Veri kartı lisansı | **Lisans alanı yok** (HF API: `license` etiketi boş). Kart gövdesi: *"The licence terms for CulturaX strictly follows those of mC4 and OSCAR."* |
| Üst kaynak içerik lisansı | mC4 payı: ODC-BY + Common Crawl şartları; OSCAR payı: paketleme CC0, içerik lisanssız (bkz. [hf-allenai-c4.md](hf-allenai-c4.md), [hf-oscar-2301.md](hf-oscar-2301.md)) |
| Erişim | **Gated (otomatik onay, form)**: sorumluluk kabulü + "zararlı amaçla kullanılmaz" beyanı |
| Türkçe boyut (kart beyanı) | **94.207.460 belge, 64.292.787.164 token** (%1,02); bayt kartta yok; datasets-server gated olduğu için yanıt vermiyor |
| Öneri `rights_status` | **`restricted`** — OSCAR bileşeninin içerik lisansı yok ve OSCAR'ın kendi erişimi askıda; mC4 bileşeni elimizdeki `wiki_oscar` ile örtüşüyor |
| Ana korpusta zaten var mı? | **Kısmen, doğrudan.** CulturaX = mC4 + OSCAR (temizlenmiş, tekilleştirilmiş). mC4-tr'nin `wiki_oscar`'a giren ilk ~9,75 M belgesi CulturaX-tr içinde de var (süzme farkları dışında). Net yeni kısım OSCAR payı + mC4'ün kalanı — mC4'ün kalanı zaten `allenai/c4`'ten daha temiz şartlarla alınabilir. |

## Okunan lisans metni (alıntılar)

- Kart "Licensing" (okundu 2026-09-19): *"The licence terms for CulturaX strictly follows those
  of mC4 and OSCAR. Please refer to both below licenses when using this dataset."* — bağlantılar:
  https://huggingface.co/datasets/allenai/c4#license ,
  https://huggingface.co/datasets/oscar-corpus/OSCAR-2301#licensing-information
- Kart erişim metni (`extra_gated_prompt`, HF API): *"By completing the form below, you
  acknowledge that the provided data is offered as is. Although we anticipate no problems, you
  accept full responsibility for any repercussions resulting from the use of this data.
  Furthermore, you agree that the data must not be utilized for malicious or harmful purposes
  towards humanity."*
- Kart dil tablosu Türkçe satırı: `12 | Turkish | 94,207,460 | 64,292,787,164 | 1.02`.

## Yükümlülükler (metinden)

| Yükümlülük | Durum |
|---|---|
| Atıf | mC4 payı için ODC-BY atfı zorunlu; kart makale atfı ister (arXiv:2309.09400). |
| Share-alike | Yok. |
| Yeniden dağıtım | mC4 payı ODC-BY; OSCAR payı için içerik hakkı yok. |
| Tazmin | Common Crawl şartları üzerinden var (her iki bileşen de Common Crawl kökenli). |
| Sorumluluk | Erişim formu: *"you accept full responsibility for any repercussions"*. |
| Erişim şartı | Var (form, otomatik onay). |

## Ne demek

Kart kendi lisansını vermiyor, iki üst kaynağa yönlendiriyor; iki üst kaynağın zayıfı OSCAR
(içerik lisansı yok, erişimi askıda). Türkçe hacmi büyük (64,3 B token beyanı) ama bunun
mC4 kısmı `allenai/c4`'ten ODC-BY ile doğrudan alınabilir, OSCAR kısmı ise OSCAR'ın hak
konumunu miras alır. Ayrıca `wiki_oscar` ile doğrudan örtüşür. Hacim planı için önerim:
**alınmasın**; aynı hacim FineWeb-2 (tek lisans sınıfı, açık erişim) ve mC4'ün kalanıyla daha
temiz elde edilir.

## Kaynaklar

- https://huggingface.co/datasets/uonlp/CulturaX
- https://huggingface.co/api/datasets/uonlp/CulturaX (`gated: auto`, `extra_gated_prompt`, lisans etiketi yok, commit sha)
- https://huggingface.co/datasets/allenai/c4#license
- https://huggingface.co/datasets/oscar-corpus/OSCAR-2301#licensing-information
- https://commoncrawl.org/terms-of-use

Erişim tarihi: 2026-09-19
