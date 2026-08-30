# Sürümlü veri profilleri uygulama planı

**Durum:** Aşama 1 kodu, izole PostgreSQL doğrulaması ve yerel veritabanı
migration/postflight adımı `000024`, `000025`, `000026` ve eşlik eden runtime
ile tamamlandı

**Tarih:** 2026-08-21

**Dayanak:** `versioned_data_profiles_rfc.md` ve üç bağımsız AI danışman
görüşünün karar sentezi

**Operasyon notu:** Şifreli backup/restore ve restore tatbikatı, kullanıcının
önceki kararıyla ertelenmiştir; bu aşamada yapılmış veya geçmiş sayılmaz.

## 1. Amaç

Derlem; haklar, immutable nesneler, lineage, PII, tekrar, çakışmasız inceleme,
audit ve frozen release işlerini tek çekirdekte yürütmeye devam edecektir.
Çeviri, reasoning ve sonraki veri türleri ayrı ürün veya ayrı veritabanı
olmayacaktır. Her biri bu çekirdeğin üzerinde açık ve sürümlü bir veri
sözleşmesi kullanacaktır.

Bu planın ilk işi çeviri veya reasoning üretmek değildir. İlk iş, ileride
eklenecek profillerin hangi sözleşme ve uygulama sürümüyle üretildiğinin,
incelendiğinin ve release edildiğinin sonradan kanıtlanabilmesini sağlamaktır.

## 2. Değişmeyecek sorumluluk sınırı

Derlem iki işi yapar:

1. Ham veya üretilmiş bir veriyi kaynağı, hakkı, sürümü ve kalite kanıtlarıyla
   nitelendirir.
2. Ham veriden türetilen aday kayıtların üretim ve inceleme zincirini yönetir.

Model eğitimi Derlem'in dışında kalır. Export kalite yaratmaz; daha önce
oluşturulmuş kalite kanıtlarını değişmez bir pakette teslim eder.

## 3. Kesin mimari kararlar

- `content_purpose`, verinin hangi kullanım havuzuna ait olduğunu belirtir.
- `data_profile`, kaydın biçimini ve kalite sözleşmesini belirtir.
- Bir kaynak tek ve immutable profil taşır. Karışık dosya ayrı derived
  source'lara bölünür.
- Rubrik profile bağlıdır: **neyin değerlendirildiğini** söyler.
- Review protocol kampanya ve amaç bağlamına bağlıdır: **kaç inceleme ve hangi
  kanıtın gerektiğini** söyler.
- Örnek nesli ile review kampanyası farklıdır. Aynı örnek seti daha sıkı bir
  protokolle yeniden incelenebilir; yeniden örnekleme zorunlu değildir.
- Profil, rubrik, protokol, politika ve export sözleşmeleri keyfi çalıştırılabilir
  kod taşımaz. DB registry ile güvenilir kod allowlist'i birlikte kullanılır.
- Sözleşme hash'i tek başına yeterli değildir. Hashlenen küçük spec baytları
  geri getirilebilir olmalı; onları yorumlayan implementation bundle kimliği
  de release kanıtına bağlanmalıdır.
- Client profil, rubrik veya protokol seçemez. Sunucu immutable kaynaktan ve
  pinned kampanyadan türetir.
- Kaynak profile config gövdesini inline JSON hakikati olarak taşımaz;
  `profile_config` artifact türü ve SHA256'sını pinler.
- Yeni claim ve review aynı server-derived `review_campaign_id` ile kampanyaya
  bağlanır; istemci kampanya kimliği seçemez.
- Eski frozen release'lere geçmişte var olmayan sözleşme snapshot'ı yazılmaz.
  Durum açıkça `absent_pre_registry` olur ve eski manifest değişmez.
- Eski review satırlarına sonradan rubrik/protokol uydurulmaz.
- Profil-aware alan çıkarma ile karşılaştırma kapsamı ayrıdır: profil hangi
  alanların fingerprint olacağını; purpose/release politikası hangi havuzlarla
  karşılaştırılacağını belirler.
- Reasoning kalitesi uzunlukla ölçülmez. Kanıt yapılandırılmış, sınırlandırılmış,
  provenance'lı ve mümkün olduğunda doğrulanabilir olmalıdır.

## 4. Aşama 1 kapsamı

Bu kapsamın profil, kampanya, örnek nesli ve release omurgası `000024`; içerik-
adresli `storage_objects` kimliğinin append-only korunması `000025`; üretim
tamamlanma ve release pinleme kanıtı `000026` ile uygulanmıştır. Kod ve izole
PostgreSQL testleri ile yerel migration ve postflight karşılaştırması
tamamlanmıştır. Eski kaynak, review/reversal ve frozen release kökleri birebir
korunmuştur.

### 1A — Kontrol düzlemi ve sözleşme kimliği

- İçeriği SHA256 ile adreslenen, append-only küçük sözleşme artifact'leri
- Sürümlü profil, rubrik, review protocol, PII/dedup/leakage politikası ve
  export-contract registry'leri
- Açık profil–purpose uyumluluğu
- Açık ve sürümlü profile×purpose sözleşme bağları
- Üretim provenance kaydı: insan/model/hibrit kökeni, producer ve
  implementation kimliği; gizli prompt/config gövdeleri bu kayda girmez

İlk migration sırasında sözleşme artifact'leri küçük kontrol-düzlemi verisi
olarak PostgreSQL'de immutable baytlar halinde tutulur. Corpus metni burada
tutulmaz. Object-store aynası daha sonra aynı SHA üzerinden eklenebilir.
Kaynak satırı profile config için yalnız `profile_config_artifact_kind` ve
`profile_config_sha256` taşır. Profil satırı config şeması artifact'ini pinler;
DB artifact türü/SHA FK'sini, runtime desteklenen profil/config allowlist'ini
doğrular.

`production_runs` çalışan bir job'ın sonradan güncellenecek durum kaydı değil,
iş başlamadan önce implementation/config/input kimliklerini sabitleyen immutable
üretim niyetidir. Başarılı çıktı aynı satıra yazılmaz;
`production_run_completions` bire bir, append-only tamamlanma kanıtıdır ve job
kimliği, çıktı manifest SHA256'sı, çıktı SHA256/boyut/kayıt sayısı ile tamamlanma
zamanını bağlar. Düzeltme veya yeniden çalıştırma yeni bir run satırı ve
gerektiğinde `parent_run_id` ilişkisi üretir.

Profil/config kimliği kaynak yaratımında sabitlenir. Model distilasyonu için
önceden açılmış fakat henüz nesne bağlanmamış boş kaynak, kuyruklama transaction'ı
içinde bir kez `unknown/NULL` kökenden `model/production_run_id` kökenine geçirilir.
İş kaydı oluşmazsa geçiş de commit edilmez; nesne bağlandıktan veya köken
pinlendikten sonra ikinci geçiş reddedilir.

### 1B — Dürüst legacy geçişi

- Mevcut kaynaklar içerikleri tahmin edilmeden terminal `legacy-auto@1`
  profiline atanır.
- Backfill, source `version` ve `updated_at` değerlerini değiştirmez.
- Yeni kaynak oluştururken `legacy-auto@1` seçilemez.
- Doğrulanmış açık profile geçiş, eski kaynağı güncellemekle değil yeni derived
  source üretmekle yapılır.
- Mevcut frozen release'ler `absent_pre_registry` olarak işaretlenir; manifest,
  SHA ve membership satırları değiştirilmez. Onlar için child contract snapshot
  veya yeni hash üretilmez; sebep güvenli audit olayında tutulur.

### 1C — Pinning ve release kanıtı

- Source, profil ile config artifact türü/SHA'sını create-time pinler; rubrik
  profil sürümünden ve kampanyadan gelir.
- Review campaign, sample generation ile birlikte review protocol ve politika
  sürümlerini pinler. Kampanya contract SHA256'sını PostgreSQL kanonik pinlerden
  türetir.
- Sample generation kaynak SHA256, örnekleme yöntemi, örnek sayısı ve job
  kimliğiyle immutable'dır; yalnız `active → superseded` yaşam döngüsü geçişi
  yapılabilir. Membership satırları da append-only'dir; deterministik membership
  sayısı/root SHA256'sı hesaplanır. Campaign ve release child snapshot nesil
  alanlarıyla membership sayısı/root'unu yeniden pinler; onaylanan güncel belge
  nesnesi immutable membership nesnesiyle eşleşmek zorundadır.
- Yeni claim ve review aynı kampanya kimliğini sunucudan alır; tarihsel claim ve
  review'lar NULL/pre-registry kalır ve sonradan etiketlenmez.
- Yeni frozen release, her kaynak için kullanılan profil/config/rubrik,
  kampanya/protokol, politika ve export sözleşmesini child snapshot olarak
  kaydeder. Her child, `review_evidence_status=campaign_pinned` ve kampanya
  kimliği ya da yalnız uygun backfilled legacy kanıtı için
  `review_evidence_status=absent_pre_registry` taşır.
- PostgreSQL child snapshot'ları `source_id` ile deterministik sıralar. Release
  üst kanıtını sabit boyutlu `source_count` + `child_snapshot_root_sha256`
  biçiminde, implementation digest'ini de sıralı child implementation
  hash'lerinden türetir.
- Child snapshot; source origin/run/parent kimliğini, run implementation/config/
  input-manifest hash'lerini ve rights/lineage referanslarının SHA256'sını bağlar.
  Model/hibrit kaynakta başarılı production completion job/manifest/çıktı
  SHA256/boyut/kayıt sayısı/tamamlanma zamanını da bağlar; bu kanıt yoksa release
  fail-closed durur.
  Dış manifest ham `lineage_ref`, yerel dosya yolu veya serbest lisans kanıt
  referansı yayımlamaz.
- Eksik/bilinmeyen sözleşme, child sayısı uyuşmazlığı, güncel review kapsamı
  eksikliği veya `contract_snapshot_status<>present` yeni freeze'i fail-closed
  durdurur.

### 1D — Audit ve geri alınabilirlik kanıtı

- Registry ve snapshot tabloları UPDATE/DELETE/TRUNCATE kabul etmez.
- Source sözleşme kimliği create-time only olur.
- DB row-change ledger yalnız güvenli kimlik ve hash özetlerini kaydeder;
  artifact baytları, config gövdesi, ham metin, URL, gerekçe veya kişisel veri
  yazmaz.
- Semantic audit; backfill, kampanya açma, review, reversal ve freeze olaylarını
  actor/request bağlamıyla korur.
- Red→geri al→onay→geri al→red zinciri satır silmeden izlenebilir kalır.

## 5. Bu aşamada yapılmayacaklar

- `translation-v1` veya `reasoning-v1` payload/projection tabloları
- Çeviri hizalama ekranı veya reasoning verifier UI'sı
- Mevcut beş skor kolonunun normalize skor modeline taşınması
- `every_record`, iki bağımsız onay veya adjudication davranışının açılması
- Reviewer qualification uygulaması
- Belgelerin milyonlarca satırına profil kopyalanması
- Otomatik içerik okuyup profile karar verme
- Çok profilli export shard uygulaması
- Takedown/redaction fiziksel şeması
- Eski frozen manifestleri yeniden yazma

Bu kararlar unutulmuş değildir; davranış ve veri modeli pilot ölçümleriyle
kanıtlandıktan sonra uygulanacaktır.

## 6. Uygulama sırası

1. RFC ve danışman karar kaydı güncellenir.
2. Migration, isolated PostgreSQL şemasında entegrasyon testleriyle yazılır.
3. Domain/repository kaynak oluşturma yolu yeni profili yalnız sunucu registry'si
   üzerinden atar.
4. Review campaign açma ve review damgalama aynı transaction sınırında eklenir.
5. Release create/freeze ve worker manifesti child sözleşme snapshot'larını
   üretir; DB `present` geçişinde sabit boyutlu üst bundle/hash'i türetir.
6. Go, worker ve web regresyonları çalıştırılır.
7. Yerel veritabanının localhost olduğu, migration checksum'larının eşleştiği
   ve lock koşullarının uygun olduğu salt-okunur preflight ile doğrulanır.
8. Migration yerel veritabanına bir kez uygulanır.
9. Postflight; schema head, trigger/constraint sayıları, source sayaçları,
   review/reversal zinciri, eski release hash'leri ve yeni audit tablolarını
   karşılaştırır.

### 6.1 Yerel rollout kaydı — 2026-08-21

- Yerel PostgreSQL 18.4 veritabanı `000023` seviyesinden `000026` seviyesine
  yükseltildi; 26/26 migration checksum'u dosyalarla eşleşti ve ikinci migration
  çalıştırması idempotent tamamlandı.
- Beklenen 12 relation, 42 kritik trigger ve 14 kritik constraint eksiksiz,
  etkin ve doğrulanmış bulundu.
- Kritik kaynak sürümü, zamanı ve `200 / 1 / 0 / 1` örnek–incelenen–onaylı–
  işaretli sayaçları değişmedi. Üç review, iki reversal ve tek etkin ret zinciri
  birebir korundu.
- Yedi tarihsel frozen release'in tamamı dürüstçe `absent_pre_registry` olarak
  işaretlendi; geçmişte bulunmayan child snapshot veya bundle üretilmedi.
  Release ve release-source legacy kökleri sırasıyla
  `c6c1acee2037c0d1ed619582599f7b9282a92ee455bd3401de8d556c8715f1bb`
  ve `3961a88187ddee02af5d8ece236448a848816fee97d5242472b366698003e31e`
  olarak değişmeden kaldı.
- `storage_objects` sayısı `742` olarak korundu. Beklenen backfill kanıtı olarak
  audit olayları `558 → 577`, DB row-change ledgeri `0 → 719` oldu; açıklanamayan
  fark, etkin claim veya bekleyen lock bulunmadı.
- Şifreli yedek ve restore tatbikatı bu rollout'un parçası değildir; aşağıdaki
  kabul kapısında belirtildiği gibi kullanıcı kararıyla ertelenmiştir.

Migration tek başına, uygulama kodu eski INSERT/FREEZE davranışında bırakılarak
deploy edilmez. Kırıcı constraint'ler ancak aynı rollout'taki sunucu ve worker
kodları hazır olduğunda etkinleştirilir.

## 7. Kabul kapıları

- Tüm eski Go, worker ve web testleri geçer.
- PostgreSQL entegrasyon testleri gerçek PostgreSQL üzerinde geçer.
- Mevcut source `version` ve `updated_at` değerleri birebir korunur.
- Eski frozen release manifest/hash/membership verisi birebir korunur;
  `release_source_contract_snapshots` child satırı veya yeni bundle hash'i
  oluşmaz. Yalnız `absent_pre_registry` durumu ve audit olayı eklenir.
- Yeni kaynakta unknown/legacy profile fail-closed reddedilir.
- Profil/config/provenance güncelleme girişimi reddedilir.
- Yalnız nesnesiz boş kaynak için transaction'la korunan tek-seferlik
  provenance finalizasyonu geçer; ikinci geçiş ve nesne bağlandıktan sonraki
  değişiklik reddedilir.
- Sample generation identity alanlarının UPDATE/DELETE/TRUNCATE girişimi
  reddedilir; yalnız `active → superseded` durum geçişi kabul edilir.
- Production run niyeti ve ona ait başarılı completion kanıtı ayrı, tek seferlik
  immutable kayıtlardır; sonradan güncelleme veya silme reddedilir. Model/hibrit
  release completion kanıtını ve fiziksel completion manifestini doğrular.
- Artifact türü ve SHA eşleşmezse kayıt reddedilir.
- Yeni claim/review server-derived aynı `review_campaign_id` olmadan yazılamaz;
  client kampanya/rubrik/protokol seçemez.
- Release child'ındaki `review_evidence_status` yalnız `campaign_pinned` veya
  `absent_pre_registry` olabilir ve kampanya kimliğiyle şekil koşulunu sağlar.
- Eksik source snapshot, güncel kampanya review kapsamı veya implementation
  digest ile freeze reddedilir; top contract kanıtını DB `source_count` ve
  deterministik sıralı child root'tan türetir.
- Release snapshot ve manifestte raw rights/lineage yolu bulunmaz; kaynak ve
  production-run kökeni ile örnek nesli pinleri SHA/kimlik üzerinden doğrulanır.
- Audit ledger hiçbir sözleşme baytı, config, ham içerik ya da kişisel veri
  sızdırmaz.
- Backup/restore envanteri ile gelecekteki doğrulama adımları belgelenir.
  Şifreli yedek ve restore tatbikatı kullanıcının önceki kararıyla ertelenmiştir;
  bu Aşama 1 çalışmasında yapılmış veya geçmiş sayılmaz.

## 8. Pilotlar

### `translation-v1`

İlk pilot 10–20 lisanslı çiftle yalnız sözleşme, validator, review UX ve export
akışını doğrular; istatistiksel kalite iddiası değildir. Kaynak/hedef yönü,
iki tarafın hakları, hizalama, sayı/ad/placeholder korunumu, eksiltme-ekleme,
sadakat, tamlık, akıcılık ve terminoloji açıkça ölçülür.

### `reasoning-v1`

İlk pilot deterministik doğrulanabilen dar bir alanla başlar. Problem kimliği,
nihai cevap, yapılandırılmış çözüm kanıtı, verifier sürümü/sonucu, provenance ve
görünürlük politikası tutulur. Otomatik verifier olmayan görevlerde validator
advisory olabilir; insan adjudication yolu korunur.

## 9. Sonraki uzman incelemeleri

Üç genel AI danışman görüşü mimari yönü doğrulamak için kullanılmıştır; insan
uzman onayı yerine geçmez. Uygulama öncesi veya pilot sınırında hedefli olarak:

- PostgreSQL migration/immutability/audit uzmanı,
- veri yönetişimi, KVKK ve lisans uzmanı,
- translation pilotunda MT/hizalama uzmanı,
- reasoning pilotunda verifier/eval uzmanı

kod, şema ve gerçek örnekler üzerinden inceleme yapmalıdır.
