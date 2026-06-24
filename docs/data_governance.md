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

## Release Dondurma Kurali

Bir corpus release'i donduruldugunda sunlar degistirilmez:

- Canonical text view
- Manifest
- Checksum paketi
- Dedup ve mixture raporlari
- Normalizasyon karari
- Tokenizer registry karari

Yeni veri veya temizlik karari gerekiyorsa mevcut release degistirilmez; yeni release acilir.

`C:\CELIK-GARDASH` tarafindaki mevcut v3.8 Faz 2 release bu kurala tabidir. Atolye yeni veri eklediginde v3.8 manifest'i geriye donuk degistirmek yerine yeni bir release id uretir.

## Kaynak/Shard Bazli Onay

Buyuk corpus kaynaklarinda inceleme kayit bazli degil, kaynak veya shard bazli yapilir:

- Her kaynak once lisans/KVKK kapisindan gecer.
- Otomatik kalite raporu kaynak ve shard seviyesinde uretilir.
- Moderator veya uzman stratified ornekleri inceler.
- Onay karari tum kaynaga, belirli shard'lara veya sadece temizlenmis alt kumeye verilir.

Insan tarafindan uretilen instruction, preference, answer review ve eval verisi icin kayit bazli review devam eder.

## Riskli Alanlar

Tıp, hukuk, finans, tarihsel iddialar, din, siyaset ve hassas toplumsal konular icin varsayilan havuz `sensitive_review` olur. Bu veriler uzman veya guvenilir moderator incelemesi olmadan egitim setine alinmaz.
