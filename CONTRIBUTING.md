# Derlem'e Katkı / Contributing to Derlem

[Türkçe](#türkçe) | [English](#english)

## Türkçe

Derlem yalnızca kod deposu değildir; veri hakları, PII, audit ve yeniden
üretilebilir release garantileri taşıyan bir sistemdir. Katkılar bu garantileri
zayıflatmamalıdır.

### Başlamadan önce

1. İlgili plan ve yönetişim belgelerini okuyun.
2. Büyük mimari değişiklikler için önce issue açın.
3. Gerçek corpus, kişisel veri, secret veya yerel `.env` dosyası eklemeyin.
4. Değişikliği mümkün olan en küçük davranışsal dilimde tutun.

### Geliştirme akışı

```powershell
git switch main
git pull --ff-only
git switch -c feature/kisa-aciklama
```

Branch adlarında `feature/`, `fix/`, `docs/`, `test/` veya `chore/` önekleri
tercih edilir. Commit mesajları kısa ve emir kipinde olmalıdır:

```text
feat: add document extraction job
fix: preserve quarantine after PII scan
docs: explain release freeze contract
```

### Kod ilkeleri

- Go kodunda mevcut repository/domain/http sınırlarını koruyun.
- Python worker işleri idempotent olmalı; retry aynı sonucu bozmasın.
- Büyük dosyaları belleğe bütünüyle almayın; stream veya bounded chunk kullanın.
- PostgreSQL constraint ve transaction'larını yalnızca uygulama kontrolüyle
  değiştirilebilir garantilerin yerine kullanmayın.
- Kanonik veri modeline model-spesifik chat token/template gömmeyin.
- Audit olaylarında secret, parola, JWT veya ham PII saklamayın.
- İnsan kararı gerektiren haklar/freeze kapılarını otomasyona devretmeyin.

### Migration kuralları

- Uygulanmış migration dosyası değiştirilmez; yeni numaralı migration eklenir.
- Migration mümkünse geriye uyumlu ve transaction içinde çalışabilir olmalıdır.
- Büyük tablo backfill'i schema migration içinde sınırsız çalıştırılmamalıdır.
- Yeni worker job tipi ekleniyorsa dağıtım sırası ve eski worker davranışı
  düşünülmelidir.
- Yeni zorunlu alanlar için mevcut kayıtların güvenli varsayılanı tanımlanmalıdır.

### Test kapısı

PR açmadan önce:

```powershell
go test ./...

$env:TEMP='C:\tmp'
$env:TMP='C:\tmp'
.\.venv\Scripts\python.exe -m pytest worker\tests

Set-Location web
npm run lint
npm run build
npm audit --audit-level=moderate
```

Kullanıcı akışı değişiyorsa ilgili Playwright testi eklenmeli veya
güncellenmelidir. Mutating E2E testleri açıkça opt-in kalmalıdır.

### Pull request içeriği

PR açıklaması şu bilgileri vermelidir:

- Sorun ve neden şimdi çözüldüğü.
- Davranış değişikliği ve etkilenen veri sözleşmeleri.
- Migration, backfill ve rollback etkisi.
- Güvenlik, PII, haklar ve audit değerlendirmesi.
- Çalıştırılan testler ve sonuçları.
- Bilinen sınırlamalar veya sonraki işler.

## English

Derlem is not only a code repository. It carries guarantees around data
rights, PII, auditability, and reproducible releases. Contributions must not
weaken those guarantees.

### Before you start

1. Read the relevant planning and governance documents.
2. Open an issue before a large architectural change.
3. Never add real corpora, personal data, secrets, or local `.env` files.
4. Keep the change to the smallest useful behavioral slice.

### Development flow

```powershell
git switch main
git pull --ff-only
git switch -c feature/short-description
```

Prefer `feature/`, `fix/`, `docs/`, `test/`, or `chore/` branch prefixes.
Use short imperative commit messages:

```text
feat: add document extraction job
fix: preserve quarantine after PII scan
docs: explain release freeze contract
```

### Engineering rules

- Preserve the existing repository/domain/http boundaries in Go.
- Python worker jobs must be idempotent and safe under retries.
- Do not buffer large files in memory; stream or use bounded chunks.
- Use PostgreSQL constraints and transactions for guarantees that must not
  depend on application code alone.
- Do not embed model-specific chat tokens or templates in canonical data.
- Never store secrets, passwords, JWTs, or raw PII in audit events.
- Keep rights and release-freeze decisions behind their required human gates.

### Migration rules

- Never edit an applied migration; add a new numbered migration.
- Keep migrations backward-compatible and transactional when possible.
- Do not run unbounded large-table backfills inside schema migrations.
- When adding a worker job type, account for rollout order and old workers.
- Define a safe state for existing records when adding required fields.

### Test gate

Before opening a PR:

```powershell
go test ./...

$env:TEMP='C:\tmp'
$env:TMP='C:\tmp'
.\.venv\Scripts\python.exe -m pytest worker\tests

Set-Location web
npm run lint
npm run build
npm audit --audit-level=moderate
```

Add or update Playwright coverage when a user workflow changes. Mutating E2E
tests must remain explicitly opt-in.

### Pull request content

Every PR should explain:

- The problem and why it is being solved now.
- Behavioral changes and affected data contracts.
- Migration, backfill, and rollback impact.
- Security, PII, rights, and audit implications.
- Tests executed and their results.
- Known limitations or follow-up work.
