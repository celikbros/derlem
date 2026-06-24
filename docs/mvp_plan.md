# MVP Plani

## Faz 0: Proje Omurgasi

- Proje adi ve amaci netlestirilecek.
- Veri havuzlari tanimlanacak.
- Katki lisansi ve kullanim izni metni hazirlanacak.
- Ilk gorev tipleri secilecek.
- Kalite skoru semasi belirlenecek.

## Faz 1: Kapali Pilot

Hedef:

- 20-50 guvenilir katilimci
- 1.000-2.000 onayli ornek
- Manuel moderator akisi
- Basit web arayuzu
- Mevcut Faz 2 pretraining corpus'unun atolye release kaydi olarak iceri alinmasi

Olculer:

- Kabul orani
- Ret nedenleri
- Ortalama kalite skoru
- Katilimci basina onayli veri
- Gorev basina sure
- Corpus tarafinda: kaynak sayisi, dedup orani, PII/telif risk dagilimi, release gate sonucu

## Faz 1B: Buyuk Corpus Pilot

Hedef:

- 10-50 GB yeni aday ham veri
- Her kaynak icin `source_dataset` metadata kaydi
- Object storage/filesystem uzerinde raw + normalized + clean candidate dizinleri
- PostgreSQL uzerinde kaynak, islem, review ve release metadata'si
- Exact dedup raporu; MinHash near-dedup icin kucuk olcekli deneme
- LLM/tokenizer ekiplerine teslim edilebilir release candidate

Olculer:

- Benzersiz dokuman orani
- Turkce/diger dil karisimi
- Bozuk encoding/OCR orani
- PII/telif nedeniyle elenen oran
- Export paketinin manifest/checksum tutarliligi
- LLM/tokenizer ekiplerinden gelen kabul/ret geri bildirimi

## Faz 2: Acik Pilot

Hedef:

- 100-500 katilimci
- 10.000+ onayli ornek
- Katki puani ve kalite rozetleri
- Otomatik filtreler
- Cift insan incelemesi

## Faz 3: Model Deneyi

Toplanan verinin etkisi kucuk bir model veya acik kaynak bir model uzerinde olculecek:

- Base model
- Turkce instruction tuning
- Preference/DPO denemesi
- Eval setinde karsilastirma

## Ilk Teknik Stack Onerisi

- Frontend: Next.js veya sade React
- Core API: Go
- Data workers: Python
- Veritabani: PostgreSQL
- Kuyruk: MVP'de PostgreSQL `FOR UPDATE SKIP LOCKED`; olculmus ihtiyacta Redis Streams
- Veri formati: JSONL export
- Auth: e-posta + opsiyonel OAuth
