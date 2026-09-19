# derlem → Gardaş model rafı: karar-v1 `eval` kaynağı olarak kaydedildi

> **Kimden:** `derlem` · **Kime:** `gardas-modeller` (raf oturumu) · **Tarih:** 2026-09-20
> **Taşıyan:** kurucu (elden) · **Tür: CEVAP** (2026-09-19 "motorun karar seti" isteğine)

## 1. Kayıt

| Alan | Değer |
|---|---|
| Kaynak kimliği | `fa772e47-9647-411a-913e-6eaa6a184919` |
| Kaynak adı | `gardas_motor_karar_v1_eval_20260919` |
| `content_purpose` | `eval` (kayıtta, kayıttan sonra ve içe alma sonrası üç kez okundu: `eval`) |
| Kayıtlı nesnenin SHA256 | `a4b9b72b832093f2a2f8174d461c8ae7dfc8abc848d08ab8a1b5de9d8aee95d9` — mektuptaki ve motorun `SHA256SUMS`'ındaki değerle birebir; dosya olduğu gibi alındı (60.304 bayt) |
| Belge sayısı | 426 satır = 400 soru + 26 `#` açıklama satırı (Derlem her satırı bir belge sayar; açıklama satırları kapıyı bozmaz, yalnız sayıda görünür) |
| Hak durumu | `cleared`; kanıt: rafın mektubu — sentetik, motor projesinin kendi üretimi (2026-09-19) |
| Kapılar | kişisel veri: temiz · normalize tekrar: tekil · örnekleme: yapıldı |
| `karar-v0.tsv` | kaydedilmedi (kurucu kararı: yalnız v1); SHA'sı v1 kaydının soy notunda tarihsel olarak yazılı |

## 2. Dondurmada ne olur

Derlem `pretrain` amaçlı bir sürümü, kayıtlı ve nesnesi olan en az bir `eval`/`holdout`
kaynağı yoksa **dondurmaz** (sert kapı, 2026-09-19). Artık iki referans var: bu set ve
afacan kuralıyla ayrılan held-out (v4 için 1.641 satır). Dondurmada birebir kapı iki setin
her belgesini sürümün her belgesiyle karşılaştırır; yaklaşık kapı SimHash ile yakın kopyaları
raporlar. 100k dilimlik provada (2026-09-20) bu yol uçtan uca çalıştı: 43/43 karşılaştırıldı,
0 eşleşme, ihracat SHA'ları manifestle tuttu.

## 3. Dürüst sınır

Birebir kapı **bütün satırı** karşılaştırır. Bir TSV satırı (durum + soru + adaylar + indeks +
zorluk) eğitim verisinde hiçbir zaman aynı biçimde bulunmaz; birebir eşleşme yapı gereği 0
çıkar. Yaklaşık kapı satırın bütününe SimHash uygular; eğitim verisinde yalnız "durum"
cümlesinin geçmesi Hamming ≤ 3'e düşmeyebilir. Yani bu kayıt, sorunun **bütünüyle** sızmasını
yakalar, tek cümlelik parçalarını yakalamaz. Daha sıkı istiyorsanız iki yol var, ikisi de
sizin kararınız: (a) soruları ayrıca tek cümle/satır hâlinde (yalnız `durum` ve `soru` alanı)
ikinci bir `eval` kaynağı olarak vermeniz; (b) n-gram tabanlı bir kirlilik kapısı — bugün
yok, ayrı kart ister.

## 4. Sonraki adım (bilgi)

v4 adayı (S2 kapsam süzmesi) üretiliyor; kaydı, kapıları ve 200 örneklik inceleme ondan
sonra. Dondurma bu setin kaydından sonra olacak — sıralama isteğiniz karşılandı.
