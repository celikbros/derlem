# Distilasyon: LLM'den Sentetik Veri Üretimi

**Durum:** v1 tamamlandı (2026-07-12). Yeniden büyüme adayları #2.

Distilasyon, dış bir LLM'e metin ürettirip çıktıyı Derlem'in kanonik akışına
sokan üretim modülüdür. "Başka modelden veri distile etme" işi artık program
içindedir; dışarıda script gerekmez.

## Desteklenen sağlayıcılar

Tek tip (sağlayıcıdan bağımsız) HTTP katmanı; istediğinizi seçersiniz:

| Sağlayıcı | Anahtar env (varsayılan) | Varsayılan model | Stil |
|---|---|---|---|
| Claude (Anthropic) | `ANTHROPIC_API_KEY` | `claude-opus-4-8` | anthropic |
| ChatGPT (OpenAI) | `OPENAI_API_KEY` | `gpt-4o` | openai |
| Gemini (Google) | `GEMINI_API_KEY` | `gemini-1.5-pro` | google |
| Grok (xAI) | `XAI_API_KEY` | `grok-2-latest` | openai-uyumlu |
| Qwen (Alibaba) | `DASHSCOPE_API_KEY` | `qwen-plus` | openai-uyumlu |
| Echo (test) | — | `echo` | ağ/anahtar gerektirmez |

Model kimlikleri hızlı değişir; arayüzdeki model kutusu düzenlenebilir —
sağlayıcının güncel model kimliğini yazabilirsiniz. Yeni bir OpenAI-uyumlu
sağlayıcı çıkarsa `PROVIDERS` sözlüğüne bir satır yeter (migration gerekmez).

## Güvenlik — API anahtarı

- **API anahtarı arayüze GİRİLMEZ.** Yalnızca anahtarı taşıyan worker ortam
  değişkeninin ADI girilir (ör. `ANTHROPIC_API_KEY`).
- Anahtar değeri ne veritabanına, ne iş yüküne, ne üretim manifestine yazılır.
  Worker, işi çalıştırırken kendi ortamından okur.
- Bu, güvenlik backlog'undaki `SEC-P0-05` (secret yönetimi) ile uyumludur;
  production'da anahtarlar secret manager'dan worker ortamına verilecektir.
- Ekleme, dış API + anahtar içeri alındığı için yeni saldırı yüzeyi doğurur;
  bu bilinçli kabuldür (yol haritası kaydı).

## Akış

1. Kaynak kaydı açılır (tip `synthetic_*`, amaç `instruction`/`pretrain`...,
   lisans `kendi-uretimimiz`, hak `cleared`, kanıt = bu belge veya üretim notu).
2. Kaynak detayında **Distilasyon** bölümü: sağlayıcı, model, anahtar env,
   sistem yönergesi, prompt şablonu (`{konu}` yer tutucusu), konular (her satır
   bir belge) veya konu yoksa belge sayısı.
3. Worker `distill_source` işi: sağlayıcıyı N kez çağırır, her çıktıyı bir belge
   (bir satır) olarak yazar, **üretim manifestini immutable depoya alır**
   (`source.distilled` audit'i + manifest SHA256), sonra dosyayı normal
   staged-ingest zincirine sokar.
4. Gerisi standarttır: PII taraması, tekrar kontrolü, risk puanlı örneklem,
   **insan incelemesi**. **Sentetik olmak kapı muafiyeti getirmez** — modelin
   ürettiği metinde de PII, tekrar veya çöp olabilir; 200 örnek yine incelenir.

## Prompt şablonu

- `{konu}` (veya `{topic}`) yer tutucusu her konuyla değiştirilir.
- Konu listesi verilmişse her konu = bir belge; boşsa şablon "belge sayısı"
  kadar tekrarlanır (sıcaklıkla çeşitlenir).
- Tek seferde en fazla 500 belge; `max_tokens` en fazla 32000.

## Sınırlar / sıradakiler

- Model kimliği doğrulaması yapılmaz; yanlış model sağlayıcıda 404 verir ve iş
  net hatayla düşer.
- Yakında: üretim manifestini kaynağın `lineage_ref`'ine otomatik bağlama,
  saf-insan havuzu için `synthetic` etiket filtresi (v0.5 katkı modeliyle),
  hız/oran sınırı ve maliyet tahmini.
