# Danışman Yanıtı - Web Veri Atölyesi MVP

**VERSION:** 1.0
**Tarih:** 2026-06-22
**Hazırlayan:** Danışman incelemesi
**İlgili plan:** `docs/web_data_atolyesi_mvp_plan.md`

---

## 0. Tek Cümlelik Özet

Planın iskeleti sağlam ve doğru. Tek kritik mesele şu: sistemin verdiği sözler
(ham veri değişmez, kaynak takibi yapılır, release yeniden üretilebilir) sadece
"öyle kabul edelim" denerek değil, **kodda ve altyapıda zorla** garanti
edilmeli. Aşağıdaki yanıt istediğin formatta; sonunda sade bir altyapı önerisi var.

---

## 1. İstenen Formatta Yanıt

**1. En kritik risk**
En büyük risk: kötü, izinsiz veya yanlış tipte verinin sessizce eğitim setine
sızması ve bunu ancak model eğitildikten **sonra** fark etmen. İki somut yol:
(a) lisans/hak durumu belirsiz veri release'e girer; (b) test (eval) verisi
eğitim (pretrain) verisine karışır. İkisi de "fark edince çok geç" türünden.

**2. Onayladığım kararlar**
- Büyük corpus'u satır satır değil, kaynak/shard bazlı onaylamak (+ örneklem denetimi).
- PostgreSQL'i sadece metadata için kullanmak, büyük metni DB'ye basmamak.
- Otomatik kontrolleri (checksum, encoding, sayım, lisans, exact-duplicate, temel PII) öne almak.
- Release'den önce kalite ve risk kapılarının çalışması.
- Ham dosyanın değişmez (immutable) kabul edilmesi.
- Donmuş release'in değiştirilmemesi; hata varsa yeni release açılması.

**3. Değişmesini önerdiğim kararlar**
- "Ham dosya değişmez" sözünü referans path ile bırakma -> dosyayı yönetilen,
  üzerine yazılamayan bir depoya **kopyala** (aşağıda altyapı kısmı).
- Gardas seed'ini sadece path + checksum ile "onaylı kaynak" yapma -> önce kopyala.
- Eğitim/test verisi ayrımını (`content_purpose`) ve test-verisi-ayıklamayı (dekontaminasyon)
  Faz 4'ten **öne çek** (bkz. Faz sıralaması).
- "PII regex" yeterli değil -> en azından TCKN için checksum'lı kontrol ekle.

**4. MVP'ye mutlaka eklenmeli**
- **Veri tipi etiketi** (`content_purpose`: pretrain / instruction / preference / eval),
  kayıt anında zorunlu ve sonradan değişmez.
- **Test/eğitim ayıklama kapısı (dekontaminasyon):** bir eval dokümanı pretrain
  havuzunda görünürse release **bloke**. (Önce exact-match; ileride yaklaşık.)
- **Sert haklar kapısı (varsayılan: reddet):** lisans/hak durumu bilinmeyen veya
  belirsiz kaynak release'e **giremez**, sadece uyarı değil.
- **TCKN-doğrulamalı temel PII taraması** (Faz 2; TCKN, IBAN, telefon, e-posta, kart).
- **Değiştirilemez denetim kaydı (audit log):** her durum değişikliği eklenir,
  silinmez/düzenlenmez; freeze anında kaynakların sha256'ları kayda sabitlenir.
- **İçerik-adresli + değişmez depo** (dosya kimliği = sha256, path değil).
- **Gerçek kimlik doğrulama** (auth) ilk günden; ajanlar da bu sisteme dahil.

**5. MVP'den sonraya ertelenebilir**
Parquet; OAuth protokolü (basit oturum/JWT ile başla); MinIO/S3 yerine local
başlamak istersen sonra geçiş; yaklaşık tekrar tespiti (near-dedup); kapsamlı
PII modeli; gelişmiş dil/mojibake skoru; gelişmiş dashboard.

**6. Veri yönetimi / acil kırmızı çizgiler** (asla olmamalı)
- Hak durumu doğrulanmamış kaynak release'e girmesin.
- Test (eval/benchmark) verisi eğitim (pretrain) release'ine girmesin.
- Donmuş release yerinde değiştirilmesin (düzeltme = yeni release).
- Onaylı verinin kanonik kopyası sadece değiştirilebilir tek bir path'te yaşamasın.
- Denetim kaydı (audit log) düzenlenebilir/silinebilir olmasın.
- PII (özellikle TCKN ve özel nitelikli veri) taranmadan/işaretlenmeden akmasın.

**7. Kısa nihai tavsiye**
İskelet sevkiyata hazır. Onu üretim-güvenli yapan şey, garantileri "kabul"den
"koda" taşımak. Üç şeyi omurga yap: (1) değişmez veri-tipi etiketi + test/eğitim
ayıklama; (2) üzerine-yazılamayan depo + değiştirilemez audit; (3) varsayılan-reddet
haklar kapısı. Geri kalan her şey bunların üstüne güvenle eklenir.

---

## 2. 9 Soruya Kısa Yanıt

1. **PostgreSQL + local FS ile başlamak doğru mu?** Evet. Tek şart: dosya
   kimliği path değil sha256 olsun ve depo bir arayüz arkasında dursun ki sonra
   S3/MinIO'ya geçiş kolay olsun. (Depo için aşağıdaki revizyona bak.)
2. **Shard bazlı onay yeterli mi?** Evet, ama "birkaç örneğe bakmak" değil,
   istatistiksel örneklem + risk bazlı yoğunlaştırma. Örneklem kötüyse tüm
   shard karantinaya alınır.
3. **Zorunlu metadata?** Senin listen iyi bir taban. Ekle: `content_purpose`
   (veri tipi), kaynak URL'i, lisans kanıtı işaretçisi, PII durumu, ham kaynağa
   bağ (lineage). `storage_path` yerine sha256 kimliği.
4. **PII/KVKK/lisans/telif minimumu?** Haklar kapısı sert ve varsayılan-reddet:
   lisansı bilinmeyen/belirsiz kaynak geçemez, kanıt + sorumlu kişi ile kaydedilir.
   Temel PII (TCKN checksum'lı) Faz 2'de. Özel nitelikli veri (sağlık, din vb.)
   için karantina. Silme/takedown yolu baştan veri modeline koyulmalı.
   *(Not: kesin yasal dayanak için avukat gerekir; ben mühendislik tarafını veriyorum.)*
5. **Freeze için zorunlu audit?** Kim + ne zaman; içerdiği kaynakların ID'leri
   **ve** o andaki sha256'ları; manifest + manifest hash'i; üreten pipeline/config
   sürümü; kapı sonuçları (kalite, PII, haklar, dekontaminasyon); onay zinciri.
   Kayıt eklenir, silinmez (ideali: hash-zincirli).
6. **Eğitim/test karışmasın diye teknik kural?** Veri tipi etiketi zorunlu/değişmez;
   havuzlar tek-tipli; Release Builder yanlış tipi **sert hatayla** reddeder; ve
   etikete güvenme - pretrain freeze'inden önce eval setlerine karşı içerik-düzeyi
   ayıklama (dekontaminasyon) çalışır.
7. **Gardas seed'i sadece path+checksum ile yeterli mi?** Kataloglamak için evet,
   onaylı kaynak yapmak için **hayır**. Önce sha256 hesapla + değişmez depoya kopyala;
   orijinal path'i sadece köken bilgisi olarak tut.
8. **Faz sıralamasında eksik/ters?** Evet - dekontaminasyon ve veri-tipi etiketi
   öne alınmalı, audit ve auth en başa. (Bkz. bölüm 4.)
9. **Ön değerlendirme kararları?** Çoğu onay. İki istisna: "ham immutable"ı gerçek
   bir değişmez depoyla zorla (lafta bırakma); "OAuth ertelenebilir" doğru ama
   **auth'un kendisi ertelenemez** (basit oturum/JWT ile başla).

---

## 3. Altyapı Önerisi (Sade)

| Katman | Öneri | Neden |
|---|---|---|
| Backend | FastAPI + Pydantic | Pydantic zorunlu alanları/etiketleri API'de zorlar. |
| Veritabanı | PostgreSQL | Sadece metadata + audit. |
| Dosya deposu | MinIO (object-lock açık) | "Değişmez" sözü lafta kalmasın; kilit altyapıda olsun. İstemezsen: local FS + dosya yazma-kilidi, ama daha zayıf. |
| Kuyruk | RQ + Redis | MVP'ye yeterli en basit seçenek. |
| Ağır işleme | DuckDB + Polars | Tek makine, düşük bellek, cluster gerekmez. |
| PII tarama | Presidio + TCKN checksum | "11 hane" değil, gerçek geçerli TCKN'leri yakalar; yanlış alarm düşer. |
| Kimlik/yetki | Basit JWT ile başla -> Keycloak'a geç | Ajanlar = aynı sistemde "servis hesabı"; insan ve ajan tek yetki modeline tabi. |
| Frontend | Next.js + TypeScript | En az riskli katman. |
| Export | JSONL/TXT -> sonra Parquet | İlk sürüm için yeterli. |

Önemli: Bunların hepsi tek bir makinede çalışır. Kubernetes, mikroservis,
karmaşık dağıtık sistem MVP'de gerekmez. Docker Compose ile başla, gerçekten
ihtiyaç olunca büyüt.

Ajan entegrasyonu: ayrı bir "ajan sistemi" kurma. Ajanlar, insanlarla aynı API'ye
bağlanan ve aynı rol/kapı kurallarına tabi istemcilerdir; sadece her eyleminde
"bu bir ajandı, şu model/sürüm" bilgisi kaydedilir.

---

## 4. Faz Sıralaması - Tek Önemli Düzeltme

Planın geneli iyi. Sadece şunları öne/başa al:

- **Faz 0'a ekle:** değiştirilemez audit kaydı (silinmez tablo) + gerçek auth.
- **Faz 1'e ekle:** veri-tipi etiketi (`content_purpose`, kayıt anında zorunlu) +
  içerik-adresli değişmez depo (seed dahil "kopyala, sonra onayla").
- **Faz 3'ten ÖNCE çalışsın:** test/eğitim ayıklama kapısı (exact-match
  dekontaminasyon). Planda bu Faz 4'te kalırsa, ayıklanmamış bir pretrain
  release'i dondurabilirsin. En kritik sıralama hatası budur.

---

## 5. Sonradan Konuşulan Kapsam

- **Katmanlı global katkı (açık giriş + güvenilir onaycılar):** açık kullanıcının
  verisi doğrudan havuza gitmez, karantinada bekler ve güvenilir onay (veya N
  bağımsız onay) ile yükselir. Kimse kendi katkısını onaylayamaz.
- **Ajan yetkisi (bazı kapılarda otonom, kritik kapılar insan):** ajan hak/lisans
  temizleyemez, release donduramaz, kullanıcı güven seviyesi yükseltemez - bunlar
  insan kapısı.
- **Ajan veri üretimi (sentetik):** her içerik "insan mı, ajan mı üretti" bilgisini
  taşır; saf-insan pretrain havuzu ajan-üretimi içeriği reddeder.

---

Bu doküman mühendislik/süreç tavsiyesidir; lisans, KVKK ve telif konularında
kesin yasal dayanak için hukuk danışmanı gereklidir.
