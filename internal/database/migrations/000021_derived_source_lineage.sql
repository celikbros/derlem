-- Turev kaynaklarin parent iliskisini serbest bicimli source_metadata yerine
-- dogrulanabilir bir foreign key ile kaydeder. Alan create-time lineage'tir;
-- uygulama update sozlesmesi bu alani degistirmez.

-- Legacy lineage kanitini sessizce kaybetmeyiz. Anahtar mevcutsa UUID bicimi,
-- parent varligi, self-reference ve uzun cycle kontrollerinin tumu migration
-- baslamadan gecmelidir; aksi halde transaction fail-loud geri alinir.
DO $migration$
DECLARE
    invalid_uuid_count bigint;
BEGIN
    SELECT count(*)
    INTO invalid_uuid_count
    FROM sources
    WHERE source_metadata ? 'derived_from_source_id'
      AND COALESCE(btrim(source_metadata->>'derived_from_source_id'), '')
          !~* '^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$';

    IF invalid_uuid_count > 0 THEN
        RAISE EXCEPTION
            'derived_from_source_id metadata contains % invalid UUID value(s)',
            invalid_uuid_count;
    END IF;
END;
$migration$;

DO $migration$
DECLARE
    invalid_reference_count bigint;
BEGIN
    WITH candidates AS MATERIALIZED (
        SELECT
            id AS child_id,
            btrim(source_metadata->>'derived_from_source_id')::uuid AS parent_id
        FROM sources
        WHERE source_metadata ? 'derived_from_source_id'
    )
    SELECT count(*)
    INTO invalid_reference_count
    FROM candidates
    LEFT JOIN sources AS parent ON parent.id = candidates.parent_id
    WHERE parent.id IS NULL OR candidates.parent_id = candidates.child_id;

    IF invalid_reference_count > 0 THEN
        RAISE EXCEPTION
            'derived_from_source_id metadata contains % missing/self parent reference(s)',
            invalid_reference_count;
    END IF;
END;
$migration$;

DO $migration$
DECLARE
    cyclic_lineage_count bigint;
BEGIN
    WITH RECURSIVE candidates AS MATERIALIZED (
        SELECT
            id AS child_id,
            btrim(source_metadata->>'derived_from_source_id')::uuid AS parent_id
        FROM sources
        WHERE source_metadata ? 'derived_from_source_id'
    ),
    lineage_walk(origin_id, current_id, path, is_cycle) AS (
        SELECT
            child_id,
            parent_id,
            ARRAY[child_id]::uuid[],
            parent_id = child_id
        FROM candidates
        UNION ALL
        SELECT
            walk.origin_id,
            next.parent_id,
            array_append(walk.path, walk.current_id),
            next.parent_id = ANY(array_append(walk.path, walk.current_id))
        FROM lineage_walk AS walk
        JOIN candidates AS next ON next.child_id = walk.current_id
        WHERE NOT walk.is_cycle
    )
    SELECT count(DISTINCT origin_id)
    INTO cyclic_lineage_count
    FROM lineage_walk
    WHERE is_cycle;

    IF cyclic_lineage_count > 0 THEN
        RAISE EXCEPTION
            'derived_from_source_id metadata contains % cyclic lineage record(s)',
            cyclic_lineage_count;
    END IF;
END;
$migration$;

ALTER TABLE sources
    ADD COLUMN derived_from_source_id uuid,
    ADD CONSTRAINT sources_derived_from_source_id_not_self
        CHECK (derived_from_source_id IS NULL OR derived_from_source_id <> id);

-- Eski clean-candidate kayitlarinda parent id source_metadata icinde tutuldu.
-- Yukaridaki fail-loud kontroller bu noktaya yalniz gecerli, mevcut ve cycle
-- olusturmayan parent'larin ulasmasini garanti eder. MATERIALIZED CTE cast ve
-- parent join siralamasini acik tutar.
-- Bu sema backfill'i kaynak icerigi/metadata karari degildir; mevcut source
-- version ve updated_at degerlerini degistirmemek icin version trigger'i
-- ACCESS EXCLUSIVE ALTER TABLE kilidi altinda gecici olarak kapatilir.
ALTER TABLE sources DISABLE TRIGGER sources_protect_content_purpose;
ALTER TABLE sources DISABLE TRIGGER sources_set_updated_at;

WITH candidates AS MATERIALIZED (
    SELECT
        id AS child_id,
        CASE
            WHEN btrim(source_metadata->>'derived_from_source_id')
                ~* '^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$'
            THEN btrim(source_metadata->>'derived_from_source_id')::uuid
        END AS parent_id
    FROM sources
    WHERE source_metadata ? 'derived_from_source_id'
)
UPDATE sources AS child
SET derived_from_source_id = candidates.parent_id
FROM candidates
JOIN sources AS parent ON parent.id = candidates.parent_id
WHERE child.id = candidates.child_id
  AND candidates.parent_id <> candidates.child_id;

ALTER TABLE sources ENABLE TRIGGER sources_set_updated_at;
ALTER TABLE sources ENABLE TRIGGER sources_protect_content_purpose;

INSERT INTO audit_events(actor_type, action, entity_type, entity_id, details)
SELECT
    'system',
    'source.lineage_backfilled',
    'source',
    source.id,
    jsonb_build_object(
        'derived_from_source_id', source.derived_from_source_id::text,
        'origin', 'source_metadata'
    )
FROM sources AS source
WHERE source.derived_from_source_id IS NOT NULL;

ALTER TABLE sources
    ADD CONSTRAINT sources_derived_from_source_id_fkey
        FOREIGN KEY (derived_from_source_id)
        REFERENCES sources(id)
        ON DELETE RESTRICT;

CREATE INDEX sources_derived_from_source_id_idx
ON sources (derived_from_source_id)
WHERE derived_from_source_id IS NOT NULL;

CREATE OR REPLACE FUNCTION protect_source_lineage()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    IF NEW.derived_from_source_id IS DISTINCT FROM OLD.derived_from_source_id THEN
        RAISE EXCEPTION 'derived_from_source_id is immutable';
    END IF;
    RETURN NEW;
END;
$$;

CREATE TRIGGER sources_protect_derived_source_id
BEFORE UPDATE ON sources
FOR EACH ROW EXECUTE FUNCTION protect_source_lineage();
