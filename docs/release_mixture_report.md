# Release Mixture Raporu

**Aktif şema:** `derlem.mixture-report.v2`

Mixture raporu, frozen release içindeki kaynak bileşimini model veya tokenizer
seçmeden gösterir. Freeze sırasında release-source snapshot metadata'sından
deterministik üretilir ve `gate_results.mixture_report` ile frozen manifestte
saklanır.

`v2`, `v1` kaynak dağılımını değiştirmeden `quality` örneklem snapshot'ını ekler.
Önceden dondurulmuş `v1` manifestleri değişmez ve arayüzde okunmaya devam eder.

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

## Kalite Örneklemi

`quality` alanının aktif sözleşmesi `derlem.quality-mixture.v2`'dir. Birim, release
kaynaklarının aktif örnek neslindeki güncel belge sürümüdür. Yalnız
`multidimensional-v1` review taşıyan belgeler kalite dağılımına girer.

Beş boyut ayrı raporlanır:

- `overall`
- `language`
- `coherence`
- `information_density`
- `cleanliness`

Her boyutta puan toplamı, tamsayı `average_score_milli` ortalaması ve üç bant vardır:

- `low`: 1-2
- `medium`: 3
- `high`: 4-5

Her bant belge sayısı ve `document_share_bps` taşır. Payın paydası yalnız geçerli
çok boyutlu puanı olan örnek belgelerdir.

Coverage kanıtı ayrıca saklanır:

- `sample_document_count`
- `scored_document_count`
- `coverage_bps`
- `legacy_document_count`
- `missing_review_document_count`
- `coverage_status`: `complete`, `partial` veya `unavailable`

Sıralı örnek nesli, belge sürümü, object SHA256, review kimliği, onay kararı,
rubric ve puanlar ham metin olmadan `ordered-sample-review-json-sha256-v2`
yöntemiyle `review_snapshot_sha256` içinde sabitlenir. Freeze commit transaction'ı
aynı snapshot'ı kaynak kilitleri altında yeniden üretir; fark varsa freeze bloke olur.

Yerel pilotta üretilmiş `derlem.quality-mixture.v1` snapshot'ları okunabilir kalır;
yeniden yazılmaz veya yerinde yükseltilmez.

## Sınır

Freeze mixture raporu kaynak snapshot'ını anlatır. JSONL export içindeki text,
conversation ve preference kayıt sayıları export manifestindeki
`record_type_counts` alanındadır. Token oranları hedef tokenizer'a bağlı olduğu
için mixture raporunda yer almaz; exact tokenizer mixture analizi tüketici
katmanının işidir.

Kalite bantları tam corpus'un her belgesinin puanlandığı anlamına gelmez; açıkça
belirtilen insan review örneklemini anlatır. Corpus geneline ilişkin çıkarım,
örnekleme yöntemi ve coverage ile birlikte tüketici ekip tarafından yapılmalıdır.

## Değişmezlik

Kaynaklar `source_id`, gruplar değer adıyla; kalite belgeleri ise `source_id` ve
`document_id` ile sıralanır. Rapor çalışma zamanı taşımaz. Aynı source metadata
ve sample/review snapshot'ı aynı mixture JSON'unu ve manifest SHA256 zincirini
üretir.
