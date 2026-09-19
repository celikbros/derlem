# Belge sınırları politikası — parça mı, bütün belge mi (TASK-022)

**Tarih:** 2026-09-19 · **Hazırlayan:** Derlem oturumu (Claude) · **Karar:** kurucu ·
**Kart:** [TASK-022](gorevler/TASK-022-document-boundary-policy-note-fragments-vs.md) ·
**Dayanak:** TASK-016 ölçümleri, [canonical_exports.md](canonical_exports.md),
[temiz_aday_v3.md](temiz_aday_v3.md), [hak_kanit_paketi_2026_09.md](hak_kanit_paketi_2026_09.md)
(S2 kararı), raf mektupları 2026-09-17 / 2026-09-18, ham arşiv `var/raw-derlem/`
(salt okunur inceleme, 2026-09-19).

Bu not iki soruya cevap verir: yeni kaynaklar (ilk aday: Hugging Face alımı, TASK-032)
belge sınırını nasıl taşıyacak, ve Faz-2 ana korpusu sınırları koruyarak bir daha
türetilecek mi. Mevcut korpusta parça birleştirme bu notun kapsamı dışındadır (kurucu
kararı 2026-09-19: liste #2 ertelendi; [plan_2026_09.md](plan_2026_09.md)).

## 1. Ölçülen durum: ham kaynaklarda belge yapısı

Ham arşivdeki yedi dosyanın altısı JSONL, biri düz metin. JSONL kayıtlarının alanları
her dosyada aynıdır: **yalnız `text` ve `source`**. Başlık, gövde, paragraf, madde başı,
makale kimliği gibi ayrı bir alan hiçbir dosyada yok (ilk 2.000 kaydın anahtarları
sayıldı; `celik_gold` ve `trt` dahil).

Paragraf sonu (`\n`) kayıt metinlerinde de yok: `wiki_oscar` ilk 100.000 kaydın 10'unda,
`celik_gold` ilk 100.000 kaydın 38'inde; `ttk`, `academic`, `tdk`, `trt` ilk 2.000 kaydın
0'ında. Sebep toplayıcıda: `clean_and_normalize` (arşivdeki
`celik_ai-kod/CELIK_AI/celik_training/data_pipeline/cleaner.py`, satır 36) her boşluk
dizisini tek boşluğa indirir (`re.sub(r'\s+', ' ', text)`), köşeli parantez içini siler.
Yani sınır kaybı **Faz-2 birleştirmesinde değil, toplama anında** oldu.

| Ham kaynak | Kayıt = ne (toplayıcı kodundan) | Ortalama karakter / < 120 payı (TASK-016) | Ne korunmuş | Ne kaybolmuş, nerede | Ham dosyadan sınır korunarak yeniden türetme kazandırır mı |
|---|---|---|---|---|---|
| `wiki_oscar` (4.253.739) | Bir Wikipedia maddesi ya da bir mC4 sayfası; `source` = `wikipedia` (%9,4) / `mc4` (%90,6) | 2.737 / %0,9 | Belge sınırı (kayıt = belge) | Paragraf sonları, toplayıcıda | **Hayır** — paragraf sonu ham dosyada da yok |
| `ttk` (84.789) | **Bir `<p>` paragrafı** (> 50 karakter); `ttk_scraper.py` 26–30 | 1.180 / ilk 20.000'de p50 676, %5,0 < 120 | Paragraf sınırı | Makale sınırı, toplayıcıda; makale kimliği kayıtta yok → paragraflar makaleye geri birleştirilemez | **Hayır** |
| `academic` (45.208) | Bir OAI-PMH `dc:description`; "Başlık . Özet" tek dizgi (ilk 20.000'de 18.798'inde ` . ` ayracı; 1.197'si, %6,0, yalnız başlık) | 1.278 / — | Özet sınırı | Başlık/özet ayrımı (ayrı alan yok; ` . ` sezgisel), toplayıcıda | **Hayır** (başlığı ayırmak sezgisel kural ister) |
| `tdk` (118.455) | **Bir anlam tanımı ya da bir örnek cümle** (> 20 karakter); `tdk_scraper.py` 42–48 | 85 / **%77,2** | — | Madde başı ve madde bütünlüğü, toplayıcıda (arşivdeki dosyada madde başı yok; koddaki `word: definition` biçimi ve `source` etiketi arşiv dosyasıyla eşleşmiyor — kod, dosyayı üreten sürüm değil) | **Hayır** |
| `tr_corpus.txt` (1.502.165) | Satır = paragraf. İlk 500 satırın **366'sı** `wiki_oscar`'ın ilk 200 kaydının içinde geçiyor (normalize edilerek); ilk 500'de p50 464, 41'i < 120 | 278 / **%39,0** | — | Aynı maddelerin paragraf parçaları; ana korpus aynı maddeyi hem bütün (`wiki_oscar`) hem paragraf paragraf (`tr_corpus`) taşıyordu, yakın kopya kuralı alt dizgiyi yakalamaz | Kaynak S2 ile dışarıda |
| `celik_gold` (4.460.931) | Diğer dosyaların birleşimi (%99'u başka dosyada; kendine özgü %1,96 bayt) | 2.647 / — | Diğerleriyle aynı | Diğerleriyle aynı | Kaynak S2 ile dışarıda |
| `trt` (388) | Haber metni | 2.552 / — | Belge sınırı | — | `blocked` |

**Ana korpus (Faz-2) kayıt sınırını korudu:** TASK-016 içerme ölçümü %100 — her ham kayıt
ana korpusta bir satır, ana korpusun her satırı bir ham kayıt. Faz-2 birleştirmesinin
kaybettiği tek şey kaynak etiketidir (`gardash_tr_dedup.jsonl` silindi; S2 süzmesi etiketi
hash ile yeniden kuruyor). Rafın 2026-09-17 dilim ölçümü (100.000 satır): 120 karakter
altı satır **%11,84 (baytın %0,44'ü)**, yalnız başlık kalıbı 61 satır (%0,061); "başlık +
gövde" satırları `academic` kalıbıdır.

**S2'nin sınır bilançosu (kestirim, v4 üretilince manifestten ölçülür):** ana korpustaki
≈ 713.000 kısa satırın ≈ 586.000'i `tr_corpus`'tan (1.502.165 × %39,0). `tr_corpus` çıkınca
v4'te 120 karakter altı satır ≈ 120–130 bin / ≈ 4,3–4,5 milyon satır ≈ **%3** (bayt olarak
< %0,2). Kalan kısa satırların kaynağı `tdk` (≈ 76 bin), `wiki_oscar` (≈ 38 bin), `ttk`
(≈ 4 bin) ve `academic` yalnız-başlık kayıtları (≈ 3 bin).

## 2. Sınırlar bugün nasıl taşınıyor

- **Alım:** kaynak dosyada bir satır = bir belge. `.jsonl` de kabul edilir
  (`ingest_jobs.py` 246); JSON satırında `text` / `content` / `body` alanı varsa belge
  metni o alandır (`sampling.py` 304–308) ve alan içindeki `\n` **korunur** (JSON kaçışı).
  Yani bugünkü alım, paragraf sonlu bir kaydı kod değişikliği olmadan taşıyabiliyor.
- **Temiz aday, kalite süzgeci, PII, tekilleştirme, held-out:** satır başına çalışır; belge
  = satır. Normalize tekilleştirme boşluk dizilerini tek boşluğa indirdiği için `\n` ile
  boşluk aynı sayılır; held-out kuralı satırın baytlarını hash'ler. **Belge sınırını
  değiştiren her karar held-out üyeliğini değiştirir** → yeni nesne, yeni SHA, 200 örnek
  incelemesi sıfırlanır.
- **JSONL ihracat:** kayıt başına `text`; belge sınırı = kayıt; metin içindeki `\n`
  korunur ([canonical_exports.md](canonical_exports.md), "JSONL Kaydı").
- **TXT ihracat:** belge başına tek satır; `CRLF`, `CR`, `LF` → **tek boşluk**
  (`releases.py` 838: `text.replace("\r\n", "\n").replace("\r", "\n").replace("\n", " ")`).
  Paragraf sınırı düz metinde silinir; belge sınırı (satır) kalır.

Bugünkü girdiler zaten satır başına belge ve `\n`'siz olduğu için iki ihracat aynı sınırı
taşıyor; fark ancak paragraf sonlu yeni kaynaklarda doğar. Düzleştirme sonradan bedava,
geri alma imkânsız: bu yüzden **saklanan nesne** sınırı korumalı, düzleştirme yalnız txt
ihracatında olmalı.

## 3. Seçenekler ve bedeli

Varsayımlar: Claude günü = 8 saat, bekleme hariç (plandaki kural). v3 tam hattı 13,57 GB
için 3,4 saat makine; TASK-016'nın 24,65 GB ham + ana korpus üzerinde bir hash geçişi
≈ 21 dk. "İnceleme sıfırlaması" = yeniden örnekleme + 200 örnek için 2 sahip oturumu
(0,5 sahip günü) + held-out sayısının/SHA'sının değişmesi (rafa yeni mektup).

| Seçenek | Ne yapılır | Claude günü | Makine | İnceleme sıfırlaması | Sınır kazancı |
|---|---|---|---|---|---|
| **(a) Yeni alımda bütün kayıt, paragraf sonları JSONL'de** | HF alımı (TASK-032) kaydı bölmeden `{"text": …}` JSONL nesnesi yazar; `\n` metinde kalır; txt ihracatı birleştirir (mevcut kural). Mevcut korpusa dokunmaz. TASK-024 pilotu da kaydı **txt değil JSONL** olarak yazmalı, yoksa `\n` boşluğa iner. | **0 ek** (TASK-032'nin 3 gününün içinde; kural bir fixture testi = ~0,25 gün, kartta zaten var) | 0 | **0** | Yeni kaynaklarda belge + paragraf sınırı tam |
| **(b) Faz-2'yi ham JSONL'den sınır koruyarak yeniden türetme** | 10.465.675 ham kaydı yeniden tekilleştirip v3 hattından geçirmek. **Ölçüm bunun boş olduğunu gösteriyor:** ham JSONL'de paragraf sonu yok (§1); kazanılacak tek şey kaynak etiketi, onu da S2 süzmesi (v4) hash ile zaten kuruyor. Gerçek sınır kazancı ancak kaynağın kendisinden (HF `wikimedia/wikipedia`, `allenai/c4` tr) yeniden indirmeyle olur — o iş TASK-032'dir, (b) değil. | **≈ 2** (Gardash'taki `rebuild_faz2_corpus.py` yolları geçersiz, determinizmi doğrulanmamış; TASK-016 sayılarıyla karşılaştırma) | ≈ 1 saat tekilleştirme + 3,4 saat v3 hattı + 25 dk dil listesi (kestirim) | **1** (200 örnek + 2 sahip oturumu; held-out değişir) | **0** — bu yol **v5** olur (v4 = v3'ün S2 süzgeci) ve sınır getirmez |
| **(c) v3/v4 v2 teslimatı olarak kalır** | Hiçbir şey. v4'ün kendi sıfırlaması S2 kararıyla verildi, bu politikaya bağlı değil. | **0** | 0 | **0** | v4'te kısa satır ≈ %3 satır / < %0,2 bayt (kestirim); `ttk` paragraf, `tdk` tanım, `academic` başlık+özet olduğu gibi kalır |

Okuma: (a) ve (c) birlikte bedelsizdir ve çelişmez. (b)'nin gerekçesi ölçümle düştü;
"sonra" demek de fazla — sınır isteniyorsa yol TASK-032'nin Vikipedi-tr / mC4-tr alımıdır
(disk ve go/no-go sayılarıyla, TASK-013). Mevcut korpusta `ttk` paragraflarını makaleye,
`tdk` tanımlarını maddeye geri birleştirmek ham dosyadan **mümkün değil** (kimlik yok);
ancak yeniden toplamayla olur, o da hak araştırması bitmeden önerilmiyor
(2026-09-18 mektubu §5).

## 4. HF alım kuralı: bir kayıt = bir belge, asla bölünmez

TASK-032 ve TASK-024 için bağlayıcı kural:

1. Veri setinin bir kaydı Derlem'de **tam olarak bir belge**dir. Kayıt cümleye, paragrafa,
   uzunluğa göre bölünmez; iki kayıt birleştirilmez. Kabul ölçütü: kayıt sınırından kısa
   belge sayısı 0 (TASK-032 kartındaki ölçüt).
2. Belge metni, manifestte adı yazan **tek metin alanı**dır (Wikipedia'da `text`).
   Başlık ayrı alandaysa metne eklenmez, alım kaydında metadata olarak durur; manifest
   `text_field` ve `title_field`'ı yazar. (`academic`'in "Başlık . Özet" kalıbı yeniden
   üretilmez.)
3. Metin içindeki paragraf sonları (`\n`, `\n\n`) **saklanan JSONL nesnesinde korunur**;
   tek boşluğa indirme yalnız txt ihracatında olur. Alım nesnesi txt değil JSONL yazılır.
4. Uzunluk kuralı yok: kısa kayıt kısa belge olarak kalır (rafın 2026-09-17 §1 görüşü,
   kurucu kararı 2026-09-18). Kalite süzgeci belgeyi bütün olarak değerlendirir.
5. Kayıt sayısı, metin alanı, sabit sürüm SHA'sı ve satır sırası manifeste yazılır; aynı
   sürümden iki alım aynı nesne SHA'sını verir.

## 5. Kurucu kararı

**Kurucu kararı (tarih: —):** (karar bekliyor — öneri: (a) evet, (c) evet, (b) sonra)

**Rafın cevabı:** henüz sorulmadı (aşağıdaki paragraf sonraki mektuba girer).

## 6. Rafa soru (sonraki mektuba, olduğu gibi)

> **Belge sınırı sorusu.** Paketleme (sequence packing) bütün belge mi ister, parçalar
> sorun çıkarır mı? Ölçülen durum: v4'e girecek dört ham kaynakta kayıt sınırı korunmuş
> ama paragraf sonu yok (toplayıcı her boşluk dizisini tek boşluğa indirmiş); `ttk`
> kaydı bir makale değil bir `<p>` paragrafı (ortanca 676 karakter), `tdk` kaydı bir tanım
> ya da bir örnek cümle (ortalama 85 karakter, %77,2'si 120'nin altında), `academic` kaydı
> "Başlık . Özet" tek dizgi (%6'sı yalnız başlık). 120 karakter altı satır ana korpusta
> satırın %11,84'ü, baytın %0,44'ü; v4'te kestirim ≈ %3 satır. Yeni Hugging Face alımında
> kuralımız "bir kayıt = bir belge, asla bölünmez"; paragraf sonları JSONL'de korunur,
> txt'de tek boşluğa iner. Sizden istediğimiz tek cevap: paketleme belge sınırında
> EOS/ayraç koyuyorsa 85 karakterlik bir sözlük kaydı sizin için bir belge mi, gürültü
> mü — yani parçalar kalsın mı, yoksa bir eşiğin altındakiler için sayı verir misiniz?
> Eşik verirseniz txt'de paragraf sonu için `\n` yerine bir ayraç isteyip istemediğinizi
> de yazın. 2026-09-18'deki "kısa satırlar kalsın" kararı bu cevap gelene kadar geçerli.

## Kaynaklar

| Bilgi | Kaynak |
|---|---|
| Kaynak başına içerme, uzunluk, bayt senaryoları | [TASK-016](gorevler/TASK-016-parent-composition-by-raw-source-document.md), ölçüm 2026-09-19 |
| Ham kayıt alanları, `\n` sayımları, `tr_corpus` alt dizgi eşleşmesi, `academic`/`ttk`/`tdk` ilk 20.000 uzunlukları | `var/raw-derlem/ham-derlem/`, salt okunur, 2026-09-19 |
| Toplayıcı davranışı | `var/raw-derlem/celik_ai-kod/CELIK_AI/corpus_builder/scrapers/{ttk,tdk,academic,mc4}_scraper.py`, `celik_training/data_pipeline/cleaner.py` |
| Alım ve ihracat davranışı | `worker/src/derlem_worker/sampling.py` 280–308, `jobs/ingest_jobs.py` 246, `releases.py` 838; [canonical_exports.md](canonical_exports.md) |
| Kısa satır ölçümü ve rafın görüşü | [2026-09-17 ölçüm mektubu](mektuplar/2026-09-17-derlem-raf-temizlik-olcumu.md) §4, §9; [2026-09-18 mektubu](mektuplar/2026-09-18-derlem-raf-kararlar-ve-v3.md) §1 |
| S2 kararı ve v4 yolu | [hak_kanit_paketi_2026_09.md](hak_kanit_paketi_2026_09.md), "Kurucu kararı (2026-09-19)" |
