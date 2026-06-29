# Model Prompt Format Soyutlaması

**Kanonik şema:** `derlem.canonical-sample.v1`

**Temel karar:** Derlem veriyi GLM, DeepSeek, Kimi, Gardas veya başka bir
modelin chat template'ine göre saklamaz.

## Sorumluluk Sınırı

Akış üç katmandır:

1. **Derlem kanonik verisi**
   - Conversation, preference, mesaj rolleri, içerik parçaları, araç tanımları
     ve tool call/result bağlarını saklar.
   - İnsan review, hak, PII, dedup, lineage ve release kapılarını uygular.
2. **LLM/tokenizer ekibinin adapter katmanı**
   - Kanonik JSONL'i hedef modelin Jinja template'i, Python encoder'ı veya
     eğitim veri yükleyicisine dönüştürür.
   - Özel token, thinking modu ve generation prompt gibi kararları verir.
3. **Türetilmiş model artifact'i**
   - Render edilmiş prompt veya tokenized paket model ekibine aittir.
   - Yeniden üretilebilirlik için template SHA256, adapter sürümü ve tokenizer
     sürümü kendi manifestinde tutulur.

Yeni bir model çıktığında Derlem kayıtları yeniden onaylanmaz. Yalnızca tüketici
adapter'ı değişir.

## Kanonik Kayıt

Her kaynak tek bir değişmez `content_purpose` taşır. Bu nedenle instruction ve
preference kayıtları ayrı kaynak/shard'larda tutulur.

Ortak alanlar:

- `schema_version`: `derlem.canonical-sample.v1`
- `record_type`: `conversation` veya `preference`
- `sample_id`: kaynak içinde kararlı örnek kimliği
- `content_purpose`: kaynak ve release amacıyla birebir aynı değer
- `language`, `domain`, `task_type`: modelden bağımsız sınıflandırma
- `train_policy`: `assistant_only`, `full_dialogue`, `no_train`, `eval_only`
- `metadata`: kanonik anlamı bozmayan ek açıklamalar

Şema dosyası: `schemas/conversation_sample.schema.json`

## Mesajlar

`messages` sıralı bir dizidir. Desteklenen roller:

- `system`
- `developer`
- `user`
- `assistant`
- `tool`
- `other`

Bir mesaj düz `content` metni veya sıralı içerik parçaları taşıyabilir. İçerik
parçaları text, image/image_url, video/video_url, audio/audio_url ve
tool_reference türlerini destekler. Binary varlık ana JSON kaydına gömülmez;
`asset_ref` ile immutable nesneye bağlanır.

## Araç Sözleşmesi

Araç tanımı model fonksiyon formatına bağlı değildir:

```json
{
  "name": "hava",
  "description": "Şehir hava durumunu getirir",
  "input_schema": {
    "type": "object",
    "properties": {"şehir": {"type": "string"}},
    "required": ["şehir"]
  },
  "strict": true
}
```

Assistant mesajındaki her tool call kararlı bir `id`, araç `name` değeri ve
JSON object `arguments` taşır. `tool` rolündeki sonuç aynı kimliği
`tool_call_id` ile referans eder. Bilinmeyen araç, tekrar eden çağrı kimliği
veya karşılığı olmayan sonuç export'u bloke eder.

## Preference Kaydı

Preference kaydı ortak bağlamı `messages` altında, iki alternatifi ise
`preference.chosen` ve `preference.rejected` mesaj dizilerinde tutar. Serbest
metin etiketleri yerine aynı mesaj sözleşmesinin kullanılması, araç çağrılı ve
multimodal tercih verisinin de modelden bağımsız kalmasını sağlar.

## Reasoning Politikası

`reasoning_content` varsa `reasoning_visibility` zorunludur:

- `hidden`: kanonik export'a içerik yazılmaz.
- `review_only`: reviewer görebilir, kanonik export'a içerik yazılmaz.
- `export_allowed`: içerik kanonik export'ta korunur.

Bu alan modelin thinking token biçimini tanımlamaz. Adapter, export'a izinli
gerekçeyi hedef modelin beklediği biçime kendisi dönüştürür.

## Kabul Edilmeyen Alanlar

Kanonik kayıt şunları kabul etmez:

- `model_compatibility`
- model/provider adı
- chat template veya Jinja metni
- özel token dizileri
- render edilmiş prompt
- tokenizer sonucu veya model-spesifik token sayımı

Bu bilgiler veri kalitesini değil tüketici uygulamasını tarif eder.

## Export Davranışı

- JSONL, sample'ı `derlem.canonical-export-record.v1` zarfında değiştirmeden ve
  anahtarları deterministik sıralayarak export eder.
- Kaynak SHA256, satır sırası ve kanonik payload SHA256 `lineage` alanına eklenir.
- Kaydın `content_purpose` değeri release ile uyuşmazsa export bloke edilir.
- Yapısal conversation/preference kaydı TXT'ye indirgenmez; TXT isteği bloke edilir.
- Token tahmini yalnız kapasite planlamasıdır. Exact tokenizer sayımı tüketici
  katmanında yapılır.

Çalışan örnekler:

- `data_samples/example_canonical_conversations.jsonl`
- `data_samples/example_canonical_preferences.jsonl`

Export zarfı: `schemas/canonical_export_record.schema.json`

## Sonuç

Derlem model uyumluluğu onaylamaz; kanonik anlamı, kaliteyi ve kökeni onaylar.
LLM/tokenizer ekibi bu standardı okuyabildiği sürece aynı release birden fazla
model ailesi için yeniden veri incelemesi yapılmadan kullanılabilir.
