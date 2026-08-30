# Ofis Ağı Kurulumu: Ekibi Tek Makineye Bağlama

Bu runbook, 5-15 kişilik bir ekibin **aynı ofis/yerel ağdan** tek bir Windows
makinesinde çalışan Derlem'e bağlanmasını sağlar. İnternete açık gerçek kurulum
için bu belge **yeterli değildir**; onun için
[Production Deployment](production_deployment.md) uygulanır.

Güven modeli: ağdaki herkese güvenilir, trafik düz HTTP'dir (TLS yok). Bu
kurulumla **internete port açmayın**.

## 1. Servisleri başlatın

Üç servis de sunucu makinede çalışmalı: PostgreSQL, Go API (8080), Python
worker ve Next.js web (3000). Başlatma komutları için
[Yerel Geliştirme](local_development.md) belgesine bakın.

Yalnız web arayüzü ağa açılır. API (8080) ve PostgreSQL (5432) `localhost`'ta
kalır — tarayıcılar API ile hiç konuşmaz, web sunucusu istekleri kendi içinden
API'ye iletir (`DERLEM_API_URL`).

## 2. Web'i ağa açın

**a. Sunucunun IP'sini bulun** (PowerShell):

```powershell
ipconfig | Select-String "IPv4"
```

Örnek çıktı: `192.168.1.42`. Ekibin kullanacağı adres: `http://192.168.1.42:18400`

**b. Güvenlik duvarında 3000 portunu açın** (yönetici PowerShell, bir kere):

```powershell
New-NetFirewallRule -DisplayName "Derlem Web (LAN)" -Direction Inbound -Protocol TCP -LocalPort 3000 -Action Allow -Profile Private
```

`-Profile Private` bilinçlidir: kural yalnız "özel" olarak işaretlenmiş ağda
geçerlidir; kafe/misafir ağında port kapalı kalır.

**c. Web'i production build ile ve çerez kaçışıyla başlatın:**

```powershell
cd web
npm run build
$env:DERLEM_COOKIE_SECURE = "false"; npm start
```

`DERLEM_COOKIE_SECURE=false` zorunludur: production build oturum çerezini
`Secure` işaretler ve tarayıcılar `Secure` çerezi düz HTTP üzerinden **saklamaz**
— ekip giriş yapar, oturum tutmaz, "kullanamıyoruz" tablosu ortaya çıkar. Bu
kaçış yalnız güvenilir LAN içindir.

**d. Test hesap kartlarını kapatın:** `NEXT_PUBLIC_LOCAL_TEST_ACCOUNTS`,
`NEXT_PUBLIC_LOCAL_LOGIN_EMAIL` ve `NEXT_PUBLIC_LOCAL_LOGIN_PASSWORD` ortam
değişkenleri **boş olmalı** (giriş ekranında yerel test hesapları görünmesin).
Bu değişkenler build sırasında gömülür; değiştirdiyseniz `npm run build`
yeniden çalıştırılmalıdır.

**e. Başka bir cihazdan doğrulayın:** telefon veya ikinci bilgisayardan
`http://<IP>:18400` açılıp giriş yapılabiliyorsa kurulum tamamdır.

## 3. Hesap ritüeli (admin, ~2 dakika/kişi)

> ### ⚠️ Önce yapılacak: yedeği şifreleyin (geri dönüşü olmayan eşik)
>
> Buradaki **ilk gerçek hesabı açtığınız an** veritabanı gerçek parola özetleri
> taşımaya başlar. Yedek aracı veritabanının tamamını kopyaladığı için bu
> özetler yedeğe de girer.
>
> Bugüne kadar bu bir sorun değildi: sistemdeki 8 hesabın hepsi
> `@derlem.local` yerel test hesabıydı ve parolaları zaten giriş ekranında
> yazıyordu — korunacak bir sır yoktu. Gerçek kişiler için durum değişir.
> İnsanlar parolalarını başka yerlerde de kullanır; sızan bir özetin zararı
> Derlem ile sınırlı kalmaz.
>
> **İlk gerçek hesabı açmadan önce, sırayla:**
>
> 1. Bir yedek parolası belirleyin ve **kasaya / parola yöneticisine yazın.**
>    Bu parolayı kaybederseniz yedek kurtarılamaz hale gelir — şifresiz yedekten
>    daha kötü bir sonuçtur.
> 2. Yedeği şifreli olarak yeniden alın:
>    [Backup/Restore](backup_restore.md) → `--passphrase-env BACKUP_PASSPHRASE`.
> 3. Şifresiz eski dump'ı (`db/derlem_*.dump`) silin; şifreli sürüm `.dump.enc`
>    uzantısıyla gelir.
>
> Ayrıca bölüm **2d**'deki kontrolü yapın: giriş ekranındaki test hesabı
> kartları kapalı olmalı. İki iş de aynı eşiğin parçasıdır.

Hesaplar **Kullanıcılar** ekranından tek tek açılır. Önce kağıt üstünde şu
tabloyu doldurun:

| Kişi | E-posta | Görünen ad | Rol(ler) | Geçici parola |
|---|---|---|---|---|
| ör. Ayşe | ayse@ekip.local | Ayşe Yılmaz | moderator | (12+ karakter) |

**Rol seçim rehberi:**

| Kişi ne yapacak? | Rol |
|---|---|
| Dosya/corpus getirip yükleyecek | `data_manager` |
| Örnek belgeleri okuyup onaylayacak | `moderator` |
| Hassas kararlar + benzerlik etiketleme | `expert_reviewer` |
| Metin/künye düzeltecek | `editor` |
| Soru-cevap çifti veya kendi metnini yazacak | `contributor` |
| Çıktı release'lerini indirecek | `consumer_team` |

Kurallar:

- Bir kişiye birden çok rol verilebilir; ama **kaynağı yükleyen onu
  onaylayamaz** (self-review engeli). Her ekipte dosya getiren kişi ile
  inceleyiciler farklı kişiler olsun: pratik dağılım 1 `data_manager` +
  2-4 inceleyici.
- E-posta gerçek olmak zorunda değildir (posta gönderilmez); ama benzersiz ve
  akılda kalır olmalı: `ad.soyad@ekip.local` gibi bir şema seçin.
- Parola en az 12 karakterdir. Kişiye özel üretin (ör. `Derlem-2026-ayse!`),
  güvenli kanaldan iletin. Parolayı sonradan yalnız admin değiştirebilir
  (kullanıcı kendi parolasını henüz değiştiremez — bilinçli eksik, v1
  sonrası).
- Rolü/durumu değişen kullanıcının açık oturumları otomatik düşer.

## 4. Ekibe ilk gün söylenecekler

Herkese verin: **adres** (`http://<IP>:18400`), **e-posta** ve **geçici parola**.

Uygulama gerisini kendisi anlatır: girişte herkes rolüne göre doğru ekrana
iner, karşılama kartı rolünün ilk adımlarını sıralar, her ekranın başındaki
**"Bu ekranda ne yapabilirim?"** kutusu o ekranı anlatır, sol menüdeki
**Rehber** programın amacını ve altı adımlık veri yolculuğunu açıklar.

Yine de sözlü özet isterseniz:

- **İnceleyicilere:** "İnceleme ekranı → kaynağa tıkla → *Güvenli paket al* →
  paketindeki belgeleri oku, puanla, onayla/reddet. Ara verirken *Paketi
  bırak*." Paket sistemi sayesinde aynı belge iki kişiye düşmez; herkes aynı
  anda çalışabilir.
- **Veri yöneticilerine:** "Kaynaklar → *Yeni kaynak* → künyeyi doldur →
  satıra tıklayıp dosyanı yükle → gerisini İşler ekranından izle."
- **Katkıcılara:** "Katkılar → görev tipini seç (soru-cevap veya serbest
  metin) → yaz, şartı onayla, gönder. Katkın havuzda birikir; kaynağa
  demetlenince normal kalite kapılarından geçer."

## 5. Sorun giderme

| Belirti | Neden / çözüm |
|---|---|
| Sayfa hiç açılmıyor | Güvenlik duvarı kuralı yok veya yanlış IP; sunucuda `npm start` çalışmıyor |
| Giriş yapılıyor ama oturum tutmuyor / tekrar giriş istiyor | `DERLEM_COOKIE_SECURE=false` verilmeden başlatılmış — bölüm 2c |
| "Geçersiz e-posta veya parola" | Parola admin'in yazdığından farklı; admin Kullanıcılar ekranından yeni parola atar |
| İşler ilerlemiyor, kaynak "queued" kalıyor | Worker servisi çalışmıyor |
| "Güvenli paket al" boş paket veriyor | Bekleyen belge kalmamış: hepsi karara bağlı veya diğer inceleyicilerin paketlerinde. 15 dakika içinde bırakılan paketler havuza döner |
| Giriş ekranında test hesapları görünüyor | `NEXT_PUBLIC_LOCAL_*` değişkenleri doluyken build alınmış — bölüm 2d |

## Güvenlik sınırları (dürüst liste)

- Trafik düz HTTP: aynı ağdaki biri paketleri dinleyebilir. Güvenilir ofis ağı
  varsayımıdır.
- Kullanıcı kendi parolasını değiştiremez; parola yönetimi admin'dedir.
- Bu kurulum tek makinedir: yedekleme sorumluluğu sunucu sahibindedir
  ([Backup/Restore](backup_restore.md)). **Gerçek hesap açılmışsa yedek şifreli
  olmalıdır** — bölüm 3'ün başındaki eşiğe bakın.
- İnternete açılacaksa: TLS, gerçek secret yönetimi ve
  [Production Deployment](production_deployment.md) + güvenlik backlog'u
  zorunludur.
