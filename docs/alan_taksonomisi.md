# Alan (Domain) Taksonomisi

**Tarih:** 2026-07-06
**Amaç:** Ekiplerin kaynak kaydederken `Alan` kutusuna ne yazacağını
standartlaştırmak. Bu bir öneri sözlüğüdür; alan serbest metin kalır,
arayüz bu listeyi öneri olarak sunar.

## Kurallar

1. **Alan bir etikettir, bölme değildir.** Konu başına ayrı sistem, ayrı
   katalog, ayrı depo yoktur; tüm kaynaklar tek katalogda alan etiketiyle durur.
2. **Alt alan tire ile yazılır:** `tip-radyoloji`, `hukuk-mevzuat`,
   `fizik-astrofizik`. Üst alanlar sabittir, alt alanlar ekiplerin ihtiyacına
   göre serbesttir.
3. **Küçük harf, Türkçe karaktersiz** yazım önerilir (`tip`, `cografya`) —
   arama ve rapor tutarlılığı için.
4. **Karışık derlemeler** (web taraması gibi çok konulu) `mixed` etiketi alır;
   alan belirsiz/önemsizse `genel`; test kaynakları `e2e`.
5. Release mixture raporu alan dağılımını bu etiketten hesaplar; etiket
   disiplini doğrudan rapor kalitesine yansır.

## Üst Alanlar (öneri sözlüğü)

| Etiket | Kapsam | Alt alan örneği |
|---|---|---|
| `hukuk` | Mevzuat, içtihat, hukuk doktrini | `hukuk-yargitay`, `hukuk-mevzuat` |
| `tip` | Tıp ve sağlık bilimleri | `tip-dahiliye`, `tip-radyoloji` |
| `felsefe` | Felsefe, mantık, etik | `felsefe-etik` |
| `matematik` | Matematik | `matematik-analiz` |
| `fizik` | Fizik | `fizik-astrofizik` |
| `kimya` | Kimya | — |
| `biyoloji` | Biyoloji, çevre | — |
| `tarih` | Tarih | `tarih-osmanli` |
| `cografya` | Coğrafya | — |
| `edebiyat` | Edebiyat, şiir, roman | `edebiyat-divan` |
| `dil` | Dilbilgisi, dilbilim, sözlük | `dil-sozluk` |
| `din` | Din, ilahiyat | — |
| `egitim` | Ders kitabı tarzı genel eğitsel içerik | `egitim-lise` |
| `teknoloji` | Bilişim, mühendislik, yazılım | `teknoloji-yazilim` |
| `ekonomi` | Ekonomi, finans, işletme | `ekonomi-finans` |
| `yurttaslik` | Siyaset bilimi, kamu yönetimi, yurttaşlık | — |
| `haber` | Haber ve güncel metin | — |
| `kultur` | Kültür, sanat, müzik, sinema | — |
| `spor` | Spor | — |
| `konusma` | Günlük diyalog, sohbet | — |
| `mixed` | Çok alanlı karışık derleme | Gardas/Faz 2 böyledir |
| `genel` | Alanı belirsiz/önemsiz | — |
| `e2e` | Test/smoke kaynakları | Release'e girmez |

Yeni üst alan ihtiyacı doğarsa bu belgeye eklenir; belge öneri sözlüğü olduğu
için ekleme migration gerektirmez.

## Mevcut Veriler Nasıl Etkilenir?

**Hiç etkilenmez.** Nedenleri:

1. `Alan` kaynağın metadata etiketidir; dosyanın kendisine, SHA256 kimliğine,
   kapı sonuçlarına, onaylara ve release'lere dokunmaz.
2. Mevcut kaynakların etiketleri zaten doğrudur: Gardas derlemeleri `mixed`
   (çok konulu web kaynaklı corpus — tek alana indirgenemez), örnek katkı
   verisi `genel`, smoke kaynakları `e2e`.
3. Bu taksonomi **ileriye dönük disiplindir**: yeni ekipler kaynaklarını
   buradaki etiketlerle kaydeder; eski kayıtlar olduğu gibi kalır.
4. Bir kaynağın etiketi ileride değişecekse editör, metadata düzenleme
   diyaloğundan değiştirir; değişiklik sürüm kontrollü ve audit kayıtlıdır.
5. Alan-özel paket ("yalnız hukuk release'i") istenirse release taslağında
   yalnız o alanın kaynakları seçilir; karışık release'te mixture raporu alan
   dağılımını zaten gösterir.
