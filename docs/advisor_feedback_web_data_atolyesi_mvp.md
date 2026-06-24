# Ic On Degerlendirme Notlari: Web Veri Atolyesi MVP

Bu belge gercek danisman cevabi degildir. Danismana gondermeden once uretilen
ic on degerlendirme notlaridir.

Gercek danisman yaniti alinmis ve
`docs/advisor_response_web_data_atolyesi_mvp.md` dosyasina islenmistir.

## Danismana Ozellikle Sorulacak Risk

Buyuk corpus'u satir satir CMS dokumani gibi yonetmeye calismak sistemi bogar.
Web-scale veri icin belge/satir duzeyinde insan onayi degil, kaynak veya shard
bazli kayit ve orneklem denetimi kullanilmalidir.

Lisans/KVKK durumu belirsiz veri release'e kesinlikle girmemelidir.

## Ic Olarak Dogru Gorunen Kararlar

- PostgreSQL + dosya sistemi ayrimi dogru.
- DB metadata, review, audit ve release kayitlarini tutmali.
- Metin dosyalari DB blob'u olmamali.
- LLM/tokenizer koduna mudahale etmeyip sadece onayli export uretme siniri dogru.
- Gardas Faz 2'nin ilk seed kaynak olarak path/checksum/manifest ile kaydedilmesi MVP icin yeterli.

## Plana Eklenmesi Onerilen Duzeltmeler

Otomatik kontroller Faz 4'e kalmamali. Asagidaki kontroller Faz 1-2'ye
cekilmelidir:

- checksum
- encoding okunabilirligi
- dosya boyutu
- satir/dokuman sayisi
- exact duplicate
- lisans durumu
- temel PII uyarilari

Release Builder'dan once kalite ve risk kapilari calismalidir.

## MVP'ye Mutlaka Eklenmesi Onerilenler

Zorunlu metadata:

- `source_name`
- `source_type`
- `license`
- `rights_status`
- `language`
- `domain`
- `storage_path`
- `sha256`
- `line_count` veya `doc_count`
- `risk_level`
- `approval_status`
- `created_by`
- `created_at`

Zorunlu audit/release kayitlari:

- immutable raw dosya
- audit log
- ret nedeni
- freeze eden kullanici
- freeze zamani
- release checksum

## Sonraya Ertelenebilir Gorunenler

- Parquet export
- OAuth
- Gelismis dashboard
- near-dedup
- kapsamli PII modeli
- gelismis kalite skoru
- MinIO/S3

Not: Storage arayuzu bastan MinIO/S3'e gecebilir tasarlanmalidir.

## Veri Yonetimi Kirmizi Cizgileri

- Lisansi belirsiz veri yok.
- KVKK/PII riski isaretlenmeden export yok.
- Eval/holdout verisi pretraining adaylarina karisamaz.
- Frozen release degistirilemez; hata varsa yeni release cikarilir.
- Raw veri overwrite edilmez.
- Instruction/preference/eval havuzlari pretraining havuzlarindan teknik olarak ayrilmalidir.

## Nihai Tavsiye

Plan dogru yonde. MVP, "her seyi yapan veri platformu" degil; kaynak kaydi,
guvenli yukleme, onay akisi ve immutable release/export sistemi olarak dar
tutulmalidir. Ilk surumde kalite kapilari hafif ama zorunlu olmalidir.
