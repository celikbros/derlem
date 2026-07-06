# Alan (Domain) Taksonomisi

**Tarih:** 2026-07-06 · **Revizyon:** 2026-07-07 (danışman geri bildirimi:
bilisim/muhendislik ayrımı, haber/konusma'nın içerik türüne taşınması,
tek-etiket kuralı, yazım kuralları)
**Amaç:** Ekiplerin kaynak kaydederken `Alan` kutusuna ne yazacağını
standartlaştırmak. Bu bir öneri sözlüğüdür; alan serbest metin kalır,
arayüz bu listeyi öneri olarak sunar.

## Kurallar

1. **Alan bir etikettir, bölme değildir.** Konu başına ayrı sistem, ayrı
   katalog, ayrı depo yoktur; tüm kaynaklar tek katalogda alan etiketiyle durur.
2. **Bir kaynak TEK alan etiketi taşır.** Kesişimli konularda baskın alan
   seçilir: "yapay zekâ ile radyoloji" derlemesi içerik tıbbi ağırlıklıysa
   `tip-radyoloji`, teknik ağırlıklıysa `bilisim-yapay-zeka` olur. Çoklu
   etiket raporlamayı bozar; kararsız kalınırsa kaynağın kullanım amacına
   en yakın alan seçilir.
3. **Alan ≠ içerik türü.** "Haber", "röportaj", "forum", "diyalog",
   "ansiklopedi" birer içerik TÜRÜdür ve `Kaynak tipi` alanına yazılır.
   Ekonomi haberi derlemesi: `Alan: ekonomi`, `Kaynak tipi: haber`.
   Doktor röportajları: `Alan: tip`, `Kaynak tipi: roportaj`.
4. **Yazım:** tüm etiketler küçük harf; Türkçe karakter yok; boşluk ve
   noktalama yok; kelimeler tire ile ayrılır (`yapay-zeka`, `siber-guvenlik`).
5. **Seviye:** alt alan `ust-alt` biçimindedir (`tip-radyoloji`). Önerilen iki,
   en fazla üç seviye (`tip-dahiliye-kardiyoloji`); **dördüncü seviye
   kullanılmaz** — kontrolden çıkar.
6. Release mixture raporu alan dağılımını bu etiketten hesaplar; etiket
   disiplini doğrudan rapor kalitesine yansır.

## Kategori Listesi (öneri sözlüğü)

21 konu kategorisi + 2 özel etiket. Alt kategoriler örnektir; ekip ihtiyaç
duyduğu alt kategoriyi kurallara uyarak kendisi türetir.

| # | Üst kategori | Kapsam | Alt kategori örnekleri |
|---|---|---|---|
| 1 | `hukuk` | Mevzuat, içtihat, doktrin | `hukuk-mevzuat`, `hukuk-ictihat`, `hukuk-doktrin`, `hukuk-sozlesme` |
| 2 | `tip` | Tıp ve tüm sağlık bilimleri | `tip-dahiliye`, `tip-cerrahi`, `tip-radyoloji`, `tip-pediatri`, `tip-psikiyatri`, `tip-biyokimya`, `tip-eczacilik`, `tip-dis`, `tip-hemsirelik`, `tip-fizyoterapi`, `tip-beslenme`, `tip-halk-sagligi` |
| 3 | `felsefe` | Felsefe, mantık, etik | `felsefe-etik`, `felsefe-mantik`, `felsefe-metafizik` |
| 4 | `matematik` | Matematik ve istatistik | `matematik-analiz`, `matematik-cebir`, `matematik-geometri`, `matematik-istatistik` |
| 5 | `fizik` | Fizik | `fizik-mekanik`, `fizik-astrofizik`, `fizik-kuantum` |
| 6 | `kimya` | Kimya | `kimya-organik`, `kimya-anorganik`, `kimya-biyokimya` |
| 7 | `biyoloji` | Biyoloji, çevre | `biyoloji-genetik`, `biyoloji-mikrobiyoloji`, `biyoloji-ekoloji` |
| 8 | `tarih` | Tarih | `tarih-osmanli`, `tarih-cumhuriyet`, `tarih-islam`, `tarih-dunya` |
| 9 | `cografya` | Coğrafya | `cografya-turkiye`, `cografya-dunya` |
| 10 | `edebiyat` | Edebiyat | `edebiyat-roman`, `edebiyat-siir`, `edebiyat-divan`, `edebiyat-halk`, `edebiyat-dunya` |
| 11 | `dil` | Dilbilgisi, dilbilim, sözlük, çeviri | `dil-dilbilgisi`, `dil-sozluk`, `dil-ceviri`, `dil-dilbilim` |
| 12 | `din` | Din, ilahiyat | `din-islam`, `din-ilahiyat`, `din-dinler-tarihi` |
| 13 | `egitim` | Ders kitabı tarzı eğitsel içerik | `egitim-ilkokul`, `egitim-ortaokul`, `egitim-lise`, `egitim-universite` |
| 14 | `bilisim` | Yazılım ve bilgi teknolojileri | `bilisim-yazilim`, `bilisim-yapay-zeka`, `bilisim-veritabani`, `bilisim-devops`, `bilisim-siber-guvenlik`, `bilisim-ag`, `bilisim-isletim-sistemi` |
| 15 | `muhendislik` | Fiziksel mühendislik dalları | `muhendislik-elektrik-elektronik`, `muhendislik-makine`, `muhendislik-insaat`, `muhendislik-robotik` |
| 16 | `ekonomi` | Ekonomi, finans, işletme | `ekonomi-finans`, `ekonomi-isletme`, `ekonomi-muhasebe` |
| 17 | `sosyal` | Sosyal bilimler | `sosyal-psikoloji`, `sosyal-sosyoloji`, `sosyal-antropoloji` |
| 18 | `yurttaslik` | Siyaset bilimi, kamu yönetimi | `yurttaslik-kamu-yonetimi`, `yurttaslik-uluslararasi-iliskiler` |
| 19 | `tarim` | Tarım, veterinerlik, gıda | `tarim-ziraat`, `tarim-veterinerlik`, `tarim-gida` |
| 20 | `kultur` | Kültür, sanat | `kultur-sanat`, `kultur-muzik`, `kultur-sinema`, `kultur-mutfak` |
| 21 | `spor` | Spor | `spor-futbol`, `spor-genel` |

### Özel etiketler

| Etiket | Kapsam |
|---|---|
| `mixed` | Tek bir alana indirgenemeyecek kadar çok konulu derlemeler (web crawl, genel corpus). Gardas/Faz 2 böyledir |
| `genel` | Alanı belirsiz veya önemsiz |
| `e2e` | Test/smoke kaynakları; release'e girmez |

### Kaldırılan/taşınan etiketler (2026-07-07)

- `haber` ve `konusma` alan listesinden çıkarıldı: bunlar içerik türüdür,
  `Kaynak tipi` alanına yazılır (kural 3).
- `teknoloji`, `bilisim` (bilgi teknolojileri) ve `muhendislik` (fiziksel
  mühendislik) olarak ikiye ayrıldı; PostgreSQL dokümanı artık net biçimde
  `bilisim-veritabani`dır.
- Bu değişikliklerin migration maliyeti yoktur: hiçbir mevcut kaynak bu
  etiketleri kullanmıyordu.

Yeni üst kategori ihtiyacı doğarsa (ör. `istatistik`in `matematik`ten,
`psikoloji`nin `sosyal`dan ayrılması) bu belgeye satır eklemek yeterlidir;
öneri sözlüğü olduğu için migration gerektirmez.

## Mevcut Veriler Nasıl Etkilenir?

**Hiç etkilenmez.** Nedenleri:

1. `Alan` kaynağın metadata etiketidir; dosyanın kendisine, SHA256 kimliğine,
   kapı sonuçlarına, onaylara ve release'lere dokunmaz.
2. Mevcut kaynakların etiketleri zaten doğrudur: Gardas derlemeleri `mixed`,
   örnek katkı verisi `genel`, smoke kaynakları `e2e`.
3. Bu taksonomi **ileriye dönük disiplindir**: yeni ekipler kaynaklarını
   buradaki etiketlerle kaydeder; eski kayıtlar olduğu gibi kalır.
4. Bir kaynağın etiketi ileride değişecekse editör, metadata düzenleme
   diyaloğundan değiştirir; değişiklik sürüm kontrollü ve audit kayıtlıdır.
5. Alan-özel paket ("yalnız hukuk release'i") istenirse release taslağında
   yalnız o alanın kaynakları seçilir; karışık release'te mixture raporu alan
   dağılımını zaten gösterir.
