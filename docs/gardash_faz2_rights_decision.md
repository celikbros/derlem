# Gardas/Faz 2 Temiz Adayı — Hak/Lisans Kararı ve Kanıt Kaydı

> **DURUM: TASLAK — veri yöneticisi doldurup karar verene kadar geçersizdir.**
> Bu şablon yalnızca insan kararını hızlandırmak için hazırlanmıştır; kararın
> içeriği ve sorumluluğu karar verene aittir. Doldurulup commit edildikten
> sonra bu dosyanın yolu, kaynağın `license_evidence_ref` alanına yazılır.

**Kaynak:** `gardash_faz2_tr_dedup_20260621_clean_candidate_20260625`
**Source ID:** `f63352dd-fdd1-4e4b-a8d2-b167b3c856cf`
**SHA256:** `ebe292793d87ec067076bbb86f39801e6ed5fae18761dfcfa3506c4503c0d989`
**Satır:** 5.922.891 · **Byte:** 12.850.383.067 · **Amaç:** `pretrain`

## 1. Verinin kökeni (doldurun)

- Corpus'u derleyen ekip/kişi: `.......`
- Derleme dönemi: `.......`
- Kaynak türleri (web taraması / kitap / kamu verisi / kendi üretimimiz / diğer): `.......`
- Ham kaynakların bilinen lisans/kullanım şartları: `.......`
- Üçüncü taraf içerik oranı ve niteliği hakkında bilinenler: `.......`

## 2. Kullanım hakkı değerlendirmesi (doldurun)

- Bu metinleri LLM/tokenizer eğitiminde kullanma dayanağımız: `.......`
- Bilinen kısıtlar (ticari kullanım, yeniden dağıtım, atıf, robots/ToS): `.......`
- KVKK/telif açısından değerlendirilen riskler ve gerekçe: `.......`

## 3. Karar (birini işaretleyin)

- [ ] `cleared` — eğitim amaçlı kullanım hakkı değerlendirildi ve uygun bulundu.
- [ ] `restricted` — yalnızca şu kapsamda kullanılabilir: `.......`
- [ ] `blocked` — kullanılamaz; gerekçe: `.......`

`license` alanına yazılacak değer (ör. `proprietary-internal`, `mixed-web`): `.......`

## 4. Karar sahibi

- Ad / rol: `.......`
- Tarih: `.......`
- Not: Karar, Derlem kaynağına girildiğinde append-only audit'e işlenir;
  bu dosya kanıt referansı olarak değişmeden korunur, güncelleme gerekirse
  yeni tarihli bölüm eklenir.

## 5. Karar sonrası üç adım (operasyon)

1. Web arayüzü → Kaynaklar → bu kaynak → "Hak bilgisini düzenle":
   `rights_status` kararını gir, `license_evidence_ref` alanına bu dosyanın
   yolunu yaz (`docs/gardash_faz2_rights_decision.md`).
2. Moderatör: İnceleme ekranı → bu kaynak → 200 örneği (toplu inceleme ile)
   puanla ve onayla → kaynak onayını ver.
3. Admin: Sürümler → pretrain draft oluştur → freeze → JSONL/TXT export.
   Manifest SHA256 zinciriyle Gardash'a teslim edilir.
