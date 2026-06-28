# Derlem Risk Bazli Ornekleme Sozlesmesi

**Algoritma:** `risk-stratified-sha256-v1`

**Durum:** Yeni `sample_documents` islerinde aktif

## Amac

Tam corpus metnini PostgreSQL'e tasimadan, insan reviewer'in hem corpus'u temsil
eden hem de sorun cikarma ihtimali yuksek belgeleri gormesini saglamak.
Algoritma kalite karari vermez; yalniz inceleme onceligi uretir.

## Secim Stratejisi

Varsayilan sample boyutu 200'dur. Kaynak tek geciste ve bounded satir okuyucuyla
taranir:

1. Sample kotasinin en fazla yarisi yuksek risk puanli belgeler icin ayrilir.
2. Tum uygun belgeler ayrica SHA256 seed'li deterministik reservoir'a girer.
3. Risk kotasi alindiktan sonra kalan yerler temsil reservoir'undan, tekrar
   etmeyen ordinal'larla doldurulur.
4. Son liste kaynak ordinal'ina gore siralanir.

Riskli belge azsa kota zorla doldurulmaz; bos kalan yerler temsil orneklerinden
gelir. Bu nedenle sonuc yalniz uc degerleri degil, corpus dagilimini da korur.

## Risk Kurallari

| Neden | Kosul | Puan |
| --- | --- | ---: |
| `short_text` | 24 karakterden kisa | 1 |
| `long_text` | 4.000 karakterden uzun | 2 |
| `control_characters` | Bosluk disi kontrol/format karakteri | 3 |
| `high_symbol_ratio` | En az 40 karakter ve sembol orani `%35` ustu | 2 |
| `repeated_character_run` | Ayni karakter en az 8 kez ardisik | 2 |
| `low_lexical_diversity` | En az 20 kelime ve benzersiz oran `%25` alti | 2 |
| `identifier_pattern` | E-posta, TR IBAN bicimi veya 11 haneli aday | 3 |
| `malformed_json` | `{` ile baslayan ancak parse edilemeyen satir | 2 |
| `missing_text_field` | JSON objesinde `text/content/body` yok | 2 |

Toplam puan 10 ile sinirlidir. `identifier_pattern` bir PII karari degildir;
yalniz reviewer onceligidir. Asil PII kapisi TCKN checksum, IBAN mod-97, Luhn ve
diger scanner kurallarini ayri calistirir.

## Saklanan Metadata

Her secilen `documents` kaydinda sunlar saklanir:

- `sampling_method`
- `risk_score`
- `risk_reasons`

Job sonucu toplam/uygun/oversized belge sayisi, riskli aday sayisi, secilen
riskli ornek sayisi ve neden sayaclarini tasir. Ham eslesme, e-posta, numara veya
belge metni job sonucuna ve audit detayina yazilmaz.

Insan belgeyi duzenlerse eski risk puani yeni metin icin gecerli olmadigindan
puan ve nedenler sifirlanir. Review kaydi karar anindaki risk snapshot'ini kendi
immutable context alaninda tutar.

## Determinizm

Ayni immutable source SHA256, algoritma surumu, sample boyutu ve belge sirasi
ayni ornek listesini uretir. Risk esitlikleri `SHA256(source_sha256:ordinal)` ile
cozulur; global rastgele duruma veya calisma zamanina baglilik yoktur.

## Mevcut Kaynaklar

Migration eski document sample kayitlarini `risk_score=0` ve bos neden listesi
ile korur. Eski sample sessizce degistirilmez. Gardas temiz adayinin mevcut 200
reservoir ornegi generation ve membership snapshot'li kontrollu yeniden
ornekleme isiyle yenilenir. Ayrinti: [Kontrollu Yeniden Ornekleme](document_resampling.md).

## Sinirlar

- Kurallar dil modeli degildir ve semantik kaliteyi tek basina olcmez.
- Domain ve source-type mixture, kaynaklar arasi release seviyesinde ele alinacak.
- Near-duplicate ve eval decontamination ayri kalite kapilaridir.
- Risk puani otomatik ret veya otomatik onay uretmez; son karar insandadir.
