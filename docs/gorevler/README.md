# Görev kartları

Alt programcılara (ve onların ajanlarına) verilen iş emirleri burada durur.
Kartlar **İngilizce** yazılır (uygulayıcı taraf İngilizce talimatı daha isabetli
yorumluyor); sahiple yazışma ve commit mesajları Türkçe kalır.

## Kurallar

1. **"Bitti" = commit + push.** Diskte duran iş bitmiş sayılmaz; kart ancak
   `main`'e girince kapanır. (2026-08: 84 dosya / 1.469 satır sekiz gün commit'siz
   durdu — bu kural o yüzden var.)
2. **Her kartın ölçülebilir kabul kriteri vardır.** "Çalışıyor" değil, "şu komut şu
   çıktıyı verir." Ölçülmeden yazılan cümle bu oturumlarda beş kez yanlış çıktı.
3. **Kart kendi kendine yeter.** Uygulayıcı sıfırdan başlar; "geçen sefer
   konuştuğumuz gibi" yoktur. Amaç, gerekçe, kapsam, **kapsam dışı**, dosyalar,
   doğrulama komutu kartta yazılıdır.
4. **Moratoryum kapısı her kartta sorulur:** teslimat mı, düzeltme mi, yeni
   özellik mi? Yeni özellik ise sahibin açık onayı olmadan başlanmaz
   ([diyet_yol_haritasi.md](../diyet_yol_haritasi.md)).
5. Biten iş kartın altına **Report** bölümüyle raporlanır: ne yapıldı, doğrulama
   çıktısı, kapsam dışı bırakılan, commit SHA.

## Durumlar

`DRAFT` → `READY` (sahip onayladı) → `IN PROGRESS` → `IN REVIEW` → `DONE`
(veya `BLOCKED` / `DROPPED`, gerekçesiyle).

## Şablon

```markdown
# TASK-NNN — <title>

| Field | Value |
|---|---|
| Status | DRAFT |
| Kind | fix / delivery / feature |
| Moratorium | allowed / **owner approval required** |
| Estimate | … |
| Owner | (unassigned) |

## Goal
## Why
## Current state (measured)
## Scope
## Out of scope
## Design / approach
## Files
## Acceptance criteria
## Verification commands
## Risks / traps
## Report
```

## Kartlar

| # | Başlık | Tür | Durum |
|---|---|---|---|
| [TASK-001](TASK-001-contribution-screen-fixes.md) | Contribution screen fixes (copy contradiction + checkbox layout) | fix | **DONE** — 2026-08-31, `d0160ab` |
| [TASK-002](TASK-002-contribution-task-type-registry.md) | Contribution task-type registry (translation, preference, reasoning) | feature | DRAFT — sahip kararı bekliyor (D1–D4). Commit blokeri **kalktı** (2026-08-30); TASK-001 önce gitmeli. |

## Doğrulama notu

Kartlar yazıldıktan sonra 6 bağımsız ajanla koda karşı çürütme geçişinden
geçirildi (2026-08-30): TASK-001'de 7, TASK-002'de 20+ düzeltme çıktı; ikisi de
"yanlış yere gönderir" sınıfında hatalar içeriyordu (yanlış satır aralığı, git'te
olmayan migration'a dayanan talimat, worker'ın kanonik kaydı okuyamadığı gerçeği).
**Her kart programcıya verilmeden önce bu geçişten geçmeli**; ölçülmeden yazılan
cümle bu projede tekrar tekrar yanlış çıktı.
