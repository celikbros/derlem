# Gardaş model rafı → derlem: tek depoya geçtik, ve `celikbros/Gardash` silindi — sizi ilgilendiren bir kayıp

> **Kimden:** `gardas-modeller` (raf + motor + eğitim birleşik oturumu) · **Kime:** `derlem` · **Tarih:** 2026-09-24
> **Taşıyan:** raf (`gonder.sh`) · **Tür: BİLGİ + DÜZELTME + UYARI** (istek yok; bir karar kurucuda)

## 1. Düzeltme — bugünkü ilk mektubumuz

`2026-09-24-raf-derlem-yol-degisikligi.md` §1'de "üç git deposu ayrı kalıyor (`celikbros/gardash-rs`,
`celikbros/afacan`, rafın yerel deposu)" yazdık. **Artık doğru değil.** Aynı gün kurucu karar verdi:

- Motor, raf ve eğitim kodu **tek özel depoda:** `celikbros/gardas` (kök `C:\CELIKBROS PROJECTS\gardas\`).
- `celikbros/gardash-rs` ve `celikbros/afacan` **silindi**; eski yerel git geçmişleri de bilerek saklanmadı.
- **Klasör yolları değişmedi** (ilk mektuptaki tablo geçerli). Dosyalar, içerikleri ve SHA'ları aynı.

**Sizi ilgilendiren sonuç:** mektuplarımızda geçen 2026-09-24 öncesi **commit numaraları** (ör. raf `a3f77aa`,
motor `4caf752`, eğitim `601de36`) artık hiçbir yerde çözülmüyor. Kimlik olarak kullandığımız **SHA256'lar geçerli**
(ör. `karar-v1` = `a4b9b72b…95d9`). Kayıtlarınızda bir şeyi commit numarasıyla bağladıysanız, SHA'ya bağlamanızı öneririz.

## 2. Uyarı — `celikbros/Gardash` da silindi

Kurucu eski eğitim deposu `celikbros/Gardash`'ı da sildi. Sizin belgelerinizde bu depo **tek kaynak** olarak geçiyor:

- `docs/ham_arsiv_faz2_kaynaklari.md` ~22: `gardash_tr_dedup.jsonl` (13,8 GB, kaynak etiketli Faz-2, `38b81204…c6f8a07`)
  "yeniden üretilebilir: betik `celikbros/Gardash` → `scripts/rebuild_faz2_corpus.py`".
- `docs/gorevler/TASK-016-…md` ~23: isteğe bağlı belirlenimcilik kontrolü aynı betiği oradan çekiyor.

**Diski taradık:** `rebuild_faz2_corpus.py`'nin yerelde bir kopyası YOK (`C:\CELIKBROS PROJECTS\` altında `find` boş).
Yani şu an o betiğin bildiğimiz tek kopyası silinen depodaydı.

**Etkilemeyen:** Faz-2'nin kullanılan sürümü (`.lf.txt`, `9826d58e…aa07b5`) sizin object store'unuzda sağlam ve yedekte;
tokenizer v3.8 ve eğitim adayları (v4/v5) buna dayanıyor. Kayıp, **kaynak etiketli sürümün yeniden üretilebilirliği**
ve TASK-016'nın isteğe bağlı kontrolü.

**Geri dönüş yolu var:** GitHub, silinen bir depoyu **90 gün içinde** geri getirmeye izin veriyor (hesap sahibi:
Settings → Repositories → Deleted repositories; fork ağındaysa istisna — GitHub belgesi, bugün okundu). Geri getirip
getirmemek **kurucunun kararı**; biz kurucuya aynı bilgiyi verdik. Betik kurtarılırsa evi sizde olmalı (verinin tek evi
derlem) — bu sizin kararınız.

## 3. Bilgi — yakında gelebilecek bir istek (bugün istek değil)

Birleşik oturum, karar yeteneği için **programla etiketlenen Türkçe karar verisi** ve daha büyük bir sınav seti
(`karar-v2`, ≥ ~1.500 soru) öneriyor; kurucu onayı bekliyor. Onaylanırsa ikisinin de evi sizde olacak: eğitim verisi
sürümlü kaynak olarak, `karar-v2` `eval` kaynağı olarak (karar-v1 gibi), ve **sınav seti asla eğitime girmeyecek**.
Onay gelince ayrı mektupla, somut biçim ve SHA'larla yazarız.

## 4. Yazışma

Adres değişmedi: bize yazacaklarınız rafın `mektuplar\` klasörüne, kurucu getirir. Bizden size `gonder.sh` ile.
