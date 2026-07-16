# Distilasyon: LLM'den Sentetik Veri Üretimi

**Durum:** v1 tamamlandı (2026-07-12). Yeniden büyüme adayları #2.

Distilasyon, dış bir LLM'e metin ürettirip çıktıyı Derlem'in kanonik akışına
sokan üretim modülüdür. "Başka modelden veri distile etme" işi artık program
içindedir; dışarıda script gerekmez.

## Desteklenen sağlayıcılar

Tek tip (sağlayıcıdan bağımsız) HTTP katmanı; istediğinizi seçersiniz:

| Sağlayıcı | Sabit worker anahtar env | Varsayılan model | Stil |
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

- **API anahtarı ve ortam değişkeni adı arayüze GİRİLMEZ.** Kullanıcı
  yalnızca allowlist'teki sağlayıcıyı seçer; worker, o sağlayıcının
  `ProviderSpec.api_key_env` sabitinden hangi anahtarı okuyacağını belirler.
- Anahtar değeri ne veritabanına, ne iş yüküne, ne üretim manifestine yazılır.
  Sabit ortam değişkeni adı yalnızca üretim manifestinde provenance olarak
  tutulur. Eski veya sahte bir iş yükündeki `api_key_env` alanı worker tarafından
  yok sayılır.
- Bu, güvenlik backlog'undaki `SEC-P0-05` (secret yönetimi) ile uyumludur;
  production'da anahtarlar secret manager'dan worker ortamına verilecektir.
- LLM anahtarlarını API/web ile paylaşılan ortam dosyasına koymayın. Systemd
  kurulumunda yalnız worker birimine enjekte edilen
  `/etc/derlem/derlem-worker.env` dosyasını kullanın. Böylece anahtarlar API/web
  process ortamına girmez; tam OS izolasyonu ayrı servis kimlikleri gerektirir.
- Ekleme, dış API + anahtar içeri alındığı için yeni saldırı yüzeyi doğurur;
  bu bilinçli kabuldür (yol haritası kaydı).

## Akış

1. Kaynak kaydı açılır (tip `synthetic_*`, amaç `instruction`/`pretrain`...,
   lisans `kendi-uretimimiz`, hak `cleared`, kanıt = bu belge veya üretim notu).
2. Kaynak detayında **Distilasyon** bölümü: sağlayıcı, model, sistem
   yönergesi, prompt şablonu (`{konu}` yer tutucusu), konular (her satır
   bir belge) veya konu yoksa belge sayısı.
3. Worker `distill_source` işi: sağlayıcıyı N kez çağırır, her çıktıyı bir belge
   (bir satır) olarak yazar, **üretim manifestini immutable depoya alır**
   (`source.distilled` audit'i + manifest SHA256), sonra child staged-ingest
   işi ile parent başarısını tek veritabanı transaction'ında atomik yayımlar.
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
- Sağlayıcı çağrıları henüz prompt başına kalıcı checkpoint/idempotency anahtarı
  kullanmaz. Geç çağrıda worker kaybı veya hata olursa retry ilk prompt'tan
  başlayabilir ve ücretli çağrıları tekrar edebilir. Production genişlemesi
  öncesinde sağlayıcı maliyet kotası, tahmin/onay kapısı ve prompt başına
  durable checkpoint zorunludur; mevcut lease parent/child veri yarışını çözer,
  dış sağlayıcı maliyetini idempotent yapmaz.
- Yakında: üretim manifestini kaynağın `lineage_ref`'ine otomatik bağlama,
  saf-insan havuzu için `synthetic` etiket filtresi (v0.5 katkı modeliyle),
  hız/oran sınırı ve maliyet tahmini.
