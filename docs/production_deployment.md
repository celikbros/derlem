# Derlem Production Deployment / Canlı Kurulum

**Durum:** ilk canlı sunucu runbook'u
**Hedef:** Docker kullanmadan tek Linux VPS üzerinde ilk canlı kurulum

> **Güvenlik blokajı:** Bu belge kurulum taslağıdır; production-ready onayı
> değildir. [Güvenlik Hardening Backlog'u](security_hardening_backlog.md)
> içindeki tüm P0 maddeleri kapanmadan internet-facing staging/production
> açılmamalıdır.

Bu runbook ilk canlıya alma için sistemi sade tutar: PostgreSQL, Go API, Python
worker, Next.js web ve Nginx aynı sunucuda çalışır. İlk canlı kesitte Docker,
Kubernetes, Redis, Kafka ve MinIO zorunlu değildir.

## 1. Sunucu Yerleşimi

Önerilen path'ler:

| Path | Amaç |
|---|---|
| `/opt/derlem/current` | Uygulama kodu |
| `/etc/derlem/derlem.env` | Production ortam değişkenleri |
| `/var/lib/derlem/storage` | İçerik-adresli immutable object store |
| `/var/lib/derlem/staging` | Geçici upload staging alanı |

Linux servis kullanıcısı:

```bash
sudo useradd --system --create-home --shell /usr/sbin/nologin derlem
sudo mkdir -p /opt/derlem /etc/derlem /var/lib/derlem/storage /var/lib/derlem/staging
sudo chown -R derlem:derlem /opt/derlem /var/lib/derlem
sudo chmod 750 /etc/derlem
```

## 2. Gerekli Yazılımlar

- Go 1.25+
- Python 3.12+
- Node.js 22+
- PostgreSQL 16+
- Nginx

Dağıtıma göre paket adları değişebilir. Ubuntu/Debian kullanırsak sürümleri
resmi depodan veya runtime sağlayıcılarının güncel depolarından kurmak yeterli.

## 3. Veritabanı

Ayrı database ve kullanıcı oluştur:

```sql
CREATE DATABASE derlem;
CREATE USER derlem WITH PASSWORD 'CHANGE_ME_DB_PASSWORD';
GRANT ALL PRIVILEGES ON DATABASE derlem TO derlem;
```

PostgreSQL 15+ şema yetkisini kısıtlarsa `derlem` database'i içinde ayrıca:

```sql
GRANT ALL ON SCHEMA public TO derlem;
ALTER SCHEMA public OWNER TO derlem;
```

## 4. Ortam Değişkenleri

Şablonu kopyala:

```bash
sudo cp deploy/production.env.example /etc/derlem/derlem.env
sudo chmod 640 /etc/derlem/derlem.env
sudo chown root:derlem /etc/derlem/derlem.env
```

Başlamadan önce mutlaka değiştirilecek alanlar:

- `WEB_ORIGIN`
- `DATABASE_URL`
- `JWT_SECRET`
- `SESSION_IDLE_TTL`
- `LOGIN_FAILURE_WINDOW`
- `LOGIN_LOCKOUT_DURATION`
- `LOGIN_ACCOUNT_FAILURE_LIMIT`
- `LOGIN_IP_FAILURE_LIMIT`
- `BOOTSTRAP_ADMIN_EMAIL`
- `BOOTSTRAP_ADMIN_PASSWORD`

`JWT_SECRET` üret:

```bash
openssl rand -base64 48
```

Varsayılan session/rate-limit değerleri ve proxy IP güven sınırı için
[`session_security.md`](session_security.md) belgesini izleyin.

İlk başarılı girişten sonra `BOOTSTRAP_ADMIN_PASSWORD` değerini boşalt veya
vault/secret manager tarafına taşı. Local login bilgilerini ekranda gösteren
`NEXT_PUBLIC_LOCAL_LOGIN_*` alanları production'da boş kalmalıdır.

## 5. Build

Sunucuda `/opt/derlem/current` altında:

```bash
bash deploy/scripts/build-production.sh
```

Bu komut şunları üretir:

- `bin/derlem-api`
- `bin/derlem-migrate`
- `.venv/` içinde kurulu `derlem-worker`
- `web/.next/` production build

Windows üzerinde aynı doğrulama için:

```powershell
.\deploy\scripts\build-production.ps1
```

## 6. Migration

```bash
set -a
. /etc/derlem/derlem.env
set +a
/opt/derlem/current/bin/derlem-migrate
```

## 7. Systemd Servisleri

Servis dosyalarını kur:

```bash
sudo cp deploy/systemd/derlem-api.service /etc/systemd/system/
sudo cp deploy/systemd/derlem-worker.service /etc/systemd/system/
sudo cp deploy/systemd/derlem-web.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable derlem-api derlem-worker derlem-web
sudo systemctl start derlem-api derlem-worker derlem-web
```

Kontrol:

```bash
systemctl status derlem-api
systemctl status derlem-worker
systemctl status derlem-web
journalctl -u derlem-api -f
```

## 8. Nginx

Domain'i düzenleyip Nginx'e bağla:

```bash
sudo cp deploy/nginx/derlem.conf /etc/nginx/sites-available/derlem.conf
sudo ln -s /etc/nginx/sites-available/derlem.conf /etc/nginx/sites-enabled/derlem.conf
sudo nginx -t
sudo systemctl reload nginx
```

TLS sertifikası Certbot veya mevcut hosting sağlayıcısının sertifika akışıyla
eklenir. Sertifika geldikten sonra HTTP trafiği HTTPS'e yönlendirilmelidir.

## 9. Smoke Check

API:

```bash
curl -fsS http://127.0.0.1:8080/health/live
curl -fsS http://127.0.0.1:8080/health/ready
```

Web:

```bash
curl -fsSI http://127.0.0.1:3000
curl -fsSI https://derlem.example.com
```

Tarayıcıdan bootstrap admin hesabıyla giriş yapılır. Sonra küçük bir kaynak
kaydı oluşturulup upload akışı denenir.

## 10. İlk Canlı Kesit Checklist

- [ ] Güvenlik backlog'unda açık P0 kalmadı.
- [ ] Domain sunucu IP'sine gidiyor.
- [ ] TLS sertifikası kuruldu.
- [ ] `/etc/derlem/derlem.env` production değerleriyle dolduruldu.
- [ ] Local credential display alanları production'da boş.
- [ ] PostgreSQL backup hedefi hazır.
- [ ] `/var/lib/derlem` storage backup kapsamına alındı.
- [ ] `bin/derlem-migrate` çalıştırıldı.
- [ ] API, worker ve web servisleri ayakta.
- [ ] `/health/ready` `200` dönüyor.
- [ ] Web login çalışıyor.
- [ ] Küçük kaynak oluşturma ve upload çalışıyor.

## Notlar

Büyük browser upload'ları için `client_max_body_size`, reverse proxy timeout'ları
ve disk kapasitesi `MAX_UPLOAD_BYTES` ile uyumlu olmalıdır. Çok GB'lık corpus
yüklerinde server-side local ingest hâlâ daha güvenli operasyon yoludur.
