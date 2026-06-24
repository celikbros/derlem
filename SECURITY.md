# Güvenlik Politikası / Security Policy

[Türkçe](#türkçe) | [English](#english)

## Türkçe

### Desteklenen sürüm

Derlem aktif MVP geliştirmesindedir. Güvenlik düzeltmeleri yalnızca `main`
dalının güncel sürümüne uygulanır.

### Açık bildirme

Bir güvenlik açığını normal GitHub issue, discussion, commit mesajı veya herkese
açık kanal üzerinden paylaşmayın.

Bu private repo içindeki **Security > Advisories > New draft security
advisory** yolunu kullanın. Erişiminiz yoksa repo yöneticisiyle özel bir kanal
üzerinden iletişim kurun ve ayrıntıları erişim sağlanana kadar göndermeyin.

Bildirimde mümkünse şunlar bulunsun:

- Etkilenen commit veya bileşen.
- Yeniden üretme adımları.
- Beklenen ve gerçekleşen davranış.
- Veri gizliliği, yetki veya bütünlük etkisi.
- Güvenli bir düzeltme önerisi varsa kısa açıklaması.

Gerçek parola, JWT, API anahtarı, kişisel veri veya corpus örneği eklemeyin.
Gerekirse redakte edilmiş ve sentetik bir örnek kullanın.

### Öncelikli güvenlik alanları

- Auth bypass, rol yükseltme ve self-review ihlali.
- Upload path traversal, staging kaçışı ve sınırsız bellek/disk tüketimi.
- Immutable object veya frozen release'in değiştirilebilmesi.
- Audit kayıtlarının güncellenmesi, silinmesi veya hassas veri sızdırması.
- PII/haklar/duplicate/decontamination kapılarının atlanması.
- Secret'ların log, API cevabı, job payload veya Git geçmişine girmesi.

## English

### Supported version

Derlem is under active MVP development. Security fixes target only the current
`main` branch.

### Private reporting

Do not disclose vulnerabilities through normal GitHub issues, discussions,
commit messages, or public channels.

Use **Security > Advisories > New draft security advisory** in this private
repository. If you do not have access, contact a repository administrator over
a private channel and do not send details until secure access is available.

Include when possible:

- The affected commit or component.
- Reproduction steps.
- Expected and actual behavior.
- Confidentiality, authorization, or integrity impact.
- A short safe-fix proposal, if available.

Never attach real passwords, JWTs, API keys, personal data, or corpus samples.
Use redacted and synthetic examples where necessary.

### Priority security areas

- Authentication bypass, privilege escalation, and self-review violations.
- Upload path traversal, staging escape, and unbounded memory/disk consumption.
- Mutation of immutable objects or frozen releases.
- Audit mutation, deletion, or sensitive-data leakage.
- Bypass of PII, rights, duplicate, or decontamination gates.
- Secrets appearing in logs, API responses, job payloads, or Git history.
