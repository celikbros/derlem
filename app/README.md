# App

Bu klasor web uygulamasi icin ayrildi.

Ilk uygulama hedefi:

- Katilimci gorev ekrani
- Katki formu
- Moderator inceleme ekrani
- JSONL export
- Basit kalite skoru

Corpus factory icin ek hedefler:

- Kaynak kayit ekrani: lisans, dil/domain, risk, path, checksum
- Ingestion job takibi: raw -> normalized -> filtered -> deduped -> reviewed
- Review queue: insan/uzman onayi, ret nedeni, sensitive flag
- Release builder: mixture secimi, manifest uretimi, checksum ve gate raporlari
- Export: `final_corpus_manifest.json`, canonical TXT/JSONL, kalite/dedup/mixture raporlari

Bu uygulama LLM veya tokenizer egitimi calistirmaz. Gorevi veri kaydetmek,
duzenlemek, onaylamak, surumlemek ve ilgili ekiplere indirilebilir/aktarilabilir
paket vermektir.

Onerilen MVP stack:

- Go core API
- Python data workers
- PostgreSQL metadata DB
- MVP'de icerik-adresli local filesystem; uretimde MinIO/S3 object storage
- MVP'de PostgreSQL job queue; olculmus ihtiyacta Redis Streams
- React/Next.js admin ve contributor UI

Uygulama kodu `cmd/`, `internal/`, `worker/` ve `web/` dizinlerindedir. Docker
ilk yerel gelistirme akisi icin kullanilmaz.
