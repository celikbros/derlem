# Sürümlü Veri Profilleri — Danışman Görüşleri ve Karar Matrisi

**Tarih:** 2026-08-21

**Durum:** Mimari sentez ve karar kaydı — Aşama 1 kodu, izole PostgreSQL
doğrulaması ve yerel veritabanı migration/postflight adımı `000024`, `000025`
ve `000026` ile tamamlandı

**Bağlı RFC:** [`versioned_data_profiles_rfc.md`](versioned_data_profiles_rfc.md)

**İcra planı:**
[`versioned_data_profiles_implementation_plan.md`](versioned_data_profiles_implementation_plan.md)

**Operasyon notu:** Şifreli backup/restore ve restore tatbikatı, kullanıcının
önceki kararıyla ertelenmiştir; bu çalışma kapsamında yapılmış sayılmaz.

## 1. Amaç ve kanıt sınırı

Bu belge Grok, Claude ve Opus danışman görüşlerini Derlem için tek bir karar
kaydında birleştirir. Görüşler mimari tasarım incelemesidir; kod, migration,
üretim veritabanı veya hukuki uygunluk denetimi değildir. Kabul edilen Aşama 1
maddeleri daha sonra mevcut şema ve izole PostgreSQL testleriyle doğrulanmış;
yerel veritabanına uygulanmış ve migration öncesi/sonrası tarihsel kökler
postflight ile birebir karşılaştırılmıştır.

Durumların anlamı:

- **Kabul:** Mimari yön veya Aşama 1 sınırı olarak benimsendi.
- **Ret:** Bu biçimiyle benimsenmedi; gerekçeli başka çözüm seçildi.
- **Ertele:** İlke doğru olabilir, fakat veri modeli veya davranış pilot
  ölçümünden önce sabitlenmeyecek.

## 2. Ortak sonuç

Üç görüşün ve iç teknik değerlendirmenin ortak sonucu:

1. Derlem tek, modüler bir veri yönetişimi çekirdeği olarak kalır.
2. Çeviri veya reasoning için ayrı ürün/veritabanı kurulmaz.
3. `content_purpose` ile `data_profile` ayrı, dik eksenlerdir.
4. Profil kaynak düzeyinde tek ve immutable'dır.
5. Aşama 1 yalnız geri dönüşü pahalı kimlik ve kanıt omurgasını kurar.
6. Translation/reasoning özelliği, normalize skorlar, typed projection'lar ve
   yeni çoklu onay davranışı pilotlarda tasarlanır.

## 3. Karar matrisi

| Konu | Grok | Claude | Opus | Derlem kararı | Durum |
|---|---|---|---|---|---|
| Ortak çekirdek + sürümlü profil | Doğrudan destekliyor | Doğrudan destekliyor | Koşullu destekliyor | Tek Derlem çekirdeği korunacak | Kabul |
| Aşama 1 kapsamı | Kimlik ve snapshot ile dar tutuyor | Kimlik şimdi, ayrıntı pilotta | Kimlik + geri getirilebilir kanıt istiyor | Aşama 1 tarihsel anlamı korur; yeni claim/review ve freeze'e pinli, fail-closed kanıt ekler | Kabul |
| Profil granülerliği | Kaynak düzeyi, immutable | Kaynak düzeyi, immutable | Kaynak düzeyi; belgeye de kopya öneriyor | Kaynak düzeyi immutable FK; Aşama 1'de `documents`a denormalize kopya yok | Kısmi ret |
| `content_purpose` ayrımı | Destekliyor | Protokolü profile gömmemeyi vurguluyor | Ayrı eksen olarak destekliyor | Purpose kullanım; profile veri sözleşmesidir | Kabul |
| İnceleme protokolü | İlk migrationda davranış açma diyor | Profil×amaç bağında ayrı protokol istiyor | Kesin protokol pinlemesi istiyor | Protokol profile gömülmez; profil×amaç için seçilip review işi başında pinlenir | Kabul |
| Freeze anında `effective_from` ile kayan seçim | Belirgin öneri yok | Binding seçimini öneriyor | İş ortasında sürüm değişimine karşı pin istiyor | Release kesin pinlenmiş sürümü snapshot'lar; freeze anında kayan seçim yapılmaz | Ret |
| Rubrik | Sürümlü kimlik öneriyor | Rubriği profile bağlıyor | Spec baytlarının da saklanmasını istiyor | Sürümlü rubrik profile bağlı; kimlik/hash/bayt kanıtı tutulur | Kabul |
| Normalize skor modeli | Pilot sonrasını destekliyor | Aşama 1'e normalize tablo öneriyor | Nihai modeli ertelemeyi öneriyor | Mevcut kolonlar korunur; normalize model pilot ölçümüyle seçilir | Ertele |
| Typed projection | Pilotta | Pilotta | Pilotta; yeniden üretilebilir olmalı | Aşama 1'de DDL yok; payload'dan yeniden üretilebilir typed projection pilotta | Ertele |
| Profil farkında dedup/leakage/PII | Genel kapıları koruyor | En kritik açık olarak alan bazlı fingerprint istiyor | Policy kimliklerinin release'e taşınmasını istiyor | Profil alan çıkarma sözleşmesi sağlar; PII, dedup ve leakage ayrı sürümlü politikalardır | Kabul |
| `profile_config` şeması | Hash öneriyor | Config şeması ve fail-closed doğrulama istiyor | Kanonik bayt kanıtı istiyor | Config şeması artifact'i profile bağlıdır; source inline JSON yerine content-addressed `profile_config` artifact türü/SHA'sını pinler | Kabul |
| Kanonik serileştirme/Unicode | Belirgin öneri yok | JCS benzeri kanonikleştirme ve Türkçe normalizasyon uyarısı | Hash'in gerçek baytları kanıtlamasını istiyor | Yöntem sürümlenir; Türkçe `I/İ/ı/i` sessizce normalize edilmez | Kabul |
| Spec baytlarının saklanması | Repo dosyası + hash'i yeterli görüyor | Repo + object-store kopyası öneriyor | Hash ancak baytlar geri getirilebilirse kanıttır diyor | Küçük kanonik spec baytları ilk aşamada atomik, content-addressed DB artifact store'da tutulur; object-store aynası sonra eklenebilir | Kısmi kabul |
| `implementation_key` | Kod allowlist'i öneriyor | Kod allowlist'i öneriyor | Kod semantiği kaymasına karşı implementation digest istiyor | Key yanında deterministik `implementation_bundle_sha256` snapshot'lanır | Kabul |
| Provenance | Üretimi provenance ile yönetmeyi destekliyor | Production job'ı giriş kapısı olarak görüyor | Origin/producer'ı birinci sınıf istiyor | Origin ve `production_run_id` immutable üretim niyetidir; başarılı çıktı ayrı append-only `production_run_completions` kanıtıyla bağlanır ve model/hibrit release bunu pinler; eğitim Derlem dışında kalır | Kabul |
| Mevcut kaynak backfill'i | `legacy-auto-v1` | Terminal legacy + atama gerekçesi | Terminal legacy + dürüst atama | Tüm eski kaynaklar `legacy-auto@1` ve `backfilled` gerekçesi alır; içerik okunarak tahmin yok | Kabul |
| Eski frozen release'e legacy snapshot | Legacy ile backfill ifadesi var | Eski release satırlarını etiketlemeye açık | Olmayan snapshot'ı sonradan yazmayı reddediyor | Eski `release_sources` overwrite edilmez; legacy snapshot yazılmaz | Ret |
| Eski snapshot yokluğu | Belirgin öneri yok | Manifesti değiştirmeme diyor | `contract_snapshot_absent` öneriyor | Release `absent_pre_registry` durumunu ve audit olayını taşır; child snapshot/hash üretilmez | Kabul |
| Takedown/redaction | Belirgin öneri yok | Kör nokta olarak işaretliyor | Frozen release ile yasal silme çatışmasını vurguluyor | Tombstone/silme kanıtı + `release_integrity_exception`; sessiz yeniden yazma yok | Kabul |
| Multi-approval/every-record | İlk migrationdan çıkarıyor | Profil×amaç protokolünde tasarlıyor | Kimlik şimdi, davranış sonra | Aşama 1 yalnız protokol kimliği taşır; davranış pilotta kalibre edilir | Ertele |
| Translation/reasoning projection ve UI | Pilot istiyor | Pilot istiyor | Pilot istiyor | Aşama 2/3'e ertelendi | Ertele |
| Reasoning ölçütü | Kısa/yapılandırılmış diyor | Doğrulanabilirlik ve provenance vurgusu | Uzun trace'in varsayılan export dışı olmasını istiyor | Ölçüt kısalık değil; yapılandırılmış, doğrulanabilir ve kökeni belli olmasıdır | Kabul |
| Dinamik plugin/EAV motoru | Önermiyor | Önermiyor | Önermiyor | Çalıştırılabilir profil/plugin yok; DB registry + kod allowlist'i | Ret |

## 4. Kabul edilen hedef ayrım

~~~text
data_profile
  ├─ payload/config schema
  ├─ validator/verifier kimliği
  ├─ review görünümü + rubric
  ├─ field extraction contract
  └─ export contract

data_profile × content_purpose
  ├─ review protocol
  ├─ PII policy
  ├─ dedup policy
  └─ leakage/decontamination policy

review campaign
  ├─ kesin profil/config/rubrik/protokol/policy pin'leri
  ├─ PostgreSQL-türetilmiş campaign contract SHA
  └─ claim + review üzerinde aynı server-derived campaign ID

new frozen release
  ├─ source başına contract snapshot + review_evidence_status
  ├─ geri getirilebilir spec artifact SHA/baytları
  ├─ model/hibrit kaynakta append-only production completion kanıtı
  ├─ DB-türetilmiş implementation bundle digest
  └─ sabit boyutlu üst kanıt: source_count + sıralı child root
~~~

Profil kaydın *ne olduğunu*, purpose *nerede kullanılabileceğini*, protokol ise
*ne kadar kanıt gerektiğini* söyler. Provenance bu eksenlerin dışında, kaydın
*nasıl ve kim tarafından üretildiğini* kanıtlar.

## 5. Aşama 1'in kesin sınırı

### Dahil

- Append-only profil, rubrik, protokol, policy ve export registry kimlikleri
- Kanonik spec baytları ve content-addressed artifact kayıtları
- Kaynakta immutable profil, content-addressed config artifact türü/SHA,
  provenance ve atama gerekçesi
- Profil×amaç uyumluluğu ve kesin sözleşme pin/snapshot kimliği
- Claim/review üzerinde aynı server-derived `review_campaign_id`
- Source snapshot'ında `review_evidence_status`:
  `campaign_pinned|absent_pre_registry`
- Yeni release'lerde PostgreSQL-türetilmiş contract/implementation bundle
  digest'leri; sabit boyutlu üst kanıtta `source_count` ve deterministik sıralı
  child root
- Eski frozen release'lerde overwrite yerine snapshot-yokluğu kanıtı
- Takedown/redaction bütünlük istisnası için bağlayıcı politika tasarımı;
  fiziksel kayıt yolu ilk yeni görev profili release'inden önce ayrı bir
  güvenlik migration'ıyla uygulanır
- İmmutability, audit ve bayt-özdeş legacy export testleri; backup/restore kabul
  envanteri belgelenir, şifreli yedek/restore tatbikatı kullanıcı kararıyla
  daha sonraya bırakılır

### Dahil değil

- Yeni translation veya reasoning iş akışı
- Normalize review score şeması
- Translation/reasoning typed projection tabloları
- Yeni `every_record`, iki onay veya hakemlik davranışı
- Çok profilli release sharding uygulaması
- Üretim/distilasyon UI'ı
- İçerik okuyarak otomatik profil tahmini

Bu sınır, gelecekte pahalı ve dürüst olmayan geriye dönük atamaları önler.
Tarihsel ingest/review/release/manifest anlamı korunur; yeni claim/review
kampanyasız yazılamaz ve yeni freeze eksiksiz DB-türetilmiş `present` kanıtı
yoksa kapanmaz.

## 6. Geçmiş veriye ilişkin bağlayıcı karar

Kaynak backfill'i ile frozen release kanıtı aynı şey değildir:

- **Mevcut kaynak:** `legacy-auto@1` atanabilir; atama zamanı ve
  `profile_assignment_reason=backfilled` açıkça kaydedilir. Kaynak
  `version`/`updated_at` değişmez.
- **Mevcut frozen release:** Freeze tarihinde olmayan sözleşme snapshot'ı
  eklenemez. `release_sources` satırı overwrite edilmez, manifest yeniden
  üretilmez ve `legacy-auto@1` snapshot'ı yazılmaz.
- **Kanıt:** Release `contract_snapshot_status=absent_pre_registry` durumunu,
  güvenli audit olayı da registry öncesi freeze açıklamasını taşır. Child
  snapshot veya yeni contract/implementation hash'i yazılmaz.

Bu ayrım geçmişi daha eksiksiz göstermez; fakat gerçeğe uygun ve denetlenebilir
gösterir.

## 7. Kalan riskler ve çıkış koşulları

| Risk | Aşama 1 çıkış koşulu |
|---|---|
| Hash var, spec baytı yok | Her spec hash'inin kanonik baytı artifact store'dan geri alınabilir ve SHA ile doğrulanabilir; restore tatbikatı ayrıca yapılacaktır |
| Aynı implementation key farklı davranıyor | Release implementation bundle digest'i taşır |
| Devam eden işte protokol değişiyor | Review campaign kesin sürümlere pinlidir; claim ve review aynı server-derived campaign ID'yi taşır |
| Kaynak sayısı büyüdükçe üst artifact şişiyor | DB üst kanıta yalnız `source_count` ve `source_id` sıralı child snapshot kökünü yazar |
| Eski release'e geriye dönük anlam yükleniyor | Eski satır değişmez; snapshot yokluğu ayrı kanıttır |
| Structured payload'da leakage atlanıyor | Profil alan çıkarma + ayrı policy sürümleri snapshot'lanır |
| Legacy profil kalıcı çöplüğe dönüşüyor | Yeni kaynakta kapalı; doğrulanmış geçiş yalnız derived source ile |
| Yasal silme release bütünlüğünü sessiz bozuyor | Politika Aşama 1'de bağlayıcıdır; yetkili takedown + tombstone + görünür bütünlük istisnası ilk yeni görev profili release'inden önce uygulanır |
| Pilot varsayımları erken DDL oluyor | Skor/projection/multi-approval Aşama 1 dışında kalır |

## 8. Son karar

Mimari yön onaylanmıştır: **ortak çekirdek + sürümlü veri sözleşmesi +
purpose'a bağlı, pinlenmiş inceleme/policy kanıtı**.

Aşama 1'in kimlik ve kanıt kapsamındaki kodu ile izole PostgreSQL doğrulaması
`000024`, `000025` ve `000026` üzerinden tamamlanmıştır. Aynı migration dizisi
yerel veritabanına uygulanmış; checksum, trigger/constraint, kaynak sayaçları,
review/reversal zinciri ve legacy frozen release kökleri postflight'ta
doğrulanmıştır. `production_runs` immutable üretim niyeti,
`production_run_completions` ise append-only tamamlanma kanıtıdır. Pilotla
ölçülmesi gereken skor, projection, reviewer yeterliliği ve çoklu onay
tasarımları bu migration dizisinin tamamlanma koşulu değildir.
