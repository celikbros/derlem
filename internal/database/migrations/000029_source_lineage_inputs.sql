-- Çoklu girdi soyu (2026-09-19). derived_from_source_id tek-parent'tır; bir türev
-- kaynağın birden çok girdisi olduğunda (Faz-2 korpusu yedi ham kaynaktan üretildi)
-- o bağ kaydedilemiyordu. Normalize tekrar kapısı yalnız ataları dışarıda tuttuğu
-- için, parent'ın girdileri ve aynı parent'tan türeyen kardeş adaylar birbirini
-- "başka kaynakta kopya" sayıp karantinaya sokuyordu. Bu tablo girdi bağlarını
-- tutar; kapı artık aynı soy ailesini (atalar, girdiler, kardeşler, torunlar)
-- dışarıda tutar, ilgisiz kaynakları eskisi gibi sayar (worker gate_jobs).
--
-- Bilgi kaydıdır, sinyal değildir: satır-değişim defterine girmez (000023).

CREATE TABLE source_lineage_inputs (
    source_id uuid NOT NULL REFERENCES sources(id) ON DELETE CASCADE,
    input_source_id uuid NOT NULL REFERENCES sources(id) ON DELETE RESTRICT,
    created_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (source_id, input_source_id),
    CONSTRAINT source_lineage_inputs_not_self CHECK (source_id <> input_source_id)
);

CREATE INDEX source_lineage_inputs_input_idx ON source_lineage_inputs(input_source_id);

COMMENT ON TABLE source_lineage_inputs IS
    'Turev kaynagin girdileri (coklu parent). derived_from_source_id tek parent icindir; '
    'kapilar iki iliskiyi birlikte "soy ailesi" olarak okur.';
