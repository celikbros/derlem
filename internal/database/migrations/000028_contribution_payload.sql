-- TASK-002 Faz A, S2: katki omurgasi (docs/katki_gorev_tipleri_karar_notu.md §2).
--
-- Iki kolonlu tablo (prompt, body) ucuncu bir alan tasiyamiyordu. Yeni tipler kendi
-- alanlarini payload'da tasir. Hangi anahtarlarin izinli ve zorunlu oldugunu Go
-- tarafindaki tip kayit defteri her gonderimde dogrular; DB yalniz payload'in bir
-- JSON nesnesi oldugunu ve kaba bir boyut sinirini garanti eder.
--
-- response_edit_pair: prompt = soru, body = duzeltilmis cevap (katkinin urettigi
-- metin; body'nin bos olamaz kurali gevsetilmez), payload.original_response =
-- orijinal cevap, payload.edit_note = istege bagli aciklama.
--
-- data_origin, sources.data_origin (000024) ile ayni sozlugu kullanir; model ya da
-- hybrid koken model_id ister. Katki tablosuna bilerek satir-degisim tetikleyicisi
-- EKLENMEZ (000023: payload da ham kullanici icerigidir).

ALTER TABLE contributions DROP CONSTRAINT contributions_task_type_check;
ALTER TABLE contributions ADD CONSTRAINT contributions_task_type_check
    CHECK (task_type IN ('qa_pair', 'free_text', 'response_edit_pair'));

ALTER TABLE contributions
    ADD COLUMN payload jsonb NOT NULL DEFAULT '{}'::jsonb,
    ADD COLUMN data_origin text NOT NULL DEFAULT 'human',
    ADD COLUMN model_id text;

ALTER TABLE contributions
    ADD CONSTRAINT contributions_payload_object
        CHECK (jsonb_typeof(payload) = 'object'),
    -- Kesin anahtar basina karakter sinirlari Go'dadir; bu yalniz derinlemesine
    -- savunma. 100.000 karakterlik Turkce metin UTF-8'de 200 KB'i asabilir.
    ADD CONSTRAINT contributions_payload_size
        CHECK (octet_length(payload::text) <= 1048576),
    ADD CONSTRAINT contributions_data_origin
        CHECK (data_origin IN ('unknown', 'human', 'model', 'hybrid')),
    ADD CONSTRAINT contributions_model_id_length
        CHECK (model_id IS NULL OR char_length(btrim(model_id)) BETWEEN 1 AND 200),
    ADD CONSTRAINT contributions_model_origin_requires_model_id
        CHECK (data_origin NOT IN ('model', 'hybrid') OR model_id IS NOT NULL),
    ADD CONSTRAINT contributions_edit_pair_prompt
        CHECK (task_type <> 'response_edit_pair' OR char_length(btrim(prompt)) > 0);
