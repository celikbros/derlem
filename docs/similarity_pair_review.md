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

Bağımsızlık sunucu tarafında kör review ile korunur. Karar verme yetkisi olan
bir kullanıcı kendi etiketini kaydedene kadar aynı çiftteki review sayısını,
etiketleri, gerekçeleri, uzlaşıyı veya uyuşmazlığı API'den göremez. Karar
kaydedilince bu kanıtlar görünür olur. Hiçbir etiket varsayılan seçili gelmez;
kayıt sonrasında arayüz sıradaki bekleyen çifte geçer.

## Gardas Importu - Tamamlandı

En yakın 100 çiftin metinlerini nesne deposuna çıkaran idempotent komut:

```powershell
cd "C:\CELIK- DERLEM"
.\.venv\Scripts\python.exe -m derlem_worker.similarity_review_import `
  --report .\var\reports\similarity_calibration_pretrain_ebe29279.json
```

Komut 2026-07-01 tarihinde başarıyla tamamlandı. Rapordaki 100 çift için 178
benzersiz belge çıkarıldı; en büyük gerekli ordinal nedeniyle kaynak 5.918.983
satıra kadar tarandı. Sonuç:

- `run_id`: `769836b7-f121-4d9d-b6cb-42f3f6ab490f`
- rapor SHA256: `365e67fa5bed3da7d670e53946542f5b6c77dab47fab4f7bcc45a75dadf0b3e1`
- çift / benzersiz belge: `100 / 178`
- başlangıç review durumu: `0 / 100`

Aynı komut tekrar çalıştırılırsa `already_imported` döner ve kayıtları
çoğaltmaz. Koşu web arayüzündeki **Benzerlik** görünümünde `pretrain` amacıyla
listelenir.

## Yetki ve API

- Tüm oturum açmış kullanıcılar koşuları ve çiftleri okuyabilir.
- `admin`, `moderator` ve `expert_reviewer` karar ekleyebilir.
- Karar yetkili kullanıcı için diğer kararlar kendi review'una kadar körlenir.
- Salt-okuma rolleri tamamlanmış karar ve uzlaşı kanıtlarını okuyabilir.
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
