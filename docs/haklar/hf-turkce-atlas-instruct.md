# `AlicanKiraz0/Turkce-Atlas-Instruct` — lisans ve olgu notu

**Tarih:** 2026-10-13 · **Hazırlayan:** Derlem oturumu (Claude) · **Karar:** kurucu
Hukuki görüş değildir; şartlar okunduğu gibi kaydedilmiştir. Hiçbir veri indirilmedi (yalnız
veri kartı, HF API üstverisi, commit geçmişi ve datasets-server `splits`/`size`/`info`/
`statistics`/`first-rows` uçları okundu). Doğrulanamayan her şey "doğrulanamadı" diye
işaretlidir.

| Alan | Değer |
|---|---|
| Veri seti | https://huggingface.co/datasets/AlicanKiraz0/Turkce-Atlas-Instruct (yayıncı: tek kişi, `AlicanKiraz0`) |
| Tür | Türkçe talimat/sohbet (SFT) seti; konuşma biçimi (`messages` listesi) |
| Bölümler | yalnız `train` (config `default`); doğrulama/test yok |
| Sabit sürüm | repo commit `c387738c5deacbb35667ab4057930adc34e647e8` (HF API `sha`; `lastModified` 2026-07-12T12:00:15Z; `createdAt` 2026-04-15T06:12:00Z) |
| Veri dosyası sürümü | `train.chat.jsonl` blob oid `b842c7ffe6061e84733ef11b7bdf1a4dca55ac5c`; 2026-04-15 yüklemesinden (`180fb437…`) beri **değişmedi**; sonraki 4 commit yalnız `README.md` |
| Kart lisansı | `mit` (kart YAML ve API `cardData.license`); kart: "bağımsız bir hak sahipliği incelemesi yapılmamıştır" |
| İçerik kaynağı | **Kartta yok** (çeviri mi, sentetik mi, insan yazımı mı, hangi modelle üretildi — hiçbiri yazılmamış). **Doğrulanamadı** |
| Erişim | açık (`gated: false`, `private: false`, `disabled: false`) |
| Boyut | **336.146 kayıt**; 1 dosya `train.chat.jsonl` = **510.875.702 bayt** (~510,9 MB); datasets-server Parquet = 480.705.099 bayt, bellek 480.995.121 bayt |
| Sütun sayısı | 1 (`messages`) |
| Öneri `rights_status` | **`unknown`** (kurucu risk kabulüyle `cleared`, ticari olmayan'a çevrilebilir) — §6 |

## 1. Lisans ve içerik kaynağı

- Kart YAML: `license: mit`. Kart "Lisans" bölümü (README, okundu 2026-10-13), aynen:
  *"Hugging Face depo metadatası lisansı `MIT` olarak bildirmektedir. YAML içindeki
  `license: mit` alanı incelenen revizyonda zaten bulunuyordu ve bu kartta korunmuştur;
  bağımsız bir hak sahipliği incelemesi yapılmamıştır. Bu bildirim, varsa dış kaynakların
  kullanım koşullarını veya veri içindeki her metnin yeniden lisanslanabilirliğini tek başına
  kanıtlamaz. Kaynak geçmişi bilgileri tamamlanana kadar yeniden dağıtım ve ticari kullanım
  öncesinde ayrıca hukuki değerlendirme yapılması önerilir."* Ardından: *"Bu bölüm hukuki
  danışmanlık değildir."*
- **İçerik kaynağı kartta açıklanmamış.** Kartın "Veri yapısı", "Gözlenen görev aileleri" ve
  "Veri kalitesi incelemesi" bölümleri biçimi ve içeriği anlatıyor; metinlerin nereden
  türetildiğini, başka bir veri setinin çevirisi olup olmadığını, bir dil modeliyle üretilip
  üretilmediğini ve üreten modelin adını **yazmıyor**. "Sentetik", "üretilmiş", "çeviri" ve
  "türetilmiş" sözcükleri kartta kaynak bağlamında geçmiyor (kart yalnız "Örneklerde
  `example.com` … sentetik görünümlü değerler bulunur" diyerek **kayıtların içindeki
  değerlerden** söz ediyor; bu, veri setinin üretim yöntemi hakkında bir beyan değil).
  Bağlantılı model, Space veya GitHub deposu da kartta ve API `tags` alanında yok; depoda
  `LICENSE` dosyası da yok (ağaçta yalnız `.gitattributes`, `README.md`, `train.chat.jsonl`).
- Aşağıdaki, kart beyanı değil **çıkarımdır**: `first-rows` örnekleri (ilk 100 kayıt)
  şablonlu komutlar, tek tip biçimli yanıtlar ve `S:`/`C:` etiketleri taşıyor; bu,
  **büyük olasılıkla** bir dil modeliyle üretilmiş (sentetik) olduğuna işaret eder. Üreten
  model **doğrulanamadı**.
- **Üreten modelin kullanım şartları:** üretici model bilinmediği için hangi şartların
  (ör. çıktıyla rakip model eğitme yasağı) geçerli olduğu **doğrulanamadı**. Kart bu konuda
  hiçbir cümle içermiyor. Şartlar modele bağlı olduğundan bu bir **açık risk**tir.
- Üst kaynak lisansları: kartta üst kaynak listesi yok → **doğrulanamadı**.
- Kart kendi içinde eski kalmış: "Depo özel olduğu sürece hesabınızın erişim yetkisi
  bulunmalıdır" ve örnek kodda `token=True  # Depo herkese açılırsa kaldırılabilir` diyor;
  depo bugün açık (`private: false`). Köken konusunda ek kanıt değil.

## 2. Sürüm sabitleme

- Alım şu sha'ya sabitlenmeli: `c387738c5deacbb35667ab4057930adc34e647e8`.
- Kartın örnek kodu başka bir revizyonu sabitliyor: `180fb437a6df27cc09505b72eec4bc536b6c113b`
  (2026-04-15 "Upload train.chat.jsonl"). **Veri baytları iki sha'da aynı** (aynı blob oid,
  aynı LFS oid `3caf3081da91ad46890b93907d5123ec1c03508368b5afbc8f9e33c89042e044`); fark
  yalnız `README.md` (ilk sürümde 24 bayt, bugün 12.967 bayt).
- Commit geçmişi (HF API, yazar hepsinde `AlicanKiraz0`): 2026-04-15 06:12 "initial commit";
  06:14 "Upload train.chat.jsonl" (`180fb437…`); 2026-07-12 11:44 "Document Türkçe Atlas
  dataset" (`24a593f4…`); 11:50 "Update Hub identifier for Türkçe Atlas" (`c3ea9576…`);
  11:57 ve 12:00 "Update README.md" (`45c682f2…`, `c387738c…`).
- Dosya ağacı (`tree/main`, 3 dosya): `.gitattributes` (2.557 B), `README.md` (12.967 B),
  `train.chat.jsonl` (510.875.702 B, LFS/Xet). Biçim: **JSON Lines** (kart: `format:json`);
  Parquet kopyası yalnız datasets-server içindedir (depoda yok). Kullanım sayacı:
  205 indirme, 55 beğeni (2026-10-13).
- Kartın "Viewer Parquet boyutu" değeri 480.703.735 bayt; datasets-server `size` ucu
  480.705.099 bayt veriyor (1.364 bayt fark; önemsiz, kayıt için not).

## 3. Şema

Split'ler: `train` (336.146 satır). `/info` şeması (tek sütun):

| Sütun | Tür | Açıklama |
|---|---|---|
| `messages` | `list[struct{role: string, content: string}]` | Sıralı mesaj listesi |
| `messages[].role` | string | `system`, `user` veya `assistant` |
| `messages[].content` | string | Düz metin (parça listesi yok) |

- **Biçim:** konuşma biçimi (messages listesi); instruction/input/output üçlüsü **değil**,
  tek alan **değil**. Girdi bağlamı (pasaj, "Orijinal:" metni) ayrı alan değil, `user`
  metninin içinde.
- **Çok turlu mu:** hayır. `/statistics`: `messages` uzunluğu min 3, maks 3, ortalama 3,0,
  std 0 → **her kayıt tam 3 mesaj**. Kart rol sırasının tüm kayıtlarda `system → user →
  assistant` olduğunu söylüyor; `first-rows`'ta 100 kaydın 100'ü bu sırada. Rol sırasını tüm
  veride kendim **doğrulamadım** (veri indirilmedi).
- **Sistem mesajı:** var; kart: tüm 336.146 kayıtta aynı (`first-rows`'ta 100 kayıtta tek
  benzersiz değer), 654 karakter, Türkçe: "Sen yardımsever, doğru ve güvenilir bir Türkçe
  yapay zekâ asistanısın. Temel ilkelerin: …" (istenen biçime tam uy, gereksiz giriş/kapanış
  ekleme, bilgi uydurma, ton ve kısıtlara uy, zararlı talepleri reddet).
- **Bölüm yok:** doğrulama/test bölümü yok; Derlem eval için ayırmak isterse kendisi ayırmalı.

Örnek kayıtlar (`/first-rows`, `train`; ilk 100 satır, `truncated: true`; metin özetlendi):

1. **Satır 0** — `system`: ortak yönerge. `user`: bir dijital sağlık uygulaması cümlesini
   "hem samimi hem resmi" yeniden yaz, anlam kayması olmasın (+ `Orijinal: '…'`).
   `assistant`: `Samimi: …` / `Resmi: …` iki paragraf.
2. **Satır 11** — `user`: sabit ilk satır "Aşağıdaki pasaja dayanarak soruyu yanıtla. Pasajda
   olmayan bilgi ekleme." + `Pasaj: …` (Türk mutfağı, baharatlar). `assistant`: `S: … / C: …`
   biçiminde kendi sorduğu soruya cevap (komutta soru yok; yanıt soruyu uyduruyor).
3. **Satır 75** — `user`: "Güvenilirleştirilemeyecekmişsiniz kelimesinin morfolojik
   çözümlemesini yap." `assistant`: `S: <sözcük> / C: Kök: Güven (İsim) | -il: … | -ir: … |
   -leş: …` ek dökümü.
4. **Satır 99** — `user`: yazılım ofisi için "Tamamen In-house / Outsourcing / Hibrit"
   karşılaştırması, akademik üslupla, kriterlere göre. `assistant`: Markdown tablo.

## 4. Derlem kanonik kaydına eşleme taslağı

Hedef: `derlem.canonical-sample.v1` (`worker/src/derlem_worker/canonical.py`).
`parse_canonical_sample` bilinmeyen alanları **reddeder** (`_reject_unknown_fields`); kaynak
bilgisi bu yüzden yalnız `metadata` içine konabilir. Roller (`system`/`user`/`assistant`)
`MESSAGE_ROLES` içinde; `content` düz string kabul ediliyor.

| Kaynak alan | Kanonik alan | Not |
|---|---|---|
| (sabit) | `schema_version` = `derlem.canonical-sample.v1` | |
| (sabit) | `record_type` = `conversation` | tercih çifti yok → `preference` değil |
| (yok) | `sample_id` | **Eksik** — kaynakta kimlik yok. Türetme: `atlas-<sha8>-<satır no>` (sabit sha + dosya sırası; dosya değişmediği için kararlı). Zorunlu alan |
| (sabit) | `content_purpose` = `instruction` | `post_training` de seçilebilir; ayrım Derlem'in tanımına bağlı (kurucu seçer) |
| (yok) | `task_type` | **Eksik** — kartta hazır etiket yok (kart: "hazır sınıf etiketi değildir"). Görev aileleri yalnız 60 kayıtlık örneklemden gözlenmiş; sonradan sınıflandırılabilir |
| (sabit) | `language` = `tr` | kart `language: tr`; kayıt düzeyinde doğrulama yok |
| (yok) | `domain` | **Eksik** (sağlık, hukuk, yazılım… karışık; etiket yok) |
| (öneri) | `train_policy` = `assistant_only` | kartın kendi TRL örneği de `assistant_only_loss=True`; sistem mesajı ortak olduğundan eğitim sinyali taşımaz |
| `messages[].role` | `messages[].role` | birebir |
| `messages[].content` | `messages[].content` | birebir (string). Üç mesaj → 3 kanonik mesaj |
| (yok) | `messages[].message_id`, `name`, `tool_*`, `reasoning_*` | **Yok** — araç/akıl yürütme alanı kaynakta bulunmuyor; `tools` boş |
| (sabit) | `preference` | kullanılmaz (`conversation_has_preference` hatasını önlemek için hiç konmaz) |
| (yok) | `created_at` | **Eksik** — kayıt başına zaman damgası yok; yalnız depo düzeyinde 2026-04-15 |
| (Derlem) | `created_by` | Derlem alım adı (kaynak yazar değil); kaynak yazar `metadata` içinde |
| (türetilmiş) | `metadata` | `source: hf:AlicanKiraz0/Turkce-Atlas-Instruct`, `source_revision: c387738c…`, `source_row`, `source_license: mit (kart beyanı)`, `provenance: undisclosed` |

Kaybolan/eksik özet: kayıt kimliği, görev türü, alan, zaman damgası, üst kaynak/üretim
modeli (kaynakta hiç yok). Sistem mesajı 336.146 satırda aynıdır → depolamada tekilleştirme
ya da sabit şablon olarak tutma mantıklı; Derlem'in anlamsal tekilleştirmesinde bu mesajı
**dışarıda bırakmak** gerekir, aksi halde tüm kayıtlar birbirine benzer görünür
(`semantic_texts` tüm mesaj metinlerini toplar).

## 5. Kalite ipuçları

Kartın kendi beyanları (tüm veri üzerinde birebir eşleşme ölçümleri; ben yeniden ölçmedim):

- Benzersiz kullanıcı komutu 335.145 (1.001 satır, %0,2978 tekrar; 688 tekrar grubu, en
  yüksek tekrar 11); benzersiz asistan yanıtı 336.010 (136 satır, %0,0405 tekrar). Anlamsal
  veya şablon temelli yakın kopyalar kapsam dışı.
- **Şablon yoğunlaşması:** 25.120 kayıt (%7,47) aynı ilk satırla başlıyor ("Aşağıdaki pasaja
  dayanarak soruyu yanıtla. Pasajda olmayan bilgi ekleme."). Kart: görev/üslup kalıbına
  aşırı uyum riski.
- 10 karakterden kısa üç yanıt var; üçü de yalnızca `S:` — kart: tamamlanmamış örnek adayı,
  eğitimden önce incelenmeli.
- **Uzunluk (karakter; kart):** `user` min 7 / ort. 290,30 / medyan 258 / %95 708 / maks 2.986;
  `assistant` min 2 / ort. 334,04 / medyan 280 / %95 855 / maks 2.000; `system` sabit 654.
  `first-rows` (100 kayıt) ile tutarlı: user ort. 315,5 / medyan 261,5; assistant ort. 342,2 /
  medyan 284. Kısa/orta uzunlukta; uzun biçimli akıl yürütme yok. Token sayısı verilmemiş.
- **PII benzeri desen (kart, alt sınır):** e-posta benzeri 405 satır, ayırıcısız TR cep
  telefonu benzeri 395, 11 haneli kimlik no benzeri 117, `http(s)://` 66, IPv4 benzeri 4.375.
  Kart çoğunun sentetik/temsili göründüğünü ama bunun gerçek olmadığını kanıtlamadığını ve
  bağlama duyarlı PII taraması gerektiğini söylüyor.
- **`/statistics` ucu** yalnız `messages` liste uzunluğunu veriyor (hepsi 3); metin
  uzunluğu istatistiği yok, uzunluk değerleri karttan.
- **Gözden geçirilen 100 satır (`first-rows`; kendi okumam, örneklem küçük, genellenemez):**
  dil akıcı ve biçimsel olarak doğal Türkçe; belirgin çeviri kokusu ya da İngilizce kalıntı
  görmedim (yalnız teknik jargon girdilerinde `sensor drift`, `firmware update` gibi bilerek
  korunmuş sözcükler). Şablonluluk açık: 100 satırın 10'u "pasaja dayanarak" ile başlıyor;
  sistem mesajı birebir aynı. Kusurlar: (a) sistem mesajı "ek açıklama ekleme" dese de bazı
  yanıtlar açıklama ekliyor (satır 10: düzeltmenin yanına parantez içinde gerekçe); (b)
  `S:`/`C:` etiketleri komutta istenmediği halde yanıta sızıyor (satır 11, 75); (c) pasaja
  dayalı soru-cevap kayıtlarında komutta soru yok, yanıt kendi sorusunu uyduruyor (satır 11);
  (d) yanıt doğruluğu doğrulanmadı; makine üretimi görünen veride olgusal hata ve uydurma
  riski var (ör. satır 75'teki ek dökümünün dilbilgisel doğruluğu denetlenmedi). Kartın
  anılan güvenli ret örneklerini 100 satırda **görmedim** (ret ifadeleri aradım, bulunmadı).

## 6. Yükümlülükler ve öneri

| Konu | Durum |
|---|---|
| Erişim şartı | Yok (gated değil, giriş gerekmiyor). |
| MIT yükümlülüğü | Telif/izin bildirimi korunur; **MIT metni (telif sahibi adı, yıl) kartta ve depoda yok** (`LICENSE` dosyası yok; yalnız `license: mit` etiketi). Atıf yapılacaksa kartın BibTeX'i: `alicankiraz0_turkce_atlas_2026` (yazar `AlicanKiraz0`, 2026). |
| Share-alike | Yok (MIT). |
| Yeniden dağıtım | MIT izin verir **yazarın kendi hakkı için**; yazarın dış kaynaklara/üreten modele ait haklarını verebildiği **doğrulanamadı**. Derlem ham metni yeniden dağıtmıyor. |
| Üretici model şartları | **Doğrulanamadı** (üretici belirtilmemiş; §1). |
| Üst kaynak lisansları | **Doğrulanamadı** (kaynak listesi yok). |
| Kaldırma (takedown) | Kartta hak sahibi/kaldırma kanalı yok; Hugging Face depo tartışması dışında bilgi yok. |
| PII | Kart kendisi PII riskini kabul ediyor (§5); Derlem'in kendi PII taraması şart. |
| Ticari kullanım | Kart "ayrıca hukuki değerlendirme önerilir" diyor; Derlem kapsamı zaten ticari değil. |

**Öneri `rights_status`: `unknown`.** Gerekçe: kart MIT diyor ama içerik kaynağını, üreten
modeli ve üst lisansları açıklamıyor, yazar da "bağımsız hak sahipliği incelemesi
yapılmamıştır" diyor; kurucunun 2026-09-19 kararındaki ilke (kökeni bilinmeyen kaynak —
`tr_corpus`, `celik_gold` özgü kısmı — `unknown`, kullanım kapsamı ticari olmayan araştırma)
bu duruma doğrudan denk geliyor.

**Kurucu kararı gerektiren nokta:** istenirse "kurucu risk kabulü, ticari olmayan araştırma"
kapsamıyla `cleared` verilebilir (`academic`/`tdk` kayıtlarındaki gibi); bu durumda kabul
edilen riskler açıkça yazılmalı: (a) sentetikse üretici modelin şartları (rakip model
eğitimi yasağı gibi; **bilinmiyor**), (b) üst kaynakların lisansları (**bilinmiyor**),
(c) PII kalıntısı, (d) tek kişilik yayıncının hak beyanının doğrulanamaması. Ticari
kullanım başlamadan önce bu kayıt yeniden değerlendirilmeli; yazara köken sorusunun
sorulması (HF depo tartışması) en ucuz çözüm yoludur.

## Doğrulanamayanlar (özet)

- İçerik kaynağı (çeviri / sentetik / insan), üreten model ve onun kullanım şartları.
- Üst kaynak veri setleri ve lisansları.
- MIT beyanının yayıncının hak zincirini gerçekten karşıladığı.
- Tüm 336.146 kayıtta rol sırasının (`system → user → assistant`) bire bir tutması
  (yalnız `/statistics` uzunluk=3 ve 100 satır doğrulandı; geri kalanı kart beyanı).
- Yanıtların olgusal doğruluğu; çeviri/sentetik kokunun tüm veride dağılımı.
- Gerçek kişiye ait PII bulunup bulunmadığı.
- Hak sahibi / kaldırma kanalı.

## Kaynaklar

- https://huggingface.co/datasets/AlicanKiraz0/Turkce-Atlas-Instruct
- https://huggingface.co/datasets/AlicanKiraz0/Turkce-Atlas-Instruct/raw/main/README.md
- https://huggingface.co/api/datasets/AlicanKiraz0/Turkce-Atlas-Instruct (sha, gated, cardData)
- https://huggingface.co/api/datasets/AlicanKiraz0/Turkce-Atlas-Instruct/tree/main
- https://huggingface.co/api/datasets/AlicanKiraz0/Turkce-Atlas-Instruct/tree/180fb437a6df27cc09505b72eec4bc536b6c113b
- https://huggingface.co/api/datasets/AlicanKiraz0/Turkce-Atlas-Instruct/commits/main
- https://datasets-server.huggingface.co/splits?dataset=AlicanKiraz0/Turkce-Atlas-Instruct
- https://datasets-server.huggingface.co/size?dataset=AlicanKiraz0/Turkce-Atlas-Instruct
- https://datasets-server.huggingface.co/info?dataset=AlicanKiraz0/Turkce-Atlas-Instruct
- https://datasets-server.huggingface.co/statistics?dataset=AlicanKiraz0/Turkce-Atlas-Instruct&config=default&split=train
- https://datasets-server.huggingface.co/first-rows?dataset=AlicanKiraz0/Turkce-Atlas-Instruct&config=default&split=train

Erişim tarihi: 2026-10-13
