# Oturum ve Login Güvenliği

**Tarih:** 2026-07-01
**Kapsam:** `SEC-P0-02` uygulama ve operasyon sözleşmesi

Derlem JWT'yi yalnız imzalı bir yetki beyanı olarak kullanır. Bir JWT'nin
imzasının doğru olması tek başına erişim için yeterli değildir; karşılık gelen
sunucu oturumu PostgreSQL'de aktif olmalı, süreleri dolmamış olmalı ve
kullanıcının güncel yetki sürümüyle eşleşmelidir.

## Oturum Modeli

- JWT, rastgele 256-bit `jti` ve kullanıcının `auth_version` değerini taşır.
- Ham `jti` veritabanına yazılmaz; `auth_sessions.jti_hash` içinde yalnız SHA-256
  özeti tutulur.
- Varsayılan idle timeout `30m`, absolute timeout JWT süresiyle aynı `8h`'dir.
- Idle ve absolute timeout API tarafından sunucu tarafında uygulanır.
- Logout aktif session kaydını revoke eder; cookie daha sonra silinir.
- `POST /api/v1/auth/logout-all` kullanıcının tüm aktif oturumlarını revoke eder.
- Kullanıcı status/parola değişikliği ile rol ekleme/silme `auth_version`
  değerini trigger ile artırır ve açık session satırlarını `principal_changed`
  gerekçesiyle revoke eder. Eski token bir sonraki istekte `401` alır.
- Yeni session modeli devreye alındığında eski, `jti` içermeyen JWT'ler geçersiz
  olur ve kullanıcı bir kez yeniden giriş yapar.

## Login Throttling

Başarısız denemeler PostgreSQL'de tutulur; bu nedenle birden fazla API instance
aynı sayacı kullanır. Ham e-posta ve IP yerine server secret'tan domain-separated
olarak türetilmiş HMAC-SHA256 anahtarları saklanır.

| Ayar | Varsayılan | Anlamı |
|---|---:|---|
| `LOGIN_ACCOUNT_FAILURE_LIMIT` | `5` | Bir hesap anahtarı için pencere içindeki üst sınır |
| `LOGIN_IP_FAILURE_LIMIT` | `30` | Bir istemci IP anahtarı için pencere içindeki üst sınır |
| `LOGIN_FAILURE_WINDOW` | `15m` | Başarısız denemelerin sayıldığı pencere |
| `LOGIN_LOCKOUT_DURATION` | `15m` | Eşik sonrası geçici blok süresi |
| `SESSION_IDLE_TTL` | `30m` | Etkinlik olmadan session kapanma süresi |
| `JWT_TTL` | `8h` | Mutlak session üst sınırı |

Eşik aşıldığında API `429 Too Many Requests` ve saniye cinsinden `Retry-After`
döner. Başarısız ve bloklanan girişler append-only audit'e yazılır; bloklar
özet anahtarlarla structured warning logu üretir. Merkezi alarm ve SIEM bağlantısı
`SEC-P1-03` kapsamındadır.

## İstemci IP Sınırı

API normalde TCP remote address değerini kullanır. Yalnız bağlantı loopback
adresinden, yani yerel Nginx/Next proxy'den gelirse doğrulanmış `X-Real-IP`
başlığını kabul eder. Public production'da API portu yalnız localhost'a bind
edilmeli ve dış dünyaya Nginx açılmalıdır.

## Admin MFA/SSO Planı

Yerel pilotta parola + server-side session devam eder. Internet-facing kullanım
öncesindeki P1 kimlik adımında Keycloak/OIDC veya eşdeğer IdP devreye alınacak;
admin ve kritik reviewer hesaplarında MFA zorunlu, ajanlarda ayrı service account
ve kısa ömürlü credential kullanılacaktır. Derlem'in `auth_sessions` tablosu bu
geçişe kadar revoke/timeout kaynağıdır; IdP sonrasında IdP session/token yaşam
döngüsüyle birleştirilir.

## Doğrulama

- Unit testler: JWT `jti/auth_version`, session entropy/hash, proxy IP güveni ve
  `Retry-After`.
- Playwright: logout sonrası çalınmış cookie tekrar kullanımının reddi,
  logout-all ile ikinci session'ın iptali ve tekrarlı yanlış parolada `429`.
- Migration smoke: rol ekleme/silme ve kullanıcı status değişiminin
  `auth_version` artırdığı transaction içinde doğrulanır.

```powershell
go test ./...
Set-Location web
npx playwright test tests/e2e/session-security.spec.ts
```

## Birincil Referanslar

- [OWASP Authentication Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Authentication_Cheat_Sheet.html)
- [OWASP Session Management Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Session_Management_Cheat_Sheet.html)
