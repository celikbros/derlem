# Yedekleme ve Restore Runbook'u

**Kapsam:** PostgreSQL metadata + içerik adresli object store + operasyon raporları.
**Araçlar:** [deploy/scripts/derlem_backup.py](../deploy/scripts/derlem_backup.py) ve
[deploy/scripts/derlem_restore_drill.py](../deploy/scripts/derlem_restore_drill.py)
(worker venv'iyle çalışır; `pg_dump/pg_restore/psql` gerekir).

## Hedefler (yerel pilot)

| Metrik | Hedef | Not |
|---|---|---|
| RPO (veri kaybı toleransı) | ≤ 24 saat | Günlük yedek; büyük ingest günlerinde ingest sonrası ek yedek |
| RTO (geri dönüş süresi) | ≤ 2 saat | Tatbikatta ölçülen uçtan uca süre ~6 dk (25 GB, yerel disk) |
| Tatbikat sıklığı | Ayda 1 | Her tatbikat raporu yedek köküne yazılır |

## Yedek alma

```powershell
$env:BACKUP_PASSPHRASE = '<kasadaki parola>'
.\.venv\Scripts\python.exe deploy\scripts\derlem_backup.py --backup-root D:\DERLEM-BACKUP --passphrase-env BACKUP_PASSPHRASE
```

Ne yapar:

1. `pg_dump` (custom format) alır; parola verildiyse `openssl aes-256-cbc -pbkdf2`
   ile şifreler ve düz kopyayı siler. Manifest'e hem şifreli hem düz SHA256 yazılır.
2. Object store aynasını **artımlı** günceller: içerik adresli olduğu için var
   olan nesne kopyalanmaz ve **asla silinmez** (yanlışlıkla silmeye karşı doğal koruma).
3. `var/reports` kopyalanır; **şemadaki tüm tabloların** satır sayımı ve tüm çıktıların
   özeti `manifests/backup_<zaman>.json` dosyasına yazılır. Liste sabit değildir,
   `information_schema`'dan türetilir — yeni migration bir tablo eklediğinde
   doğrulama kapsamı kendiliğinden genişler.

Not: `var/derived` yedeğe alınmaz; temiz aday deterministik olarak yeniden
üretilebilir ve kendisi zaten object store'da bir nesnedir.

## Restore tatbikatı

```powershell
$env:BACKUP_PASSPHRASE = '<kasadaki parola>'
.\.venv\Scripts\python.exe deploy\scripts\derlem_restore_drill.py --backup-root D:\DERLEM-BACKUP --passphrase-env BACKUP_PASSPHRASE
```

Ne doğrular (herhangi biri tutmazsa çıkış kodu 1):

1. Şifreli dump çözülür; düz SHA256 manifest ile karşılaştırılır.
2. Dump, **ayrı** `derlem_restore_drill` veritabanına geri yüklenir (canlı DB'ye
   asla dokunulmaz); **tüm tabloların** sayımı yedek anındaki manifestle birebir
   karşılaştırılır.
3. Yedek aynasındaki **her nesnenin** SHA256'sı yeniden hesaplanır ve dosya
   adıyla doğrulanır (bit çürümesi/bozulma kontrolü).
4. Geri yüklenen katalogdaki her `storage_objects` kaydının ve her frozen
   release manifest nesnesinin yedekte var olduğu kanıtlanır (zincir bütünlüğü).
5. Rapor `manifests/restore_drill_<zaman>.json` olarak yazılır; tatbikat
   veritabanı silinir (`--keep` ile korunabilir).

## Gerçek felakette geri dönüş

1. Yeni makinede PostgreSQL + repo kurulumunu yapın ([local_development.md](local_development.md)).
2. `pg_restore --no-owner --dbname <yeni derlem db> <çözülmüş dump>` (şifreliyse
   önce `openssl enc -d -aes-256-cbc -pbkdf2` ile çözün).
3. Yedek `objects/` aynasını `STORAGE_ROOT/objects/` konumuna kopyalayın.
4. Doğrulama için tatbikat scriptini `--backup-root` olarak yeni depoya karşı koşun.
5. Servisleri başlatın; İşler ekranı ve kaynak kataloğu durumu teyit edin.

## Güvenlik notları

- Yedek parolası yedek diskinde TUTULMAZ; parola kasasında saklanır.
  (İlk kurulumda üretilen `PASSPHRASE-MOVE-TO-VAULT.txt` dosyasını kasaya
  taşıyıp diskten silin.)
- Object aynası şifresizdir; yedek sürücüsünde BitLocker önerilir. Uçtan uca
  at-rest şifreleme `SEC-P1-06` kapsamındadır.
- Yedek kökü ayrı fiziksel sürücüde olmalıdır; offsite/ikinci kopya ve gerçek
  WORM/object-lock `SEC-P0-06`'nın açık kalan ayağıdır.

## Tatbikat Kaydı

| Tarih | Yedek | Sonuç | Kanıt |
|---|---|---|---|
| 2026-07-06 | `backup_20260705_213712` (şifreli dump + 724 nesne, 25 GB) | **PASS** — 16 tablo sayımı birebir; 724/724 nesne SHA256 doğru; katalog + frozen manifest zinciri tam; süre ~6 dk | `D:\DERLEM-BACKUP\manifests\restore_drill_20260705_213916.json` |

> **Bu kaydın sınırı (2026-07-26'da eklendi).** Yukarıdaki PASS damgası o günkü kod
> gereği yalnız **16 tabloyu** karşılaştırdı; `document_fingerprints`,
> `document_sample_memberships`, `document_sample_generations`, `roles`, `user_roles`
> ve `contributions` doğrulama dışındaydı. Sayım listesi 07-26'da şemadan türetilecek
> şekilde düzeltildi; bundan sonraki tatbikatlar tüm tabloları kapsar.
>
> **Ayrıca:** kanıt dosyasının yolu (`D:\DERLEM-BACKUP`) bugün erişilemiyor — bu makinede
> D: sürücüsü yok. Yedek kökünün nerede tutulacağı açık bir karardır; 2026-07-16'daki
> depo kaybı bu boşlukta yaşandı (bkz. [veri_kurtarma_2026_07.md](veri_kurtarma_2026_07.md)).
