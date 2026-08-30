# TASK-001 — Contribution screen fixes (welcome copy contradiction + terms checkbox layout)

| Field | Value |
|---|---|
| Status | READY |
| Kind | fix |
| Moratorium | allowed (correction, no new behaviour) |
| Estimate | 1–2 h (edits ~20 min; hunk-level staging and the visual check take the rest) |
| Owner | (unassigned) |
| Verified against code | 2026-08-30, adversarial pass (6 agents); line numbers are for the working tree as of that date |

## Goal

Two visible defects on the **Katkılar** (Contributions) screen, found while the owner
was testing the live system on 2026-08-30:

1. The welcome card tells a contributor *"Kimse buraya elle metin yazmaz"* ("nobody
   writes text here by hand") — on the one screen whose purpose is writing text by hand.
   The same false claim exists in two other places (see Current state).
2. The terms-acknowledgement checkbox renders detached from its label: the box sits
   alone, centred, on its own row; the label text is on the row below.

## Why

- (1) is the **first sentence a contributor reads**. It was written for the Sources
  screen (file ingest) before the contribution queue existed, and is now false for
  the contributor role. A contradictory onboarding message costs trust.
- (2) is a legal-acknowledgement control ("I produced this text myself; I transfer
  training-use rights…"). A checkbox visually separated from the sentence it
  acknowledges is a bad pattern for consent UI, and looks broken.

## Current state (measured)

**Copy — three places carry the claim, with different wording each:**

| Where | Lines | Wording |
|---|---|---|
| `web/components/derlem-app.tsx` (WelcomeTip) | 163–168 (`<p>`) | "…Kimse buraya elle metin yazmaz: dosyalar alınır, otomatik kapılardan geçer ve insan onayıyla eğitime hazır değişmez paketlere dönüşür. **Bu zincirdeki her karar size güvenilir.**" — the last sentence is on line 167 and must be **kept**. Emphasis uses `<em>`. |
| `web/components/guide-panel.tsx` (Rehber intro) | 14–22 (`<p>`), clause at 19–21 | A longer paragraph with a different lead ("Bir dil modeli ancak verisi kadar iyidir…"); the clause is "Kimse buraya elle metin yazmaz: var olan corpus dosyaları sisteme alınır, otomatik kalite kapılarından geçirilir, insan incelemesiyle onaylanır ve eğitim ekiplerine değişmez (frozen) paketler olarak sunulur." Emphasis uses `<strong>`. |
| `README.md` | 92–95 ("Nasıl Çalışır?") | "Derlem'e kimse elle metin yazmaz. … İnsanlar veri üretmez; kaynağı kaydeder, örnekleri inceler ve kararı verir." |

These are **paraphrases, not copies** — rewrite each in its own voice; do not paste
one into the others.

The role line under the WelcomeTip paragraph renders `info.title` and `info.who`
from `roleInfoByRole` (`web/lib/roles.ts:162`), not `summary`. (The comment at
`roles.ts:19` saying the welcome tip uses `summary` is stale — fix that comment too.)

**Checkbox.** Markup at `web/components/contributions-panel.tsx:163-165`:

```tsx
<label className="full-width terms-check">
  <input type="checkbox" name="accept_terms" required />
  Bu metni kendim ürettim; … (şart: office-v1).
</label>
```

Root cause, two layers:

1. Global `label { display: grid; gap: 6px; … }` (`web/app/globals.css:1523-1529`)
   stacks the input and the text as two grid rows. `.terms-check`
   (`globals.css:4266-4273`) sets `flex-direction: row !important` but never sets
   `display: flex`, so `flex-direction` is a no-op on a grid container.
2. Global `input, select { width: 100%; height: 38px; padding: 0 10px; border: …; }`
   (`globals.css:1531-1541`) still sizes the checkbox; `.terms-check input`
   (`globals.css:4275-4278`) only resets `width: auto` and `margin-top`. Fixing (1)
   alone leaves a 38 px-tall box next to 12.5 px text. The stylesheet already has
   the right pattern: `.bulk-selection-row input { width: 16px; height: 16px;
   accent-color: … }` (`globals.css:2173-2177`).

## Scope

1. **WelcomeTip** (`derlem-app.tsx:163-168`): replace the "Kimse buraya…" sentence so
   it is true for every role, keep the three `<em>` phrases and the closing sentence
   "Bu zincirdeki her karar size güvenilir." Suggested:

   > Derlem, LLM eğitiminde kullanılacak metnin *hakları belli*, *kalitesi insan
   > onaylı* ve *tekrarı ayıklanmış* biçimde toplandığı veri atölyesidir. Metin ister
   > dosyayla alınsın ister katkı olarak yazılsın, aynı kapılardan geçer: otomatik
   > kontroller, insan onayı ve eğitime hazır değişmez paketler. Bu zincirdeki her
   > karar size güvenilir.

2. **Guide** (`guide-panel.tsx:19-21`): rewrite only that clause in the guide's own
   voice, e.g. "Metin ister var olan corpus dosyalarından alınsın ister katkı olarak
   yazılsın, otomatik kalite kapılarından geçirilir, insan incelemesiyle onaylanır
   ve eğitim ekiplerine değişmez (frozen) paketler olarak sunulur."
3. **README.md:92-95**: same correction in the README's voice ("İnsanlar veri
   üretmez" is now false too — contributors do).
4. **CSS** (`globals.css:4266-4278`):
   - `.terms-check`: add `display: flex;`, drop the `!important`, keep
     `align-items: flex-start`.
   - `.terms-check input`: `width: 16px; height: 16px; flex: 0 0 auto; margin-top: 2px;
     accent-color: var(--green);` (mirror `.bulk-selection-row input`).
5. Fix the stale comment at `web/lib/roles.ts:19`.

## Out of scope

- Any change to what the checkbox *does* (validation, `terms_ack_version`, API).
- Any other copy on the screen or in the README.
- The task-type list (see TASK-002, which **depends on this card landing first** —
  it edits the same label/CSS).

## Files

- `web/components/derlem-app.tsx` (WelcomeTip `<p>`, lines 163–168)
- `web/components/guide-panel.tsx` (lines 19–21)
- `README.md` (lines 92–95)
- `web/app/globals.css` (`.terms-check`, `.terms-check input`, ~4266–4278)
- `web/lib/roles.ts` (comment at line 19)

## Acceptance criteria

- [ ] `grep -rn "elle metin yazmaz\|İnsanlar veri üretmez" README.md web/components` returns nothing.
- [ ] Logged in as `contributor@derlem.local` / `DerlemTest123!` (`docs/local_role_testing.md:22`;
      the login screen also offers one-click test accounts), **after** clearing the
      dismissal flag — in the browser console:
      `Object.keys(localStorage).filter(k => k.startsWith('derlem-welcome-dismissed-')).forEach(k => localStorage.removeItem(k))`
      then reload — the welcome card renders and contains the new sentence plus
      "Bu zincirdeki her karar size güvenilir." (WelcomeTip returns `null` once
      dismissed, `derlem-app.tsx:144-152`; without the reset the check passes vacuously.)
- [ ] Rehber panel shows the corrected clause.
- [ ] On the contribution form, the checkbox and "Bu metni kendim ürettim…" are on
      the same line at ≥ 900 px; at 600 px the text wraps beside the box, the box
      does not drop to its own row.
- [ ] In the console: `getComputedStyle(document.querySelector('.terms-check')).display === 'flex'`
      and `document.querySelector('.terms-check input').getBoundingClientRect().height <= 20`.
- [ ] Submitting with the box unchecked is still blocked by the browser (`required` unchanged).
- [ ] `npm run typecheck && npm run lint && npm run build` pass in `web/`.

## Verification commands

```powershell
Set-Location web
npm run typecheck; npm run lint; npm run build
```

Then start the stack (`docs/local_development.md`, web 18400 / API 18401), log in as
the contributor test account, open **Katkılar**, run the console checks above.

## Risks / traps

- **Staging.** The working tree holds ~84 uncommitted files from another session, and
  two of this card's target files are among them: `web/app/globals.css` (+843/−1,
  foreign hunks around lines 1571–1694 and 4279–4313) and `web/components/derlem-app.tsx`
  (22 lines). **Do not `git add` those two files whole** — that would sweep ~860 lines
  of someone else's work into this commit. Stage hunk-by-hunk:
  `git add -p web/app/globals.css web/components/derlem-app.tsx`, accept only your
  `.terms-check` hunk and your `<p>` hunk; then `git add web/components/guide-panel.tsx
  README.md web/lib/roles.ts` (clean files). Confirm with `git diff --cached --stat`
  before committing. (Alternative: wait for that session to commit first.)
- `web/next-env.d.ts` may flip between `.next/dev/…` and `.next/types/…` after a
  build; never stage it.
- Do not "improve" the rest of the welcome card; it is shared by all roles.

## Close-out

Commit message in Turkish with the two `Co-Authored-By` trailers from `CLAUDE.md`
(no Claude trailer); push to `main`; set Status to DONE here and in the table in
`docs/gorevler/README.md`; fill **Report** with the typecheck/lint/build output and
the commit SHA.

## Report

_(filled by the implementer)_
