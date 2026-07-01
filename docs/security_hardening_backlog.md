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
| `SEC-P0-04` | Audit DB trigger ile append-only; fakat runtime/migration DB yetkileri ayrılmamış. Actor email/rol snapshot'ı yok; `request_id` HTTP isteğiyle korele değil; CLI import `system` görünür; hassas read/download olaylarının çoğu audit edilmez. | Yetkili DB hesabı logu bozabilir; geçmiş kimlik ve olay zinciri ispatı zayıflar; veri sızıntısı izlenemez. | Ayrı migration-owner/runtime DB rolleri; runtime için audit mutation kesin yasak; gerçek request correlation, actor email/rol snapshot, hashed session ID ve kontrollü IP/user-agent metadata; CLI service/operator identity; raw/sensitive read ve download audit'i; off-host append-only/WORM veya hash-zincirli audit; retention/redaction politikası. |
| `SEC-P0-05` | Secret'lar env dosyasından yükleniyor; rotation/revocation mekanizması yok. Bootstrap secret'ı yanlışlıkla production'da kalabilir; `CHANGE_ME` ve local test hesapları startup'ta reddedilmiyor. | Secret sızıntısı, kalıcı hesap ele geçirme ve ortam karışması. | Vault/secret manager veya korumalı secret dosyası; düzenli JWT/DB secret rotation runbook'u; ayrı servis kimlikleri; production'da `CHANGE_ME`, bootstrap password ve local test-account env'lerini fail-closed reddetme; secret scanning. |
| `SEC-P0-06` | Local object store dosya izniyle read-only; gerçek object lock/WORM yok. API ve worker aynı OS kullanıcısı/depo yetkisini paylaşır. PostgreSQL ve object store restore tatbikatı yapılmadı. | Ransomware, uygulama hesabı veya operatör hatası ham nesneyi/audit kanıtını değiştirebilir; felaket sonrası geri dönüş kanıtlanamaz. | S3/MinIO Object Lock veya ayrı yazıcı/okuyucu OS yetkili WORM yaklaşımı; periyodik checksum inventory; şifreli DB+object backup; tanımlı RPO/RTO; restore ve frozen-manifest doğrulama tatbikatı. |
| `SEC-P0-07` | Upload üst sınırı 50 GiB; request deadline kaldırılıyor. Kullanıcı/rol kotası, eşzamanlı upload sınırı, disk headroom rezervasyonu, içerik allowlist'i veya zararlı dosya karantinası yok. | Disk tüketimi ve uzun bağlantılarla DoS; beklenmeyen/malicious dosya işleme. | Rol bazlı kota ve rate limit; global/per-user concurrency sınırı; disk headroom kontrolü; read/write deadline; yalnızca izinli format/encoding/content; quarantine scanner; yarım upload cleanup ve dolu-disk testleri. |
| `SEC-P0-08` | CI test/build çalıştırıyor; fakat `govulncheck`, `gosec`, `pip-audit`, CI `npm audit`, secret scan, CodeQL/SAST, Dependabot ve SBOM yok. | Bilinen bağımlılık veya kaynak kod açığı release'e girebilir. | CI güvenlik job'ları; kritik/yüksek açıkta fail; Dependabot/Renovate; secret scan; CodeQL veya eşdeğer SAST; sürüm pinleme ve release SBOM'u. |

## P1 - v1.0 Öncesi Zorunlu

| ID | Hedef ve kapanış kriteri |
|---|---|
| `SEC-P1-01` | Keycloak/OIDC veya eşdeğer merkezi kimlik; MFA, servis hesapları, key rotation ve kullanıcı yaşam döngüsü. |
| `SEC-P1-02` | Kaynak/proje bazlı ACL; least privilege rol matrisi; aynı kişinin çoklu hesapla bağımsız onay vermesini engelleyen organizasyon kimliği. |
| `SEC-P1-03` | Merkezi güvenlik logu, başarısız login/yetki ihlali/audit boşluğu alarmı, queue ve disk anomali uyarıları. |
| `SEC-P1-04` | ASVS Level 2 kontrol matrisi, threat model, abuse-case testleri ve dış güvenlik testi/pentest. |
| `SEC-P1-05` | Takedown/delete, KVKK erişim ve veri saklama süresini immutable release modeliyle bağlayan onaylı politika. |
| `SEC-P1-06` | Hassas veri ve backup için at-rest encryption/KMS; anahtar erişimi ve rotation audit'i. |

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
