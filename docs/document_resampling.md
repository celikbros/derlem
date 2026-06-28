# Kontrollu Belge Yeniden Ornekleme

**Is tipi:** `resample_documents`

**Yetki:** Yalniz `admin`

## Neden Nesil Modeli Var?

Sample listesi bir kalite kararinin girdisidir. Eski 200 belgeyi silip yerine
yeni 200 belge yazmak, hangi listenin incelendigini kanitlamayi zorlastirir.
Derlem bu nedenle her sample listesini numarali bir nesil olarak saklar.

- `document_sample_generations`: kaynak, nesil, source SHA256, algoritma,
  durum, sample sayisi, job ve zaman.
- `document_sample_memberships`: o nesilde secilen document, ordinal, object
  SHA256 ve karar oncesi risk snapshot'i.
- `documents.is_active`: reviewer'in su anda gordugu nesil.

## Sert Kapilar

Yeniden ornekleme su durumlarda baslamaz:

- Kaynak henuz sample edilmemisse veya aktif bir resample varsa.
- Aktif sample belgesi editlendiyse.
- Herhangi bir sample generation icin document review varsa.
- Kaynak review/onay sureci baslamissa.
- Aktif sample listesi bulunamiyorsa.

Bu kontroller hem API transaction'inda hem worker publish transaction'inda
tekrar edilir.

## Iki Fazli Yayin

Corpus taramasi uzun surebilir. Tarama boyunca eski nesil aktif kalir. Yeni
orneklerin object'leri hazir olduktan sonra tek transaction icinde:

1. Eski aktif nesil `superseded` olur.
2. Eski document satirlari pasiflenir.
3. Yeni secimler insert edilir veya ayni ordinal ise guvenle yeniden aktiflenir.
4. Yeni generation ve tum membership satirlari yazilir.
5. Kaynak generation/method/count alanlari yeni nesle tasinir.

Transaction basarisizsa eski nesil ve uyelikleri degismez. Job tum retry'lar
sonunda basarisiz olursa kaynak tekrar `sampled` durumuna doner.

## API

```text
POST /api/v1/sources/{source_id}/documents/resample
GET  /api/v1/sources/{source_id}/document-sample-generations
```

Queue yaniti `202` ve job kimligi verir. Tamamlanma `GET /jobs?source_id=...`
ve kaynak `document_sampling_status` alaniyla izlenir.

## Gardas Operasyonu

Gardas clean candidate yaklasik 13 GB oldugu icin resample uzun bir disk tarama
isidir. Is kuyruga alindiktan sonra worker log'u ve Isler ekrani izlenir; Codex
etkilesimli olarak surekli poll yapmaz. Tamamlaninca generation 1 arsiv,
generation 2 aktif ve algoritma `risk-stratified-sha256-v1` olmalidir.
