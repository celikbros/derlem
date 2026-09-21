# Görev kartları

Alt programcılara (ve onların ajanlarına) verilen iş emirleri burada durur.
Kartlar **İngilizce** yazılır (uygulayıcı taraf İngilizce talimatı daha isabetli
yorumluyor); sahiple yazışma ve commit mesajları Türkçe kalır.

## Kurallar

1. **"Bitti" = commit + push.** Diskte duran iş bitmiş sayılmaz; kart ancak
   `main`'e girince kapanır. (2026-08: 84 dosya / 1.469 satır sekiz gün commit'siz
   durdu — bu kural o yüzden var.)
2. **Her kartın ölçülebilir kabul kriteri vardır.** "Çalışıyor" değil, "şu komut şu
   çıktıyı verir." Ölçülmeden yazılan cümle bu oturumlarda beş kez yanlış çıktı.
3. **Kart kendi kendine yeter.** Uygulayıcı sıfırdan başlar; "geçen sefer
   konuştuğumuz gibi" yoktur. Amaç, gerekçe, kapsam, **kapsam dışı**, dosyalar,
   doğrulama komutu kartta yazılıdır.
4. **Moratoryum kapısı her kartta sorulur:** teslimat mı, düzeltme mi, yeni
   özellik mi? Yeni özellik ise sahibin açık onayı olmadan başlanmaz
   ([diyet_yol_haritasi.md](../diyet_yol_haritasi.md)).
5. Biten iş kartın altına **Report** bölümüyle raporlanır: ne yapıldı, doğrulama
   çıktısı, kapsam dışı bırakılan, commit SHA.

## Durumlar

`DRAFT` → `READY` (sahip onayladı) → `IN PROGRESS` → `IN REVIEW` → `DONE`
(veya `BLOCKED` / `DROPPED`, gerekçesiyle).

## Şablon

```markdown
# TASK-NNN — <title>

| Field | Value |
|---|---|
| Status | DRAFT |
| Kind | fix / delivery / feature |
| Moratorium | allowed / **owner approval required** |
| Estimate | … |
| Owner | (unassigned) |

## Goal
## Why
## Current state (measured)
## Scope
## Out of scope
## Design / approach
## Files
## Acceptance criteria
## Verification commands
## Risks / traps
## Report
```

## Çalışma planı (2026-09-19)

Beş fazlı plan: [plan_2026_09.md](../plan_2026_09.md). TASK-015…037 bu planın kartlarıdır
(DRAFT; onay isteyenler işaretli). Faz 1 = v2'nin rafa teslimi; sonrası sahip sırasıyla
çok dilli temel → Hugging Face alımı → distilasyon sınırları.

## Kartlar

| # | Başlık | Tür | Durum |
|---|---|---|---|
| [TASK-001](TASK-001-contribution-screen-fixes.md) | Contribution screen fixes (copy contradiction + checkbox layout) | fix | **DONE** — 2026-08-31, `d0160ab` |
| [TASK-002](TASK-002-contribution-task-type-registry.md) | Contribution backbone (`payload jsonb` + kanonik yayın + kanonik-okur worker) + ilk tip `response_edit_pair` — **Faz A** | feature | **IN PROGRESS** — Faz A, 7 dilim (S1–S7). **S1–S6 bitti**, 2026-09-13: worker kanonik kaydı okuyor; migration 000028; Go tip kayıt defteri + doğrulama; demet soru-cevabı ve düzeltme çiftini kanonik kayıt olarak, köken ve not dahil kayıpsız yazıyor (Go↔Python ortak fixture); web formu Go kayıt defterinden üretilen katalogdan — "Cevap düzeltme" ekranda; inceleyici düzeltmenin iki tarafını etiketli bölümler halinde görüyor. S7: belgeler ve ihracat kapısı testleri bitti; sahibin arayüz denemesi (API yeniden başlatma + worker) bekleniyor. Panel notu: [katki_gorev_tipleri_karar_notu.md](../katki_gorev_tipleri_karar_notu.md). |
| [TASK-003](TASK-003-large-download-write-timeout.md) | Large release downloads cut off by the server write timeout | fix | **DONE** — 2026-09-12, `110b77f`. Uçtan uca doğrulandı: 42.28 sn süren indirme tam geldi (önceden 30 sn'de kesiliyordu). |
| [TASK-004](TASK-004-contribution-bundle-silent-loss.md) | Contribution bundling silently loses data and mislabels purpose | fix | **DONE** — 2026-09-12. Amaç eşlemesi kayıt defterinde + hata varsayılanı; `free_text`+prompt reddi; demet alan filtresi. Entegrasyon testi gerçekten koştu. |
| [TASK-005](TASK-005-pii-scanner-language-honesty.md) | PII scanner reports "clear" on languages it cannot inspect | fix | **DONE** — 2026-09-13. `basic-tr-v2`: desteklenmeyen dilde `not_evaluated` (freeze bloke, incelemeye ilerlemez); migration 000027. Kontrol koşusu: v1 davranışı 9 testi kırmızı yaptı. Migration çalışma DB'sine uygulandı (2026-09-13, sahip onayıyla). |
| [TASK-006](TASK-006-preference-branches-identical.md) | Canonical preference records accept identical chosen/rejected branches | fix | **DONE** — 2026-09-12. `preference_branches_identical`; karşılaştırma eğitim sinyali alanlarında (bayrak/metadata hariç). |
| [TASK-007](TASK-007-silently-skipped-integration-tests.md) | 37 integration tests skip silently on every local run | fix | **DONE** — 2026-09-12, CI düzeltmesi 2026-09-13. `internal/testdb` + conftest: adres yoksa kırmızı, `_test` olmayan DB reddedilir; `scripts/test.ps1`; CI'da `DERLEM_SKIP_DB_TESTS` yasak. İlk CI kontrolü (log grep) kendi birim testini yakalayıp CI'ı kırmızı yapmıştı. |
| [TASK-008](TASK-008-leaked-test-schemas.md) | Integration tests leaked schemas into the working database | fix | **DONE** — 2026-09-13. Süpürücü: yaş şema adından, yalnız 1 saatten eski, eklenti içeren şema asla; her pakette TestMain + worker oturum başı. Çalışma DB'sindeki iki şema yedeklenip silindi (CASCADE etki alanı ölçüldü: dışarıda 0 nesne). |
| [TASK-010](TASK-010-recovered-objects-and-raw-archive.md) | Recovered objects + custody of the Faz-2 raw sources | ops | **IN PROGRESS** — 2026-09-19: 422 nesne depoda ve doğrulandı; ham arşiv alındı (9/9); 7 ham kaynağın 6'sı kayıtlı (wiki_oscar 2026-09-19, hak durumları S2'ye göre işlendi); açık: celik_gold kaydı (sor), restore tatbikatı
| [TASK-012](TASK-012-clean-candidate-v3.md) | Clean candidate v3: quality v2, held-out split, near-dedup, rejection report | feature | **DONE** — 2026-09-20: v3 üretildi ve kaydedildi; S2 kararıyla v3'ten süzülen **v4** üretildi (4.297.899 satır / 11.255.199.803 bayt, `23bfcdcf…`; held-out v2 1.641 satır `2dc81fcd…`), kaynak kayıtları `47c5748c…` / `596ae2fa…`, içe alındı; kapılar ve 200 örnek inceleme sırada; 7 sınır satırı için TASK-039
| [TASK-014](TASK-014-lineage-family-dedup.md) | Normalized dedup quarantines a source's own lineage family | fix | **DONE** — 2026-09-19. Tekrar kapısı yalnız ataları dışarıda tutuyordu; kardeş adaylar (v1/v3) ve parent'ın kayıtsız ham girdileri birbirini karantinaya sokuyordu (ölçüldü: 5.807.521 sahte kopya). `source_lineage_inputs` (000029, çoklu girdi) + "soy ailesi" dışlaması; API `lineage_input_source_ids`. Migration çalışma DB'sine uygulandı, parent'a 5 girdi bildirildi, kapı yeniden koştu: iki kaynak `unique`. Bakım taraması yalnız açılışta koşuyor → TASK-015. |
| [TASK-013](TASK-013-hacim-plani.md) | Volume plan: where the next tokens come from | plan | **PLANNED** — 2026-09-20: [hacim_plani_2026_09.md](../hacim_plani_2026_09.md); v4 ≈ 2,08 milyar token (kestirim), 2,6'ya açık 0,52; öneri Vikipedi pilotu + FineWeb-2 tur 2 parça (8,99 GB, ~76,8 GB tepe disk); go/no-go listesi kurucuda
| [TASK-015](TASK-015-periodic-maintenance-sweep-inside-the-worker.md) | Periodic maintenance sweep inside the worker loop (TASK-014 follow-up) | fix | **DONE** — 2026-09-19, `cc4e945`: bakım taraması `run_forever` içinde 5 dk'da bir (sahte-saat testleri, kontrol koşusu kırmızı); worker yeniden başlatıldı. |
| [TASK-016](TASK-016-parent-composition-by-raw-source-document.md) | Parent composition by raw source, document-boundary measurement, and the v2 rights contingency table | research | **DONE** — 2026-09-19: containment %100, exclusive attribution, length and bytes per scenario measured; decision was TASK-011's (S2)
| [TASK-017](TASK-017-hard-gate-no-pretrain-freeze-without.md) | Hard gate: no `pretrain` freeze without a registered eval/holdout reference source | fix | **DONE** — 2026-09-19, `cc4e945`: `QueueFreeze` pretrain'de eval/holdout referansı yoksa `eval_reference_missing`; entegrasyon testi + kontrol koşusu kırmızı; API yeniden başlatıldı. |
| [TASK-018](TASK-018-rehearse-pretrain-draft-freeze-txt-jsonl.md) | Rehearse pretrain draft → freeze → txt/jsonl export on the `_test` database with the 100k slice (Go half: draft + QueueFreeze; Python half: freeze + export jobs in-process) | delivery | **DONE** — 2026-09-20, `eff4d98`: Go + pytest provası `derlem_ci_test`'te geçti; freeze 0,62 MB/s (11,9 GB için ~5,3 sa kestirim), txt 30 MB/s, jsonl 28 MB/s; dekontaminasyon 43/43, 0 eşleşme; kod hatası yok
| [TASK-019](TASK-019-v2-release-draft-freeze-txt-jsonl.md) | v2 release: draft → freeze → txt + jsonl export → delivery letter with SHAs; post-export backup | delivery | **DRAFT** — plan 2026-09-19, Faz 1, 1.5 gün |
| [TASK-020](TASK-020-rejection-report-false-drop-audit-pack.md) | Rejection-report false-drop audit pack: stratified sheet (50 per reason) and byte-weighted scorer, no UI | ops | **DONE** — 2026-09-22: 706 satirlik sayfa raf tarafindan dolduruldu; kopya esleri duzeltmesinden sonra yanlis atma orani **%32,9** [%27,5-%38,9] (once %41,8 raporlanmisti); kurucu uyumu 50 satirda kappa 0,35. Karar: TASK-040 kural duzeltmesi.
| [TASK-021](TASK-021-read-only-observability-cli-job-durations.md) | Read-only observability CLI: job durations, queue depth, review throughput from existing columns (read-only session enforced in code) | ops | **DRAFT** — plan 2026-09-19, Faz 2, 1 gün; **onay ister** |
| [TASK-022](TASK-022-document-boundary-policy-note-fragments-vs.md) | Document-boundary policy note (fragments vs whole documents) for new intake and any re-derivation | research | **DONE** — 2026-09-19: [belge_sinirlari_politikasi.md](../belge_sinirlari_politikasi.md); sınırlar toplamada kaybolmuş; kurucu: (a) evet, (c) evet, (b) sonra; rafa soru hazır
| [TASK-023](TASK-023-licence-notes-for-turkish-hugging-face.md) | Licence notes for Turkish Hugging Face datasets in the TASK-011 format | research | **DONE** — 2026-09-19: `docs/haklar/` altında 6 not; FineWeb-2/mC4/Wikipedia `cleared` (ticari olmayan), HPLT/CulturaX `restricted`, OSCAR `blocked`; kurucu önerileri onayladı
| [TASK-024](TASK-024-overlap-pilot-one-pinned-turkish-wikipedia.md) | Overlap pilot: one pinned Turkish Wikipedia slice through the existing local-file intake, net-new share measured | research | **DRAFT** — plan 2026-09-19, Faz 2, 1 gün; **onay ister** |
| [TASK-025](TASK-025-language-on-contributions-and-language-partitioned.md) | Language on contributions and language-partitioned bundles | feature | **DRAFT** — plan 2026-09-19, Faz 3, 1.5 gün; **onay ister** |
| [TASK-026](TASK-026-quality-filter-language-honesty-tr-web.md) | Quality-filter language honesty: `tr-web-*` policies write `not_evaluated` for non-Turkish sources | fix | **DONE** — 2026-09-19, `90e5c21`: `tr-web-*` Türkçe olmayan kaynakta `not_evaluated`, 8 test, kontrol koşusu kırmızı
| [TASK-027](TASK-027-research-language-detection-options-that-run.md) | Research: language detection options that run in the Python 3.14 worker, measured against the fastText baseline | research | **DONE** — 2026-09-19: öneri alt süreç köprüsü (`DERLEM_LID_PYTHON`, SHA sabit), üretimle 30/30 aynı; üretim listesinin 2.000 karakter penceresi belgelendi; kurucu onayladı
| [TASK-028](TASK-028-language-detection-gate-job-with-a.md) | Language detection gate job with a stored per-source distribution; `detected_language` on sampled documents; mismatch risk reason | feature | **DRAFT** — plan 2026-09-19, Faz 3, 2 gün; **onay ister** |
| [TASK-029](TASK-029-per-language-reporting-in-the-release.md) | Per-language reporting in the release mixture report (bytes by detected distribution; PII/quality coverage per language) | feature | **DRAFT** — plan 2026-09-19, Faz 3, 1 gün; **onay ister** |
| [TASK-030](TASK-030-machine-readable-licence-registry-on-sources.md) | Machine-readable licence registry on sources with a code-enforced derivation rule | feature | **DRAFT** — plan 2026-09-19, Faz 4, 2 gün; **onay ister** |
| [TASK-031](TASK-031-licence-mixture-in-the-release-report.md) | Licence mixture in the release report, `intended_use` on releases, freeze gate on incompatible terms | feature | **DRAFT** — plan 2026-09-19, Faz 4, 1.5 gün; **onay ister** |
| [TASK-032](TASK-032-in-app-import-hf-dataset-job.md) | In-app `import_hf_dataset` job: pinned revision, licence required, one record = one document, shard-resumable — Wikipedia-tr first | feature | **DRAFT** — plan 2026-09-19, Faz 4, 3 gün; **onay ister** |
| [TASK-033](TASK-033-tokenizer-true-counting-with-a-registered.md) | Tokenizer-true counting with a registered tokenizer artifact (estimate kept; exact count added when configured) | feature | **DRAFT** — plan 2026-09-19, Faz 4, 1.5 gün; **onay ister** |
| [TASK-034](TASK-034-distillation-cost-estimate-approval-gate-hard.md) | Distillation cost estimate + approval gate + hard caps (calls/tokens, durable daily counter) + model-id validation | feature | **DRAFT** — plan 2026-09-19, Faz 5, 2 gün; **onay ister** |
| [TASK-035](TASK-035-distillation-per-prompt-durable-checkpoint-keyed.md) | Distillation per-prompt durable checkpoint keyed by request hash | feature | **DRAFT** — plan 2026-09-19, Faz 5, 2 gün; **onay ister** |
| [TASK-036](TASK-036-eval-set-registry-cross-release-contamination.md) | Eval-set registry + cross-release contamination re-check report | feature | **DRAFT** — plan 2026-09-19, Faz 5, 2 gün; **onay ister** |
| [TASK-037](TASK-037-release-lineage-diff-auto-datasheet-per.md) | Release lineage diff + auto datasheet per frozen release | feature | **DRAFT** — plan 2026-09-19, Faz 5, 2 gün; **onay ister** |
| [TASK-038](TASK-038-tr-corpus-provenance-wikipedia-share.md) | `tr_corpus` provenance: how much of it is Wikipedia paragraphs | research | **DONE** — 2026-09-20, `250368e`: `tr_corpus` baytının %94,0'ı Wikipedia metni (tam içerme, kesinlik/duyarlılık 1,0); öneri: kayıt `unknown` kalsın, köken artık bilinen
| [TASK-039](TASK-039-zlib-dependent-compression-rule.md) | `tr-web-*` compression-ratio rule depends on the zlib implementation (3.14 zlib-ng vs 3.13 zlib) | fix | **DONE** — 2026-09-21: zlib bagimliligi `tr-web-v3` icinde saf Python LZ77 ile kaldirildi (1.206 satirda iki yorumlayici ayni); manifest interpreter + zlib surumunu tasiyor.
| [TASK-011](TASK-011-ham-kaynak-hak-arastirmasi.md) | Rights research for the seven Faz-2 raw sources | research | **DONE (v2 için)** — 2026-09-19 kurucu kararı **S2, ticari olmayan kullanım**: kökeni bilinmeyenler ve TRT çıkar; wiki_oscar (mC4+Wikipedia, kaynağı içerikten doğrulandı), TTK, akademik, TDK kalır (son ikisi kapsamlı risk kabulü). Bedel baytın %5,33'ü. Ticari kullanımdan önce yeniden açılır. |
| [TASK-009](TASK-009-contribution-form-help.md) | Contribution form explains nothing | fix | **IN REVIEW** — 2026-09-16. Açıklama/ipucu/örnek metinleri Go kayıt defterinde (test zorlar); her alanda (?) yardım düğmesi; tip açıklaması; düzeltme çiftinde varsayılan köken "Model çıktısını düzenledim"; demet penceresinde konu önerileri + "kaç katkı demetlenecek" önizlemesi; hata mesajları alan adlarıyla. Köken = "kelimeleri kim yazdı" açıklaması; isteğe bağlı "Bilgi kaynağı" alanı (soru-cevap ve cevap düzeltmede; düz metin satırı taşıyamadığı için serbest metinde yok, test zorlar); form düz yazı tipinde. Sahibin ekran kontrolü bekleniyor. |

## Altyapı kapanış listesi (sahip onayı: 2026-09-12)

Sahip kararı: **"Belgeleri incelemeden önce altyapıyı doğru kurmamız lazım; daha
önce hiçbir şey incelenmeyecek."** Release #1'in insan incelemesi bu altı madde
kapanmadan başlamaz. Her madde "bitti" = commit + push + kartta Report.

| # | Madde | Kart | Durum |
|---|---|---|---|
| 1 | Demetlemede sessiz veri kaybı | [TASK-004](TASK-004-contribution-bundle-silent-loss.md) | **DONE** 2026-09-12 |
| 2 | PII tarayıcı dil dürüstlüğü | [TASK-005](TASK-005-pii-scanner-language-honesty.md) | **DONE** 2026-09-13 |
| 3 | Özdeş tercih dalları | [TASK-006](TASK-006-preference-branches-identical.md) | **DONE** 2026-09-12 |
| 4 | Katkı omurgası + `response_edit_pair` (Faz A) | [TASK-002](TASK-002-contribution-task-type-registry.md) | **IN PROGRESS** — S6/7 bitti (2026-09-13) |
| 5 | Sessizce atlanan **37** entegrasyon testini (29 Go + 8 worker) yerelde çalıştır; atlama görünür olsun | [TASK-007](TASK-007-silently-skipped-integration-tests.md) | **DONE** 2026-09-12 |
| 6 | **Çalışma veritabanına** sızmış iki test şemasını temizle (21 Ağu 2026); `_test` koruması + sızıntı süpürücüsü | [TASK-008](TASK-008-leaked-test-schemas.md) | **DONE** 2026-09-13 |

Ölçek altyapısı (bölümleme, presigned upload, PgBouncer, worker havuzu, üretim web
sunucusu) bu listede **değil**. Sahip kararı (2026-09-12): **ekip kullanıp ölçtükten
sonra**, ölçüm verisiyle boyutlandırılır. Duvarların listesi ve gerekçe:
[scalability_architecture.md](../scalability_architecture.md).

## Doğrulama notu

Kartlar yazıldıktan sonra 6 bağımsız ajanla koda karşı çürütme geçişinden
geçirildi (2026-08-30): TASK-001'de 7, TASK-002'de 20+ düzeltme çıktı; ikisi de
"yanlış yere gönderir" sınıfında hatalar içeriyordu (yanlış satır aralığı, git'te
olmayan migration'a dayanan talimat, worker'ın kanonik kaydı okuyamadığı gerçeği).
**Her kart programcıya verilmeden önce bu geçişten geçmeli**; ölçülmeden yazılan
cümle bu projede tekrar tekrar yanlış çıktı.

TASK-003 (2026-09-12) bunu bir kez daha gösterdi: kart ilk halinde "13 GB'lık
export indirilemiyor" diyordu, oysa o nesne bir export değil ve hiçbir release'de
yok; önerilen doğrulama komutu da **düzeltilmemiş kodda geçerdi**. Kabul kriteri
yazarken sorulacak soru "bu komut hatayı gerçekten üretiyor mu?" — üretmiyorsa
kriter değil, süstür. Aynı kartta ikinci tuzak: hız sınırı altında **kısa süren
koşu başarı değil, hatadır** (hata gövdesi küçüktür, hemen iner).

TASK-007 (2026-09-13) aynı dersin CI tarafı: "atlama olursa düş" diye eklenen CI
adımı kendi birim testinin bilerek bastığı satırı yakaladı ve CI'ı iki commit
boyunca kırmızı yaptı — kart ise CI sonucuna bakılmadan DONE raporlanmıştı.
**"Bitti" demeden önce CI'ın o commit için yeşil olduğu görülür.**
