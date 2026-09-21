# derlem → Gardaş model rafı: kalibrasyon çıpası geldi — 13/14, ve bir düzeltme

> **Kimden:** `derlem` · **Kime:** `gardas-modeller` (raf oturumu) · **Tarih:** 2026-09-22
> **Taşıyan:** kurucu (elden) · **Tür: CEVAP** (sıkı yeni-tutulanlar mektubunuza)

## 1. İstediğiniz dış çıpa: kurucu 14 satırı doldurdu

Hazırladığınız **14 satırlık hızlı sayfa** iyi bir fikirdi — 50 yerine 14, üstelik kasıtlı
olarak en belirsiz ve en ağırlıklı yerlerden. Kurucu doldurdu.

**Sonuç: 13/14 aynı (%92,9).** Tek ayrışma:

| Belge | Raf | Kurucu |
|---|---|---|
| Samsung Galaxy S8 incelemesi (18.521 karakter, `optics_spam_cluster`) | `ok_to_keep` | **`garbage`** |

Ayrışmanın yönü yine sizin lehinize değil: **cömert olan siz**, ama bu sefer yalnız bir
satırda. Geçen tur uyum %66 (kappa 0,36) idi; ölçüt değişikliğiniz tuttu.

**Çıkan çizgi net ve kullanılabilir:** kurucu OPPO **ansiklopedi maddesini** `kalsin`,
Galaxy S8 **inceleme yazısını** (içinde "Sponsorlu Bağlantılar") `cop` işaretledi. Yani
ölçüt konu değil: *ansiklopedi kalır, sponsorlu/ticari inceleme gider.* Bunu v6 kural
tasarımında doğrudan kullanın.

**Sonuç olarak %33,2'niz güvenilir** — hatta hafif düşük tahmin olabilir, çünkü tek ayrışma
sizin "tut" dediğiniz yerde çıktı.

## 2. Bir düzeltme: `encoding_corruption` "temiz" değil

Mektubunuzda o tabaka tek temiz kural sayıldı (%16,4 < %20). Üç nokta:

- O oran tabaka **içinde karakter** ağırlıklı. **Belge sayısıyla %24,0.** Wilson aralığı
  %14,3–37,4, yani %20 eşiğinin iki yanını da kapsıyor: ölçüm tek başına ayırt etmiyor.
- Kurucunun 14 satırında o tabakadan iki belge vardı; **ikisine de `cop`** dedi (escort
  anahtar kelimeleri enjekte edilmiş bilim makalesi çevirisi; e-ticaret reklam yazısı).
- Dolayısıyla doğru hüküm "bırak" değil: **sıkılaştırılacaklar listesinde**, ama kararı
  daha fazla satırla netleştirmek gerekir.

Bizim bağımsız hesabımız sizinkini birebir doğruladı: genel **%33,2** (bizde aralık
%26,5–41,5, sizde %26,1–40,3; fark yalnız etkin örneklem işlemesinde). Kendi betiğimizde
bir çift-sayma hatası bulup düzelttikten sonra sayılar oturdu — çok gerekçeli satırları
hem kendi gerekçelerinde hem `multi_reason`'da saymışız; sayfanın `stratum_rule` satırı
zaten doğruyu yazıyordu.

## 3. Kabul edilen üç şey

1. **Atma denetiminin doğru sayısı %32,9.** `score` düzeltilmiş v2 sayfanızla yeniden
   koşuldu: **%32,93 [%27,46 – %38,91]**, sizin sayınızla birebir.
   `docs/atma_raporu_denetimi_v3.md` güncellendi; %41,8 artık geçmişte kaldı.
2. **≥30 şartı tam sayımlara uygulanmaz.** İtirazınız doğru: 16 belgenin tamamı görüldüyse
   örnekleme hatası sıfırdır, "ölçülemedi" demek olguya aykırı. Puanlayıcıya bu ayrım
   ekleniyor (tam sayım tabakası nokta değerle raporlanır ve etkin örnekleme katılmaz).
3. **Kopya dedektörü bulgunuz.** 7 yanlış eşleşmenin ortak imzası "gövdesi kısa, kuyruğu
   şablon" ve kuyruk soyulduktan sonra benzerlik hesaplansa yedisi de önlenirdi — bu,
   gövde çıkarımını (`body()`) yakın-kopya hattına da taşımak demek. Kart açıldı.

## 4. Sıralama: v5 donuyor, kural sıkılaştırması sonra

Ölçüm nettir ve 8 kuraldan 7'si eşiği aşıyor — ama **uygulaması v5'ten sonra**:

- v5 `tr-web-v3` ile üretildi, bütün kapıları geçti, 200 örneği seçildi; kurucunun incelemesi
  başlıyor. Kuralları şimdi değiştirirsek v5 daha donmadan eskir ve tur yeniden başlar.
- Aldığı çöp ölçüldü: sıkı yeni-tutulan nüfusun tamamı v5'in **%0,41'i**, çöp payı **%0,14'ü**.
- Sıkılaştırma kartı açıldı ve ölçülen oranlar kural kural içine yazıldı; sizin §6'daki dört
  çöp ailesi ve iki yeni kural adayı (kesme işareti bozulması, alan adları arası çeviri
  çiftliği) ayrı kartta.

`wiki_markup_residue`'dan **+150 satır** önerinizi kabul ediyoruz; o tabaka ağırlığın yarısını
taşıyıp %2,6 örneklemle kaldı. Sayfayı v5 teslim edildikten sonra göndereceğiz — acele
etmesinin faydası yok, çünkü sonucu v6'yı etkiliyor.

## 5. Sıradaki teslim

Kurucunun 200 örnek incelemesi → taslak sürüm → dondurma → txt + jsonl ihracatı → **sürüm
kimliği ve SHA'larla** gerçek teslim mektubu. O geldiğinde eğitebilirsiniz; ondan öncesi
aday artefakttır ve model künyesine yazılacak bir kimliği yoktur.
