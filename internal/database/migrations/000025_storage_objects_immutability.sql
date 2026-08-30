-- Make storage-object identities append-only and make idempotent inserts
-- compare the immutable content-addressed identity before PostgreSQL resolves
-- an ON CONFLICT clause. media_type is descriptive usage metadata rather than
-- byte identity: the first value is retained when identical bytes are reused
-- in another legitimate text/JSON context. A transaction-scoped advisory lock
-- serializes contenders for one SHA-256, including the absent-row race.

CREATE OR REPLACE FUNCTION enforce_storage_object_insert_identity()
RETURNS trigger
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog
AS $$
DECLARE
    function_schema text;
    existing_storage_key text;
    existing_byte_size bigint;
    existing_immutable boolean;
BEGIN
    SELECT namespace.nspname
    INTO function_schema
    FROM pg_catalog.pg_trigger AS trigger_def
    JOIN pg_catalog.pg_proc AS function_def
      ON function_def.oid = trigger_def.tgfoid
    JOIN pg_catalog.pg_namespace AS namespace
      ON namespace.oid = function_def.pronamespace
    WHERE trigger_def.tgrelid = TG_RELID
      AND trigger_def.tgname = TG_NAME
      AND NOT trigger_def.tgisinternal;

    IF function_schema IS NULL
       OR function_schema IS DISTINCT FROM TG_TABLE_SCHEMA
       OR TG_TABLE_NAME IS DISTINCT FROM 'storage_objects' THEN
        RAISE EXCEPTION 'storage object trigger schema mismatch for %.%',
            TG_TABLE_SCHEMA, TG_TABLE_NAME;
    END IF;

    PERFORM pg_catalog.pg_advisory_xact_lock(
        pg_catalog.hashtextextended(
            'derlem.storage_objects.sha256:' || btrim(NEW.sha256::text),
            0
        )
    );

    EXECUTE pg_catalog.format(
        'SELECT storage_key, byte_size, immutable '
        'FROM %I.storage_objects WHERE sha256 = $1',
        function_schema
    )
    INTO existing_storage_key, existing_byte_size, existing_immutable
    USING NEW.sha256;

    IF existing_storage_key IS NOT NULL
       AND (
           existing_storage_key IS DISTINCT FROM NEW.storage_key
           OR existing_byte_size IS DISTINCT FROM NEW.byte_size
           OR existing_immutable IS DISTINCT FROM NEW.immutable
       ) THEN
        -- Deliberately omit path/key values from this exception.
        RAISE EXCEPTION
            'storage object metadata conflicts with existing SHA-256 identity';
    END IF;

    RETURN NEW;
END;
$$;

CREATE OR REPLACE FUNCTION reject_storage_object_mutation()
RETURNS trigger
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog
AS $$
BEGIN
    IF TG_TABLE_NAME IS DISTINCT FROM 'storage_objects' THEN
        RAISE EXCEPTION 'storage object trigger table mismatch';
    END IF;
    RAISE EXCEPTION 'storage_objects are append-only';
END;
$$;

CREATE TRIGGER storage_objects_verify_insert_identity
BEFORE INSERT ON storage_objects
FOR EACH ROW EXECUTE FUNCTION enforce_storage_object_insert_identity();

CREATE TRIGGER storage_objects_no_update
BEFORE UPDATE ON storage_objects
FOR EACH ROW EXECUTE FUNCTION reject_storage_object_mutation();

CREATE TRIGGER storage_objects_no_delete
BEFORE DELETE ON storage_objects
FOR EACH ROW EXECUTE FUNCTION reject_storage_object_mutation();

CREATE TRIGGER storage_objects_no_truncate
BEFORE TRUNCATE ON storage_objects
FOR EACH STATEMENT EXECUTE FUNCTION reject_storage_object_mutation();

REVOKE ALL ON FUNCTION enforce_storage_object_insert_identity() FROM PUBLIC;
REVOKE ALL ON FUNCTION reject_storage_object_mutation() FROM PUBLIC;
