# Danışman İnceleme İsteği: Derlem'de Çok Türlü Eğitim Verisi Mimarisi

**Tarih:** 2026-08-21

**Durum:** Karar öncesi inceleme — kod/migration uygulanmadı

**Teknik taslak:** `docs/versioned_data_profiles_rfc.md`

## Kısa talep

Derlem'i ayrı çeviri ve reasoning ürünlerine bölmeden; aynı veri yönetişim
çekirdeğinde farklı eğitim verisi türlerini güvenli, sürümlü ve yeniden
üretilebilir biçimde yönetmek istiyoruz.

Önerimiz, kaynağın kullanım amacından (`content_purpose`) ayrı, sürümlü bir
**veri sözleşmesi** (`data_profile`) kimliği eklemektir. Bu kimlik kaydın
şemasını, validator'larını, insan inceleme kapsamını/rubriğini ve export
sözleşmesini sürümleyecektir.

Sizden uzun bir genel değerlendirmeden çok, bu temel kararın şimdi alınıp
alınmaması ve önerilen sınırların doğru olup olmadığı konusunda net görüş
istiyoruz.

## Derlem bugün nedir?

Derlem model veya tokenizer eğitmez. Aşağıdaki veri yaşam döngüsünü yönetir:

- Kaynak, hak/lisans, dil, domain ve lineage kaydı
- Büyük içeriğin SHA256 adresli immutable object store'da tutulması
- PII, exact/normalized dedup, risk ve örneklem kapıları
- Çakışmasız insan incelemesi, append-only karar ve geri alma geçmişi
- Frozen release, manifest, checksum ve JSONL/TXT export
- İnsan katkısı (`qa_pair`, `free_text`) ve kontrollü LLM distilasyonu

PostgreSQL büyük metni değil; metadata, job, review, audit ve release
kayıtlarını tutar. Go API, Python worker ve Next.js arayüz kullanılır.

## Mevcut gerçek sınırlar

- `content_purpose` verinin kullanım havuzunu belirtir; veri şekli değildir.
- Kaynakta yalnız tek `language` vardır.
- Belge incelemesi genel metin rubriği kullanır.
- Kanonik conversation/preference export vardır; fakat serbest `task_type`
  göreve özel validator veya UI seçmez.
- Aktif katkı API'si yalnız `qa_pair` ve `free_text` kabul eder.
- Çeviri için source-target pair/alignment ve çeviri rubriği yoktur.
- Reasoning alanını taşıma/görünürlük politikası vardır; problem-adım-final
  cevap-verifier üretim ve doğrulama hattı yoktur.
- Mevcut büyük-corpus örneklemesi kaynak kabul sinyalidir; milyonlarca satırın
  tek tek doğrulandığı anlamına gelmez.
- Mevcut freeze kapısı profile göre her kayıt için onay, birden çok bağımsız
  onay veya uyuşmazlık çözümü zorunluluğu tanımlayamaz.
- Export kalite yaratmaz; seçilmiş frozen release'i deterministik paketler.

## Hedefimiz

Tek Derlem kurulumu içinde şu veri türlerini yönetmek:

- düz pretraining metni
- instruction / soru-cevap
- kaynak-hedef çeviri çiftleri
- doğrulanabilir reasoning çözümleri
- preference/chosen-rejected
- tool-use kayıtları
- eval ve holdout

Ham veri değişmeyecek. Her üretim veya düzeltme ayrı türetilmiş kaynak ve
lineage oluşturacak. İnsan ve sentetik üretim açıkça ayrılacak. Eski kararlar ve
eski release'ler yeni kurallarla yeniden yorumlanmayacak.

## Önerdiğimiz mimari

```text
Derlem ortak çekirdeği
  + sürümlü data profile registry
  + profile özgü validator/verifier
  + profile özgü review kapsamı, güvenli UI ve rubrik
  + profile/version snapshot'lı frozen release
  + modelden bağımsız export sözleşmeleri
```

Ayrı mikroservis veya ayrı veritabanı önermiyoruz. Profil, kullanıcı tarafından
yüklenen çalıştırılabilir plugin olmayacak; desteklenen sürümler kod ve migration
allowlist'iyle açılacak.

İlk migration yalnız profile registry, immutable source profile kimliği ve
release snapshot alanlarını ekleyecek. Translation/reasoning özellikleri daha
sonraki küçük pilotlarda açılacak.

## Değerlendirdiğimiz alternatifler

1. **Mevcut metadata/task_type ile devam:** ucuz, ancak sözleşme ve eski karar
   kanıtı zayıf.
2. **Her görev için ayrı sistem:** güçlü ayrım, fakat auth/audit/storage/release
   tekrarına ve operasyon yüküne yol açar.
3. **Her şeyi generic JSONB/EAV yapmak:** esnek, fakat DB bütünlüğü ve güvenli
   sorgu zayıflar.
4. **Ortak çekirdek + sürümlü profil + gerektiğinde typed projection:** önerimiz.

## Planımız

1. Danışman görüşü ve mevcut kaynak-profile envanteri
2. Davranış değiştirmeyen geriye uyumlu temel migration
3. 10–20 kayıtlık `translation-v1` pilotu
4. Otomatik doğrulanabilir küçük bir alanda `reasoning-v1` pilotu
5. Pilot ölçümleriyle rubrik, validator ve export sözleşmesini sürümlemek

## Özellikle yanıtlamanızı istediğimiz sorular

1. Derlem'in ürün sınırı yalnız veriyi doğrulamak/release etmek mi olmalı;
   insan ve LLM üretimini provenance ile yöneten birinci sınıf veri üretim
   katmanı da kapsamda olmalı mı?
2. `content_purpose` ile `data_profile` ayrımı doğru ve gerekli mi?
3. Bu temel profile kimliğini şimdi eklemek mi doğru, yoksa gerçek translation
   pilotundan sonra mı genelleştirmeliyiz?
4. Profil kaynak düzeyinde tek ve immutable mı olmalı; belge düzeyinde karışık
   profile izin verilmeli mi?
5. Mevcut kaynakları `legacy-auto-v1` ile korumak mı, envanterle açık profillere
   sınıflandırmak mı daha güvenli?
6. Profile registry DB + kod allowlist'i şeklinde mi olmalı?
7. Göreve özgü metadata için typed projection + object-store payload hibriti
   doğru mu? Kritik alanlardan hangileri mutlaka relational olmalı?
8. Göreve özgü rubrik skorları için JSONB, normalize dimension tablosu veya
   typed annotation tablolarından hangisini önerirsiniz?
9. İnceleme kapsamı, gerekli bağımsız onay sayısı ve uyuşmazlık çözümü hangi
   sürümlü sözleşmede tutulmalı?
10. Frozen release profil/schema/rubric/review-protocol/export contract
   sürümlerini kaynak
   snapshot'ında tutmalı mı?
11. Bir release birden fazla profili taşımalı mı; taşıyacaksa shard ve manifest
   sınırı nasıl olmalı?
12. Yüksek değerli translation/reasoning verisinde per-record insan onayı hangi
    durumlarda zorunlu; verifier+örneklem ne zaman yeterlidir?
13. Reasoning için uzun serbest chain-of-thought yerine kısa, yapılandırılmış ve
    doğrulanabilir çözüm kaydı yaklaşımını onaylıyor musunuz?
14. Bu öneride ileride pahalı migration veya veri kaybına yol açacak hangi
    kör nokta var?

## Kırmızı çizgilerimiz

- Ham kaynak yerinde değişmez.
- Hak/PII/eval sızıntısı kapıları atlanmaz.
- Producer kendi kaydını onaylamaz.
- Review ve reversal geçmişi silinmez veya overwrite edilmez.
- Export sırasında açıklanmayan/sessiz kalite filtresi çalışmaz.
- Frozen release sonradan değiştirilmez.
- Model/provider özel template kanonik veriye gömülmez.

## Beklenen kısa cevap biçimi

```text
Danışman:
Uzmanlık:
Tarih:

1. Ana karara katılıyor musunuz? (Evet/Hayır/Kısmen)
2. En kritik mimari risk:
3. Şimdi yapılması gereken temel değişiklik:
4. Ertelenmesi gereken bölüm:
5. Kaynak düzeyi mi, belge düzeyi profil mi?
6. Registry ve schema saklama öneriniz:
7. Review/rubrik veri modeli öneriniz:
8. Release/export sözleşmesi için zorunlu alanlar:
9. Translation pilotu için zorunlu kontroller:
10. Reasoning pilotu için zorunlu kontroller:
11. Migration/backfill için kırmızı çizgi:
12. Nihai tavsiye:
```
