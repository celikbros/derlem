# `karar-v1` sınav seti — kalite kaydı

**Kaynak:** `gardas_motor_karar_v1_eval_20260919` · `fa772e47-9647-411a-913e-6eaa6a184919` ·
`content_purpose = eval` · SHA256 `a4b9b72b832093f2a2f8174d461c8ae7dfc8abc848d08ab8a1b5de9d8aee95d9`
**Sahibi:** `gardas-motor` (setin kendisi ve düzeltme kararı onların) · **Kayıt burada:** Derlem

Bu belge, `karar-v1` ile ölçülmüş bir sayıyı okuyan herkesin setin bilinen kusurlarını da
görmesi için tutulur. İlk kayıt: model rafının 2026-09-22 mektubu
([2026-09-22-raf-derlem-karar-v1-kalite-kaydi.md](mektuplar/2026-09-22-raf-derlem-karar-v1-kalite-kaydi.md)).

## 1. Set türdeş değil — alt küme yazılmadan doğruluk kıyasa girmez

Aday sayısı (`k`) ile soru türü birebir örtüşüyor:

| k | Satır | Benzersiz aday kümesi | Tür |
|---|---:|---:|---|
| 2 | 120 | 1 | hepsi `evet\|hayır` (ikili) |
| 3 | 227 | 166 | çeşitli, ağırlıkla kategorik |
| 4 | 53 | 10 | sıralı ölçek (derecelendirme: `zayıf\|orta\|iyi\|çok iyi` vb.) |

400 satır üç ayrı ölçüm türünün karışımıdır. **Bir `karar-v1` doğruluğu, hangi alt kümede
ölçüldüğü ve o alt kümenin kendi rastgele tabanı yazılmadan başka bir sayıyla
kıyaslanmaz.** Katmanlar arasında aday sayısı dağılımı değiştiği için tüm setin tabanı
(0,3723) bir katmana uygulanamaz: kolay 0,3640 · orta 0,3658 · zor 0,3874.

## 2. `k=2` bloğunda etiket dengesizliği, zorlukla ters yığılmış

`k=2` bloğunda "evet" etiketinin oranı: kolay **0,9722** · orta **0,6571** · zor **0,1020**.
Sabit cevap veren bir model kolay katmanı şişirir, zor katmanı çökertir; ikisi aynı hatanın
iki yüzüdür. O blokta "zorluk" büyük ölçüde etiket dengesizliğidir.

## 3. Zor katmanda dilden bağımsız ipucu şüphesi — doğrulanmadı

Yalnız İngilizce eğitilmiş bir model (Laya-en) `k ≥ 3` zor katmanda rastgelenin **+2,07
standart hata** üstünde çıktı (doğruluk 0,4268, n = 82). Türkçeyi anlamayan bir modelin
bunu yapması, o katmanda dile bakmadan çalışan yüzey ipuçları (aday uzunluğu, ortak alt
dizge, biçim düzenlilikleri) olabileceğini düşündürür. **n = 82 ve sapma sınırda; hüküm
değil, kayıt.**

## Kayıtla ilgili not

Bu notlar belgede duruyor; kaynağın veritabanı kaydına (`lineage_ref` ya da bir kalite
alanı) işlenmedi — çalışma veritabanında değişiklik kurucu onayı ister. Setin düzeltilmesi
(etiket dengeleme, `karar-v2`) motorun kararıdır; yeni sürüm gelirse ayrı `eval` kaynağı
olarak kaydedilir, bu kayıt ona taşınmaz.
