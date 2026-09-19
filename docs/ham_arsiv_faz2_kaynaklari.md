# Faz-2 ham kaynak arşivi (`var/raw-derlem`)

**Tarih:** 2026-09-17
**Durum:** arşiv alındı ve doğrulandı; kaynak kaydı (Derlem `sources`) sırada
**Kaynak:** Gardaş model rafı mektubu
`gardas-modeller/mektuplar/2026-09-17-raf-derlem-ham-kaynaklar.md`

## Neden burada

2026-09-17'de kurucu iki şeyi sildi: OneDrive'daki eski yedek klasörü
(`OneDrive\aaaaaaa yedek\`) ve yerel `C:\CELIKBROS PROJECTS\gardash\` klasörü. Faz-2
derlemini üreten yedi ham kaynağın **tek kopyası** o yedekteydi; raf oturumu kurtardı
ve `C:\CELIKBROS PROJECTS\onedrive-kurtarma-2026-09-17\ham-derlem\` altına koydu.
**O kurtarma klasörü 2026-09-17'de silindi; içeriği artık yalnız `var/raw-derlem/`
altında.** Silmeden önce model rafı bizim kopyalarımızı bağımsız olarak ölçtü:
`ham-derlem` 9/9 OK, 422 nesnenin 422'sinde SHA = dosya adı, kazıyıcı kodunda
157/157 OK ve `diff -r` boş.
Veri atölyesi Derlem olduğu için kurucu kararıyla arşiv buraya alındı.

Silinen klasörle birlikte `gardash_tr_dedup.jsonl` (13,8 GB, kaynak etiketli sürüm,
`38b81204…c6f8a07`) da gitti. **Yeniden üretilebilir:** betik GitHub'da
`celikbros/Gardash` → `scripts/rebuild_faz2_corpus.py`, ama içindeki yollar artık
geçersiz. Faz-2'nin kullanılan sürümü (`.lf.txt`, `9826d58e…aa07b5`,
13.569.773.056 B) Derlem'in object store'unda sağlam ve yedekte.

## Arşivin yeri ve içeriği

```
C:\CELIKBROS PROJECTS\derlem\var\raw-derlem\
  ham-derlem\      7 korpus + SHA256SUMS + manifest + README_PRIVATE.md  (24,65 GB)
  celik_ai-kod\    TDK/TTK/haber/akademik kazıyıcılarının kodu (158 dosya)
  KURTARMA_README.md
```

| Kaynak | Dosya | Bayt | Belge | SHA256 (baş) |
|---|---|---|---|---|
| celik_gold | `celik_gold_corpus.clean.jsonl` | 13.001.668.604 | 4.460.931 | `28d053a5…` |
| wiki_oscar | `wiki_oscar_corpus.jsonl` | 12.811.797.729 | 4.253.739 | `3aaef2c2…` |
| ttk | `ttk_corpus.jsonl` | 113.165.227 | 84.789 | `edb6e151…` |
| academic | `academic_corpus.jsonl` | 64.958.602 | 45.208 | `22a7b875…` |
| tdk | `tdk_corpus.jsonl` | 16.177.989 | 118.455 | `bee0557a…` |
| trt | `trt_news_corpus.jsonl` | 1.098.941 | 388 | `4aae47a0…` |
| tr_corpus | `tr_corpus.txt` | 457.814.564 | 1.502.165 | `29a2099a…` |

Belge sayıları rafın ölçümü; yedi sayının yedisi de arşivdeki
`gardash_tr_dedup.jsonl.manifest.json` içindeki `per_source.in` ile birebir.
Tam hash listesi: `ham-derlem/SHA256SUMS` (9 satır). Kopyalama sonrası
`sha256sum -c` ile doğrulandı (2026-09-17, Derlem oturumu).

`celik_ai-kod`, bu kaynakların **nasıl toplandığının tek kaydıdır**; hak durumu
netleştirilirken gerekecek. Kurucu kararıyla arşivde tutulur, Derlem deposuna
(git) alınmaz — başka bir projenin kodudur.

## Yedek durumu: bilinçli olarak kapsam dışı

**Kurucu kararı (2026-09-17):** ham arşivin bulut yedeği olmayacak; tek yerel kopya
olarak duracak. Gerekçe: ham verinin kaybı telafi edilebilir, çünkü Faz-2 metni ve
temiz aday zaten object store'da ve yedekte. Risk bilinerek kabul edilmiştir.
`derlem_backup.py` bu klasörü kapsamaz ve kapsamasın
([backup_restore.md](backup_restore.md)).

## Hak durumu: `unknown` (açık iş)

Kaynaklar kayda alınırken `rights_status = 'unknown'` yazılır. Bu güvenli
varsayılandır: `unknown` bir kaynak sürüme (release) giremez. Hak araştırması ayrı
bir iş olarak açıktır ve ürün çıkmadan önce yapılacaktır
([TASK-011](gorevler/TASK-011-ham-kaynak-hak-arastirmasi.md)). `wiki_oscar` (Vikipedi
/ OSCAR türevleri), `tdk`, `ttk`, `trt`, `academic` (kazıyıcı çıktıları) ve
`celik_gold` için her biri ayrı değerlendirilmelidir; kazıyıcı kodu bu
değerlendirmenin girdisidir.

## Kaynak kaydı: durum (2026-09-19)

| Kaynak | Derlem kaydı | Hak durumu (S2 kararı, 2026-09-19) |
|---|---|---|
| `trt` | `faz2_ham_trt_20260918` | `blocked` |
| `tdk` | `faz2_ham_tdk_20260918` | `cleared` (kurucu risk kabulü, ticari olmayan) |
| `academic` | `faz2_ham_academic_20260918` | `cleared` (kurucu risk kabulü, ticari olmayan) |
| `ttk` | `faz2_ham_ttk_20260918` | `cleared` (CC BY-NC, ticari olmayan) |
| `tr_corpus` | `faz2_ham_tr_corpus_20260918` | `unknown` |
| `wiki_oscar` | `faz2_ham_wiki_oscar_20260919` (`e6f3b29b…`), içe alma v4 kapılarından sonra kuyruğa | `cleared` (belgeli lisans, ticari olmayan) |
| `celik_gold` | **kayıtsız** (TASK-010b; S2'de dışarıda, özgü kısmı %1,96) | `unknown` |

Hak dayanakları: [hak_kanit_paketi_2026_09.md](hak_kanit_paketi_2026_09.md). Beş küçük
kaynak ve `wiki_oscar`, ana korpusun (`gardash_faz2_tr_dedup_20260621`) girdileri olarak
bağlıdır (000029); bu yüzden tekrar kapısı onları kopya saymaz, PII kapısı ham metni
beklendiği gibi karantinaya alır. `wiki_oscar` dosyası `IMPORT_ROOT` altına kopyalanmadı,
**sabit bağ** (hard link) verildi: aynı disk, içe alma yalnız okur, arşiv kopyası değişmez.

Eski plan (kurucu kararı: küçükten büyüğe, iki büyük dosya en sonda):

1. `trt` → `tdk` → `academic` → `ttk` → `tr_corpus` (toplam ~0,65 GB) — yapıldı 2026-09-18
2. `celik_gold` ve `wiki_oscar` (13,0 + 12,8 GB) — `wiki_oscar` kaydedildi 2026-09-19
   (v4'ün soy kaydı için); `celik_gold` bekliyor

Her kaynak `IMPORT_ROOT` altına kopyalanıp yerel dosya içe alma yoluyla kaydedilir
(yalnız admin), `content_purpose = pretrain`, `rights_status = unknown`,
`lineage_ref` bu belgeye ve mektuba işaret eder. Kayıt sonrası normal kapılar
çalışır; `celik_gold`'un Faz-2 metninin girdisi olması nedeniyle normalize tekrar
kapısının onu **tekrar** sayıp karantinaya alması beklenir — bu doğru sonuçtur,
hata değildir.

Kaynak kaydı, `.lf.txt` için 2026-06-25'te yapılanın aynısıdır; yordam:
[gardash_seed_import.md](gardash_seed_import.md).
