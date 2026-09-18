# Veri Yonetişimi

## Ana Kural

Toplanan veri otomatik olarak egitim verisi sayilmaz. Her kayit bir yasam dongusunden gecer:

1. Katki alindi
2. Otomatik filtrelerden gecti
3. Insan incelemesine girdi
4. Kalite skoru aldi
5. Veri havuzuna atandi
6. Egitim veya eval icin uygunlugu belirlendi

Buyuk pretraining corpus icin ayni kural dosya seviyesinde uygulanir. Bir kaynak sisteme girmis olabilir, fakat lisans, PII, dedup, kalite ve release gate'leri tamamlanmadan `pretraining_releases` havuzuna alinmaz.

## Asla Dogrudan Kullanilmayacak Icerikler

- Kisisel veri veya ozel mesajlar
- Telif hakki supheli uzun metinler
- Kaynaksiz tibbi, hukuki, finansal kesin tavsiyeler
- Nefret, taciz, spam veya manipülatif siyasi propaganda
- Otomatik uretilmis ve insan tarafindan denetlenmemis metin yigini
- Tekrarli, sisirilmis veya puan kazanmak icin uretilmis dusuk kalite icerik

## Kalite Boyutlari

Her katki asagidaki boyutlarla puanlanir:

- Dogal Turkce
- Anlam sadakati
- Bilgi dogrulugu
- Gorev uyumu
- Aciklik
- Ozgunluk
- Risk seviyesi
- Egitime uygunluk

## Egitim/Eval Ayrimi

Eval verisi egitimde kullanilmaz. Eval havuzuna ayrilan kayitlar kapali tutulur, tekrarli gorevlerde katilimcilara gosterilmez ve model egitim pipeline'ina girmez.

Buyuk corpus release oncesinde eval/holdout sizintisi icin overlap kontrolu yapilir. Eval kaynaklari checksum, n-gram veya MinHash benzeri yontemlerle training corpus'tan ayrik tutulur. Eval havuzundaki ornek metinler public raporlara yazilmaz.

## Hicbir Metin Yerinde Temizlenmez (kurucu karari, 2026-09-17)

Temizlik, filtreleme ve normalizasyon **hicbir zaman** var olan bir dosyanin ya da
nesnenin uzerine yazmaz. Her temizlik adimi:

1. **Yeni nesne** uretir (icerik adresli depoda ayri bir dosya),
2. **Yeni SHA256** tasir (kimlik path degil, icerik hash'idir),
3. **Yeni surum adi** alir (ornek: `..._clean_candidate`, `..._v2`).

Girdi oldugu gibi kalir; boylece her turev, girdisinin hash'inden geriye dogru
izlenebilir ve bir temizlik karari yanlis cikarsa geri donulecek bir sey vardir.
Uygulamada bunu zorlayan noktalar: temiz aday ureticisi girdinin uzerine yazmayi
reddeder (`derive_clean_candidate`, test: `..._refuses_to_overwrite_input`), depo
nesneleri degismezdir (immutable) ve dondurulmus surum manifesti geriye donuk
degistirilemez.

Modeller **yalnizca dondurulmus bir surumden** egitilir; egitilen modelin kunyesine
o surumun SHA'si yazilir. Bir model "hangi veriden egitildi" sorusuna path ya da
klasor adiyla degil, bu SHA ile cevap verir.

## Turev, Girdisinden Daha Temiz Olamaz (kurucu karari, 2026-09-17)

Turetilmis bir kaynagin hak durumu, girdisinin hak durumundan daha iyi olamaz.
Girdi `unknown` ise turev de `unknown`'dir; temizlik (PII ayiklama, tekrar alma,
kalite suzgeci) metnin hakkini degistirmez. Hak durumu yalniz kaynak bazli hak
arastirmasiyla yukseltilir, turetme islemiyle degil.

## Sinav Seti Olmadan Pretrain Surumu Dondurulmaz (kurucu karari, 2026-09-17)

`eval`/`holdout` amacli en az bir kaynak kayitli olmadan hicbir `pretrain` surumu
dondurulmaz. Gerekce: bu kaynaklar yokken dekontaminasyon kapilari
`not_applicable` doner; surum donar ama sinav kirliligi kaniti uretilemez ve o
surumle egitilen modelin karnesi dayanaksiz kalir. Bu kaynaklar amac alani geregi
bir `pretrain` surumune dahil edilemez.

**Held-out nasil secilir (kurucu karari, 2026-09-18; kural afacan'in,
`afacan-held-out-v1`):** dosya beklenmez, kural uygulanir. Belge = satirin sondaki LF
haric ham baytlari; `int(sha256(baytlar)[:8], 16) % 2500 == 0` ise held-out. Konumdan
ve yeniden uretimden bagimsizdir: ayni belge her surumde ayni tarafa duser. Derlem bu
bolmeyi temiz aday uretiminde, kalite suzgecinden sonra ve ortak tekillestirmeyle
yapar ([temiz_aday_v3.md](temiz_aday_v3.md)); held-out ayri bir `holdout` kaynagi
olarak kaydedilir. Birebir kirlilik kapisinin 0 vermesi yapi geregidir; bu, dis bir
sinav setine karsi kirlilik olmadigi anlamina gelmez, kendi bolmemizin dogru
yapildigini kanitlar. Gorev sinavlari (ornegin "karar" dersi) ayri `eval` kaynaklari
olarak gelir.

Not: bu kural bugun surec kuralidir; kodda sert kapi degildir (`QueueFreeze`
sinav kaynagi yoklugunu engellemez). Sert kapiya cevrilmesi ayri bir istir.

## Release Dondurma Kurali

Bir corpus release'i donduruldugunda sunlar degistirilmez:

- Canonical text view
- Manifest
- Checksum paketi
- Dedup ve mixture raporlari
- Normalizasyon karari
- Tokenizer registry karari

Yeni veri veya temizlik karari gerekiyorsa mevcut release degistirilmez; yeni release acilir.

`C:\CELIKBROS PROJECTS\gardash` tarafindaki mevcut v3.8 Faz 2 release bu kurala tabidir. Atolye yeni veri eklediginde v3.8 manifest'i geriye donuk degistirmek yerine yeni bir release id uretir.

## Kaynak/Shard Bazli Onay

Buyuk corpus kaynaklarinda inceleme kayit bazli degil, kaynak veya shard bazli yapilir:

- Her kaynak once lisans/KVKK kapisindan gecer.
- Otomatik kalite raporu kaynak ve shard seviyesinde uretilir.
- Moderator veya uzman stratified ornekleri inceler.
- Onay karari tum kaynaga, belirli shard'lara veya sadece temizlenmis alt kumeye verilir.

Insan tarafindan uretilen instruction, preference, answer review ve eval verisi icin kayit bazli review devam eder.

## Riskli Alanlar

Tıp, hukuk, finans, tarihsel iddialar, din, siyaset ve hassas toplumsal konular icin varsayilan havuz `sensitive_review` olur. Bu veriler uzman veya guvenilir moderator incelemesi olmadan egitim setine alinmaz.
