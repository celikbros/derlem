# Çok Boyutlu Belge Kalitesi

**Aktif rubric:** `multidimensional-v1`

Derlem belge kalitesini model veya tokenizer şemasına göre değil, kanonik insan
değerlendirmesi olarak kaydeder. Tüm puanlarda `1` en düşük, `5` en yüksek
değerdir.

## Boyutlar

| Alan | Anlamı |
|---|---|
| `quality_score` | Belgenin bütünsel eğitim değeri |
| `language_quality_score` | Dil doğruluğu, doğallığı ve okunabilirliği |
| `coherence_score` | İç anlam, bağlam ve akış tutarlılığı |
| `information_density_score` | Yararlı bilgi veya görev sinyali yoğunluğu |
| `cleanliness_score` | Gürültüden, bozuk biçimden ve anlamsız artıklardan arınmışlık |

Karar (`approved`, `rejected`, `sensitive_review`) puanlardan ayrı bir insan
etiketidir. Ret ve hassas inceleme kararlarında gerekçe zorunludur.

## Geriye Uyumluluk

Migration eski review kayıtlarını değiştirmez veya uydurma alt puanlarla
doldurmaz:

- Eski kayıtlar `overall-v1` olarak kalır ve yalnız `quality_score` taşır.
- Yeni kayıtlar `multidimensional-v1` olur ve beş puanın tamamını zorunlu taşır.
- PostgreSQL constraint'i eksik veya `1..5` dışındaki yeni puanları reddeder.
- `document_reviews` append-only kalır; rubric bilgileri sonradan düzenlenemez.

## API

Tekil ve toplu review payload'ları aynı kalite alanlarını kullanır:

```json
{
  "decision": "approved",
  "reason": null,
  "quality_score": 4,
  "language_quality_score": 5,
  "coherence_score": 4,
  "information_density_score": 3,
  "cleanliness_score": 5,
  "document_version": 1
}
```

Kaynak özeti:

```text
GET /api/v1/sources/{source_id}/document-quality-summary
```

Özet yalnız aktif sample neslindeki belgelerin güncel sürümüne bağlı
`multidimensional-v1` review'ları kapsar. Eski rubric kayıtlarının sayısı ayrıca
`legacy_review_count` olarak döner; ortalamalara karıştırılmaz.

## Audit

Tekil ve toplu review audit event'leri rubric sürümünü, beş puanı, belge
sürümünü ve object SHA256 bağını taşır. Böylece puanın hangi içerik sürümüne ve
hangi sample nesline verildiği kanıtlanabilir.
