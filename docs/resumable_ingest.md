# Kesintiden Devam Eden Büyük Dosya Alımı

Derlem, `ingest_local_file` ve `ingest_staged_file` işlerinde tamamlanan kopyalama
bölümünü job UUID'si ve lease attempt numarasına bağlı bir checkpoint olarak
saklar. Normal yeniden denenebilir hata yolunda kapanmış checkpoint atomik olarak
sonraki attempt'e devredilir ve aynı dosya baştan yazılmaz. Heartbeat'i kesilmiş
stale attempt hâlâ yazıyor olabileceğinden onun checkpoint'i güvenlik gereği
devredilmez; yeni attempt sıfırdan başlar.

## Güvenlik Sözleşmesi

- Checkpoint yolu kullanıcı girdisinden alınmaz; yalnızca doğrulanmış job UUID'si
  ve pozitif attempt numarasından
  `var/storage/.tmp/ingest-<job-id>-attempt-<n>.part` biçiminde üretilir.
- Devam etmeden önce checkpoint'in tamamı kaynak dosyanın aynı uzunluktaki önekiyle
  byte byte karşılaştırılır.
- Checkpoint kaynaktan büyükse veya önek farklıysa checkpoint silinir ve kopyalama
  güvenli biçimde sıfırdan başlar.
- Kaynağın boyutu, değiştirilme zamanı veya dosya kimliği işlem sırasında değişirse
  ingest hata verir; karışık içerik yayımlanmaz.
- POSIX metin hızlı yolu özel attempt adına hard link kullanır; Windows özel
  kopya kullanır. Hard link ad/inode kimliğini
  sabitler ama inode baytlarını salt-okunur yapmaz; `IMPORT_ROOT` dosyaları ve ata
  dizinleri job tamamlanana kadar yazma/rename yetkisi olmayan güvenilir handoff
  alanı olmalıdır. Düşmanca yerel writer bu sözleşmenin dışındadır.
- SHA256, UTF-8 doğrulaması ve satır sayımı checkpoint öneği yeniden okunarak kurulur.
  Hash nesnesi veya güvenilmeyen ara durum serileştirilmez.
- Content-addressed nesneye hard-link olmuş bir checkpoint'e yeni byte eklenmeden
  önce bağlantı ayrılır. Eski SHA256 nesnesi yerinde değiştirilemez.
- Final CAS yolu hiçbir zaman stream-copy hedefi yapılmaz. Tam yazılmış ve
  `fsync` edilmiş özel dosya atomik create-only yayımlanır; mevcut hedef boyut ve
  SHA256 ile doğrulanmadan başarı kabul edilmez.

## Yaşam Döngüsü

1. İlk denemede worker checkpoint'e 1 MiB bloklarla yazar.
2. Yaklaşık her 64 MiB'de checkpoint `flush` ve `fsync` edilir, ardından progress
   PostgreSQL'e yazılır.
3. Normal retryable hatada kapanmış checkpoint sonraki attempt adına atomik
   taşınır. Lease timeout/stale recovery'de eski writer ile yarışmamak için eski
   checkpoint silinir veya DB-aware sweeper'a bırakılır.
4. Sonraki deneme önce `validating_checkpoint`, sonra `ingesting` fazını yayınlar.
5. İçerik immutable store'a yayımlanıp kaynak transaction'ı başarıyla commit edilince
   checkpoint silinir.
6. İş son denemesinde de başarısız olursa checkpoint temizlenir. Tarayıcı staging
   dosyası yalnızca başarılı ingest sonrasında silinir.

## Sonuç ve Denetim Alanları

Başarılı job result ve `source.ingested` audit olayı şu operasyon alanlarını taşır:

- `resumed_from_bytes`: yeni kopyalamanın başladığı doğrulanmış byte konumu,
- `checkpoint_revalidated_bytes`: bu denemede yeniden doğrulanan byte sayısı,
- `checkpoint_reset`: geçersiz checkpoint nedeniyle sıfırdan başlanıp başlanmadığı.

Bu alanlar içerik kimliği değildir. Kanonik kimlik her zaman yayımlanan nesnenin
SHA256 değeridir.
