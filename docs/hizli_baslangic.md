# Hızlı Başlangıç: İlk Kaynağınızı Uçtan Uca Geçirin

Bu kılavuz, Derlem'i ilk kez açan birinin ~15 dakikada tüm veri yolculuğunu
küçük bir deneme dosyasıyla yaşamasını sağlar. Servislerin kurulumu için önce
[Yerel Geliştirme](local_development.md) belgesini uygulayın; üç servis de
çalışıyor olmalı (API, worker, web).

Ekranların ve rollerin özeti için web arayüzündeki **Rehber** sekmesine de
bakabilirsiniz. Bir ekibi aynı ofis ağından bu kuruluma bağlayacaksanız:
[Ofis Ağı Kurulumu](ofis_kurulumu.md).

## 0. Deneme dosyası hazırlayın

Birkaç satırlık bir metin dosyası yeterli:

```powershell
@'
Bu bir deneme belgesidir.
İkinci deneme belgesi de bu satırdır.
Üçüncü satır üçüncü belgedir.
'@ | Out-File -Encoding utf8 C:\tmp\deneme_corpus.txt
```

Gerçek akışta bu dosya, hakları bilinen bir corpus dosyasıdır (ör. bir web
derlemesi veya Gardas gibi mevcut bir corpus'un çıktısı).

## 1. Giriş yapın

`http://localhost:3000` adresini açın ve admin hesabıyla girin
(local hesaplar: [Local Rol Test Kullanıcıları](local_role_testing.md)).
Sol menüde rolünüze açık ekranlar listelenir.

## 2. Kaynak kaydı açın

**Kaynaklar → Yeni kaynak**:

| Alan | Örnek değer | Not |
|---|---|---|
| Kaynak adı | `deneme_corpus_v1` | |
| Kaynak tipi | `test` | serbest metin |
| İçerik amacı | `Pretrain` | **sonradan değiştirilemez** |
| Lisans | `internal-test` | |
| Hak durumu | `Temizlendi` | gerçek veride kanıt olmadan Temizlendi seçmeyin |
| Dil | `tr` | |
| Alan | `genel` | |
| Lisans kanıtı | `docs/ornek_kanit.md` | kanıt referansı zorunlu kapıdır |
| Köken bilgisi | `C:\tmp\deneme_corpus.txt` | dosyanın nereden geldiği |

Kaydettiğinizde katalogda "Kaydedildi" durumunda yeni satır belirir; satırdaki
**Sıradaki kapı** sütunu her an "şimdi ne bekleniyor" sorusunun cevabıdır
(şu an: "Dosya bekliyor").

## 3. Dosyayı yükleyin

Katalogda kaynağın adına tıklayın; sağda detay paneli açılır. Dosya yükleme
bölümünden `deneme_corpus.txt` dosyasını yükleyin. Yükleme kuyruğa alınır ve
worker sırasıyla şunları yapar: SHA256 hesabı, değişmez depoya kopya, PII
taraması, tekrar kontrolü, belge parmak izleri ve örneklem çıkarma.

**İşler** ekranında bu işlerin durumunu ve ilerlemesini izleyebilirsiniz.
Birkaç saniye içinde kaynak "Örneklem incelemesi" durumuna gelir.

## 4. Örnekleri inceleyin

**İnceleme** ekranına geçin; kaynak kuyruktadır. Detay panelinde örnek
belgeler listelenir (deneme dosyasında 3 belge). Her belgeyi açıp kalite
puanı verin ve onaylayın — veya hepsini seçip toplu karar uygulayın.

Kural: örneklerin **tamamı** incelenmeden kaynak onaylanamaz.

## 5. Kaynağı onaylayın

Tüm örnekler onaylanınca detay panelindeki karar bölümünde **Onayla** aktif
olur. Karar gerekçesiyle birlikte audit kaydına yazılır. Sıradaki kapı
"Onaylı" olur.

Onay aktif olmuyorsa detay panelindeki kapı listesi hangi koşulun eksik
olduğunu gösterir (hak durumu, lisans kanıtı, PII, tekrar, örnek kapsaması).

## 6. Release oluşturun ve dondurun

**Sürümler** ekranında yeni taslak release oluşturun; aynı içerik amacındaki
(Pretrain) onaylı kaynaklar seçilebilir listede görünür. Taslağı oluşturduktan
sonra (admin rolüyle) **Freeze** deyin. Freeze işi kapıları yeniden çalıştırır,
eval/holdout sızıntı kontrolü yapar ve SHA256 manifest'ini sabitler.

## 7. Export alın ve doğrulayın

Frozen release detayından JSONL veya TXT export kuyruğa alın; hazır olunca
artifact ve manifest'i indirin. Manifest'teki SHA256 değerini indirilen dosyayla
karşılaştırarak doğrulayın:

```powershell
Get-FileHash indirilen_export.jsonl -Algorithm SHA256
```

Bu çıktı artık herhangi bir LLM/tokenizer ekibine verilebilir; içinde model
template'i, özel token veya tokenizer varsayımı yoktur.

## Sık takılınan noktalar

- **"Onayla" pasif:** kapı listesine bakın; en sık neden incelenmemiş örnek
  veya `Bilinmiyor` durumundaki hak alanıdır.
- **Kaynak karantinada:** PII bulgusu veya tekrar tespiti var demektir; detay
  panelindeki tarama sonuçlarına bakın. Karantina bir hata değil, kapının
  çalıştığının kanıtıdır.
- **Aynı dosyayı ikinci kez yüklediniz:** exact-duplicate kapısı ikinci kaynağı
  reddeder; bu bilinçlidir.
- **Hiçbir iş ilerlemiyor:** worker servisi çalışmıyor olabilir;
  [Yerel Geliştirme](local_development.md) içindeki worker komutunu kontrol edin.
