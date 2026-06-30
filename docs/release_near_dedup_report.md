# Release Yakın Tekrar Raporu

Derlem, bir release dondurulmadan önce release içindeki belgeleri hem aynı
kaynak içinde hem de kaynaklar arasında yaklaşık benzerlik açısından tarar.
Sonuç `gate_results.near_duplicate_report` altında frozen manifest ve API
snapshot'ına bağlanır.

## Sözleşme

- Şema: `derlem.release-near-dedup-report.v1`
- Yöntem: `normalized-word-3gram-simhash64-v1-hamming3-bands4x16-v1`
- Politika: report-only; bulunan çiftler freeze'i tek başına bloke etmez.
- Kapsam: tüm release amaçları (`pretrain`, `instruction`, `preference`, `eval`,
  `holdout`, `post_training`).
- Saklama: ham metin yok; yalnızca SHA256 kaynak kimliği, satır ordinal'i,
  ilişki türü, Hamming mesafesi ve yaklaşık benzerlik oranı.

## Yöntem

1. Düz metin ve yaygın JSONL `text/content/body` alanları kanonik belge metnine çevrilir.
2. `derlem.canonical-sample.v1` conversation/preference kayıtlarında JSON kabuğu
   yerine mesaj, araç ve export edilebilir semantik metinler kullanılır.
3. En az beş token içeren belgeden sözcük 3-gram tabanlı 64-bit SimHash üretilir.
4. İmza dört adet 16-bit banda ayrılır ve geçici SQLite indeksine yazılır.
5. Yeni belge, en az bir bandı aynı olan daha önceki belgelerle karşılaştırılır.
6. Hamming mesafesi en fazla 3 olan her benzersiz belge çifti raporlanır.

Üç bit fark dört banda dağıtılsa bile en az bir bandın değişmeden kalması
zorunludur. Bu nedenle aday sınırı aşılmadığı sürece Hamming mesafesi 3 veya
daha düşük çiftler band indeksinde kaçırılmaz. SimHash'in metinsel benzerliği
temsil etme sınırları yine geçerlidir.

## Alanlar

- `document_count`: boş olmayan ve taranan belgeler.
- `indexed_document_count`: en az beş token içerdiği için imzalanan belgeler.
- `potential_pair_count`: Hamming eşiğini geçen benzersiz çiftler.
- `within_source_pair_count`: aynı kaynak içindeki çiftler.
- `cross_source_pair_count`: farklı kaynaklar arasındaki çiftler.
- `candidate_overflow_document_count`: 5.000 aday sınırını aşan belgeler.
- `sample_pairs`: ham metin içermeyen en fazla 20 örnek çift.

`status=reported`, taramanın bounded sözleşme içinde tamamlandığını belirtir.
`status=inconclusive`, en az bir belgede aday sınırının aşıldığını ve raporun
eksiksiz kabul edilemeyeceğini belirtir.

## Yorumlama

Mesafe 0 aynı SimHash imzasıdır; tek başına byte veya metin eşitliği kanıtı
değildir. Pozitif çiftler otomatik silinmez. Veri yöneticisi örnek çiftleri ve
kaynak bağlamını inceleyerek ayrı bir dedup kararı verir. Eşik, gerçek Derlem
corpus ölçümleri tamamlanmadan yükseltilmez ve hard gate yapılmaz.
Kalibrasyon yöntemi ve uzun Gardas komutu için
[SimHash Kalibrasyon Raporu](similarity_calibration.md) kullanılır.
