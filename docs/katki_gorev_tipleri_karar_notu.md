# Katkı görev tipleri — karar notu (2026-09-12)

**Ne bu:** "Katkılar ekranındaki iki görev tipi (soru-cevap, serbest metin) yeter mi?
Çok alanlı veri kümeleri nasıl girilecek? Düşünce zinciri görev tipi mi?" sorularına,
altı bağımsız uzman merceği + her önerinin koda karşı doğrulanmasıyla üretilmiş cevap
(5 okuyucu, 6 panelist, 21 öneri için 21 doğrulama; 33 ajan, 2026-09-12).

**Nasıl okunmalı:** Her iddia `dosya:satır` taşır. §7'deki **beş "bugün canlı" hata
sahibin oturumunda satır satır ayrıca doğrulandı** (`contributions.go:189-208, 222`;
`pii.py:15-56`; `release_jobs.py:680`; `canonical.py:72-80, 115-140`). Diğer
bölümlerdeki satır referansları panel ajanlarının okumasıdır; uygulamaya alınmadan
önce ilgili kartın çürütme geçişinden geçer (`docs/gorevler/README.md`).

**Sonuç, tek cümle:** iki tip yetmiyor, ama eksik olan N yeni tip değil — bir aileyi
açan tek bir tesisat değişikliği; ondan önce de her yeni tipin miras alacağı beş sessiz
yanlışın kapatılması. Sıralama ve kartlar: §6 ve `docs/gorevler/README.md`.

---

## 1. İki tip yetiyor mu? **Hayır.**

Kaçamak yok: `qa_pair` + `free_text` iki *metin alanı* demektir, iki *veri türü* değil. Altı merceğin altısı da yetmez dedi ve kod bunu doğruluyor. Ama gerekçe önemli — eksik olan şey "seçenek listesi" değil:

- Bugün depolanan içerik tam olarak iki serbest metin kolonu: `prompt` (≤10k) ve `body` (1–100k) — `000020_contributions.sql:12-13`. `task_type` veritabanı seviyesinde `CHECK (task_type IN ('qa_pair','free_text'))` ile kilitli (`:10`).
- Demetleme `map[string]string{"id","text"}` yayınlıyor (`contributions.go:196`) — bu Go tipi üçüncü bir alanı veya iç içe değeri **tutamaz**; imza değişmeden hiçbir depolama düzeltmesi aşağı akışa ulaşmaz.
- `qa_pair` zaten geri döndürülemez biçimde düzleştiriliyor: `"Soru: "+prompt+"\n\nCevap: "+body` (`contributions.go:190-195`), ve kodun kendi yorumu bunun geçici olduğunu kabul ediyor (`:191-194`).
- API fazladan alanı sessizce atmıyor, **400 döndürüyor**: `decoder.DisallowUnknownFields()` (`json.go:35`).

Yani bugün üçüncü bir alan ne gönderilebilir, ne saklanabilir, ne demetlenebilir. Aynı anda: kanonik ihracat formatı zaten zengin yapılı kayıtları kabul ediyor (çok turlu konuşma, araç çağrısı, tercih çifti — `canonical.py:9-56`, `releases.py:747-802`), ve depoda çalışan bir tercih fixture'ı var (`data_samples/example_canonical_preferences.jsonl`). **Boşluk formatta değil, katkı kapısının tesisatında.**

Tek satırlık cevap: iki tip yetmiyor, ama eksik olan N yeni tip değil — bir aileyi açan tek bir tesisat değişikliği.

---

## 2. Gerçek veri kümelerinin BİRDEN FAZLA ALANI var — ne yapacağız?

**Doğru gözlem, ve krize dönüşmesi gerekmiyor.** Üç seçenekten hangisi:

| Seçenek | Verdict |
|---|---|
| Her şekil için ekstra metin kolonları | **Hayır.** Her yeni şekil bir migration + per-type CHECK demek, ve her kolon diğer tüm tipler için NULL/anlamsız kalır. RFC bunu adıyla reddetti (alternatif B, `versioned_data_profiles_rfc.md:402-422`). |
| Şema güdümlü motor / kullanıcı eklentisi | **Hayır.** Üç danışman + Derlem birlikte reddetti: "Profil, çalıştırılabilir kullanıcı eklentisi değildir… kod ve migration ile allowlist'e alınır" (`rfc:135-137`, `synthesis:71`). Ayrıca sınırsız JSONB'yi *kritik* alanlar için reddetti (`rfc:336, 414-417`). |
| **Tek `payload jsonb` + kanonik kayıt yayını + Go tarafında per-type anahtar şeması** | **Evet.** Dört koordineli düzenleme, N migration değil. |

Asgari dürüst değişiklik (birlikte yapılır, parça parça değil):
1. `payload jsonb NOT NULL DEFAULT '{}'` + `000020:10` CHECK'inin genişletilmesi; `prompt`/`body` eski iki-alanlı vaka olarak kalır.
2. `SubmitContributionInput`'a `payload` alanı + `normalizeAndValidateContribution` içinde **per-task-type izinli-anahtar şeması** (aksi halde jsonb, RFC'nin adıyla reddettiği doğrulanmamış çöplük olur).
3. `buildContributionJSONL`'ın `map[string]string` yerine `derlem.canonical-sample.v1` yayınlaması — worker bu şekli **zaten** ayrıştırıp ihraç ediyor, yani aşağı akışa yeni format eklenmiyor.
4. `contentPubposeForTaskType`'ın iki-dallı fallthrough'unun (`contributions.go:203-208`) açık bir per-type tabloya dönüşmesi. **Bu madde 1-3 ile aynı değişiklikte olmak zorunda** — gerekçesi §7'de.

Yan not: "binlerce sektör" sorusu bununla karışmasın. O zaten cevaplı ve alan sorunu değil: **alan bir etikettir, bölme değildir** (`alan_taksonomisi.md:12-13`), serbest metin 1–120 karakter, sektör başına ayrı katalog/veritabanı yok. Binlerce sektör bugün sıfır şema değişikliği istiyor.

### Vermesi gereken TEK karar

> **Hangi alanlar TİPLİ (birinci sınıf, doğrulanan, kapı koyulabilen, sorgulanabilen) olacak; hangileri tipsiz `metadata` içinde yolculuk edecek?**

Geri kalan her şey bu karardan mekanik olarak çıkar. Nedeni:

- `TOP_LEVEL_FIELDS` tam 14 anahtar (`canonical.py:26-41`); bilinmeyen anahtar `sample_unknown_fields` hatası veriyor (`:81, 305-308`) ve ihracatta bu hata kaydı atlamıyor — **tüm release'i bloke ediyor** (`releases.py:746-760`). Sürüm yükseltmek de kapalı: `unsupported_schema_version` (`:78-79`).
- `metadata` ise **sadece "dict mi"** diye kontrol ediliyor (`canonical.py:100, 300-302`) ve ihracata harfiyen kopyalanıyor (`releases.py:791`).

Dolayısıyla: **tipli istiyorsan format değişir** (whitelist-kapalı, release-bloke eden bir doğrulayıcıya dokunmak; mevcut tüm donmuş release'ler bugünkü whitelist'e göre doğrulanmıştı). **Tipsiz kabul ediyorsan ucuz** — ama o alan üzerinde kapı yok, lineage yok (`releases.py:792-801` dili/alanı hâlâ *kaynak satırından* alıyor), sorgu yok, ve o alanı okuyan bir kapı eksik/yanlış yazılmış etikette **boş geçer**. Bu ikinci durum tam olarak 0e5c7c5 şekli.

Bu karar bir kez verilir ve sonra her tip için tekrar tartışılmaz. Benim önerim: **çeviri dil çifti ve tercih verdict'i tipli olmak zorunda** (ikisi de kapı ve muhasebe gerektiriyor); *rationale, not, etiket kümeleri* metadata'da kalabilir. Ama bu senin çağrın.

---

## 3. Akıl yürütme / chain-of-thought: görev tipi mi, dik eksen mi?

**İkisi de — ama asimetrik, ve kodun kendisi hangi yarının hangisi olduğunu söylüyor.**

**Veri katmanında: dik bir ÖZELLİK.** `reasoning_content` ve `reasoning_visibility` **mesaj** alanları (`canonical.py:42-52`), kayıt alanı değil; `RECORD_TYPES` `{conversation, preference}` ile kapalı (`:10`). `record_type='reasoning'` yok ve olmamalı. `task_type` serbest metin olduğu için (`:92-96`) bugün `task_type='translation'` + asistan mesajında `reasoning_content` **zaten yasal**. Bir çeviri de, bir hukuk cevabı da, bir araç-kullanım izi de akıl yürütme taşıyabilir. Akıl yürütmeyi görev tipi yaparsan aynı veriyi beş slug altında beş kez toplarsın (`reasoning_qa`, `reasoning_translation`, …). Yanlış eksen.

**İş katmanında: ayrı bir GÖREV TİPİ.** Bir çözüm yazmak, iki türetmeyi karşılaştırmak ve adımları etiketlemek üç farklı insan işi: farklı alan kümesi, farklı kapı, farklı rubrik. Katkı kapısında "görev tipi" tam olarak bunu ifade ediyor (bir CHECK değeri + bir form + bir purpose eşlemesi). Yani akıl yürütme bir *kayıt şekli* değil, bir *iş şekli* ailesi.

**`reasoning_visibility` kanıtı — bunu bu oturumda kendim okudum (`canonical.py:206-218`):**

```
if visibility == "export_allowed": semantic_texts.append(reasoning)
else: message.pop("reasoning_content", None)
```

Bundan üç kesin sonuç çıkıyor:

1. **Akıl yürütme, Derlem'in toplayıp inceleyip kasten teslim ETMEYECEĞİ tek içerik türüdür.** Cevabın böyle bir şalteri yok. Bu onu ticari/hukuki olarak özel kılıyor (üçüncü taraf ToS maruziyeti, kaynak IP, iç kural sızıntısı, ~kat kat fazla PII yüzeyi orada). Bu, "özellik" tarafını güçlendiriyor: görünürlük `train_policy`'ye (bir ihracat-politikası ekseni) `task_type`'tan daha yakın.
2. **Görünürlük toplama-anında bir karardır, sonradan çevrilecek bir düğme değil.** `review_only`/`hidden` metni ihracata **hiç ulaşamaz**. TASK-002'de yazılı varsayılan `review_only` (`TASK-002:248-270`) ile rasyonel toplarsan, hiçbir release'in içerebileceği olmayan metin için katkıcıya ödeme yapıyorsun. Katkıcının onayında bunu peşinen söylemek zorundasın.
3. **Ve kaçak yol bu garantiyi sessizce deliyor:** pop **yalnız** `reasoning_content`'i alıyor; `metadata`'ya dokunmuyor. Yani "adımları `metadata.solution_steps`'e koyarım, görünürlük `review_only` olur" diyen tasarım, adımları ihracata **aynen gönderir** ve sen göndermediğini sanırsın. Yapılandırılmış akıl yürütme tasarlanmadan önce doğrulanması gereken tek şey bu.

Ek iki ölçülmüş sınır: `reasoning_content` **tek** boş olmayan string (`:206-210`) — tipli adım nesnesi, adım-başı verdict, process reward model verisi **ihraç edilemez**; ve bu en sonuçlu hukuki şalteri çeviren yol bugün şema doğrulaması olmayan bir textarea düzenlemesi (`document_handlers.go:156-172`: sadece UTF-8, boş değil, ≤1 MiB).

**Pratik kural:** `rationale` + `rationale_visibility`'yi *herhangi bir* tipin registry satırının açabileceği opsiyonel alan çifti yap. `qa_pair`'in kardeşi olarak `reasoning` tipi **açma** — ta ki otomatik bir doğrulayıcı olana kadar.

---

## 4. Bugün HAZIR olan (sıfır kod)

- `qa_pair`, `free_text` — uçtan uca çalışıyor (iki sessiz veri kaybı hariç, §7).
- **Tercih karşılaştırması** (prompt + chosen + rejected) — kanonik olarak yerli (`canonical.py:115-139`), dosya olarak yüklenebilir, ihraç edilebilir. Tek şart: kaynağın `content_purpose`'u `preference` olmalı.
- **Akıl yürütme izi** düz blob olarak + görünürlük redaksiyonu — yüklenen kanonik JSONL yolunda gerçekten çalışıyor ve testlerle sabitlenmiş (`test_canonical.py:16-80`).
- Çok turlu konuşma, araç tanımı + `tool_call`/`tool_result` id eşleşmesi (**kodda tek gerçek karşılık kontrolü**, `canonical.py:225-252`), çok kipli içerik.
- Bir çeviri çiftinin **iki metni** (iki mesaj olarak). Dil çifti hayır.
- **Binlerce sektör** — alan etiketi olarak, migration'sız.

Yani: lisanslı bir tercih, akıl yürütme veya çeviri korpusu **bugün** kaynak olarak yüklenebilir. Kapalı olan tek şey katkı kapısı.

## 5. Ne değişmesi gerekiyor — katman, maliyet

**A. Paylaşılan omurga (depolama) — ~8-12 iş günü.** §2'deki dört düzenleme + `contributions_test.go:9-66`'nın yeniden yazılması (iki-anahtarlı çıktıyı ve "Soru:/Cevap:" stringini sabitliyor) + `sampling.py:189-194`'ün kanonik satırları `missing_text_field` diye işaretlemeyi bırakması. Bu, TASK-002'nin kendi tahmini. **Her yapılandırılmış tip bunun arkasında** — tipe özel değil, ön koşul.

**B. Kapı işi — tipe göre 1-6 gün, ve bazıları hiç yok.** Kodda hiçbir yerde **iki alanı karşılaştıran** bir kapı yok (tek istisna yukarıdaki tool-id eşleşmesi, o da yalnız ihracatta). Ölçülmüş yokluklar: edit distance / diff / Levenshtein **hiç yok**; JSON Schema doğrulayıcı **hiç yok** (worker bağımlılıkları: `psycopg`, `pypdf`, `python-docx`); sandbox/`subprocess` çalıştırma **hiç yok**; script/Unicode-blok kontrolü **hiç yok** (tek script kodu Latin-vs-Kiril spam sinyali ve otomatik zincirde değil).

**C. İnceleme yüzeyi — 4-8 gün, ve bu kalem sürekli unutuluyor.** `readable-document.ts:4` **tüm** boşluğu (newline dahil) tek boşluğa indiriyor, sonra noktadan bölüyor: iki taraflı hiçbir kayıt insan tarafından görülemiyor. Rubrik beş düz 1-5 tam sayı (`source-inspector.tsx:69-75`) ve **aynı beşi** release kalite kapısı topluyor (`releases.py:19-25`) — yani yeni bir "karşılık/uygunluk" boyutu UI işi değil, **release politikası** işi.

**D. Format değişikliği gerekenler (ayrı, bir kereye mahsus karar — §2).** Tipli kaynak+hedef dil; tercih verdict'i / tie / both-bad / skor / annotator; yapılandırılmış akıl yürütme adımları; span offset'leri için metin sabitleme; per-kayıt otorite/yargı-yetkisi/`as_of_date`.

## 6. Sıralama

**0. Release #1'i teslim et. Başka hiçbir şey yok.** ~35 belge, 2-4 saat insan incelemesi. Moratoryum yalnız hata düzeltme, budama, dokümantasyon ve teslimat desteğine izin veriyor (`diyet_yol_haritasi.md:49-73`), ve §6 çeviri + tercih görevlerini **Faz C**'ye koyuyor (`katki_platformu_tasarimi.md:88-95`). Bu notta yazan hiçbir tip release #1'den önce başlamamalı.

**1. Moratoryum-içi düzeltmeler (feature değil, hata).** Sırayla §7'deki 1-5. Hepsi mevcut sessiz yanlışları kapatıyor; hiçbiri yeni endpoint/tablo istemiyor. `contentPurposeForTaskType` koruması Go'da yapılır, migration gerekmez.

**2. Release #1 + ikinci gerçek insan sonrası: paylaşılan omurga (§5A).** Tek değişiklik, bir aile açılıyor. Bunu tipten önce yap.

**3. İlk yeni tip: `response_edit_pair`.** Kodun desteklediği seçim bu — nedeni §8'de.

**4. Sonra:** `preference_pair` (verdict/tie muhasebesi format kararını bekler), `schema_extraction` (JSON Schema doğrulayıcı + versiyonlu kod kitabı kayıt defteri yazılırsa), `scope_boundary` (format açısından en ucuz tip: iki mesaj, tek dil, `instruction` purpose — ama `sensitive_review` politikası dokümanda var, kodda yok).

**5. Bekleyecekler:** `translation_pair` (12-18 gün: format kararı + per-dil PII + yan yana inceleme + dört yeni rubrik boyutu). Akıl yürütme **görev tipi** — doğrulayıcı var olana kadar hayır; doğrulayıcısız sürümü dürüstçe "tek stringlik sohbet turu" diye adlandır, önerilen tipin adını taşıtma. `reasoning_step_critique` **en son**: hedef kaydın tipli adımları olmadan anlamsız, üstelik işaret edecek kimliği de yok — `sample_id` bir kez doğrulanıp **bir daha kullanılmıyor** (`releases.py`/`similarity.py`'de sıfır kullanım), ihracat id'si türetilmiş bir hash (`releases.py:784-786`).

**6. Reddedilenler:** `script_variant_pair` — dejenere bir `translation_pair`; tek dil etiketini zorlamıyor, yani tek tipli çift tipi + disiplinli varyant etiketleriyle kapsanır; üçüncü registry satırı ikinci bir rubrik + protokol + PII politikası sürümü satın alır. `case_analysis` — dört katmanın hepsini birden değiştirmesi yetmiyor, üstelik hiç var olmayan bir **kredensiyel kayıt defteri** istiyor (`expert_reviewer` tek global rol, `000001_initial.sql:41`; per-alan yetkinlik alanı yok).

---

## 7. "Kontrol etmeden kontrol edildi mührü" — tip tip

Sahibinin endişesi (0e5c7c5 sınıfı: hak edilmemiş bir etiketin **değiştirilemez** donmuş manifestoya kazınması) burada bir ihtimal değil, **bazı yerlerde zaten canlı.**

### Bugün canlı olanlar — tip kararı beklemeden düzeltilmesi gerekenler

1. **PII mührü Türkçe olmayan metinde yalan söylüyor.** `PIIScanner.version = "basic-tr-v1"`; desenler TCKN, TR IBAN (`^TR`), TR cep (`05xx`), e-posta, kart. Kürtçe/Arapça metinde beş sayaç sıfır → `status = "clear"` (`pii.py:28-29`) → `gate_jobs.py` bunu kaynağa yazıyor → freeze yalnız `pii_status = 'clear'` kontrol ediyor (`release_jobs.py:680`). Yani **ku/ar bir kaynak, yapısal olarak inceleyemediği bir tarayıcıdan yeşil, freeze-yetkilendiren bir mühür alıyor.** 0e5c7c5'ten kötü: orada etiket ile sayaç çelişiyordu, burada çıktı gerçek temiz bir Türkçe taramasıyla **bit bit aynı**; tek ipucu `scanner_version`, ve hiçbir şey ona kapı koymuyor. **Gereken:** per-dil desenler + `not_evaluated` durumu + tarayıcı-sürümü/kaynak-dili kilidi. Herhangi bir AR/KU freeze'inden önce, tip tartışmasından bağımsız.
2. **`contentPurposeForTaskType` korumasız varsayılanı.** `if taskType == "qa_pair" { return "instruction" }; return "pretrain"` (`contributions.go:203-208`). CHECK'e yeni bir tip eklenip bu fonksiyona dokunulmazsa demet **kalıcı olarak** `pretrain` bir kaynak oluyor (`000001_initial.sql:102-117` trigger'ı ile değişmez), ve o kaynaktaki tercih kayıtları ihracatta sonsuza dek reddediliyor (`canonical.py:89-90, 116-117`) — hem de tüm release'i bloke ederek. Tek çare kaynağı yeniden kaydetmek. **Bugün bir koruma (`default: error`) koy.**
3. **`free_text` üzerinde `prompt` sessizce düşüyor** (`contributions.go:189`): API 201 dönüyor, satır veritabanına yazılıyor, demette yok. Ve **per-katkı `domain` hiç okunmuyor**: `Bundle` yalnız `(id, prompt, body)` seçiyor (`:222`), kaynağa demet-seviyesi etiket yazılıyor (`:280-283`). Hiçbir insan bu kaybı hiçbir aşamada göremiyor.
4. **Katkı yolunda `review_only` akıl yürütme korunmuyor.** Demetlenen satırın `schema_version`'ı yok → `parse_canonical_sample` `None` dönüyor (`canonical.py:76-77`) → ihracat düz metin dalını alıyor (`releases.py:810-829`) ve metni **aynen yazıyor**. Görünürlük seçicisini kanonik yayından **önce** göndermek, katkıcıya tutulmayan bir söz vermektir.
5. **`chosen == rejected` hiç kontrol edilmiyor.** `canonical.py:119-139` iki dalın *var olduğunu* doğruluyor, asla karşılaştırmıyor. Byte-byte aynı iki dal geçerli sayılıp ihraç ediliyor, ve `record_type_counts` bunu donmuş manifestoya "N tercih çifti" olarak yazıyor. En ucuz gerçek kapı bu (~yarım gün, `canonical.py` içinde — kapıda değil, çünkü kapı doğrudan dosya yüklemesiyle atlanır).

### Tip bazlı: kapısı olmayan her tipin ima ettiği yalan

| Tip | Eksik kapı | Mühür ne diyor, ne doğrulanmadı |
|---|---|---|
| `translation_pair`, `script_variant_pair` | Sayı/placeholder eşleşmesi, script-blok, uzunluk oranı, kopya, `src≠tgt` | "PII temiz + kapılar geçti" — hedef taraf hiç incelenmedi (madde 1) |
| `preference_pair`, `translation_post_edit`, `reasoning_preference` | Dal karşılaştırması; yargıç başına yanlılık; yeter sayı | Manifesto "N tercih çifti" diyor; bazıları sıfır sinyal. Ayrıca N inceleme saklanabiliyor ama **ilk tık statüyü belirliyor** (`documents.go:1421-1427`) |
| `response_edit_pair`, `correction_pair` | Edit distance / diff (kodda **hiç yok**) | İnsan onayı + beş metin-kalitesi puanı; düzeltme okuma panelinde **görünmüyor** (boşluk düzeltmeleri birebir aynı render ediliyor) |
| `schema_extraction` | `arguments` ↔ `input_schema` uygunluğu (JSON Schema kütüphanesi **yok**) | İhracat kaydı şemayı çıktının **yanına** koyuyor + `canonical_payload_sha256` ile imzalıyor → "bu çıktı bu şemaya uygundur" iddiası, hiç kontrol edilmemiş. Enum dışı etiket + yanlış tip + fazladan alan birlikte sorunsuz geçiyor |
| `reasoning_worked_solution`, `case_analysis` | Doğrulayıcı (sandbox çalıştırma **yok**), adım geçerliliği | "İncelendi" mührü, adımların birim olarak var olmadığı bir blob üzerinde. Doğrulayıcı gelmeden gönderilirse `verification_status: not_evaluated` **zorunlu** |
| `constrained_summary`, `sourced_qa`, `authority_extract`, `span_annotation` | Sayısal/kapsam/tarih/offset kontrolü | Katkıcının iddiası (`length_budget`, `no_new_facts`, `as_of_date`, span offset'leri) `metadata`'da, **imzalı** ihracata giriyor; "iddia edildi" ile "doğrulandı" ayırt edilemiyor. `span_annotation`'da ayrıca `_document_from_line`'ın sessiz `.strip()`'i (`sampling.py:245-246`) her offset'i kaydırıyor |
| `tool_call_trace` | `arguments` şema uygunluğu; çağrı→sonuç yönü (ters yön var, bu yön yok) | Var olan en iyi doğrulayıcı **yalnız ihracatta** çalışıyor; bozuk iz freeze'i temiz geçiyor, sonra **tüm** release'i bloke ediyor |
| Hepsi | `document_review_gate: "passed"` | İnceleyen, boşluğu ezilmiş prozayı beş metin-kalitesi boyutuyla puanladı. Etiket "insan yargıladı" diyor; yargılayamadığı şeyi değil |

**Genel kural, kararınıza dönüştürülmüş:** bir kapı yoksa, release sözleşmesinde ve kayıtta adını **anma**. 0e5c7c5'in gerçek düzeltmesi "bulamadı"yı "değerlendirmedi"den ayırmaktı (`releases.py:440` — `not_evaluated`). Yeni her tip aynı disiplini taşımak zorunda: eksik kapı **yok** olarak değil, `not_evaluated` olarak görünür.

---

## 8. Panelin anlaşmadığı yerler — kodun desteklediği taraf

1. **"Sorun alan sayısı" vs "sorun tesisat".** Çoklu-dilli mercek alan sayısını, yapılandırılmış ve veri-modeli mercekleri tesisatı öne çıkardı. **Kod tesisatı destekliyor:** `map[string]string` (`contributions.go:196`) ve `DisallowUnknownFields` (`json.go:35`), form veya taksonomi değil, gerçek duvarlar. Formdaki iki tip yedi yerde sabit ama **yalnız bir dal** gerçekten alan kümesini değiştiriyor (`contributions-panel.tsx:156-162`) — UI en ucuz katman.
2. **İlk hangi tip?** Tercih merceği `response_edit_pair`, yapılandırılmış mercek `schema_extraction`, veri-modeli merceği `preference_pair` dedi. **Kod `response_edit_pair`'i destekliyor:** üç metni kanonik olarak yerli (paylaşılan bağlam + chosen/rejected), her iki dal zorunlu olduğu için **tie/both-bad duvarına hiç çarpmıyor**, yeter sayı sorununu atlıyor, ve tek kapısı (diff) submit anında üç ayrı değer hâlâ elde iken en ucuz yerde çalışıyor. `schema_extraction`'ın kaldıraç iddiası doğru ama **satış argümanı uygulanamaz durumda**: şema uygunluğu doğrulayıcısı ve versiyonlu kod kitabı için tipli yer yok — `TOOL_FIELDS`'te sürüm alanı yok (`canonical.py:54`), `guideline_version`'ın üst seviye yuvası yok. Doğrulayıcı + kayıt defteri yazılırsa ikinci sıraya geçer.
3. **Tercih için format değişmeli mi?** Çoklu-dilli mercek "bugün çalışıyor", tercih merceği "yargı metadata'sı zorunlu, format değişmeli" dedi. **İkisi de farklı kayıt hakkında haklı:** indirgenmiş chosen/rejected bugün yerli ve fixture'lı; tie, both-unacceptable, skor, margin, annotator `PREFERENCE_FIELDS = {chosen, rejected}` küme-eşitliğiyle (`canonical.py:56, 122-126`) **imkânsız**. Karar §2'nin tek kararına bağlı. Eğer tipsiz kalırsa: tie'ları sessizce atma — **release raporunda say**, yoksa "bu korpusta tie yok"u "tie'lar atıldı"dan ayırt edemezsin.
4. **Akıl yürütme: özellik mi tip mi?** Altı mercek de "ikisi de" dedi; ağırlıkta ayrıldılar (%90 özellik ↔ eşit ağırlık). **Kod veri katmanında özelliği destekliyor** (mesaj alanı, `RECORD_TYPES` kapalı), **iş katmanında tipi** (farklı alan kümesi + rubrik + kapı). §3'teki ayrım bu.
5. **`release_jobs.py:556-567`'deki koşulsuz `"passed"` literalleri.** Bir mercek bunları "hiç girdisi olmayan" hak edilmemiş mühürler diye tanımladı. **Bu oturumda o bloğu kendim okudum: literaller gerçekten koşulsuz, ama daha yukarıdaki sert `ReleaseGateError` yükseltmelerinin arkasında** — yani etiket, *kendi koşuluna göre* hak edilmiş. Kodun desteklediği daha dar iddia şudur: yalan etikette değil, **koşulun ne anlama geldiğinde** (madde 1: `pii_status = 'clear'` = "Türkçe dedektörler bir şey bulamadı"). Aynı blokta `approximate_decontamination` için `not_applicable`/`not_evaluated` durumlarının var olması, uygulanacak deseni de gösteriyor.
6. **Kapı submit'te mi, ihracatta mı?** Mercekler bölündü. **Kod ikisini de gerektiriyor:** yalnız submit, doğrudan kanonik dosya yüklemesiyle atlanıyor; yalnız ihracat, 10.000 kaydın içindeki bir hatalı kaydın **tüm teslimatı** son adımda öldürmesi demek (`releases.py:746-760`). Yapısal değişmezler `canonical.py`'de (fail-closed), kullanıcıya dönük geri bildirim submit'te.

---

## 9. Belirsizlikler — dürüstçe

- Gün tahminleri kaba ve tek bir okuyucudan. TASK-002'nin kendi 8-12 günlük tahmini yalnız registry'yi kapsıyor; kapıları ve inceleme görünümünü **kapsamıyor**.
- ~35 belge / 2-4 saat figürü sizden geldi, doğrulamadım.
- "Faz C'yi öne çekmek" bir yönetişim kararı, uygulama kararı değil — TASK-002 bunu zaten "sahibin çağrısı, uygulayıcının değil" diye kaydetmiş (`TASK-002:5-8`).
- Doğrulanması gereken tek teknik varsayım, uygulamadan önce: **`metadata` içeriğinin `review_only` görünürlüğünden etkilenmediği** (§3, madde 3). Bunu kendim okudum ve pop yalnız `reasoning_content`'e vuruyor, ama yapılandırılmış akıl yürütme tasarlanacaksa uçtan uca bir testle sabitleyin.
- Bu notta önerilen hiçbir şey release #1'den önce başlamıyor. §7'nin 1-5 maddeleri hata düzeltmesi olarak moratoryuma sığar; omurga (§5A) sığmaz.