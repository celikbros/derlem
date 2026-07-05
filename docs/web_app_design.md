# Web Uygulamasi Tasarimi

Bu uygulama LLM veya tokenizer egitimi yapmaz. Amac, veri kumelerini kaydetmek, duzenlemek, kalite ve izin sureclerinden gecirmek, onaylamak ve surumlenmis export paketleri uretmektir.

## Urun Fikri

Sistemi bir **veri atolyesi CMS'i** gibi dusunelim:

- Veri girilir veya dosya olarak yuklenir.
- Kaynak, lisans, dil, domain ve risk bilgisi tutulur.
- Otomatik kontroller calisir.
- Editor/moderator duzenleme ve onay yapar.
- Uzman gerekiyorsa kayit veya kaynak uzman kuyruguna gider.
- Onayli veriler havuza alinir.
- Belirli bir tarih/versiyonda dataset release dondurulur.
- LLM ve tokenizer ekipleri bu release'i manifest ve export dosyalariyla alir.

## Roller

| Rol | Yetki |
| --- | --- |
| `admin` | Kullanici, rol, sistem ayarlari, release freeze |
| `data_manager` | Kaynak ekleme, veri yukleme, havuz/karisim yonetimi |
| `editor` | Metin duzenleme, metadata tamamlama, kalite puani verme |
| `moderator` | Onay/ret, sensitive review yonlendirme |
| `expert_reviewer` | Tip/hukuk/finans/siyaset gibi hassas alan onayi |
| `contributor` | Gorev tamamlama veya veri onerme |
| `consumer_team` | Sadece onayli release ve raporlari indirme |

## Temel Ekranlar

1. **Dashboard**
   - Toplam kaynak, onay bekleyen kayit, riskli veri, son release, kalite dagilimi.

2. **Kaynak Katalogu**
   - Kaynak adi, tip, lisans, dil, domain, dosya path'i, checksum, durum.
   - Baslangicta `C:\CELIKBROS PROJECTS\gardash` Faz 2 verisi burada seed kaynak olarak gorunur.

3. **Veri Giris/Yukleme**
   - Tek metin girisi.
   - JSONL/TXT/CSV yukleme.
   - Kaynak metadata formu.
   - Otomatik checksum ve satir/dokuman sayimi.

4. **Temizleme ve Kontrol Kuyrugu**
   - Encoding/bozuk karakter uyarilari.
   - Dil/domain tahmini.
   - Kisa/uzun/metin tekrari/spam uyarilari.
   - PII/telif/sensitive flag.

5. **Editor Ekrani**
   - Orijinal metin ve duzenlenmis metin yan yana.
   - Metadata duzeltme.
   - Kalite puanlari: dogal Turkce, bilgi guvenilirligi, kaynak sadakati, egitime uygunluk.

6. **Moderator Kuyrugu**
   - `needs_review`, `sensitive_review`, `approved`, `rejected`.
   - Ret nedeni ve audit notu zorunlu.

7. **Dataset Havuzlari**
   - `clean_tr_text`
   - `instruction_answer`
   - `preference`
   - `evaluation_holdout`
   - `pretraining_candidates`
   - `sensitive_review`

8. **Release Builder**
   - Hangi havuz/kaynaklar release'e girecek?
   - Train/eval/post-training ayrimi.
   - Export format secimi: JSONL, TXT, Parquet.
   - Manifest, checksum ve rapor uretimi.

9. **Release Arsivi**
   - Onceki surumler degistirilemez.
   - LLM/tokenizer ekipleri buradan indirir veya path alir.

## Veri Saklama Modeli

PostgreSQL:

- Kullanici ve roller
- Kaynak metadata'si
- Dokuman/kayit metadata'si
- Review ve audit log
- Kalite puanlari
- Release kayitlari

Filesystem veya MinIO/S3:

- Ham dosyalar
- Temizlenmis JSONL/TXT
- Export paketleri
- Raporlar ve checksum dosyalari

Ilk MVP'de local filesystem yeterli:

```text
storage/
  raw/
  normalized/
  reviewed/
  releases/
  reports/
```

## Baslangic MVP

Ilk surum icin en kucuk kullanisli kapsam:

1. Login ve rol sistemi.
2. Kaynak ekleme formu.
3. TXT/JSONL yukleme.
4. Veri listeleme ve arama.
5. Kayit duzenleme.
6. Moderator onay/ret akisi.
7. Basit kalite puani.
8. JSONL/TXT export.
9. Release manifest ve checksum uretimi.

Bu MVP, LLM/tokenizer ekiplerine ilk gunden fayda verir: "su tarihte dondurulmus, su kaynaklardan gelen, su checksum'a sahip, su kalite filtresinden gecmis veri".

## Onerilen Teknik Stack

- Core API: Go
- Data workers: Python
- DB: PostgreSQL
- Dosya: local filesystem, sonra MinIO/S3
- Queue: MVP'de PostgreSQL `FOR UPDATE SKIP LOCKED`; olculmus ihtiyacta Redis Streams
- Frontend: React/Next.js
- Auth: e-posta/parola, sonra OAuth opsiyonel
- Export: JSONL/TXT ilk gun; Parquet ikinci faz

## Ilk Veriyle Baslama

Baslangic icin `C:\CELIKBROS PROJECTS\gardash` Faz 2 verisi sisteme "mevcut frozen kaynak" olarak kaydedilir. Dosyanin kendisi kopyalanmak zorunda degil; path, checksum, doc sayisi ve rapor path'leri kaydedilebilir.

Sonra yeni veriler Atolye uzerinden girilir ve ayri release olarak dondurulur. Boylece ekipler eski veriyle yeni veriyi karsilastirabilir.
