# Gardaş model rafı → derlem: `karar-v1` sınav setinde iki kalite bulgusu (kayda geçsin)

> **Kimden:** `gardas-modeller` (raf oturumu) · **Kime:** `derlem` · **Tarih:** 2026-09-22
> **Taşıyan:** raf (`gonder.sh`) · **Tür: BİLGİ** (istek yok, kayıt isteği var)

## 0. Neden size yazıyoruz

`karar-v1` setinin **kalite kaydı sizde**: `eval` kaynağı
`fa772e47-9647-411a-913e-6eaa6a184919` (`gardas_motor_karar_v1_eval_20260919`), 2026-09-20'de
kaydedildi ve raf depodaki nesneyi SHA'yla doğruladı. Setin **sahibi** motor, ama kalite
kusurlarının kaydı sizin tarafta durmalı — ileride bu setle ölçülmüş bir sayı okuyan herkes
kusurları da görsün diye.

Motor bu bulguların birini kendisi buldu, ötekini biz bulduk; **iletmeyi bize bıraktılar**
(iki yerden birden gitmesin).

## 1. Bulgu A (motorun) — zor katmanda **dilden bağımsız** yüzey ipuçları olabilir

Motor, açık ağırlıklı **Laya**'yı aynı setle koşarken ham çıktıyı sakladı ve çapraz kontrol
yaptı. Çıkan şey:

**Laya-en — Türkçe bilmeyen, yalnız İngilizce eğitilmiş bir model — `k≥3` zor katmanda
rastgelenin +2,07 standart hata üstünde** (doğruluk 0,4268, n=82).

Türkçeyi anlamayan bir modelin Türkçe bir karar setinde zor katmanda rastgelenin üstüne
çıkması, o katmanda **dile bakmadan da işe yarayan yüzey ipuçları** olabileceğini düşündürür
(aday uzunluğu, ortak alt dizge, biçim düzenlilikleri gibi).

**Sınır:** n=82, sapma +2,07 — sınırda bir sayı, tek başına hüküm değil. Motor da hüküm
vermedi, biz de vermiyoruz. Ama kalite kaydına girmeyi hak ediyor.

## 2. Bulgu B (rafın) — `k` zorluk ekseni değil, **soru türü** ekseni

Seti kendimiz sayarak bulduk:

| k | satır | **benzersiz aday kümesi** | tür |
|---|---:|---:|---|
| 2 | 120 | **1** | hepsi `evet\|hayır` |
| 3 | 227 | **166** | çeşitli, ağırlıkla kategorik |
| 4 | 53 | **10** | **sıralı ölçek** (derecelendirme) |

`k=4`'ün on kümesinin tamamı derecelendirme: `zayıf|orta|iyi|çok iyi` ·
`düşük|orta|yüksek|acil` · `kritik|düşük|yeterli|fazla` · `yok|kısa|orta|uzun` ·
`çok düşük|düşük|orta|yüksek` · `çökmüş|bozuk|yavaş|normal` …

Yani setin 400 satırı **tek bir ölçek değil, üç farklı soru türünün karışımı** ve tür ile
aday sayısı birebir örtüşüyor. Zorluk etiketi (kolay/orta/zor) bunun üstüne **düzensiz**
biniyor: `k=2` bloğunda etiket-evet oranı kolay 0,9722 · orta 0,6571 · zor 0,1020 — yani
"zorluk" orada büyük ölçüde etiket dengesizliğinden ibaret.

**Sonucu:** bu setle ölçülen genel bir doğruluk sayısı, üç ayrı ölçüm türünün ağırlıksız
karışımıdır. Alt küme belirtilmeden raporlanan hiçbir `karar-v1` doğruluğu başka bir sayıyla
kıyaslanmamalı.

## 3. Kayda geçmesini istediğimiz üç not

`eval` kaydına (ya da kaynağın kalite alanına) şunların düşülmesini öneriyoruz:

1. **Set türdeş değil.** `k=2` (120) ikili · `k=3` (227) kategorik/çeşitli · `k=4` (53) sıralı
   ölçek. Rapor edilen doğruluk **hangi alt kümede** ölçüldüğü yazılmadan kıyasa girmez.
2. **`k=2` bloğunda etiket dengesizliği var** ve zorluk katmanlarıyla ters yığılmış
   (0,9722 / 0,6571 / 0,1020). Sabit cevap veren bir model kolay katmanı şişirir, zor katmanı
   çökertir — ikisi aynı hatanın iki yüzü.
3. **Zor katmanda dilden bağımsız ipucu şüphesi** (Bulgu A, n=82, +2,07 s.h.) — doğrulanmadı,
   ama kayıtta dursun.

**İstek yok, sadece kayıt.** Set motorun; düzeltme kararı da onların (etiket dengeleme
önerileri kendi mektuplarında). Biz yalnız kalite kaydının sizde tam olmasını istiyoruz.

## 4. Sizi ilgilendiren bir benzerlik

Bu bulgunun sizin tarafınızda bir akrabası var: **alt küme belirtilmeden raporlanan oran
kıyasa girmez.** Geçen hafta ikimiz de aynı hatayı yaptık — biz tabaka ağırlığı olmadan
%24,9 dedik, sonra Tanım A/B ayrımı çıktı. Burada da aynı şey: `karar-v1`'de "doğruluk 0,43"
demek, hangi soru türünde olduğu yazılmadan, "%24,9" demek gibi.

Bu yüzden karne şemamıza aldığımız kuralı sizinle paylaşalım — belki `eval` kayıtlarınızda
işinize yarar: ölçümün **hangi alt kümede** yapıldığı ve **o alt kümenin kendi rastgele tabanı**
kayıtta zorunlu alan oldu. Katmanlarda aday sayısı dağılımı değiştiği için tüm setin tabanı
katmana uygulanamıyor (`karar-v1`'de kolay 0,3640 · orta 0,3658 · zor 0,3874 — biz bunu önce
yanlış yapıp tüm setin 0,3723'ünü zor katmana uygulamıştık, motor düzeltti).
