# derlem → Gardaş model rafı: v4'ün 200 örneği için ön eleme

> **Kimden:** `derlem` · **Kime:** `gardas-modeller` (raf oturumu) · **Tarih:** 2026-09-20
> **Taşıyan:** kurucu (elden) · **Tür: İSTEK** (v2 dondurmasının kritik yolunda)

## 1. İstek

v4 adayının 200 belgelik örneğini ön elemeden geçirin: her belge için **`temiz` /
`supheli` / `hassas`**, gerekirse tek cümlelik gerekçe ve öneri puanları.

**Karar sizin değil.** 200 örneğin onayı kurucunundur ve kurucunun hesabıyla veritabanına
yazılır; sürümün sözleşme anlık görüntüsü "bu belgeleri kim onayladı" sorusuna o kaydı
gösterir. Kapının varlık sebebi bir insanın bakmış olmasıdır. Sizden istediğimiz o kaydın
yerine geçmek değil, kurucunun okuma sırasını kısaltmak: hangi belge dikkat ister, hangisi
bir bakışta temiz.

## 2. Paket

Kurucunun elinde `rafa-inceleme-on-elemesi-2026-09-20` klasörü var:

| Dosya | Ne | SHA256 (baş) |
|---|---|---|
| `belgeler.jsonl` | 200 belgenin **tam** metni + risk alanları (2,2 MB) | `2a0db0206e288cc3…` |
| `on-eleme.csv` | dolduracağınız sayfa; son üç sütun boş | `2284ca476103ef5e…` |
| `OKU-BENI.md` | biçim, rubrik, sınırlar, geri verme | `f2049c4c7a521ad2…` |

Anahtar `source_ordinal` + `object_sha256`. Sıra risk puanına göre; 121/200 belgenin
otomatik risk işareti var (uzun metin, kontrol karakteri, kimlik/iletişim kalıbı, düşük
kelime çeşitliliği). Bunlar hüküm değil, dikkat çağrısıdır.

## 3. Neden buna ihtiyacımız var

v2'nin son insan engeli bu inceleme. Kurucu iki oturumda 200 belge okuyacak; sizin ön
elemeniz "şüpheli" olanları öne alarak o iki oturumu kısaltır. Ölçülmüş hız yok
(TASK-012'de ilk inceleme hızı da bu turda ölçülecek).

## 4. Dürüst sınırlar

- **Metni değiştirmeyin**, özetlemeyin, düzeltmeyin. Bu belgeler eğitim verisi adayı;
  kaynak metin olduğu gibi kalır (Derlem kuralı: hiçbir metin yerinde temizlenmez).
- Emin olmadığınıza `supheli` deyin. Yanlış `temiz` en pahalı hata: kurucunun gözünden
  kaçmasına yol açar.
- Ön elemeniz veritabanına yazılmaz, denetim izine girmez. Yalnız kurucunun okuma sırasını
  belirler. İsterse hepsini kendi baştan okur.

## 5. Bağlam

v4 = Faz-2 korpusunun temizlenmiş (`clean-candidate-v3`: kişisel veri, `tr-web-v2` kalite,
yakın kopya, dil listesi) ve S2 hak kararıyla süzülmüş hâli — yalnız `wiki_oscar`, `ttk`,
`academic`, `tdk` kaynaklarında geçen satırlar. 4.297.899 satır / 11.255.199.803 bayt,
SHA `23bfcdcf175afa18fa661c82b4fe396b837566922c9a8a43bc8aabdbfafae074`. Held-out v2
(1.641 satır) ve motorun karar seti (`karar-v1`, 400 soru) kayıtlı `eval`/`holdout`
referanslar olarak duruyor; dondurma kapısı artık sayı üretebilir.

Aynı gün size iki paket gidiyor: bu ve **atma denetimi** (706 satır). Sıra önemliyse
önce bunu yapın — atma denetimi v2'yi beklemiyor, bu bekletiyor.
