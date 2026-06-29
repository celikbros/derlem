# Release Mixture Raporu

**Şema:** `derlem.mixture-report.v1`

Mixture raporu, frozen release içindeki kaynak bileşimini model veya tokenizer
seçmeden gösterir. Freeze sırasında release-source snapshot metadata'sından
deterministik üretilir ve `gate_results.mixture_report` ile frozen manifestte
saklanır.

## Boyutlar

Rapor şu boyutları ayrı ayrı toplar:

- `language`
- `domain`
- `source_type`
- `license`
- `rights_status`

Her değer için kaynak sayısı, byte boyutu ve satır/kayıt sayısı bulunur. Kaynak
metadata'sında boş değer varsa `unknown` grubuna yazılır.

## Pay Birimi

Ondalık kayan nokta yerine basis point kullanılır:

- `10000 bps` = `%100`
- `2500 bps` = `%25`
- `1 bps` = `%0,01`

Pay hesabı tamsayı ve deterministiktir. Arayüz öncelikle `byte_share_bps`
gösterir; byte boyutu sıfırsa `source_share_bps` kullanır.

## Toplamlar

`totals` alanı şunları taşır:

- `source_count`
- `byte_size`
- `line_count`
- `missing_byte_size_count`
- `missing_line_count`

Eksik byte veya satır bilgisi sıfır varsayılmazmış gibi gizlenmez; eksik sayaçta
açıkça raporlanır, ağırlıklı toplamda `0` katkı yapar.

## Sınır

Freeze mixture raporu kaynak snapshot'ını anlatır. JSONL export içindeki text,
conversation ve preference kayıt sayıları export manifestindeki
`record_type_counts` alanındadır. Token oranları hedef tokenizer'a bağlı olduğu
için mixture raporunda yer almaz; exact tokenizer mixture analizi tüketici
katmanının işidir.

## Değişmezlik

Kaynaklar `source_id`, gruplar ise değer adıyla sıralanır. Rapor çalışma zamanı
taşımaz. Aynı frozen source snapshot aynı mixture JSON'unu ve manifest SHA256
zincirini üretir.
