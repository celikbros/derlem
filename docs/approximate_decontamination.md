# Yaklaşık Dekontaminasyon Pilotu

Derlem, `pretrain` release dondurulurken eval ve holdout kaynaklarına karşı
yaklaşık belge benzerliği raporu üretir. Bu rapor exact dekontaminasyon
kapısından sonra çalışır ve `gate_results.approximate_decontamination` altında
frozen release snapshot'ına bağlanır.

## Politika

- Exact belge eşleşmesi sert kapıdır ve release'i bloke eder.
- Yaklaşık eşleşme pilotu yalnızca rapor üretir; tek başına freeze'i bloke etmez.
- Potansiyel eşleşmeler insan incelemesine adaydır, otomatik sızıntı kararı değildir.
- Eval/holdout kaynağı yoksa sonuç `not_applicable` olur.
- Aday sınırı aşılırsa sonuç temiz sayılmaz; `inconclusive` olur.
- Ham kaynak ve eval metni rapora veya geçici indekse yazılmaz.

## Yöntem

Yöntem kimliği:
`normalized-word-3gram-simhash64-v1-hamming10-bands8x8-v1`.

1. Düz metin/JSONL belge alanı seçilir; kanonik conversation/preference kaydında
   JSON kabuğu yerine mesaj, araç ve export edilebilir semantik metin kullanılır.
2. Seçilen metin Derlem'in kanonik document normalizasyonundan geçirilir.
3. En az beş token içeren belgelerden sözcük 3-gramları çıkarılır.
4. BLAKE2b tabanlı deterministik 64-bit SimHash imzası oluşturulur.
5. Eval/holdout imzaları geçici SQLite indeksinde sekiz adet 8-bit banda ayrılır.
6. Pretrain belgesiyle en az bir bandı paylaşan en fazla 5.000 aday karşılaştırılır.
7. Hamming mesafesi 10 veya daha düşük en iyi aday potansiyel eşleşme sayılır.

Geçici indeks yalnızca 64-bit imza, kaynak SHA256 ve satır ordinal'i taşır ve iş
bitince silinir. Raporda en fazla 20 örnek eşleşmenin kaynak kimlikleri, ordinal
değerleri, Hamming mesafesi ve yaklaşık benzerlik oranı bulunur; metin bulunmaz.

## Sonuçlar

- `reported` ve `potential_match_count = 0`: taranan aday uzayında eşleşme bulunmadı.
- `reported` ve sayı pozitif: insan incelemesi gereken adaylar bulundu.
- `inconclusive`: en az bir belgede 5.000 aday sınırı aşıldı; sonuç temiz kabul edilmez.
- `not_applicable`: release pretrain değildir veya eval/holdout referansı yoktur.

İşler ekranı referans/indekslenen belge sayısını, release belge sayısını,
potansiyel eşleşmeleri ve aday taşmalarını canlı gösterir.

## Bilinen Sınırlar

SimHash ve band tabanlı aday seçimi yaklaşık bir yöntemdir; yanlış pozitif ve
yanlış negatif üretebilir. Kısa belgeler indekslenmez. Sözcük sırası ciddi biçimde
değiştirilmiş, çevrilmiş veya yoğun biçimde dönüştürülmüş sızıntılar kaçabilir.
Bu nedenle pilot sonucu hukuki ya da nihai kalite kararı değildir. Eşik ve band
ayarları gerçek Derlem corpus ölçümleriyle kalibre edilmeden hard gate yapılmaz.
