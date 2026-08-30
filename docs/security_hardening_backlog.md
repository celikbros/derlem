# Derlem Güvenlik Hardening Backlog'u

**Tarih:** 2026-07-01
**Durum:** Açık, production güvenlik kapısı; 6/8 P0 açık
**Referans seviye:** OWASP ASVS Level 2 hedefi

Bu belge bilinen güvenlik eksiklerinin sohbet veya genel yol haritası içinde
kaybolmasını önler. Yerel, tek makinedeki kapalı Gardas pilotu devam edebilir;
ancak **P0 maddeleri kapanmadan internet-facing staging/production, açık katkı
ve dış kullanıcı erişimi açılamaz.**

## Öncelik Tanımı

- **P0:** Production ve dış erişim bloklayıcısı.
- **P1:** v1.0 ve resmi model-ekibi kullanımı öncesi zorunlu.
- **P2:** Savunma derinliği ve operasyon olgunluğu.

## Mevcut Güçlü Kontroller

- JWT doğrulaması, RBAC ve bcrypt parola hash'i.
- En az 32 karakter JWT secret ve en az 12 karakter bootstrap parola kontrolü.
- Parametreli PostgreSQL sorguları ve transaction tabanlı karar akışları.
- Append-only audit trigger'ları.
- İçerik-adresli SHA256 nesne deposu ve immutable frozen release sözleşmesi.
- Upload boyut sınırı, filename sanitization ve staging izolasyonu.
- PII, haklar, dedup, decontamination ve insan review kapıları.
- `HttpOnly`, `SameSite=Lax`; production build'de `Secure` session cookie.
- Temel `nosniff`, frame deny ve referrer güvenlik başlıkları.

Bu kontroller önemlidir fakat aşağıdaki production açıklarını tek başına kapatmaz.

## P0 - Production Bloklayıcıları

| ID | Açık / mevcut kanıt | Risk | Kapanış kriteri |
|---|---|---|---|
| `SEC-P0-01` | **Kapandı, 2026-07-01.** Tüm veri route'ları açık ve boş olmayan rol politikasıyla fail-closed kaydediliyor; ham/karantina çalışma alanı operasyon rollerine, similarity tam metni reviewer rollerine, job verisi admin/data manager'a kapalı; consumer yalnız frozen release görür. | Yeni endpoint'in yanlış role açılması veya frontend kontrolüne güvenilmesi. | [`api_authorization_matrix.md`](api_authorization_matrix.md), yedi rolün tüm korumalı GET uçlarındaki pozitif/negatif testleri ve consumer draft-release filtresi. Kaynak/proje ACL'si public multi-tenant katkı öncesi `SEC-P1-02` kapsamındadır. |
| `SEC-P0-02` | **Kapandı, 2026-07-01.** PostgreSQL session store, hash'li 256-bit `jti`, 30m idle/8h absolute timeout, current/all-session revoke, `auth_version` status/parola/rol trigger'ları ve hesap+IP throttling çalışıyor. | Yanlış proxy güveni, session tekrar kullanımı veya rate-limit regression'ı. | [`session_security.md`](session_security.md); unit ve desktop/mobile E2E testleri; `429 + Retry-After`; başarısız/bloklu login audit ve structured warning; rollback'li auth-version trigger smoke. Merkezi alarm `SEC-P1-03`, admin MFA/Keycloak uygulaması `SEC-P1-01` kapsamındadır. |
| `SEC-P0-03` | Nginx örneği HTTP dinliyor ve HTTPS redirect yorum satırında; HSTS/CSP/Permissions-Policy yok. Hassas API yanıtlarında genel `Cache-Control: no-store` ve state-changing BFF uçlarında açık CSRF kontrolü yok. Production DB örneği `sslmode=disable`. | Token/veri dinleme, downgrade, XSS etkisinin büyümesi, cache sızıntısı ve CSRF. | Production startup fail-closed; HTTPS-only TLS 1.2/1.3, HSTS; `Secure` cookie doğrulaması; CSP, Permissions-Policy, `no-store`, logout `Clear-Site-Data`; Origin/CSRF doğrulaması; DB TLS veya belgelenmiş private-network istisnası. |
| `SEC-P0-04` | **Kısmen kapandı — Faz 1 (2026-08-21):** mevcut semantik `audit_events` defterine ek olarak kritik kalıcı iş tablolarındaki `INSERT/UPDATE/DELETE` işlemleri veritabanı trigger'larıyla `row_change_events` tablosuna yazılıyor. Defter append-only; tablo/işlem/güvenli satır anahtarı/değişen kolonlar, transaction ve DB rolü ile pozitif izin listeli kırpılmış önce/sonra özetleri ve bunların SHA256 değerlerini tutuyor. Ayrıca her `/api/` isteği için sunucuda UUID `request_id` üretilip yanıtta `X-Request-ID` olarak dönülüyor; `http.request` olayı actor ID/rolleri, hash'li session kimliği, method, ham path yerine route pattern, status, `duration_ms` ve `response_bytes` alanlarını, ortak API hata yanıtlarında (401/403, başarısız giriş, 429 ve handler 4xx/5xx dahil) `failure_code` değerini kaydediyor. DB audit kaydına raw path/query/header/body ile IP/UA alınmıyor. Açık kalan Faz 2/3: semantik business `audit_events` ve `row_change_events` aynı `request_id`/transaction ile korele değil; immutable actor e-posta/kimlik snapshot'ı, CLI operatör kimliği ve hassas read/download olay sınıflandırması yok. Runtime/migration DB yetkileri ayrılmadı; DB sahibi trigger'ı aşabilir veya doğrudan sahte ledger kaydı ekleyebilir; off-host/WORM ya da hash zinciri ile retention politikası yok. | Yetkili DB hesabı logu bozabilir; geçmiş kimlik ve olay zinciri ispatı zayıflar; veri sızıntısı izlenemez. | Ayrı migration-owner/runtime DB rolleri; runtime için audit mutation ve doğrudan insert kesin yasak; semantik olay/row-change ile gerçek request/transaction korelasyonu; immutable actor kimlik snapshot'ı; CLI service/operator identity; hassas read/download audit sınıflandırması; off-host append-only/WORM veya hash-zincirli audit; retention/redaction politikası. |
| `SEC-P0-05` | Secret'lar env dosyasından yükleniyor; rotation/revocation mekanizması yok. Bootstrap secret'ı yanlışlıkla production'da kalabilir; `CHANGE_ME` ve local test hesapları startup'ta reddedilmiyor. | Secret sızıntısı, kalıcı hesap ele geçirme ve ortam karışması. | Vault/secret manager veya korumalı secret dosyası; düzenli JWT/DB secret rotation runbook'u; ayrı servis kimlikleri; production'da `CHANGE_ME`, bootstrap password ve local test-account env'lerini fail-closed reddetme; secret scanning. |
| `SEC-P0-06` | **Kısmen kapandı (2026-07-06):** şifreli pg_dump + artımlı object aynası + tam SHA256/zincir doğrulamalı restore tatbikatı PASS ([backup_restore.md](backup_restore.md)). Açık kalan: gerçek object lock/WORM, offsite kopya, API/worker OS yetki ayrımı. | Ransomware, uygulama hesabı veya operatör hatası ham nesneyi/audit kanıtını değiştirebilir; felaket sonrası geri dönüş kanıtlanamaz. | S3/MinIO Object Lock veya ayrı yazıcı/okuyucu OS yetkili WORM yaklaşımı; periyodik checksum inventory; şifreli DB+object backup; tanımlı RPO/RTO; restore ve frozen-manifest doğrulama tatbikatı. |
| `SEC-P0-07` | **Kısmen kapandı (2026-07-15):** PDF/DOCX worker hattı parser öncesi magic/format doğrulaması; 100 MiB ikili kaynak, 2.048 DOCX ZIP girdisi, 256 MiB açılmış DOCX, 1.000 PDF sayfası ve 32 Mi karakter çıkarılmış metin için ayarlanabilir fail-closed sınırlar uygular. Extraction/raw lineage aynı özel snapshot'tan okunur; cross-device snapshot boş alanı başlamadan denetlenir ve stale attempt dosyaları DB referansıyla süpürülür. Açık kalan: parser ayrı OS sandbox'ında değil; upload üst sınırı 50 GiB ve request deadline kaldırılıyor; kullanıcı/rol kotası, eşzamanlı upload sınırı, genel upload disk rezervasyonu ve zararlı dosya karantinası yok. Metin hard-link hızlı yolu güvenilir, job boyunca değişmeyen handoff invariantına dayanır; yazma/rename yetkili yerel process'e karşı dirfd/openat veya immutable kopya izolasyonu yoktur. | Disk/CPU/bellek tüketimi, uzun bağlantılar veya parser açığıyla DoS/worker hesabı etkisi; beklenmeyen/malicious dosya işleme; paylaşımlı local drop alanında TOCTOU. | Extraction için ayrı düşük yetkili sandbox/process, CPU/bellek/zaman/egress kotaları; rol bazlı upload kota ve rate limit; global/per-user concurrency sınırı; genel upload disk headroom kontrolü; read/write deadline; yalnızca izinli format/encoding/content; quarantine scanner; yarım upload cleanup ve dolu-disk testleri; ayrı servis kimlikleriyle atomic salt-okunur handoff veya dirfd/openat2 tabanlı çözüm. |
| `SEC-P0-08` | **Kısmen kapandı (2026-07-15):** CI artık `govulncheck`, `pip-audit`, `npm audit`, Go/worker/web test-build ve gerçek PostgreSQL üzerinde migration/worker lease entegrasyon testlerini çalıştırır. Açık kalan: `gosec`, secret scan, CodeQL/SAST, Dependabot/Renovate ve release SBOM/provenance yok. | Bilinen bağımlılık veya kaynak kod açığı release'e girebilir. | CI güvenlik job'ları; kritik/yüksek açıkta fail; Dependabot/Renovate; secret scan; CodeQL veya eşdeğer SAST; sürüm pinleme ve release SBOM'u. |

### `SEC-P0-04` Faz 1 — Veritabanı satır değişikliği defteri

Faz 1, uygulama katmanından geçmeyen doğrudan SQL değişikliklerini de görünür
kılan bir güvenlik ağıdır. Kritik kalıcı iş tablolarındaki satır ekleme, değiştirme
ve silme işlemleri aynı transaction içinde `row_change_events` defterine yazılır.
Bir inceleme önce ret, sonra onay, sonra yeniden ret alırsa özgün
`document_reviews` ve `document_review_reversals` kayıtları silinmez; her ekleme ve
ilgili belge/kaynak durum geçişi ayrı zaman, transaction, DB rolü ve güvenli satır
anahtarıyla izlenebilir.

HTTP katmanı her `/api/` isteği için sunucuda bir UUID `request_id` üretir ve
yanıtın `X-Request-ID` başlığında döndürür. Ayrı `http.request` audit olayı
actor ID ve rollerini, yalnız hash'lenmiş session kimliğini, methodu, ham path
yerine eşleşen route pattern'ını, status, süre ve yanıt byte sayısını tutar.
Ortak API hata yanıtları; yetkilendirme 401/403, başarısız giriş, rate limit ve
handler kaynaklı 4xx/5xx sonuçları dahil olmak üzere `failure_code` ile
sınıflandırılır. Veri minimizasyonu gereği DB audit olayına
raw path, query, header, body, IP veya user-agent yazılmaz.

Kayıt tasarımı veri minimizasyonuna dayanır. Tam satır kopyalamak veya tam satırın
hash'ini almak yerine tabloya özel pozitif alan izin listeleri kullanılır. Yeni bir
kolon kendiliğinden özete girmez. `changed_columns` yalnız kolon adlarını taşır;
e-posta, parola hash'i, ad, ham metin, gerekçe, PII bulgusu, URL, dosya yolu,
preview ve keyfi JSON değerleri özet veya özet hash'ine dahil edilmez.

Faz 1'in genel trigger kapsamı bilinçli olarak şu grupları dışarıda bırakır:

- `audit_events`, `row_change_events` ve `schema_migrations`: özyineleme, çift kayıt
  ve migration muhasebesini iş olayı gibi göstermemek için.
- `background_jobs`, `auth_sessions`, `login_rate_limits` ve
  `document_review_claims`: hassas veya yüksek değişim hacimli geçici koordinasyon
  durumu oldukları için; anlamlı olaylar mevcut semantik audit akışında kalır.
- `document_fingerprints`: yeniden üretilebilir, çok yüksek hacimli türetilmiş veri
  olduğu için.
- `contributions`: prompt/body ham kullanıcı içeriği taşıdığı için; bunun yaşam
  döngüsü ayrıca tasarlanacak kırpılmış semantik olaylarla kaydedilmelidir.
- `active_document_reviews`: append-only inceleme ve geri alma kayıtlarından
  üretilebilen değişebilir bir projeksiyon olduğu için.

Bu faz "her okuma ve her kullanıcı eylemi eksiksiz denetlendi" anlamına gelmez.
Trigger'lar yalnız kapsamdaki satır yazmalarını, HTTP katmanı ise istek sınırını
görür. Semantik business olayları ve row-change transactionları henüz aynı
`request_id` ile bağlanmaz; hassas okuma/download türleri ayrıca sınıflandırılmaz
ve CLI işlemlerinin operatör kimliği yoktur. Aynı iş transactionı geri alınırsa
row-change ledger kaydı da geri alınır; HTTP olayı ise transaction dışındadır.
Ayrıca HTTP audit satırı yanıt tamamlandıktan sonra ayrı ve kısa, best-effort bir
DB işlemiyle yazılır. Bu nedenle DB kesintisi, timeout veya süreç çökmesi sırasında
özellikle salt-okunur ya da başarısız bir isteğin HTTP audit satırı kaybolabilir;
kalıcı iş yazmalarında aynı transaction içindeki `row_change_events` ikincil kanıttır.
Ayrıca tablo sahibi/süper kullanıcı trigger'ları devre dışı bırakabilir veya
deftere sahte `INSERT` yapabilir. Bu nedenle Faz 1 ancak ayrı
migration-owner/runtime rolleri, runtime `INSERT` yasağı, dış/WORM kopya ya da
hash zinciri ve retention/redaction politikasıyla tamamlandığında üretim kanıt
zinciri sayılacaktır.

## P1 - v1.0 Öncesi Zorunlu

| ID | Hedef ve kapanış kriteri |
|---|---|
| `SEC-P1-01` | Keycloak/OIDC veya eşdeğer merkezi kimlik; MFA, servis hesapları, key rotation ve kullanıcı yaşam döngüsü. |
| `SEC-P1-02` | Kaynak/proje bazlı ACL; least privilege rol matrisi; aynı kişinin çoklu hesapla bağımsız onay vermesini engelleyen organizasyon kimliği. |
| `SEC-P1-03` | Merkezi güvenlik logu, başarısız login/yetki ihlali/audit boşluğu alarmı, queue ve disk anomali uyarıları. |
| `SEC-P1-04` | ASVS Level 2 kontrol matrisi, threat model, abuse-case testleri ve dış güvenlik testi/pentest. |
| `SEC-P1-05` | Takedown/delete, KVKK erişim ve veri saklama süresini immutable release modeliyle bağlayan onaylı politika. |
| `SEC-P1-06` | Hassas veri ve backup için at-rest encryption/KMS; anahtar erişimi ve rotation audit'i. |
| `SEC-P1-07` | Distilasyon iş kayıtlarında ham `system_prompt`/`prompt_template` ve sağlayıcı env anahtarı adını kalıcı payload/manifestte taşımayan, yalnız digest + yetkili artifact referansı kullanan secret-minimized sözleşme; dış release manifestinde mutlak yerel dosya yolu içerebilen ham `lineage_ref` yerine güvenli lineage kimliği. Mevcut kayıtlar için redaksiyon/takedown politikası ve sızıntı regresyon testi zorunludur. |

## P2 - Savunma Derinliği

- Riskli oturum ve davranış anomalisi tespiti.
- Tamper-evident audit hash zinciri ve periyodik dış anchor.
- Network segmentation, egress allowlist ve opsiyonel yönetim API'si mTLS.
- Chaos/restore tatbikatı, güvenlik olay müdahale oyunu ve düzenli red-team.
- Artifact provenance/imzalama ve reproducible production build kanıtı.

## Uygulama Sırası

1. `SEC-P0-01`, `SEC-P0-02`: tamamlandı.
2. `SEC-P0-03`: dış erişim ve taşıma sınırı.
3. `SEC-P0-04`, `SEC-P0-05`: kanıt ve secret güvenliği.
4. `SEC-P0-06`, `SEC-P0-07`: veri dayanıklılığı ve DoS direnci.
5. `SEC-P0-08`: supply-chain kapısı.
6. P0 kapandıktan sonra P1 merkezi kimlik, gözlemlenebilirlik ve resmi politika.

Her madde kod, negatif test, production runbook kanıtı ve gerekiyorsa restore
tatbikatı olmadan tamamlandı sayılmaz. Sadece doküman veya “operatör dikkat
eder” ifadesi kapanış kanıtı değildir.

## Birincil Referanslar

- [OWASP ASVS](https://devguide.owasp.org/en/06-verification/01-guides/03-asvs/)
- [OWASP Authorization Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Authorization_Cheat_Sheet.html)
- [OWASP Session Management Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Session_Management_Cheat_Sheet.html)
- [OWASP Logging Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html)
- [OWASP File Upload Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/File_Upload_Cheat_Sheet.html)
- [OWASP REST Security Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/REST_Security_Cheat_Sheet.html)
- [OWASP TLS Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Transport_Layer_Security_Cheat_Sheet.html)
