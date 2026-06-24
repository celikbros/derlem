# Model Prompt Format Abstraction

Bu belge GLM-5.2, DeepSeek-V4-Pro ve Kimi-K2.7-Code gibi modellerin chat
template/encoding farklari nedeniyle Veri Atolyesi veritabaninda nasil veri
tutulmasi gerektigini tanimlar.

## Karar

Veritabani herhangi bir modelin Jinja template'ine gore tasarlanmaz.

Veriler birden fazla model ailesinin egitimi, degerlendirmesi veya post-training
akislari icin yeniden kullanilabilir kalacak sekilde tasarlanir. Bir kayit
`glm-5.2-format`, `deepseek-v4-format` veya `kimi-format` olarak saklanmaz;
model bagimsiz semantik kayit olarak saklanir.

Veritabani su iki katmani ayri tutar:

1. **Kanonik veri:** conversation, message, content part, tool call, tool result,
   reasoning metadata, kaynak ve kalite bilgisi.
2. **Model render katmani:** belirli model/template/encoder ile kanonik veriden
   uretilen model-spesifik prompt string'i veya tokenized artifact.

Bu ayrim zorunludur. GLM, DeepSeek, Kimi veya baska bir model farkli ozel
tokenlar ve formatlar kullansa bile ayni kanonik veri korunur; sadece render
adapter'i degisir.

## Coklu Model Prensipleri

- Veri modeli hedef modele kilitlenmez.
- Model-spesifik ozel tokenlar, chat template metni ve renderer sonucu ana veri
  tablosuna yazilmaz.
- Veri Atolyesi model bazli "uyumludur/uyumsuzdur" onayi vermez.
- Her sample standart kanonik semantik ile etiketlenir; model egiten katman
  kendi adapter'i ile bu veriyi hedef model formatina donusturur.
- Ayni conversation sample birden fazla adapter ile render edilebilir; bu islem
  veri atolyenin ana veri modelini degistirmez.
- Render edilmis prompt birincil veri degil, turetilmis artifact'tir.
- Turetilmis artifact sha256/object uri ile izlenir; kanonik veri degismeden kalir.

## Neden

LLM'e giden girdi cogunlukla duz yazi degildir. Ornek farklar:

- GLM-5.2 template'i `messages`, `tools`, `reasoning_effort`,
  `enable_thinking`, `reasoning_content`, `tool_calls` ve `tool` rollerini
  model-spesifik token/XML benzeri bloklara render eder.
- DeepSeek-V4-Pro Jinja chat template vermek yerine OpenAI uyumlu
  `messages` yapisini model girdisine cevirmek icin ayri bir encoding katmani
  tanimlar.
- Kimi-K2.7-Code template'i text disinda image/video content part'larini,
  role `name` alanini, tool declaration ve tool call bloklarini destekler.

Sonuc: veriyi sadece `prompt_text` ve `answer_text` olarak saklamak yetersizdir.

## Kanonik Conversation Modeli

Minimum mantiksal varliklar:

```text
conversation_samples
messages
message_parts
tool_definitions
tool_calls
tool_results
prompt_renderings
model_adapters
export_profiles
```

### conversation_samples

- `sample_id`
- `content_purpose`: pretrain, instruction, preference, eval, holdout, post_training
- `task_type`
- `language`
- `domain`
- `source_id`
- `quality_status`
- `train_policy`: assistant_only, full_dialogue, no_train, eval_only
- `created_at`

### messages

- `message_id`
- `sample_id`
- `ordinal`
- `role`: system, user, assistant, tool, developer, other
- `name`
- `content_text`
- `reasoning_content`
- `reasoning_visibility`: hidden, review_only, export_allowed
- `tool_call_id`
- `metadata_json`

### message_parts

Metin disi ve parcali mesajlar icin:

- `part_id`
- `message_id`
- `ordinal`
- `part_type`: text, image, image_url, video, video_url, audio, tool_reference
- `text`
- `asset_ref`
- `mime_type`
- `metadata_json`

### tool_definitions

- `tool_id`
- `sample_id`
- `name`
- `schema_json`
- `defer_loading`
- `strict`

### tool_calls

- `tool_call_id`
- `message_id`
- `name`
- `arguments_json`
- `call_order`

### tool_results

- `tool_result_id`
- `tool_call_id`
- `message_id`
- `content_text`
- `content_json`

### model_adapters

- `adapter_id`
- `model_id`
- `provider`
- `template_kind`: jinja, python_encoder, openai_compatible, custom
- `template_ref`
- `template_sha256`
- `renderer_version`
- `notes`

### export_profiles

- `profile_id`
- `name`: canonical_messages, instruction_jsonl, preference_jsonl, eval_jsonl
- `purpose`: pretrain, instruction, preference, eval, holdout, post_training
- `schema_version`
- `required_fields`
- `notes`

Bu profil model uyumlulugu degil, verinin hangi standart export sozlesmesine
uydugunu belirtir. GLM, DeepSeek, Kimi veya baska bir hedef model bu standart
export'u kendi egitim katmaninda adapter ile donusturur.

### prompt_renderings

Bu tablo opsiyoneldir ama debug/reproducibility icin yararlidir.

- `rendering_id`
- `sample_id`
- `adapter_id`
- `render_config_json`
- `rendered_prompt_sha256`
- `rendered_prompt_object_uri`
- `token_count`
- `created_at`

Render config ornekleri:

- `add_generation_prompt`
- `enable_thinking`
- `reasoning_effort`
- `thinking_mode`
- `tools_enabled`
- `multimodal_policy`

## Export Politikasi

Veri Atolyesi model template'i uygulamak zorunda degildir, ama su iki export'u
uretebilmelidir:

1. **Kanonik JSONL export**
   - Model bagimsizdir.
   - `messages`, `message_parts`, `tools`, `tool_calls`, `tool_results`
     alanlarini tasir.

2. **Render-ready export**
   - Belirli model ailesi icin hazir metadata tasir.
   - Render islemi LLM/tokenizer ekibinde veya ayri adapter job'unda yapilir.

3. **Model-specific rendered export**
   - Sadece talep edilirse uretilir.
   - Aynı kanonik veri GLM, DeepSeek, Kimi veya Gardas adapter'lariyla farkli
     prompt string'lerine donusturulebilir.
   - Bu export yeniden uretilebilir olmalidir: adapter id, template sha256,
     renderer version ve render config zorunludur.

Model-spesifik render edilmis prompt saklanacaksa immutable object store'a
sha256 ile yazilir. DB'de buyuk prompt blob'u tutulmaz.

## DB Tasarim Sonucu

GLM-5.2 template'ine gore veritabani tasarlanmaz. Ama GLM-5.2'nin ihtiyac
duydugu yapilar kanonik modelde desteklenir:

- `reasoning_effort`
- `enable_thinking`
- `reasoning_content`
- `tools`
- `tool_calls`
- `tool_results`
- system/user/assistant/tool rolleri

DeepSeek-V4-Pro icin:

- `messages`
- `reasoning_content`
- `thinking_mode`
- Python encoder adapter kaydi

Kimi-K2.7-Code icin:

- multimodal `message_parts`
- role `name`
- tool declaration
- tool call/result baglantisi
- assistant reasoning

Bu sekilde veri platformu model degistikce veri modelini yikmaz; sadece
`model_adapters` ve render job'lari degisir.

## Pratik Sonuc

Egitim verisi hazirlarken varsayilan export kanonik JSONL olmalidir. LLM ekibi
hangi model ailesi icin egitim veya ince ayar yapacaksa ilgili adapter ile
render eder. Veri Atolyesi, ayni verinin birden fazla modele uygun kalmasini
garanti etmek icin kanonik semantigi korur ve model-spesifik formati turetilmis
artifact olarak ele alir.

Yeni bir model ciktiginda Veri Atolyesi her sample'i tekrar onaylamaz. Yeni
model icin adapter veya egitim pipeline'i, kanonik export'u okuyup hedef
formatina cevirir. Atolye tarafinda yalnizca kanonik schema/export profilinin
gecerliligi korunur.
