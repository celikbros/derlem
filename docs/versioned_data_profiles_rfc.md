# RFC: Sürümlü Veri Profilleri

**Durum:** Karar kaydı — Aşama 1 kodu, izole PostgreSQL doğrulaması ve yerel
veritabanı migration/postflight adımı `000024`, `000025`, `000026` ile
tamamlandı

**Tarih:** 2026-08-21

**Kapsam:** Derlem çekirdeğinin genel metin, çeviri, reasoning, preference,
tool-use ve eval verisini aynı güvenlik ve release zincirinde yönetebilmesi

**Operasyon notu:** Şifreli backup/restore ve restore tatbikatı, kullanıcının
önceki kararıyla ertelenmiştir; bu çalışma kapsamında yapılmış sayılmaz.

## 1. Karar özeti

Derlem ayrı çeviri veya reasoning ürünlerine bölünmemelidir. Ortak çekirdek
korunmalı; veri örneğinin anlamını, doğrulamasını, rubriğini ve export biçimini
belirleyen **sürümlü veri sözleşmeleri** eklenmelidir. Bu sözleşmenin
veritabanındaki kısa adı `data_profile` olacaktır.

Bu RFC tam çeviri veya reasoning özelliğini hemen uygulamayı önermez. Önce şu
temel ayrımı kalıcılaştırmayı önerir:

- `content_purpose`: verinin hangi havuzda kullanılacağını belirtir
  (`pretrain`, `instruction`, `preference`, `eval`, `holdout`, `post_training`).
- `data_profile`: bir kaydın ne olduğunu ve hangi sözleşmeyle işleneceğini
  belirtir (`text-document`, `translation`, `reasoning` gibi).
- `review_protocol`: ne kadar kanıt gerektiğini belirtir; profil ve amaç
  birleşimine göre kapsamı, bağımsız onay sayısını, örneklemeyi, inceleyici
  yeterliliğini ve uyuşmazlık çözümünü tanımlar.
- `origin/provenance`: kaydın insan, model veya karma üretimini; üreticiyi,
  üretim işini ve kullanılan uygulama/config sürümünü kanıtlar.

İlk migration kimlik ve kanıt omurgasını kurar. Geçmiş kaynak, review, release ve
manifest anlamını değiştirmez; buna karşılık **yeni** claim/review işlemlerini
sunucunun seçtiği bir review campaign'e bağlar ve **yeni** freeze işlemini eksiksiz,
DB-türetilmiş sözleşme kanıtı yoksa fail-closed durdurur. Normalize skorlar,
profile özgü typed projection'lar, çoklu onay uygulaması ve translation/reasoning
özellikleri pilot aşamalarına ertelenmiştir.

Danışman görüşlerinin kabul/ret/ertele matrisi
[`versioned_data_profiles_advisor_synthesis.md`](versioned_data_profiles_advisor_synthesis.md)
belgesindedir.

## 2. Neden şimdi karar gerekiyor?

Mevcut sistemde:

- `sources.content_purpose` zorunlu ve değişmezdir, fakat veri biçimini veya
  görev semantiğini tanımlamaz.
- Kaynakta tek bir `language` alanı vardır; kaynak-hedef dil çifti yoktur.
- `documents` değişmez nesne SHA'sı taşıyan genel inceleme birimidir.
- `document_reviews` karar geçmişini güvenli tutar, ancak rubrik kolonları
  genel metin kalitesine göre sabittir.
- Kanonik `conversation` ve `preference` kayıtları taşınabilir; `task_type`
  serbest metindir ve göreve özel doğrulama seçmez.
- Frozen release kaynak sürümü ve SHA256 snapshot'ı alır, fakat verinin profil
  ve şema sürümünü snapshot'lamaz.
- Mevcut freeze kapısı bütün amaçlarda aynı kaynak örnekleme kuralını kullanır;
  profil bazında her kaydı inceleme, iki bağımsız onay veya uyuşmazlık çözümü
  gibi bir inceleme protokolü seçemez.

Çeviri veya reasoning bu yapıya yalnız yeni ekran ve birkaç JSON alanıyla
eklenirse profil kimliği farklı tablolara ve manifestlere dağılır. Daha sonra
veri kökenini, eski incelemelerin hangi kurala göre verildiğini ve export'un
hangi şemayı kullandığını ispatlamak pahalı bir migration gerektirir.

## 3. Korunacak temel değişmezler

1. Büyük veya ham metin PostgreSQL'e taşınmaz; içerik immutable object store'da
   SHA256 ile tutulur.
2. Ham veri yerinde değiştirilmez. Temizlik, hizalama, çeviri veya reasoning
   üretimi yeni bir türetilmiş kaynak ve açık lineage üretir.
3. Kaynağın `content_purpose` ve veri profili oluşturulduktan sonra değişmez.
   Yanlış sınıflama yeni kaynakla düzeltilir.
4. İnceleme ve geri alma kayıtları append-only kalır.
5. Kendi ürettiği örneği aynı kişi onaylayamaz.
6. Export kalite üretmez veya sessizce satır elemez. Seçim, sürümlü ve
   tekrarlanabilir bir derived-source/release politikasıdır.
7. Frozen release; kaynak SHA'sı yanında profil, şema, rubrik ve export
   sözleşmesi sürümlerini ve bunları yorumlayan implementation digest'ini de
   kanıtlamalıdır.
8. Model eğitimi Derlem'in dışında kalır.
9. Sözleşme hash'i ancak hash'i alınan kanonik baytlar geri getirilebiliyorsa
   kanıttır. Şema, rubrik, protokol, politika ve export spec baytları küçük,
   gizli olmayan kontrol-düzlemi artifact'leri olarak content-addressed ve
   append-only saklanır. İlk aşamada atomik migration için PostgreSQL'de
   tutulur; aynı SHA ile object-store aynası daha sonra eklenebilir.
10. Geçmiş frozen release kanıtı sonradan uydurulmaz veya overwrite edilmez.
    Registry öncesinde frozen olmuş release'in durumu
    `contract_snapshot_status=absent_pre_registry` ve güvenli audit olayıyla
    açıkça kanıtlanır; child snapshot veya yeni hash üretilmez.
11. Yasal/akdi takedown veya redaction frozen release'i sessizce değiştirmez;
    append-only istisna kaydı ve tombstone ile açıklanır.

## 4. Hedef mimari

```text
Ortak Derlem çekirdeği
├── kaynak / immutable nesne / lineage / haklar
├── RBAC / claim / audit / review / reversal
├── PII / dedup / decontamination
├── release / freeze / manifest
├── provenance / production job / takedown kanıtı
└── sürümlü veri profilleri
    ├── text-document@1
    ├── translation-v1
    ├── reasoning-v1
    ├── preference-v1
    └── sonraki profiller
```

Her profil aşağıdaki sürümlü sözleşmeleri bağlar:

1. Kanonik payload şeması
2. Import veya üretim adaptörü
3. Otomatik validator/verifier kümesi
4. Güvenli inceleme görünümü ve rubrik
5. Modelden bağımsız export eşlemesi
6. PII, dedup ve leakage kapılarının hangi payload alanlarını hangi birimde ve
   hangi normalizer sürümüyle okuyacağını belirleyen alan çıkarma sözleşmesi

İnceleme protokolü profile gömülmez. Rubrik *neyin* değerlendirildiğini, protokol
ise *ne kadar kanıtın* gerekli olduğunu tanımlar. Kesin protokol sürümü
`data_profile + content_purpose` birleşimi için seçilir ve iş başladıktan sonra
değişmemesi için review campaign/ilk claim anında pinlenir. Release aynı kesin
sürümü snapshot'lar; freeze anında kayan bir `effective_from` seçimi yapılmaz.

PII, dedup ve leakage birbirinden ayrı sürümlü politikalardır. Profil yalnız
alan semantiğini ve çıkarma yöntemini sağlar. Böylece örneğin translation
kaydının kaynak ve hedef tarafı, reasoning kaydının problem ve çözüm alanı,
preference kaydının prompt alanı ayrı fingerprint'lenebilir.

Profil, çalıştırılabilir kullanıcı eklentisi değildir. Desteklenen profil
sürümleri kod ve migration ile allowlist'e alınır; veritabanından keyfi kod veya
şema çalıştırılmaz.

Tüm spec ve config hash'leri deterministik kanonik serileştirmeye dayanır.
Kanonik JSON yöntemi ve Unicode normalizasyonu sözleşmede açıkça sürümlenir;
Türkçedeki `I/İ/ı/i` dönüşümleri sessizce uygulanmaz. Kampanya ve release üst
bundle baytları ile SHA256 değerlerinin kanonik otoritesi PostgreSQL'dir;
uygulama bu hash'leri istemciden kabul edip hakikat kaynağı yapmaz.

## 5. Önerilen asgari veri modeli

İlk temel migration bir özellik migration'ı değil, kimlik ve kanıt
migration'ıdır.

### Sözleşme artifact'ları

Profil, payload/config şeması, rubrik, inceleme protokolü, alan çıkarma
politikası ve export sözleşmesinin her sürümü için:

- değişmez key/version
- deterministik `spec_sha256`
- content-addressed artifact SHA'sı ve geri getirilebilir kanonik baytlar
- kanonik serileştirme ve Unicode normalizasyon kimliği
- oluşturma aktörü/zamanı

tutulur. Registry satırı kimliği ve tarihi; artifact kaydı hash'i alınan gerçek
spec baytlarını; kod allowlist'i ise hangi implementation'ın çalışabileceğini
kanıtlar. DB kaydı, spec baytı ve kod allowlist'i uzlaşmıyorsa ilgili ingest ve
freeze işlemi fail-closed durur.

Bu baytlar corpus veya kullanıcı içeriği değildir. Boyut sınırı olan kontrol-
düzlemi spec'leridir. Mevcut SQL migrator dış object store'a atomik dosya
yazamadığından ilk kanonik kopya PostgreSQL'de tutulur; iki ayrı hakikat kaynağı
oluşturulmaz.

### `review_rubric_versions`

- `rubric_key`
- `rubric_version`
- `spec_object_sha256`
- `spec_sha256`
- karar gerekçesi kodları ve puan sözleşmesinin kimliği

Rubrik *neyin* değerlendirildiğini tanımlar. Bir rubriği düzeltmek mevcut satırı
güncellemek değil, yeni sürüm yayımlamak demektir. Normalize skor boyutlarının
nihai tablosu Aşama 1'e alınmaz; mevcut skor kolonları davranış değişmeden kalır.

### `review_protocol_versions`

- `protocol_key`
- `protocol_version`
- `spec_object_sha256`
- `spec_sha256`
- kapsam, örneklem, bağımsız onay, yeterlilik ve uyuşmazlık çözümü kimliği

Protokol *ne kadar kanıt* gerektiğini tanımlar. Aşama 1 yalnız protokol
kimliğini ve pinleme kanıtını taşır; yeni `every_record`, çoklu onay veya
hakemlik davranışı açmaz.

### `data_profile_versions`

- `profile_key`
- `profile_version`
- `payload_kind`
- `payload_schema_id` ve `payload_schema_sha256`
- `config_schema_id` ve `config_schema_sha256`
- `field_extraction_contract_key/version`
- `rubric_key/version`
- `export_contract_key/version`
- `implementation_key`
- `implementation_bundle_sha256`
- `profile_spec_object_sha256`
- `created_at`

Birleşik anahtar `(profile_key, profile_version)` olur. Kayıtlar append-only ve
değişmezdir. `review_coverage` ve review protocol kimliği profile gömülmez.
Profil tanım satırında güncellenebilir `status` veya çalıştırılabilir SQL/kod
tutulmaz. Etkinleştirme/emeklilik ayrı append-only yaşam döngüsü olayı ve kod
allowlist'i ile yönetilir.

`implementation_key` tek başına yeterli kanıt değildir. Sözleşmeyi yorumlayan
uygulama, validator, normalizer ve allowlist kümesinin deterministik
`implementation_bundle_sha256` değeri release'e kadar taşınır.

### Profil–amaç bağları

İzin verilen profil ve `content_purpose` birleşimleri FK ile sınırlandırılır.
Her bağ kesin bir `review_protocol_key/version` ve ayrı sürümlü PII, dedup ve
leakage policy kimliklerini belirtir. `translation-pair@1 + instruction` ile
`translation-pair@1 + eval` aynı payload/rubriği, fakat farklı inceleme ve
sızıntı politikasını kullanabilir.

Yeni protokol sürümü devam eden işi sessizce değiştiremez. İnceleme işi
review campaign veya ilk claim anında kesin sürüme pinlenir; release freeze
anında bu pin yeniden çözülmez, snapshot'lanır.

### `sources` ve provenance

- `data_profile_key/version`
- `profile_config_artifact_kind` ve `profile_config_sha256`
- `profile_assignment_reason` (`declared_at_ingest` veya `backfilled`)
- `profile_assigned_at`
- `data_origin` (`unknown`, `human`, `model`, `hybrid`)
- immutable `production_run_id` referansı
- `data_profile_versions` FK

Kaynak satırı config JSON'unu inline hakikat olarak taşımaz. Küçük ve gizli
olmayan config'in kanonik baytları `contract_spec_artifacts` içinde
`artifact_kind=profile_config` olarak içerik-adresli tutulur; kaynak yalnız
artifact türü ve SHA256'yı pinler. Profilin config şeması da ayrı bir
`profile_config_schema` artifact'idir. DB, artifact türü/SHA FK'sini; güvenilir
runtime ise desteklediği profil/config allowlist'ini doğrular. Profil ve config
alanları create-time only'dir. Provenance normalde kaynak oluşturulurken pinlenir;
tek istisna, henüz hiçbir nesnesi bağlanmamış boş bir kaynağın distilasyon işiyle
aynı transaction içinde `unknown/NULL` durumundan `model|hybrid/production_run_id`
durumuna bir kez geçirilmesidir. Bu geçişten sonra provenance yine immutable'dır.

`production_runs` güncellenebilir iş durumu tablosu değildir. İş başlamadan önce
implementation/config/input kimliklerini sabitleyen immutable bir üretim niyeti
kaydıdır. Başarılı çıktı, aynı satırı güncellemek yerine bire bir ve append-only
`production_run_completions` kaydıyla kanıtlanır. Tamamlama kaydı job kimliği,
çıktı manifest SHA256'sı, çıktı SHA256/boyut/kayıt sayısı ve tamamlanma zamanını
taşır. Düzeltme veya yeniden çalıştırma eski satırları değiştirmez; yeni bir run
ve gerekirse `parent_run_id` ilişkisi üretir. Gizli prompt/config gövdeleri bu
kayıtlara girmez.

Bir kaynak tek profil taşır; karışık biçimli dosya profil bazlı ayrı türetilmiş
kaynaklara bölünür ve lineage korunur. Kaynak düzeyi profil kuralı varken Aşama
1'de milyonlarca `documents` satırına denormalize profil kopyası eklenmez.
Kullanılan kesin rubrik/protokol ise kampanya, claim ve review kanıtına damgalanır.

### Review campaign, claim ve karar bağı

`review_campaigns`, bir kaynak ve örnek nesli için profil/config, rubrik,
profil×amaç sözleşmesi, protokol, PII/dedup/leakage politikaları ve
implementation bundle'ı kesin sürümlere pinler. Kampanya bundle SHA256'sı bu
pinlerden PostgreSQL tarafından türetilir. Örnek neslinin kaynak nesne SHA256'sı,
örnekleme yöntemi, örnek sayısı ve işi de kampanyaya damgalanır.
`document_sample_generations` kimliği yerinde değiştirilemez; yalnız mevcut
`active` neslin `superseded` durumuna geçirilmesine izin verilir.

Yeni `document_review_claims` ve `document_reviews` satırları aynı
`review_campaign_id` değerini taşımak zorundadır. Bu kimliği client seçmez;
sunucu immutable kaynak ve örnek neslinden türetir. Registry öncesi tarihsel
satırlar NULL kalır; onlara sonradan kampanya uydurulmaz. Kampanyasız eski claim
yeniden kullanılmaz, geçerli kampanya altında yeniden alınır.

### Yeni release snapshot'ı

Yeni bir freeze sırasında en az aşağıdakiler snapshot'lanır:

- profil key/version ve profile-config artifact türü/SHA256
- payload/config şeması kimlikleri, hash'leri ve artifact referansları
- rubrik ve pinlenmiş inceleme protokolü key/version/hash
- uygulanan PII, dedup, leakage ve alan çıkarma policy key/version/hash
- export sözleşmesi key/version/hash
- `contract_snapshot_sha256` ve `implementation_bundle_sha256`
- provenance: origin, production run kimliği ve run implementation/config/input
  manifest hash'leri; model/hibrit kaynakta ayrıca append-only completion job,
  çıktı manifesti, çıktı SHA256/boyut/kayıt sayısı ve tamamlanma zamanı; varsa
  parent/derived source kimliği
- rights ve lineage referanslarının güvenli SHA256 kanıtları; taşınabilir
  manifestte ham yerel yol veya serbest referans yayımlanmaz
- örnek nesli: generation, kaynak SHA256, yöntem, örnek sayısı ve job kimliği;
  ayrıca deterministik sıralı membership sayısı ve membership root SHA256'sı
- shard record count, deterministik sıralama ve checksum kanıtı

Hash'i alınan artifact baytları kanonik artifact store'dan geri getirilebilir
olmalıdır. Her `release_source_contract_snapshots` satırı ayrıca inceleme
kanıtının biçimini `review_evidence_status` ile açıklar:

- `campaign_pinned`: aynı satırda kesin `review_campaign_id` bulunur;
- `absent_pre_registry`: yalnız backfilled terminal legacy kaynakta, kampanya
  öncesi review kanıtı için kullanılır ve kampanya kimliği NULL'dır.

Release üst kanıtı kaynak sayısıyla büyüyen bir JSON gövdesi değildir.
PostgreSQL, child source snapshot'larını `source_id` ile deterministik sıraya
koyar, bunlardan bir `child_snapshot_root_sha256` üretir ve sabit boyutlu üst
artifact'a `source_count` ile bu kökü yazar. Üst
`contract_snapshot_sha256` ve sıralı child implementation digest'lerinden
türetilen `implementation_bundle_sha256` yalnız DB tarafından hesaplanır. Her
yeni freeze; source/snapshot sayısı, her child'ın güncel inceleme kapsaması ve
`contract_snapshot_status=present` koşullarından biri eksikse reddedilir.

### Geçmiş frozen release dürüstlüğü

Migration, mevcut frozen `release_sources` satırlarını **overwrite etmez** ve
eski manifestleri yeniden üretmez. Freeze tarihinde bulunmayan profil/rubrik/
protokol snapshot'ı sonradan `legacy-auto@1` diye yazılmaz. Bu release'lerin
`contract_snapshot_status` değeri `absent_pre_registry` olur ve sebep güvenli
bir audit olayıyla kaydedilir. Onlar için `release_source_contract_snapshots`
child satırları, contract hash'i veya implementation hash'i üretilmez. Böylece
geçmiş kanıt eksik ama dürüst; eski manifest ve üyelik birebir korunmuş kalır.

### `documents`, typed projection ve inceleme skorları

`documents` ortak iş/inceleme birimi olarak, ham payload object store'da
kalmaya devam eder. Translation/reasoning projection tabloları ve normalize
skor modeli Aşama 1'e girmez. Pilot sonunda gerekli alanlar kesinleşince typed,
payload'dan yeniden üretilebilir ve projector sürümü taşıyan projection'lar
eklenir. Sınırsız JSONB/EAV kritik kapı, sorgu veya export alanlarında gerçek
kaynak olarak kullanılmaz.

Mevcut `document_reviews` karar, reviewer, belge sürümü, nesne SHA'sı ve
reversal zincirinin sahibi olmayı sürdürür. Yeni karar ve claim aynı
server-derived `review_campaign_id` ile kesin rubrik/protokol/policy bağlamına
bağlanır. Client profil/rubrik/protokol veya kampanya seçemez.

### Takedown ve redaction kanıtı

KVKK/GDPR, lisans veya akdi yükümlülük nedeniyle zorunlu bayt silme için
önceden tanımlı yol gerekir: yetkili takedown olayı, object tombstone/silme
kanıtı ve append-only `release_integrity_exception`. Eski release veya
manifest sessizce yeniden yazılmaz; bütünlük istisnası doğrulama ve export'ta
görünür olur. Bu politikanın uygulama ayrıntısı Aşama 2 pilotundan önce
tamamlanır.

## 6. Profillerin anlamı

### `text-document@1`

Bugünkü düz belge akışıdır: dil, bütünlük, bilgi yoğunluğu, temizlik, PII ve
tekrar kontrolleri.

### `translation-v1`

Tek inceleme birimi kaynak-hedef çifttir. En az:

- kaynak/hedef dil ve metin
- belge/segment bağlamı
- hizalama yöntemi ve sürümü
- insan/sentetik köken
- anlam sadakati, tamlık, akıcılık, terminoloji rubriği
- sayı, özel ad, placeholder, eksiltme ve ekleme validator'ları

### `reasoning-v1`

Uzun ve denetlenemez iç monolog yerine yapılandırılmış, doğrulanabilir ve kökeni
belli çözüm kanıtıdır. En az:

- problem ve bağlam
- nihai cevap
- doğrulanabilir çözüm adımları veya gerekçe
- verifier/test/araç sonuçları
- insan/model kökeni
- doğruluk, adım geçerliliği, kanıta dayanma ve güvenlik rubriği
- `reasoning_visibility` export politikası

## 7. Mevcut verinin migration stratejisi

Mevcut kaynakları içerik dosyalarını SQL migration içinde okuyarak tahmin etmek
güvenli değildir. Karar:

1. Bütün mevcut kaynaklara davranışı birebir koruyan gerçek ve terminal
   `legacy-auto@1` profili atanır.
2. Atama `profile_assignment_reason=backfilled` ile ayrı kanıtlanır; kaynak
   `version` ve `updated_at` değerleri değişmez.
3. `legacy-auto@1` yeni kaynak oluşturmak için kullanılamaz.
4. Salt-okunur envanter raporu üretilebilir; ancak heuristik sonuç mevcut
   kaynağa yazılmaz. Doğrulanmış açık profile geçiş yeni bir derived source ile
   yapılır.
5. Mevcut frozen `release_sources` satırları ve manifestleri değiştirilmez.
   Onlara `legacy-auto@1` sözleşme snapshot'ı yazılmaz; release
   `contract_snapshot_status=absent_pre_registry` olur, sebep audit olayına
   yazılır ve child snapshot/hash üretilmez.

## 8. Alternatifler

### A — Mevcut `task_type` ve metadata ile devam

En az kod değişikliği; fakat doğrulama, rubrik ve export kimliği yalnız uygulama
geleneğine kalır. Eski kaydın hangi sözleşmeyle işlendiği kanıtlanamaz.

### B — Her görev için ayrı ürün/veritabanı

Görev şeması güçlü olur; ancak auth, audit, storage, claim, release ve güvenlik
tekrar edilir. Küçük ekip ve mevcut ölçek için önerilmez.

### C — Sınırsız generic JSONB/EAV

Hızlı genişler; fakat DB constraint, sorgu, indeks, migration ve sızıntı
denetimi zayıflar. Kritik metadata için önerilmez.

### D — Ortak çekirdek + sürümlü profil + typed projection

Ortak güvenlik ve lifecycle tekrar kullanılabilir; görev farkları açık kalır.
Bu RFC'nin önerisidir.

## 9. Aşamalı uygulama planı

### Aşama 0 — Karar ve envanter (tamamlandı)

- Üç danışman görüşü karşılaştırıldı.
- Kaynak düzeyi immutable profil, profil×amaç protokolü ve dürüst legacy
  stratejisi kararlaştırıldı.
- Pilotla ölçülmesi gereken skor/projection ayrıntıları Aşama 1'den çıkarıldı.

### Aşama 1 — Kimlik, pinleme ve fail-closed kanıt

Kod, izole PostgreSQL doğrulaması ve yerel veritabanı rollout'u tamamlandı.
`000024` profil, kampanya,
örnek nesli ve release kanıtını; `000025` içerik-adresli `storage_objects`
kimliğinin append-only korunmasını; `000026` ise üretim tamamlanma kanıtını
somutlar. Postflight; migration head/checksum, kritik trigger/constraint,
kaynak sayaçları, review/reversal zinciri ve eski frozen release köklerinin
migration öncesi değerlerle birebir eşleştiğini doğrulamıştır.

- Profil, rubrik, protokol, policy ve export kimlik/hash registry'si
- Spec baytlarının content-addressed, geri getirilebilir artifact kanıtı
- Kaynakta immutable profil/config-artifact/provenance ve atama gerekçesi
- Yeni claim ve review'da server-derived `review_campaign_id`
- Yeni release için kesin sözleşme child snapshot'ları ve
  `review_evidence_status`
- Geçmiş frozen release için child/hash uydurmadan `absent_pre_registry`
- PostgreSQL'in türettiği kampanya ve release contract/implementation bundle
  digest'leri; release üst kanıtında `source_count` + deterministik sıralı child
  root
- Takedown/redaction bütünlük istisnasının bağlayıcı politika tasarımı; fiziksel
  şema ilk yeni görev profili release'inden önce ayrı güvenlik migration'ıyla
- İmmutability, audit ve migration testleri; backup/restore kabul maddesi ve
  envanteri tanımlanır, tatbikat kullanıcı kararıyla daha sonraya bırakılır
- Tarihsel review/release/manifest anlamı korunur; yeni review ve freeze
  işlemleri kampanya/snapshot eksikse fail-closed durur
- Normalize skor, typed projection, çoklu onay ve yeni profil özelliği açılmaz

### Aşama 2 — `translation-v1` pilotu

- 10–20 lisanslı kaynak-hedef çift
- typed projection, validator, yan yana review ve export
- profil farkında PII/dedup/leakage alan çıkarımı ve iki taraflı rights kanıtı
- reviewer uyumu ile inceleme protokolünün kalibrasyonu
- Mevcut claim/reversal/audit çekirdeğinin yeniden kullanımı

### Aşama 3 — `reasoning-v1` pilotu

- Otomatik doğrulanabilir küçük bir alan (örneğin matematik veya testli kod)
- problem/solution/final/verifier sözleşmesi
- problem ve çözüm için ayrı leakage fingerprint'leri
- reasoning görünürlük ve purpose-specific export

## 10. İlk migration kabul ölçütleri

- Eski kaynak, belge, review, release ve export checksum davranışı değişmez.
- Mevcut source `version` ve `updated_at` değerleri korunur.
- Her kaynak tam bir profil key/version taşır; belirsizlik sessiz tahmin edilmez.
- Legacy atamanın `backfilled` olduğu açıkça kanıtlanır ve legacy profil yeni
  kaynaklarda kullanılamaz.
- Profil create-time only ve FK ile doğrulanır.
- Kaynak profile config'ini inline JSON olarak değil,
  `profile_config` artifact türü ve SHA256 ile taşır; FK ve güvenilir runtime
  allowlist'i doğrulanır.
- Profil–purpose birleşimi kesin protokol/policy kimlikleriyle doğrulanır.
- Client profil/rubrik/protokol seçemez; server pinlenmiş sözleşmeden türetir.
- Yeni claim ve review aynı, sunucunun türettiği `review_campaign_id` değerini
  taşır; tarihsel kampanyasız satırlar sonradan etiketlenmez.
- Yeni frozen release yalnız `contract_snapshot_status=present` olduğunda;
  eksiksiz child snapshot ve güncel review kapsamıyla freeze olabilir.
- Model/hibrit kaynak başarılı, append-only production completion kanıtı olmadan
  release'e giremez; completion manifestinin fiziksel baytları SHA256 ve boyutla
  freeze sınırında doğrulanır.
- Örnek neslinin membership satırları değişmezdir; child snapshot membership
  sayısı/root'unu pinler ve onaylanan belge nesneleri üyelik kanıtıyla eşleşir.
- PostgreSQL üst release kanıtını `source_count` ve deterministik sıralı
  `child_snapshot_root_sha256` üzerinden, sabit boyutlu artifact olarak türetir.
- Hash'i alınan spec baytları artifact store'dan geri getirilebilir ve SHA ile
  doğrulanabilir.
- Eski frozen `release_sources` satırları overwrite edilmez; eski manifest
  yeniden üretilmez; release `absent_pre_registry` ve audit kanıtı taşırken
  child snapshot/hash üretilmez.
- Profile registry ve kritik değişiklikler DB-level audit kapsamındadır.
- Backup/restore envanteri ve gelecekteki doğrulama adımları belgelenir;
  şifreli yedek/restore tatbikatı bu çalışmada yapılmış sayılmaz ve kullanıcı
  kararıyla ertelenmiştir.
- Migration öncesi ve sonrası aynı legacy release export'u bayt-özdeş kalır.
- PostgreSQL entegrasyon, Go, worker ve web regresyon testleri geçer.

## 11. Pilotta kararlaştırılacak ayrıntılar

Ana mimari kararlar kapanmıştır. Aşağıdakiler bilinçli olarak pilot verisine
bırakılmıştır:

1. Göreve özgü normalize skor kataloğunun kesin kolon ve constraint modeli.
2. Translation/reasoning typed projection tablolarının kesin alanları.
3. Her profil×amaç için per-record inceleme, bağımsız onay ve uyuşmazlık
   eşikleri.
4. Reviewer yeterlilik ve reviewer'lar arası uyum ölçümü.
5. Çok profilli release shard ve üst-manifest sözleşmesi.
6. Takedown/redaction yetki, retention ve fiziksel silme runbook'u.
7. Üretim provenance'ının kaynak ve production-job düzeyindeki kesin
   granülerliği.

Ayrıntılı icra sırası
[`versioned_data_profiles_implementation_plan.md`](versioned_data_profiles_implementation_plan.md)
belgesinde tutulur.
