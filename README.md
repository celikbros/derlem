# Derlem

Derlem, Turkce merkezli ve cok dilli yapay zeka modelleri icin temiz, denetlenebilir, surumlenebilir ve yuksek sinyalli veri uretmeyi hedefleyen bir veri atolyesidir.

Bu proje "ne kadar cok metin, o kadar iyi model" varsayimi ile kurulmaz. Hedef, insanlarin web sitesi uzerinden yapilandirilmis gorevler tamamlayarak kaliteli Turkce instruction, preference, reasoning, duzeltme ve degerlendirme verisi uretmesidir.

## Iki Veri Hatti

Atolye iki farkli ama birbirine bagli veri hattindan olusur:

1. **Corpus Factory:** LLM pretraining ve tokenizer egitimi icin buyuk ham/temiz metin corpus'u toplar, temizler, dedup eder, surumler ve donmus manifest olarak teslim eder.
2. **Human Data Workshop:** instruction, preference, answer review, natural Turkish duzeltme ve eval verisi gibi daha kucuk ama yuksek sinyalli insan katkisini toplar.

Atolye LLM veya tokenizer koduna mudahale etmez. Bu ekipler, ihtiyac duyduklari veriyi Atolye'nin onayli ve surumlenmis export paketlerinden alir.

Buyuk corpus verisi veritabanina ham dosya olarak basilmaz. Ham ve temizlenmis metinler object storage / filesystem uzerinde tutulur; PostgreSQL yalnizca kaynak kaydi, kalite sinyalleri, onay durumu, denetim izi ve release metadata'si icin kullanilir.

## Temel Ilke

Ham veri coplugu degil, kalite kontrollu veri isligi.

Toplanan her katki dogrudan egitim verisi olmaz. Katkilar once otomatik filtrelerden, sonra insan incelemesinden, gerekirse uzman onayindan gecer. Bazi veriler egitimde kullanilmaz; sadece test ve degerlendirme icin ayrilir.

## Ilk MVP Gorevleri

1. Metin sadelestirme
2. Metinden soru-cevap uretme
3. Model cevabini puanlama ve duzeltme
4. Bozuk/dogal olmayan Turkceyi dogal hale getirme

## Veri Havuzlari

| Havuz | Amac |
| --- | --- |
| `raw_sources` | Orijinal kaynaklar, lisans ve sahiplik metadata'si |
| `clean_corpus_candidates` | Temizlenmis ama henuz release olmamis buyuk corpus parcalari |
| `pretraining_releases` | LLM/tokenizer ekiplerine dondurulmus corpus surumleri |
| `clean_tr_text` | Temiz genel Turkce metin |
| `instruction_answer` | Talimat-cevap egitimi |
| `preference` | Iki cevap arasinda tercih / DPO-RLHF |
| `reasoning` | Gerekceli cevap ve adim adim dusunme verisi |
| `evaluation_holdout` | Egitimde kullanilmayan test verisi |
| `sensitive_review` | Uzman kontrolu gerektiren riskli alanlar |

## Ilk Hedef

Kucuk ama guvenilir bir pilot kurmak:

- 100-500 gonullu katilimci
- 10.000 kaliteli ve onayli ornek
- Veri kalite skoru ve denetim kaydi
- Egitim havuzu ile eval havuzunun kesin ayrimi
- Ilk acik rapor: hangi veri turu ne kadar toplandi, kalite dagilimi nedir?

Buyuk corpus icin paralel ilk hedef:

- Mevcut `C:\CELIK-GARDASH` corpus manifest/gate disiplinini atolye standardi yapmak
- Her kaynak icin lisans, dil, domain, PII riski ve checksum kaydi tutmak
- Exact dedup + opsiyonel MinHash near-dedup raporu uretmek
- Tokenizer ekibine `final_corpus_manifest.json` ve canonical text view teslim etmek
- LLM ekibine manifest, checksum ve kalite raporlariyla birlikte frozen release vermek

## Ana Dokumanlar

- [docs/pretraining_data_factory.md](docs/pretraining_data_factory.md) - buyuk corpus mimarisi ve yasam dongusu
- [docs/web_app_design.md](docs/web_app_design.md) - web uygulamasi rolleri, ekranlari ve veri modeli
- [docs/web_data_atolyesi_mvp_plan.md](docs/web_data_atolyesi_mvp_plan.md) - uygulanabilir MVP plani
- [docs/model_prompt_format_abstraction.md](docs/model_prompt_format_abstraction.md) - model chat template/encoding bagimsiz veri modeli
- [docs/scalability_architecture.md](docs/scalability_architecture.md) - milyonlarca kullanici icin olceklenebilir mimari
- [docs/advisor_request_web_data_atolyesi_mvp.md](docs/advisor_request_web_data_atolyesi_mvp.md) - danisman inceleme istegi
- [docs/advisor_feedback_web_data_atolyesi_mvp.md](docs/advisor_feedback_web_data_atolyesi_mvp.md) - ic on degerlendirme notlari
- [docs/advisor_response_web_data_atolyesi_mvp.md](docs/advisor_response_web_data_atolyesi_mvp.md) - gercek danisman yaniti
- [docs/advisor_review_packet.md](docs/advisor_review_packet.md) - danismanlara sorulacak karar sorulari
- [docs/mvp_plan.md](docs/mvp_plan.md) - asamali MVP plani
- [docs/data_governance.md](docs/data_governance.md) - veri yonetisimi ve kalite kurallari

## Calisan Ilk Dilim

Depoda su anda calisan ilk kaynak katalogu dilimi bulunur:

- Go Core API: JWT auth, rol kontrolu, kaynak katalogu ve audit
- PostgreSQL: migration, metadata, release temeli ve job queue
- Python worker: SHA256, UTF-8, satir sayimi, immutable ingest ve temel PII taramasi
- Next.js arayuz: kaynak katalogu, metadata duzenleme, review kapilari ve job takibi

Yerel gelistirme ve test komutlari icin
[docs/local_development.md](docs/local_development.md) belgesine bakiniz.
API ve durum makinesi icin [docs/api_workflows.md](docs/api_workflows.md)
belgesine bakiniz.

## Neden Bu Proje?

Turkce modellerin en buyuk aciklarindan biri sadece token sayisi degil, kaliteli Turkce talimat, duzeltme, tercih ve gerekce verisinin azligidir. Bu proje, buyuk ham corpus ihtiyacini tek basina kapatmayi hedeflemez; onun yerine kucuk hacimde yuksek etki ureten veri katmanini insa eder.
