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

## Kategori Listesi (öneri sözlüğü)

24 üst kategori. Alt kategoriler `ust-alt` biçiminde serbestçe türetilir;
listedekiler örnektir, ekip ihtiyaç duyduğu alt kategoriyi kendisi açabilir.
Rapor okunabilirliği için en fazla iki seviye önerilir
(gerekirse üç: `tip-dahiliye-kardiyoloji`).

| # | Üst kategori | Alt kategori örnekleri |
|---|---|---|
| 1 | `hukuk` | `hukuk-mevzuat`, `hukuk-ictihat`, `hukuk-doktrin`, `hukuk-sozlesme` |
| 2 | `tip` | `tip-dahiliye`, `tip-cerrahi`, `tip-radyoloji`, `tip-pediatri`, `tip-psikiyatri`, `tip-eczacilik`, `tip-dis`, `tip-halk-sagligi` |
| 3 | `felsefe` | `felsefe-etik`, `felsefe-mantik`, `felsefe-metafizik`, `felsefe-siyaset-felsefesi` |
| 4 | `matematik` | `matematik-analiz`, `matematik-cebir`, `matematik-geometri`, `matematik-istatistik` |
| 5 | `fizik` | `fizik-mekanik`, `fizik-astrofizik`, `fizik-kuantum` |
| 6 | `kimya` | `kimya-organik`, `kimya-anorganik`, `kimya-biyokimya` |
| 7 | `biyoloji` | `biyoloji-genetik`, `biyoloji-mikrobiyoloji`, `biyoloji-ekoloji` |
| 8 | `tarih` | `tarih-osmanli`, `tarih-cumhuriyet`, `tarih-islam`, `tarih-dunya` |
| 9 | `cografya` | `cografya-turkiye`, `cografya-dunya` |
| 10 | `edebiyat` | `edebiyat-roman`, `edebiyat-siir`, `edebiyat-divan`, `edebiyat-halk`, `edebiyat-dunya` |
| 11 | `dil` | `dil-dilbilgisi`, `dil-sozluk`, `dil-ceviri`, `dil-dilbilim` |
| 12 | `din` | `din-islam`, `din-ilahiyat`, `din-dinler-tarihi` |
| 13 | `egitim` | `egitim-ilkokul`, `egitim-ortaokul`, `egitim-lise`, `egitim-universite` |
| 14 | `teknoloji` | `teknoloji-yazilim`, `teknoloji-yapay-zeka`, `teknoloji-elektrik-elektronik`, `teknoloji-makine`, `teknoloji-insaat` |
| 15 | `ekonomi` | `ekonomi-finans`, `ekonomi-isletme`, `ekonomi-muhasebe` |
| 16 | `sosyal` | `sosyal-psikoloji`, `sosyal-sosyoloji`, `sosyal-antropoloji` |
| 17 | `yurttaslik` | `yurttaslik-kamu-yonetimi`, `yurttaslik-uluslararasi-iliskiler` |
| 18 | `tarim` | `tarim-ziraat`, `tarim-veterinerlik`, `tarim-gida` |
| 19 | `haber` | `haber-gundem`, `haber-yerel` |
| 20 | `kultur` | `kultur-sanat`, `kultur-muzik`, `kultur-sinema`, `kultur-mutfak` |
| 21 | `spor` | `spor-futbol`, `spor-genel` |
| 22 | `konusma` | `konusma-diyalog`, `konusma-forum` |
| 23 | `mixed` | Çok alanlı karışık derleme (Gardas/Faz 2 böyledir) |
| 24 | `genel` | Alanı belirsiz/önemsiz |
| — | `e2e` | Test/smoke kaynakları; release'e girmez |

Yeni üst kategori ihtiyacı doğarsa bu belgeye eklenir; belge öneri sözlüğü
olduğu için ekleme migration gerektirmez.

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
