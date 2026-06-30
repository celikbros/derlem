# Benzerlik Çifti İncelemesi

**Veri modeli:** `000016_similarity_pair_reviews.sql`
**Importer:** `calibration-closest-pair-materialization-v1`

Bu akış, `derlem.similarity-calibration.v1` raporundaki en yakın doğal belge
çiftlerini insan incelemesine taşır. Kalibrasyon raporu tek başına eşik
değiştirmez; purpose-specific politika kararı için bağımsız etiket üretir.

## Değişmezlik Sınırı

- Kalibrasyon JSON dosyası içerik-adresli nesne olarak saklanır.
- Koşu ve çift kayıtları update/delete/truncate kabul etmez.
- Tam metin PostgreSQL'e yazılmaz. Yalnızca SHA256 nesnesi, en fazla 500
  karakterlik önizleme, kaynak kimliği ve ordinal metadata olarak tutulur.
- İnsan kararları çift satırını değiştirmez; `similarity_pair_reviews` tablosuna
  append-only kayıt olarak eklenir.
- Bir kullanıcı aynı çifti yalnızca bir kez etiketleyebilir.
- Import sırasında kaynak SHA256, ordinal belge, SimHash uygunluğu ve rapordaki
  Hamming mesafesi yeniden doğrulanır.
- Aynı rapor tekrar import edilirse yeni koşu oluşturulmaz.

## Etiketler

| Etiket | Anlamı |
|---|---|
| `exact_duplicate` | Anlamsal içerik ve ifade pratikte aynı. |
| `near_duplicate` | Küçük düzenleme, sıra veya yüzey farkıyla aynı bilgi. |
| `related` | Konu/kalıp ilişkili fakat ayrı eğitim örneği. |
| `different` | Ayrı içerik. |
| `uncertain` | Karar için alan bilgisi gerekiyor; gerekçe zorunlu. |

İki veya daha fazla bağımsız review aynı etikette birleşirse çift `consensus`,
etiketler ayrışırsa `disagreement` olarak hesaplanır. Tek review tamamlanmış
sayılır fakat uzlaşı değildir.

## Gardas Importu

Kalibrasyon raporu üretildikten sonra en yakın 100 çiftin metinlerini nesne
deposuna çıkarmak için:

```powershell
cd "C:\CELIK- DERLEM"
.\.venv\Scripts\python.exe -m derlem_worker.similarity_review_import `
  --report .\var\reports\similarity_calibration_pretrain_ebe29279.json
```

Komut yalnızca raporda geçen ordinarları alır fakat ilgili satırlara ulaşmak
için kaynak dosyayı akış halinde tarar. Gardas dosyasında uzun sürebilir ve her
100.000 satırda ilerleme yazar. Sonuçtaki `run_id`, web arayüzündeki
**Benzerlik** görünümünde otomatik listelenir.

## Yetki ve API

- Tüm oturum açmış kullanıcılar koşuları, çiftleri ve mevcut kararları okuyabilir.
- `admin`, `moderator` ve `expert_reviewer` karar ekleyebilir.
- `GET /api/v1/similarity-calibrations`
- `GET /api/v1/similarity-calibrations/{id}/pairs`
- `GET /api/v1/similarity-pairs/{id}`
- `POST /api/v1/similarity-pairs/{id}/reviews`

Her karar `similarity.pair_reviewed`; her import
`similarity.calibration_imported` audit olayı üretir.

## Smoke Kanıtı

`Bulk Review Smoke 1782584401697` instruction kalibrasyonu üç çiftle import
edildi. İlk çift admin ve moderator tarafından bağımsız `near_duplicate`
etiketlendi. API özeti `1` incelenen çift, `2` bağımsız karar, `1` uzlaşı ve
`0` uyuşmazlık döndürdü. Masaüstü ve Pixel 7 Playwright akışı yatay taşma ve
browser console hatası olmadan geçti.
