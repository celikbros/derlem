# Kitlesel Katkı Platformu Tasarımı

**Tarih:** 2026-07-06
**Durum:** Tasarım — v0.5 katkı kuyruğunun kitlesel ölçek vizyonu
**Güncelleme (2026-07-16):** Çekirdek katkı kuyruğu ofis ölçeğinde uygulandı
(sahibin moratoryum istisnası kararı, gelen ilk gerçek ekip için): uygulama
içi qa_pair/free_text gönderimi, geri çekme, havuzun kaynağa demetlenmesi ve
mevcut kapılardan geçiş canlıdır (Faz A-B arası). Güven kademeleri, N-onay,
altın görevler, self-signup/CLA/OIDC bu belgedeki ön koşullara bağlı kalır.
**Vizyon:** Çok sayıda gönüllü/uzmanın (hedef: yüz binler kayıtlı, binlerce aktif)
Türkçe yapay zekâ verisine katkı vermesi: soru-cevap, çeviri, yorum/derecelendirme,
veri bağışı ve kalite kontrolü.

## 1. Gerçekçilik Çerçevesi

- "1.000.000 kişi destek olmak istedi" hedefi kayıt sayısıdır; dünya deneyimi
  (Wikipedia, Common Voice) kayıtlıların ~%1-5'inin aktifleştiğini gösterir.
  **Tasarım hedefi: on binlerce kayıt, binlerce aktif katkıcı** — bu bile Türkçe
  veri için dönüştürücüdür.
- Herkes uzman değildir ve olmak zorunda da değildir: görev tipleri beceri
  seviyesine göre katmanlanır; güven, unvanla değil ölçülmüş performansla kazanılır.
- Katkı hacmi pretrain'i büyütmez (o iş v2 web-ölçekli alımın);
  katkı platformunun ürünü **instruction/eval/preference verisi ve inceleme
  kapasitesidir** — token başına en kıymetli veri.

## 2. Görev Tipleri ve Veri Karşılıkları

| Görev | Kim yapabilir | Ürettiği veri (`content_purpose`) | Not |
|---|---|---|---|
| Soru yazma | Herkes (eğitimli) | `instruction` / `eval` adayı | Soru yazan cevabını yazamaz/onaylayamaz |
| Cevap yazma | Alan uzmanı | `instruction` | Kanonik conversation kaydı (user→assistant) |
| Cevap karşılaştırma ("hangisi daha iyi?") | Herkes | `preference` (chosen/rejected) | Şema hazır; RLHF/DPO girdisi |
| EN→TR çeviri | Dil yetkinliği ölçülmüş | `instruction` / paralel korpus | **Kaynak metnin hakkı şart**: yalnız izinli/kamu malı kaynak (Wikipedia, PD kitaplar); çeviri türev eserdir |
| Yorum/derecelendirme | Herkes | Kalite sinyali (veri değil, metadata) | Belge kalite rubric'ine kitlesel girdi |
| Örnek inceleme (veri kontrolü) | Güven kademesi 2+ | İnceleme kapasitesi | Bugünkü 200-örnek darboğazının kitlesel çözümü |
| Metin bağışı | Herkes | `pretrain` adayı (karantinada) | Kendi ürettiği metin; CLA ile hak devri |

## 3. Güven Modeli (tasarımın kalbi)

Hiçbir katkı doğrudan corpus'a girmez (mevcut ilke). Üstüne dört mekanizma:

1. **Güven kademeleri:** `yeni` → `kanıtlı` → `güvenilir` → `uzman onaycı`.
   Yükselme yalnız ölçümle: kabul oranı, altın-görev başarısı, tutarlılık.
   Kademe düşme de otomatiktir.
2. **N bağımsız onay:** her katkı, birbirini görmeyen N (başlangıç: 2-3)
   inceleyiciden geçer; benzerlik çiftlerindeki **sunucu taraflı körleme**
   deseni aynen genellenir. Anlaşmazlıkta uzman onaycıya yükselir.
3. **Altın görevler (honeypot):** doğru cevabı bilinen görevler akışa serpiştirilir;
   inceleyici güvenilirliği sürekli ölçülür. Ham metin gibi altın cevaplar da
   inceleyiciye ifşa edilmez.
4. **Self-review yasağı genişler:** kendi katkını, kendi çevirini, kendi sorunun
   cevabını inceleyememek; aynı kişinin çoklu hesabına karşı organizasyon
   kimliği `SEC-P1-02` kapsamında.

Mevcut altyapının hazır verdiği parçalar: rol modeli (`contributor` rezerve),
append-only audit, karantina durumu, kanonik conversation/preference şeması,
self-review engeli, körlemeli inceleme akışı.

## 4. Kimlik ve Hesap Açma

- Bugünkü admin paneli (elle hesap) yalnız **çekirdek ekip** içindir; kitle için
  **self-signup + e-posta doğrulama + Keycloak/OIDC** gerekir (`SEC-P1-01`).
  1M hesap elle açılamaz ve açılmamalıdır.
- Kayıtta zorunlu **Katkıcı Lisans Anlaşması (CLA)**: katkının eğitim amaçlı
  kullanım hakkını platforma devreder. Böylece her katkının `rights_status`
  sorusu baştan çözülür; CLA sürümü her katkıya lineage olarak işlenir.
- KVKK: katkıcıların kişisel verisi (e-posta, IP) için aydınlatma + saklama
  politikası; katkı içeriği ile katkıcı kimliği ayrık tutulur (release'lere
  kimlik sızmaz, yalnız takma-ad/katkıcı-id istatistiği girer).
- **"İstihdam" uyarısı:** katkı gönüllüyse şartlar sözleşmesi yeter; ödeme/mikro
  görev ücreti planlanıyorsa iş/vergi hukuku devreye girer — bu karar hukuk
  danışmanıyla verilmelidir; teknik tasarım iki modeli de destekler (katkı
  sayacı ve kalite skoru zaten ölçülüyor).

## 5. Ön Koşullar (sıra kesin)

1. **P0 güvenlik kapanışı** — kendi kuralımız: dış kullanıcı erişimi
   `SEC-P0-03..08` kapanmadan açılamaz (TLS/CSRF, audit attribution, secret,
   kota/DoS, supply-chain). 06'nın restore ayağı kapandı; diğerleri açık.
2. **İnternet'e açık altyapı** — staging/production sunucu, S3/MinIO,
   offsite yedek, gözlemlenebilirlik (v0.6).
3. **Keycloak/OIDC + self-signup + CLA akışı.**
4. **Katkı kuyruğu uygulaması** — görev tipleri, karantina, N-onay, güven
   kademeleri, altın görevler.

## 6. Fazlı Yol

| Faz | Ölçek | İçerik | Ön koşul |
|---|---|---|---|
| A — Çekirdek (şimdi mümkün) | 5-20 tanıdık uzman | Admin panelden hesap; Gardas 200 örneği, benzerlik etiketleri, ilk S-C seti; süreç öğrenilir | Yok — bugün başlanabilir |
| B — Kapalı pilot | 50-200 davetli | Katkı kuyruğu v1 (S-C + inceleme), güven kademeleri, altın görevler | Katkı kuyruğu kodu + P0'ların çoğu |
| C — Açık kayıt | Binler-on binler | Self-signup + CLA + Keycloak; çeviri ve preference görevleri; liderlik tablosu/rozet | Tüm P0 + v0.6 altyapı |
| D — Kitle | Yüz binler kayıt | Moderasyon ekibi, topluluk yönetimi, ölçek altyapısı (queue/CDN) | C'nin ölçüm verisi |

Her faz bir sonrakinin varsayımlarını ölçerek doğrular ("ölçek ölçümle büyür").

## 7. Hesap Açılış Modelleri (2026-07-06 kararı)

Kullanıcının önerdiği model **başvuru-onay** modelidir: kişi hesabını kendisi
açar, hangi görev için geldiğini beyan eder; yetkili görevli başvuruyu
onaylar/reddeder ve rol/görev atar. Beş bilinen model ve ödünleşimleri:

| Model | Nasıl çalışır | Güçlü yanı | Zayıf yanı | Uygun faz |
|---|---|---|---|---|
| Davet | Mevcut güvenilir üye davet eder; davet ilk güveni taşır | En yüksek kalite girişi | Büyümez | A-B |
| **Başvuru-onay** (önerilen taban) | Self-signup + görev beyanı + insan onayı + rol atama | Kontrollü, denetlenebilir, niyet verisi toplar | Ölçekte onay darboğazı: günde binlerce başvuruyu insan okuyamaz | B-C |
| Açık kayıt + kazanılmış güven | Anında kayıt (e-posta doğrulama); herkes yalnız düşük-riskli görev görür; yükselme ölçümle | Sınırsız ölçeklenir, onay emeği sıfır | Girişte kimlik/niyet bilgisi zayıf | C-D |
| Yeterlilik sınavı | Rol, testi geçmekle açılır (çeviri testi, alan quizi) | Beceri kanıtı nesnel | Tek başına motivasyonu ölçmez | Rol yükseltmede ek |
| Kurumsal/federated | Üniversite/dernek toplu getirir, kurum kefil olur | Toplu ve nitelikli giriş | Kurum anlaşması gerekir | C-D |

**Karar — hibrit:** giriş ile yetki ayrılır.

1. **Giriş otomatiktir** (e-posta doğrulamalı self-signup): hesap `pending`
   değil, anında `contributor` olur ama YALNIZ düşük-riskli görevleri görür
   (tercih karşılaştırma, kalibrasyon/altın görevler). Bot/istismar riski
   düşük-riskli görevlerde sınırlıdır; insan onayı beklemek 1M ölçeğinde
   imkânsızdır.
2. **Görev beyanı kayıtta alınır** ("hangi görev için geldiniz": çeviri,
   cevap yazma, inceleme, alan uzmanlığı + kısa gerekçe/kanıt). Bu beyan
   yönlendirme verisidir ve ilgili onaycının kuyruğuna düşer.
3. **İnsan onayı yükseltmeye uygulanır** (kullanıcının önerdiği akış tam
   burada): görevli, başvuru + ölçülmüş performansı (altın görev skoru,
   kabul oranı) birlikte görür; rolü/görevi atar veya reddeder. Onay/ret
   gerekçesiyle audit'e yazılır; onaycı kendi davet ettiğini onaylayamaz.
4. **Yüksek-riskli roller her zaman insan kapısındadır:** uzman onaycı,
   moderatör, hak/lisans görevleri hiçbir zaman otomatik verilmez.

Uygulama notu: bugünkü şemaya küçük ek yeter — `users.status`'a `pending`
yerine, ayrı bir `role_applications` tablosu (beyan, kanıt referansı, karar,
karar veren, gerekçe) + Kullanıcılar paneline "Başvurular" kuyruğu. Mevcut
admin kullanıcı yönetimi (2026-07-06) bunun çekirdeğidir.

## 8. Açık Sorular (karar bekliyor)

- Ödeme/gönüllülük modeli (hukuk görüşü şart).
- Çeviri kaynak havuzu: hangi izinli EN kaynaklar? (Wikipedia + PD önerisi.)
- Katkıcı itibarının kamuya açıklığı (liderlik tablosu) ve takma ad politikası.
- Eval sorularının gizliliği: eval'e giden katkılar yayımlanmaz — katkıcıya
  baştan bildirilir.
