# Gardas clean-candidate v2 çalışma kılavuzu

**Tarih:** 2026-08-19  
**Karar:** Titiz yol (B)  
**V1 kaynak:** `f63352dd-fdd1-4e4b-a8d2-b167b3c856cf`  
**Ham ata:** `06ac330e-350f-45f0-b596-3dd4aa1dbc57`

## Değişmez güvenlik kuralları

- V1 kaynak ve içerik-adresli nesnesi değiştirilmez.
- Belge ret/onay kararlarını yalnız oturum açmış insan moderatör verir.
- Codex insan adına review API çağrısı yapmaz.
- Final üretimde `--force` kullanılmaz; benzersiz hedef adı seçilir.
- Ret audit dosyası ham metin içermez; yalnız parent ordinal ve neden kodlarını taşır.
- V2, V1'in alt kümesidir. Yeni kaynakta bütün PII/dedup/örnekleme kapıları yine çalıştırılır.
- Şifreli yedek ve restore tatbikatı kullanıcının kararıyla şimdilik ertelenmiştir.

## 1. İnsan politika doğrulaması

Mevcut aktif örnek nesli 200 belgedir. Ön rapordaki 16 sorunlu ordinal:

`645741, 951612, 1040293, 4369844, 4369906, 4370196, 4376871,
4377120, 4377565, 4378486, 4379804, 4382098, 4382863, 4387794,
4388325, 4395538`

İlk raporda tam okunmamış aşağıdaki 19 belge insan spot-check adayıdır:

`1547919, 1636358, 3310016, 3667964, 4365013, 4369207, 4369575,
4371678, 4372404, 4373625, 4374703, 4378254, 4381554, 4392360,
4394099, 4394254, 4396137, 4397081, 4401086`

Moderatör akışı:

1. Moderatör hesabıyla giriş yap.
2. V1 kaynakta paket boyutunu 200 seç ve güvenli paket al.
3. İlk 16 belgeyi ordinal ile bul; tam metni oku ve kendi beş rubric puanın ile gerekçeni girerek uygun kararı ver.
4. Ek 19 adayı da tam metin üzerinden spot-check et. Bunlar otomatik olarak “kötü” kabul edilmez; amaç hard-filter politikasının yanlış pozitif üretmediğini doğrulamaktır.
5. “İşaretli” görünümünde insan kararlarını kontrol et ve kullanılmayan claim'leri bırak.

Claim 15 dakika yaşar, UI beş dakikada yeniler. Kararlar reviewer kimliği, belge sürümü,
object SHA, puanlar ve gerekçeyle append-only audit kaydına yazılır.

## 2. Uygulanan v2 kalite politikası

Politika kimliği: `tr-web-v1`. Tek URL, belge uzunluğu, yetişkin konu, Kiril
karakter veya tek anahtar kelime ret nedeni değildir. Neden kodları:

- `extreme_repetition`
- `hashtag_stuffing`
- `mixed_script_artifact`
- `repeated_segments`
- `navigation_boilerplate`
- `commercial_keyword_stuffing`
- `dating_spam_cluster`
- `optics_spam_cluster`
- `adult_service_spam_cluster`
- `sexual_pharma_spam_cluster`

Bilinen 16 örneğin 16'sı yakalandı. Risk-ağırlıklı 200 örnekte 19 ek insan
spot-check adayı bulundu. Kelime-kökü eşleşmeleri Unicode kelime sınırına
sıkılaştırıldıktan sonra bunların 18'i hard-filter tarafından işaretlenmeye devam
etti; `4372404` yalnız insan spot-check listesinde kaldı.
İlk 100.000 satırlık uçtan uca smoke sonucu:

- 100.000 okunan
- 99.999 yazılan
- 1 kalite reddi (`source_ordinal=84993`, `navigation_boilerplate`)
- 0 PII, duplicate, oversized veya boş satır kaybı
- çıktı SHA-256: `f517491ca2a3215d2d5b7f369e89cdfd182a8633282ba796063810dda803e685`
- ret audit SHA-256: `019b551b9b2826629fb820b7df747f9e2d31b452b9531b9d94ac9bdcc194ebcc`

Bu ilk-N oranı corpus geneline ilişkin istatistik değildir.

## 3. Teknik hazırlık ve smoke

Önce migration, Go, worker ve web testleri temiz olmalıdır. Ardından:

```powershell
.\.venv\Scripts\python.exe -m derlem_worker.clean_candidate `
  --source-id f63352dd-fdd1-4e4b-a8d2-b167b3c856cf `
  --output-path .\var\run\gardas_v2_smoke_100k.txt `
  --quality-policy tr-web-v1 `
  --quality-rejections-path .\var\run\gardas_v2_smoke_100k.rejections.jsonl `
  --limit-lines 100000 `
  --force
```

Smoke için `--force` yalnız bu açıkça geçici hedefte kabul edilir.

## 4. Final v2 üretimi

İnsan spot-check sonucu politika kabul edildikten sonra, kopya sayısını azaltmak için
çıktı doğrudan `IMPORT_ROOT` altında ve yeni bir adla üretilir:

```powershell
.\.venv\Scripts\python.exe -m derlem_worker.clean_candidate `
  --source-id f63352dd-fdd1-4e4b-a8d2-b167b3c856cf `
  --output-path .\var\import\gardas_clean_candidate_v2_20260819.txt `
  --quality-policy tr-web-v1 `
  --quality-rejections-path .\var\import\gardas_clean_candidate_v2_20260819.rejections.jsonl
```

Finalde `--limit-lines` ve `--force` kullanılmaz. Manifestte şu muhasebe sağlanır:

`total_lines = written_lines + removed_pii_lines + removed_duplicate_lines +
removed_oversized_lines + removed_quality_lines + skipped_blank_lines`

Çıktı ve ret audit dosyasının gerçek SHA-256/boyutu manifestle karşılaştırılır.

## 5. Yeni kaynak ve yeniden inceleme

1. Kaynak oluşturma formunda “Türetildiği kaynak” olarak V1 UUID'sini seç.
2. Hak/lisans alanlarını V1 kanıtıyla uyumlu doldur; lineage_ref'e v2 manifest referansını yaz.
3. Final dosyayı local ingest ile al.
4. Worker sırasını tek instance ile tamamla: ingest → PII → exact dedup → normalized dedup → sampling.
5. Beklenen kapılar: PII `clear`, exact `unique`, normalized `unique`, örnek sayısı 200.
6. Yeni 200 örnek baştan insan incelemesine girer; V1 kararları V2'ye taşınmaz.
7. Ancak 200/200 onay, sıfır flag ve diğer kapılar temizse insan kaynak onayı verir.

Lineage dedup, V2'nin hem V1'i hem ham atasını geçişli olarak hariç tutar; ilişkisiz
kaynaklardaki gerçek tekrarlar hariç tutulmaz.

## Geri dönüş

V1 doğal geri dönüş noktasıdır. Hatalı V2 nesnesi veya kaynak kaydı overwrite/silme ile
“düzeltilmez”; reddedilir ve yeni sürümlü aday üretilir. Fingerprint silmek, object
değiştirmek veya gate sonucunu elle `unique` yapmak yasaktır.
