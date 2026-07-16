# Eşzamanlı Belge İnceleme

Belge inceleme dağıtımı veritabanı tabanlı atomik claim/lease modeli kullanır.
Uygulama sunucusunda global kilit tutulmadığı için birden fazla API kopyası aynı
PostgreSQL üzerinde güvenle çalışabilir; load balancer için sticky session
gerekmez.

## İnceleyici Akışı

1. Kaynak ayrıntısında **Güvenli paket al** seçilir.
2. Paket boyutu 10, 20, 50, 100 veya 200 olarak belirlenir. Normal kullanımda
   10–20 önerilir.
3. Sistem risk puanı yüksek bekleyen belgeleri önce dağıtır. Başka bir
   inceleyicideki aktif belgeler atlanır.
4. İnceleyici yalnız kendi paketindeki belgelerde karar verebilir.
5. Açık arayüz 15 dakikalık lease'i her 5 dakikada yeniler.
6. Çalışma yarıda bırakılacaksa **Paketi bırak** seçilir. Tarayıcı kapanırsa
   kalan belgeler en geç lease sonunda havuza döner.
7. Paket tamamlanınca yeni paket alınır. Kaynak onayı ancak örneklerin tamamı
   güncel sürümlerinde onaylandığında açılır.

## Çakışma Güvenceleri

- Dağıtım `FOR UPDATE SKIP LOCKED` ile kısa bir transaction içinde yapılır.
- Her belgede aynı anda yalnız bir aktif claim bulunabilir.
- Claim tahmin edilemez bir UUID token, reviewer kimliği ve belge sürümüne
  bağlıdır.
- Süre hesabında API makinesinin değil PostgreSQL'in saati kullanılır.
- Belge düzenlenir, pasifleştirilir veya karar verilirse claim trigger ile
  geçersizleşir.
- Tekil ve toplu kararlar claim sahipliğini transaction içinde yeniden kontrol
  eder. Toplu işlemde tek bir belge bile uyuşmazsa bütün karar geri alınır.
- Claim token audit ayrıntılarına veya loglara yazılmaz; yalnız paket sayısı ve
  bitiş zamanı audit edilir.

## Kaç Kişi Aynı Anda Çalışabilir?

Kullanıcı oturumu bakımından sabit bir 200 kişi sınırı yoktur. Binlerce kullanıcı
aynı anda sisteme bağlı olabilir. Üretken eşzamanlı inceleyici sayısını bekleyen
belge sayısı ve paket boyutu belirler:

```text
azami üretken inceleyici = min(aktif kullanıcı, bekleyen belge / kişi başı paket)
```

200 örnek için paket boyutu 20 ise 10 kişi, paket boyutu 10 ise 20 kişi verimli
çalışır. Teorik üst sınır, kişi başına bir belgeyle 200 kişidir. 1.000 kişi aynı
anda paket isterse 200 farklı belge çakışmasız dağıtılır; kalan 800 kişi boş
paket yanıtı alır. Birden çok kaynakta veya daha büyük iş havuzunda bu sayı
bekleyen toplam belge sayısıyla büyür.

## Production Kapasite Kapısı

Claim algoritmasının çakışmasız olması tek başına binlerce kullanıcılık kapasite
garantisi değildir. Production açılışından önce şu ölçümler yapılmalıdır:

- API kopyaları stateless olarak load balancer arkasında çalıştırılmalı.
- PostgreSQL bağlantı bütçesi API kopyası başına mevcut 20 bağlantı dikkate
  alınarak hesaplanmalı; yüksek kopya sayısında PgBouncer transaction pooling
  kullanılmalı.
- 1.000, 5.000 ve hedef tepe kullanıcıyla claim, renew ve karar yük testi
  yapılmalı; p95/p99 süre, hata oranı, DB lock wait ve pool bekleme süresi
  izlenmeli.
- Claim alma/yenileme uçlarına kullanıcı ve IP bazlı rate limit uygulanmalı.
- Süresi dolmuş claim sayısı, boş paket oranı, karar throughput'u ve lease
  yenileme hataları için dashboard/alarm kurulmalı.

Entegrasyon testi `TestDocumentReviewClaimsDistributeWithoutCollisions`, 1.000
eşzamanlı talebin 200 belgeyi tekrar olmadan dağıttığını ve başka reviewer'ın
claim token ile karar veremediğini gerçek PostgreSQL üzerinde doğrular.
