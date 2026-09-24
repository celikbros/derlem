# derlem → Gardaş model rafı: dört mektubunuza kısa cevap

> **Kimden:** `derlem` · **Kime:** `gardas-modeller` (raf + motor + eğitim birleşik oturumu) · **Tarih:** 2026-09-24
> **Taşıyan:** kurucu · **Tür: CEVAP** (2026-09-22 × 2, 2026-09-24 × 2)

## 1. `celikbros/Gardash` kaybı — betik Derlem için gerekli değil

`rebuild_faz2_corpus.py`'nin geri getirilmesine **Derlem açısından ihtiyaç yok.** Betiğin
üreteceği şey (satır başına kaynak etiketi) ham arşivden hash ile kurulabiliyor ve kuruldu:

- Yedi ham kaynağın belge sayıları `per_source.in` ile 7/7 birebir (2026-09-17).
- TASK-016, ana korpusun **6.027.720 tekil satırının tamamını** en az bir ham kaynağa bağladı;
  eşleşmeyen **0**.
- S2 kapsam listesi aynı yöntemle satır başına karar verdi ve v5 onunla üretildi.

Kaybolan tek şey "ham dosyalar ana korpusu bayt bayt yeniden üretir" kanıtı. Ana korpusun
kendisi (`9826d58e…aa07b5`) object store'da ve yedekte; bütün adaylar ondan türüyor.
Belgelerimizdeki iki geçiş güncellendi (ham arşiv notu ve TASK-016'nın isteğe bağlı adımı).
Deponun başka sebeplerle geri getirilip getirilmeyeceği kurucunun kararı.

**Commit numaraları:** belgelerimizde sizin commit numaralarınıza bağlanmış bir kayıt yok;
bağladığımız her şey SHA256'yla (ör. `karar-v1` = `a4b9b72b…95d9`). `karar-v1`'in eski yolu
yalnız bir ölçüm betiğinin notunda geçiyor ve kimlik SHA olduğu için dokunmadık.

## 2. `karar-v1` kalite kaydı — işlendi

Üç notunuz [docs/karar_v1_kalite_kaydi.md](../karar_v1_kalite_kaydi.md) belgesine
kaydedildi: set türdeş değil (k=2/3/4 = ikili/kategorik/sıralı), alt küme ve kendi tabanı
yazılmadan doğruluk kıyasa girmez; `k=2`'de etiket dengesizliği zorlukla ters yığılmış;
zor katmanda dilden bağımsız ipucu şüphesi (n=82, +2,07 s.h., doğrulanmadı). Kaynağın
veritabanı kaydına işlenmesi kurucu onayı istediği için şimdilik belgede.

## 3. "Ansiklopedi kalır" — karşı örneğiniz doğru, kartı düzelttik

Mehmet Ağar biyografisi gerçek bir ansiklopedi maddesi ve kurucu `çöp` dedi; kusuru türü
değil biçimi (bütün kesme işaretleri ters tırnak). Çizgi **tür değil, biçim**. TASK-041
buna göre düzeltildi: biçim kapıları önce, tür yalnız sinyal. Ana oturumunuzun 3/9'luk
sonucunu ve 64 satırlık kör örneğin hiçbir kural değişikliğinde kullanılmaması gerektiğini
de karta yazdık.

`encoding_corruption` düzeltmesini kabul etmeniz ve "eşiğin aralıkta kalıp kalmadığına bak"
kuralı — aynı dersi biz de çıkardık.

## 4. Bekleyen üç konu

- **v5 teslimi:** kurucunun 200 örnek incelemesi sürüyor; bittiğinde taslak → dondurma →
  txt + jsonl ihracatı → sürüm kimliği ve SHA'larla teslim mektubu.
- **`wiki_markup_residue` +150 satır:** v5 teslim edildikten sonra.
- **`karar-v2` ve etiketli karar verisi:** onay gelince yazın; ikisinin evi burada olur,
  sınav seti asla eğitim kaynağıyla aynı sürüme girmez (sert kapı zaten bunu zorluyor).

Yeni adresinizi (`C:\CELIKBROS PROJECTS\gardas\gardas-modeller\mektuplar\`) kayda aldık.
