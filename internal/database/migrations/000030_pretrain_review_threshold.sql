-- TASK-048 (2026-10-13): pretrain inceleme kapisinda sifir tolerans yerine esik.
--
-- Esik KAYNAK satirinda durur (pretrain_review_reject_threshold, yuzde, 0-100,
-- iki ondalik). NULL = esik yok = eski sifir-tolerans davranisi, bayt bayt.
-- Yalniz content_purpose = 'pretrain' kaynakta konabilir ve ilk inceleme
-- izinden (document_reviews, reviews, acik inceleme talebi) SONRA degistirilemez:
-- "cubugu olcmeden once koy" kurali burada, tetikleyicide.
--
-- Kapi formulu (Go approvalGateReasons ve worker ile ayni):
--   sampled > 0 AND reviewed = sampled AND (
--     (approved = sampled AND flagged = 0)                       -- eski kural
--     OR (pretrain AND esik var AND approved + flagged = sampled
--         AND flagged * 100 <= esik * sampled)                   -- yeni kural
--   )
-- flagged_document_count = reddedilen + sensitive_review (refreshSourceDocumentReviewCounts).
--
-- 000024'teki uc fonksiyon (dondurma tazelik denetimi, sozlesme anlik goruntusu
-- dogrulamasi, inceleme kaniti dogrulamasi) birebir kopyalanip yalniz bu
-- noktalarda degistirildi: sayim denetimi yardimci fonksiyona, inceleme
-- kanitindaki "her ornek onayli" sarti esik kipinde "her ornek incelenmis"e.
-- Esiksiz kaynak icin her ucunun sonucu degismedi.

ALTER TABLE sources
    ADD COLUMN pretrain_review_reject_threshold numeric(5, 2),
    ADD CONSTRAINT sources_pretrain_review_reject_threshold_check CHECK (
        pretrain_review_reject_threshold IS NULL
        OR (
            content_purpose = 'pretrain'
            AND pretrain_review_reject_threshold >= 0
            AND pretrain_review_reject_threshold <= 100
        )
    );

COMMENT ON COLUMN sources.pretrain_review_reject_threshold IS
    'TASK-048: pretrain ornek incelemesinde izin verilen (ret + sensitive_review) / ornek yuzdesi. '
    'NULL = sifir tolerans. Ilk inceleme izinden sonra degismez (sources_lock_pretrain_review_threshold).';

CREATE OR REPLACE FUNCTION pretrain_review_threshold_active(
    target_content_purpose text,
    target_threshold numeric
)
RETURNS boolean
LANGUAGE sql
IMMUTABLE
SET search_path FROM CURRENT
AS $$
    SELECT target_content_purpose = 'pretrain' AND target_threshold IS NOT NULL
$$;

CREATE OR REPLACE FUNCTION source_document_review_gate_passes(
    target_content_purpose text,
    target_threshold numeric,
    sampled bigint,
    reviewed bigint,
    approved bigint,
    flagged bigint
)
RETURNS boolean
LANGUAGE sql
IMMUTABLE
SET search_path FROM CURRENT
AS $$
    SELECT COALESCE(
        sampled > 0
        AND reviewed = sampled
        AND (
            (approved = sampled AND flagged = 0)
            OR (
                pretrain_review_threshold_active(target_content_purpose, target_threshold)
                AND approved + flagged = sampled
                AND flagged::numeric * 100 <= target_threshold * sampled::numeric
            )
        ),
        false
    )
$$;

CREATE OR REPLACE FUNCTION lock_pretrain_review_threshold()
RETURNS trigger
LANGUAGE plpgsql
SET search_path FROM CURRENT
AS $$
BEGIN
    IF NEW.pretrain_review_reject_threshold IS DISTINCT FROM
       OLD.pretrain_review_reject_threshold THEN
        IF OLD.reviewed_document_count > 0
           OR EXISTS (
               SELECT 1
               FROM document_reviews AS review
               JOIN documents AS document ON document.id = review.document_id
               WHERE document.source_id = OLD.id
           )
           OR EXISTS (
               SELECT 1 FROM reviews AS review WHERE review.source_id = OLD.id
           )
           OR EXISTS (
               SELECT 1
               FROM document_review_claims AS claim
               JOIN documents AS document ON document.id = claim.document_id
               WHERE document.source_id = OLD.id
           ) THEN
            RAISE EXCEPTION 'pretrain_review_reject_threshold is locked once review has started';
        END IF;
    END IF;
    RETURN NEW;
END;
$$;

CREATE TRIGGER sources_lock_pretrain_review_threshold
BEFORE UPDATE ON sources
FOR EACH ROW EXECUTE FUNCTION lock_pretrain_review_threshold();

-- 000024 validate_release_review_evidence; degisen: threshold_mode.
CREATE OR REPLACE FUNCTION validate_release_review_evidence(
    target_source_id uuid,
    target_evidence_status text,
    target_campaign_id uuid
)
RETURNS void
LANGUAGE plpgsql
SET search_path FROM CURRENT
AS $$
DECLARE
    source_profile text;
    source_assignment text;
    source_object_sha char(64);
    current_generation integer;
    evidence_generation integer;
    generation_source_sha char(64);
    generation_status text;
    generation_sample_count integer;
    membership_evidence record;
    threshold_mode boolean;
BEGIN
    SELECT data_profile_key, profile_assignment_reason,
           object_sha256, document_sample_generation,
           pretrain_review_threshold_active(
               content_purpose, pretrain_review_reject_threshold
           )
    INTO source_profile, source_assignment, source_object_sha,
         current_generation, threshold_mode
    FROM sources WHERE id = target_source_id
    FOR UPDATE;

    evidence_generation := current_generation;

    IF target_evidence_status = 'campaign_pinned' THEN
        SELECT sample_generation INTO evidence_generation
        FROM review_campaigns
        WHERE id = target_campaign_id AND source_id = target_source_id;
        IF NOT FOUND THEN
            RAISE EXCEPTION 'release review campaign does not match source';
        END IF;
    ELSIF target_evidence_status = 'absent_pre_registry' THEN
        IF source_profile <> 'legacy-auto' OR source_assignment <> 'backfilled'
           OR target_campaign_id IS NOT NULL THEN
            RAISE EXCEPTION 'absent_pre_registry review evidence is only valid for backfilled legacy sources';
        END IF;
    ELSE
        RAISE EXCEPTION 'invalid release review evidence status';
    END IF;

    IF evidence_generation IS DISTINCT FROM current_generation THEN
        RAISE EXCEPTION 'release review evidence is not for the current sample generation';
    END IF;
    SELECT source_sha256, status, sample_count
    INTO generation_source_sha, generation_status, generation_sample_count
    FROM document_sample_generations
    WHERE source_id = target_source_id
      AND generation = evidence_generation
    FOR SHARE;
    IF NOT FOUND OR generation_status <> 'active'
       OR generation_source_sha IS DISTINCT FROM source_object_sha THEN
        RAISE EXCEPTION 'release review evidence sample generation is not current';
    END IF;
    SELECT * INTO membership_evidence
    FROM derive_document_sample_membership_evidence(
        target_source_id, evidence_generation
    );
    IF membership_evidence.membership_count IS DISTINCT FROM
           generation_sample_count THEN
        RAISE EXCEPTION 'release review evidence membership count does not match generation';
    END IF;

    IF evidence_generation <= 0 OR NOT EXISTS (
        SELECT 1 FROM documents AS document
        WHERE document.source_id = target_source_id
          AND document.sample_generation = evidence_generation
          AND document.is_active
    ) THEN
        RAISE EXCEPTION 'release review evidence has no active sample documents';
    END IF;

    IF target_evidence_status = 'absent_pre_registry' AND EXISTS (
        SELECT 1
        FROM document_reviews AS review
        LEFT JOIN document_review_reversals AS reversal
          ON reversal.review_id = review.id
        JOIN documents AS document ON document.id = review.document_id
        WHERE document.source_id = target_source_id
          AND document.sample_generation = evidence_generation
          AND document.is_active
          AND review.document_version = document.current_version
          AND review.object_sha256 = document.current_object_sha256
          AND reversal.id IS NULL
          AND review.review_campaign_id IS NOT NULL
    ) THEN
        RAISE EXCEPTION 'absent_pre_registry cannot coexist with campaign review evidence';
    END IF;

    PERFORM document.id
    FROM documents AS document
    WHERE document.source_id = target_source_id
      AND document.sample_generation = evidence_generation
      AND document.is_active
    ORDER BY document.id
    FOR SHARE;

    PERFORM review.id
    FROM document_reviews AS review
    LEFT JOIN document_review_reversals AS reversal
      ON reversal.review_id = review.id
    JOIN documents AS document ON document.id = review.document_id
    WHERE document.source_id = target_source_id
      AND document.sample_generation = evidence_generation
      AND document.is_active
      AND review.document_version = document.current_version
      AND review.object_sha256 = document.current_object_sha256
      AND reversal.id IS NULL
      AND (review.decision = 'approved' OR threshold_mode)
      AND (
          (target_evidence_status = 'campaign_pinned'
           AND review.review_campaign_id = target_campaign_id)
          OR (target_evidence_status = 'absent_pre_registry'
              AND review.review_campaign_id IS NULL)
      )
    ORDER BY review.id
    FOR UPDATE OF review;

    IF EXISTS (
        SELECT 1
        FROM documents AS document
        WHERE document.source_id = target_source_id
          AND document.sample_generation = evidence_generation
          AND document.is_active
          AND NOT EXISTS (
              SELECT 1
              FROM document_reviews AS review
              LEFT JOIN document_review_reversals AS reversal
                ON reversal.review_id = review.id
              WHERE review.document_id = document.id
                AND review.document_version = document.current_version
                AND review.object_sha256 = document.current_object_sha256
                AND reversal.id IS NULL
                AND (review.decision = 'approved' OR threshold_mode)
                AND (
                    (target_evidence_status = 'campaign_pinned'
                     AND review.review_campaign_id = target_campaign_id)
                    OR (target_evidence_status = 'absent_pre_registry'
                        AND review.review_campaign_id IS NULL)
                )
          )
    ) THEN
        RAISE EXCEPTION 'release review evidence does not cover every active sample document';
    END IF;
END;
$$;

-- 000024 validate_release_source_snapshot_fresh; degisen: sayim denetimi.
CREATE OR REPLACE FUNCTION validate_release_source_snapshot_fresh(
    target_schema text,
    target_release_id uuid,
    target_source_id uuid
)
RETURNS void
LANGUAGE plpgsql
SET search_path FROM CURRENT
AS $$
DECLARE
    source_row record;
    release_source_row record;
    snapshot_row record;
    current_license_sha char(64);
    current_lineage_sha char(64);
BEGIN
    SELECT data_profile_key, data_profile_version, content_purpose,
           profile_config_artifact_kind, profile_config_sha256,
           data_origin, production_run_id, derived_from_source_id,
           license_evidence_ref, lineage_ref, object_sha256, version, name,
           source_type, license, rights_status, language, domain,
           byte_size, line_count, approval_status, pii_status,
           duplicate_status, normalized_dedup_status,
           document_sampling_status, document_sample_generation,
           document_sampling_method, sampled_document_count,
           reviewed_document_count, approved_document_count,
           flagged_document_count, pretrain_review_reject_threshold
    INTO source_row
    FROM sources
    WHERE id = target_source_id
    FOR UPDATE;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'release snapshot source does not exist';
    END IF;

    SELECT source_sha256, source_version, source_name, source_type, license,
           rights_status, language, domain, lineage_ref, byte_size, line_count
    INTO release_source_row
    FROM release_sources
    WHERE release_id = target_release_id AND source_id = target_source_id
    FOR SHARE;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'release snapshot has no release source';
    END IF;

    SELECT data_profile_key, data_profile_version, content_purpose,
           profile_config_artifact_kind, profile_config_sha256,
           data_origin, production_run_id, derived_from_source_id,
           license_evidence_ref_sha256, lineage_ref_sha256,
           sample_generation, sample_source_sha256, sample_sampling_method,
           sample_count
    INTO snapshot_row
    FROM release_source_contract_snapshots
    WHERE release_id = target_release_id AND source_id = target_source_id;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'release source contract snapshot does not exist';
    END IF;

    IF source_row.object_sha256 IS NULL
       OR source_row.approval_status <> 'approved_source'
       OR source_row.rights_status <> 'cleared'
       OR source_row.license_evidence_ref IS NULL
       OR length(btrim(source_row.license_evidence_ref)) = 0
       OR source_row.pii_status <> 'clear'
       OR source_row.duplicate_status <> 'unique'
       OR source_row.normalized_dedup_status <> 'unique'
       OR source_row.document_sampling_status <> 'sampled'
       OR NOT source_document_review_gate_passes(
           source_row.content_purpose,
           source_row.pretrain_review_reject_threshold,
           source_row.sampled_document_count,
           source_row.reviewed_document_count,
           source_row.approved_document_count,
           source_row.flagged_document_count
       )
       OR source_row.sampled_document_count IS DISTINCT FROM
          snapshot_row.sample_count::bigint THEN
        RAISE EXCEPTION 'release source is not eligible';
    END IF;

    IF release_source_row.source_sha256 IS DISTINCT FROM source_row.object_sha256
       OR release_source_row.source_version IS DISTINCT FROM source_row.version
       OR release_source_row.source_name IS DISTINCT FROM source_row.name
       OR release_source_row.source_type IS DISTINCT FROM source_row.source_type
       OR release_source_row.license IS DISTINCT FROM source_row.license
       OR release_source_row.rights_status IS DISTINCT FROM source_row.rights_status
       OR release_source_row.language IS DISTINCT FROM source_row.language
       OR release_source_row.domain IS DISTINCT FROM source_row.domain
       OR release_source_row.lineage_ref IS DISTINCT FROM source_row.lineage_ref
       OR release_source_row.byte_size IS DISTINCT FROM source_row.byte_size
       OR release_source_row.line_count IS DISTINCT FROM source_row.line_count THEN
        RAISE EXCEPTION 'release source snapshot does not match current source';
    END IF;

    current_lineage_sha := contract_spec_artifact_sha256(
        convert_to(source_row.lineage_ref, 'UTF8')
    );
    current_license_sha := contract_spec_artifact_sha256(
        convert_to(source_row.license_evidence_ref, 'UTF8')
    );
    IF snapshot_row.data_profile_key IS DISTINCT FROM source_row.data_profile_key
       OR snapshot_row.data_profile_version IS DISTINCT FROM source_row.data_profile_version
       OR snapshot_row.content_purpose IS DISTINCT FROM source_row.content_purpose
       OR snapshot_row.profile_config_artifact_kind IS DISTINCT FROM
          source_row.profile_config_artifact_kind
       OR snapshot_row.profile_config_sha256 IS DISTINCT FROM
          source_row.profile_config_sha256
       OR snapshot_row.data_origin IS DISTINCT FROM source_row.data_origin
       OR snapshot_row.production_run_id IS DISTINCT FROM source_row.production_run_id
       OR snapshot_row.derived_from_source_id IS DISTINCT FROM
          source_row.derived_from_source_id
       OR snapshot_row.license_evidence_ref_sha256 IS DISTINCT FROM current_license_sha
       OR snapshot_row.lineage_ref_sha256 IS DISTINCT FROM current_lineage_sha
       OR snapshot_row.sample_generation IS DISTINCT FROM
          source_row.document_sample_generation
       OR snapshot_row.sample_source_sha256 IS DISTINCT FROM source_row.object_sha256
       OR snapshot_row.sample_sampling_method IS DISTINCT FROM
          source_row.document_sampling_method THEN
        RAISE EXCEPTION 'release contract snapshot source evidence is stale';
    END IF;

    PERFORM validate_source_production_provenance(
        target_schema, source_row.data_origin, source_row.production_run_id
    );
END;
$$;

-- 000024 validate_release_source_contract_snapshot; degisen: sayim denetimi.
CREATE OR REPLACE FUNCTION validate_release_source_contract_snapshot()
RETURNS trigger
LANGUAGE plpgsql
SET search_path FROM CURRENT
AS $$
DECLARE
    release_purpose text;
    release_status text;
    source_row record;
    release_source_row record;
    profile_row record;
    contract_row record;
    campaign_row record;
    generation_row record;
    membership_evidence record;
    run_row record;
    derived_license_sha char(64);
    derived_lineage_sha char(64);
    expected_sample_generation integer;
    expected_sample_source_sha char(64);
    expected_sample_sampling_method text;
    expected_sample_count integer;
    expected_sample_job_id uuid;
    expected_membership_count integer;
    expected_membership_root_sha256 char(64);
BEGIN
    SELECT content_purpose, status INTO release_purpose, release_status
    FROM releases WHERE id = NEW.release_id
    FOR UPDATE;
    IF release_status IS DISTINCT FROM 'draft' THEN
        RAISE EXCEPTION 'contract snapshots can only be added to draft releases';
    END IF;
    IF release_purpose IS DISTINCT FROM NEW.content_purpose THEN
        RAISE EXCEPTION 'release contract snapshot purpose mismatch';
    END IF;

    SELECT data_profile_key, data_profile_version, content_purpose,
           profile_config_sha256, data_origin, production_run_id,
           derived_from_source_id, license_evidence_ref, lineage_ref,
           document_sample_generation, object_sha256, version, name,
           source_type, license, rights_status, language, domain,
           byte_size, line_count, approval_status, pii_status,
           duplicate_status, normalized_dedup_status,
           document_sampling_status, document_sampling_method,
           sampled_document_count, reviewed_document_count,
           approved_document_count, flagged_document_count,
           pretrain_review_reject_threshold
    INTO source_row
    FROM sources
    WHERE id = NEW.source_id
    FOR UPDATE;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'release contract snapshot source does not exist';
    END IF;
    IF source_row.data_profile_key IS DISTINCT FROM NEW.data_profile_key
       OR source_row.data_profile_version IS DISTINCT FROM NEW.data_profile_version
       OR source_row.content_purpose IS DISTINCT FROM NEW.content_purpose
       OR source_row.profile_config_sha256 IS DISTINCT FROM NEW.profile_config_sha256 THEN
        RAISE EXCEPTION 'release contract snapshot does not match source profile';
    END IF;
    IF source_row.object_sha256 IS NULL
       OR source_row.approval_status <> 'approved_source'
       OR source_row.rights_status <> 'cleared'
       OR source_row.license_evidence_ref IS NULL
       OR length(btrim(source_row.license_evidence_ref)) = 0
       OR source_row.pii_status <> 'clear'
       OR source_row.duplicate_status <> 'unique'
       OR source_row.normalized_dedup_status <> 'unique'
       OR source_row.document_sampling_status <> 'sampled'
       OR NOT source_document_review_gate_passes(
           source_row.content_purpose,
           source_row.pretrain_review_reject_threshold,
           source_row.sampled_document_count,
           source_row.reviewed_document_count,
           source_row.approved_document_count,
           source_row.flagged_document_count
       ) THEN
        RAISE EXCEPTION 'release source is not eligible';
    END IF;

    SELECT source_sha256, source_version, source_name, source_type, license,
           rights_status, language, domain, lineage_ref, byte_size, line_count
    INTO release_source_row
    FROM release_sources
    WHERE release_id = NEW.release_id AND source_id = NEW.source_id
    FOR SHARE;
    IF NOT FOUND
       OR release_source_row.source_sha256 IS DISTINCT FROM source_row.object_sha256
       OR release_source_row.source_version IS DISTINCT FROM source_row.version
       OR release_source_row.source_name IS DISTINCT FROM source_row.name
       OR release_source_row.source_type IS DISTINCT FROM source_row.source_type
       OR release_source_row.license IS DISTINCT FROM source_row.license
       OR release_source_row.rights_status IS DISTINCT FROM source_row.rights_status
       OR release_source_row.language IS DISTINCT FROM source_row.language
       OR release_source_row.domain IS DISTINCT FROM source_row.domain
       OR release_source_row.lineage_ref IS DISTINCT FROM source_row.lineage_ref
       OR release_source_row.byte_size IS DISTINCT FROM source_row.byte_size
       OR release_source_row.line_count IS DISTINCT FROM source_row.line_count THEN
        RAISE EXCEPTION 'release source snapshot does not match current source';
    END IF;

    derived_lineage_sha := contract_spec_artifact_sha256(
        convert_to(source_row.lineage_ref, 'UTF8')
    );
    IF source_row.license_evidence_ref IS NULL THEN
        derived_license_sha := NULL;
    ELSE
        derived_license_sha := contract_spec_artifact_sha256(
            convert_to(source_row.license_evidence_ref, 'UTF8')
        );
    END IF;

    IF (NEW.data_origin IS NOT NULL
        AND NEW.data_origin IS DISTINCT FROM source_row.data_origin)
       OR (NEW.production_run_id IS NOT NULL
           AND NEW.production_run_id IS DISTINCT FROM source_row.production_run_id)
       OR (NEW.derived_from_source_id IS NOT NULL
           AND NEW.derived_from_source_id IS DISTINCT FROM source_row.derived_from_source_id)
       OR (NEW.license_evidence_ref_sha256 IS NOT NULL
           AND NEW.license_evidence_ref_sha256 IS DISTINCT FROM derived_license_sha)
       OR (NEW.lineage_ref_sha256 IS NOT NULL
           AND NEW.lineage_ref_sha256 IS DISTINCT FROM derived_lineage_sha) THEN
        RAISE EXCEPTION 'release contract snapshot provenance does not match source';
    END IF;
    NEW.data_origin := source_row.data_origin;
    NEW.production_run_id := source_row.production_run_id;
    NEW.derived_from_source_id := source_row.derived_from_source_id;
    NEW.license_evidence_ref_sha256 := derived_license_sha;
    NEW.lineage_ref_sha256 := derived_lineage_sha;

    IF source_row.production_run_id IS NULL THEN
        IF NEW.production_run_implementation_digest IS NOT NULL
           OR NEW.production_run_config_sha256 IS NOT NULL
           OR NEW.production_run_input_manifest_sha256 IS NOT NULL THEN
            RAISE EXCEPTION 'release contract snapshot has production run evidence without a run';
        END IF;
        NEW.production_run_implementation_digest := NULL;
        NEW.production_run_config_sha256 := NULL;
        NEW.production_run_input_manifest_sha256 := NULL;
    ELSE
        SELECT origin_kind, run_kind, implementation_digest,
               config_sha256, input_manifest_sha256
        INTO run_row
        FROM production_runs
        WHERE id = source_row.production_run_id;
        IF NOT FOUND THEN
            RAISE EXCEPTION 'release contract snapshot production run does not exist';
        END IF;
        IF run_row.origin_kind = 'system' THEN
            IF source_row.data_origin <> 'unknown' OR run_row.run_kind <> 'import' THEN
                RAISE EXCEPTION 'release contract snapshot source/run provenance mismatch';
            END IF;
        ELSIF run_row.origin_kind IS DISTINCT FROM source_row.data_origin
           OR (source_row.data_origin = 'human'
               AND run_row.run_kind <> 'human_authored')
           OR (source_row.data_origin = 'model'
               AND run_row.run_kind <> 'model_generation')
           OR (source_row.data_origin = 'hybrid'
               AND run_row.run_kind <> 'hybrid_generation') THEN
            RAISE EXCEPTION 'release contract snapshot source/run provenance mismatch';
        END IF;
        IF (NEW.production_run_implementation_digest IS NOT NULL
            AND NEW.production_run_implementation_digest IS DISTINCT FROM
                run_row.implementation_digest)
           OR (NEW.production_run_config_sha256 IS NOT NULL
               AND NEW.production_run_config_sha256 IS DISTINCT FROM
                   run_row.config_sha256)
           OR (NEW.production_run_input_manifest_sha256 IS NOT NULL
               AND NEW.production_run_input_manifest_sha256 IS DISTINCT FROM
                   run_row.input_manifest_sha256) THEN
            RAISE EXCEPTION 'release contract snapshot production run evidence mismatch';
        END IF;
        NEW.production_run_implementation_digest := run_row.implementation_digest;
        NEW.production_run_config_sha256 := run_row.config_sha256;
        NEW.production_run_input_manifest_sha256 := run_row.input_manifest_sha256;
    END IF;

    IF NEW.review_campaign_id IS NOT NULL THEN
        SELECT source_id, data_profile_key, data_profile_version,
               content_purpose, purpose_contract_version,
               sample_generation, sample_source_sha256,
               sample_sampling_method, sample_count, sample_job_id,
               sample_membership_count, sample_membership_root_sha256
        INTO campaign_row
        FROM review_campaigns
        WHERE id = NEW.review_campaign_id;
        IF NOT FOUND
           OR campaign_row.source_id IS DISTINCT FROM NEW.source_id
           OR campaign_row.data_profile_key IS DISTINCT FROM NEW.data_profile_key
           OR campaign_row.data_profile_version IS DISTINCT FROM NEW.data_profile_version
           OR campaign_row.content_purpose IS DISTINCT FROM NEW.content_purpose
           OR campaign_row.purpose_contract_version IS DISTINCT FROM
              NEW.purpose_contract_version THEN
            RAISE EXCEPTION 'release contract snapshot campaign mismatch';
        END IF;
        expected_sample_generation := campaign_row.sample_generation;
        expected_sample_source_sha := campaign_row.sample_source_sha256;
        expected_sample_sampling_method := campaign_row.sample_sampling_method;
        expected_sample_count := campaign_row.sample_count;
        expected_sample_job_id := campaign_row.sample_job_id;
        expected_membership_count := campaign_row.sample_membership_count;
        expected_membership_root_sha256 :=
            campaign_row.sample_membership_root_sha256;
        SELECT source_sha256, sampling_method, sample_count, job_id, status
        INTO generation_row
        FROM document_sample_generations
        WHERE source_id = NEW.source_id
          AND generation = expected_sample_generation
        FOR SHARE;
        IF NOT FOUND THEN
            RAISE EXCEPTION 'release contract snapshot campaign generation does not exist';
        END IF;
    ELSE
        expected_sample_generation := source_row.document_sample_generation;
        SELECT source_sha256, sampling_method, sample_count, job_id, status
        INTO generation_row
        FROM document_sample_generations
        WHERE source_id = NEW.source_id
          AND generation = expected_sample_generation
        FOR SHARE;
        IF NOT FOUND THEN
            RAISE EXCEPTION 'release contract snapshot sample generation does not exist';
        END IF;
        expected_sample_source_sha := generation_row.source_sha256;
        expected_sample_sampling_method := generation_row.sampling_method;
        expected_sample_count := generation_row.sample_count;
        expected_sample_job_id := generation_row.job_id;
    END IF;

    IF expected_sample_generation IS DISTINCT FROM source_row.document_sample_generation
       OR generation_row.status <> 'active'
       OR generation_row.source_sha256 IS DISTINCT FROM source_row.object_sha256
       OR expected_sample_source_sha IS DISTINCT FROM generation_row.source_sha256
       OR expected_sample_sampling_method IS DISTINCT FROM generation_row.sampling_method
       OR expected_sample_count IS DISTINCT FROM generation_row.sample_count
       OR source_row.sampled_document_count IS DISTINCT FROM
          expected_sample_count::bigint
       OR source_row.document_sampling_method IS DISTINCT FROM
          expected_sample_sampling_method
       OR expected_sample_job_id IS DISTINCT FROM generation_row.job_id THEN
        RAISE EXCEPTION 'release contract snapshot sample generation is not current';
    END IF;
    SELECT * INTO membership_evidence
    FROM derive_document_sample_membership_evidence(
        NEW.source_id, expected_sample_generation
    );
    IF membership_evidence.membership_count IS DISTINCT FROM
           generation_row.sample_count THEN
        RAISE EXCEPTION 'release contract snapshot membership count does not match generation';
    END IF;
    IF NEW.review_campaign_id IS NULL THEN
        expected_membership_count := membership_evidence.membership_count;
        expected_membership_root_sha256 :=
            membership_evidence.membership_root_sha256;
    END IF;
    IF expected_membership_count IS DISTINCT FROM membership_evidence.membership_count
       OR expected_membership_root_sha256 IS DISTINCT FROM
           membership_evidence.membership_root_sha256 THEN
        RAISE EXCEPTION 'release contract snapshot campaign membership evidence is stale';
    END IF;
    IF (NEW.sample_membership_count IS NOT NULL
        AND NEW.sample_membership_count IS DISTINCT FROM expected_membership_count)
       OR (NEW.sample_membership_root_sha256 IS NOT NULL
           AND NEW.sample_membership_root_sha256 IS DISTINCT FROM
               expected_membership_root_sha256) THEN
        RAISE EXCEPTION 'release contract snapshot membership evidence mismatch';
    END IF;

    IF (NEW.sample_generation IS NOT NULL
        AND NEW.sample_generation IS DISTINCT FROM expected_sample_generation)
       OR (NEW.sample_source_sha256 IS NOT NULL
           AND NEW.sample_source_sha256 IS DISTINCT FROM expected_sample_source_sha)
       OR (NEW.sample_sampling_method IS NOT NULL
           AND NEW.sample_sampling_method IS DISTINCT FROM expected_sample_sampling_method)
       OR (NEW.sample_count IS NOT NULL
           AND NEW.sample_count IS DISTINCT FROM expected_sample_count)
       OR (NEW.sample_job_id IS NOT NULL
           AND NEW.sample_job_id IS DISTINCT FROM expected_sample_job_id) THEN
        RAISE EXCEPTION 'release contract snapshot sample pins do not match evidence generation';
    END IF;
    NEW.sample_generation := expected_sample_generation;
    NEW.sample_source_sha256 := expected_sample_source_sha;
    NEW.sample_sampling_method := expected_sample_sampling_method;
    NEW.sample_count := expected_sample_count;
    NEW.sample_job_id := expected_sample_job_id;
    NEW.sample_membership_count := expected_membership_count;
    NEW.sample_membership_root_sha256 := expected_membership_root_sha256;

    SELECT profile_config_schema_artifact_kind,
           profile_config_schema_sha256,
           payload_schema_sha256, field_extraction_sha256,
           implementation_key, implementation_digest,
           rubric_key, rubric_version, export_contract_key,
           export_contract_version
    INTO profile_row
    FROM data_profile_versions
    WHERE data_profile_key = NEW.data_profile_key
      AND data_profile_version = NEW.data_profile_version;
    IF (NEW.profile_config_schema_artifact_kind IS NOT NULL
        AND NEW.profile_config_schema_artifact_kind IS DISTINCT FROM
            profile_row.profile_config_schema_artifact_kind)
       OR (NEW.profile_config_schema_sha256 IS NOT NULL
           AND NEW.profile_config_schema_sha256 IS DISTINCT FROM
               profile_row.profile_config_schema_sha256)
       OR profile_row.payload_schema_sha256 IS DISTINCT FROM NEW.payload_schema_sha256
       OR profile_row.field_extraction_sha256 IS DISTINCT FROM NEW.field_extraction_sha256
       OR (NEW.profile_implementation_key IS NOT NULL
           AND NEW.profile_implementation_key IS DISTINCT FROM
               profile_row.implementation_key)
       OR (NEW.profile_implementation_digest IS NOT NULL
           AND NEW.profile_implementation_digest IS DISTINCT FROM
               profile_row.implementation_digest)
       OR profile_row.rubric_key IS DISTINCT FROM NEW.rubric_key
       OR profile_row.rubric_version IS DISTINCT FROM NEW.rubric_version
       OR profile_row.export_contract_key IS DISTINCT FROM NEW.export_contract_key
       OR profile_row.export_contract_version IS DISTINCT FROM NEW.export_contract_version THEN
        RAISE EXCEPTION 'release contract snapshot does not match data profile';
    END IF;
    NEW.profile_config_schema_artifact_kind :=
        profile_row.profile_config_schema_artifact_kind;
    NEW.profile_config_schema_sha256 := profile_row.profile_config_schema_sha256;
    NEW.profile_implementation_key := profile_row.implementation_key;
    NEW.profile_implementation_digest := profile_row.implementation_digest;

    SELECT protocol_key, protocol_version,
           pii_policy_key, pii_policy_version,
           dedup_policy_key, dedup_policy_version,
           leakage_policy_key, leakage_policy_version,
           implementation_bundle_sha256
    INTO contract_row
    FROM profile_purpose_contract_versions
    WHERE data_profile_key = NEW.data_profile_key
      AND data_profile_version = NEW.data_profile_version
      AND content_purpose = NEW.content_purpose
      AND purpose_contract_version = NEW.purpose_contract_version;
    IF contract_row.protocol_key IS DISTINCT FROM NEW.protocol_key
       OR contract_row.protocol_version IS DISTINCT FROM NEW.protocol_version
       OR contract_row.pii_policy_key IS DISTINCT FROM NEW.pii_policy_key
       OR contract_row.pii_policy_version IS DISTINCT FROM NEW.pii_policy_version
       OR contract_row.dedup_policy_key IS DISTINCT FROM NEW.dedup_policy_key
       OR contract_row.dedup_policy_version IS DISTINCT FROM NEW.dedup_policy_version
       OR contract_row.leakage_policy_key IS DISTINCT FROM NEW.leakage_policy_key
       OR contract_row.leakage_policy_version IS DISTINCT FROM NEW.leakage_policy_version
       OR contract_row.implementation_bundle_sha256 IS DISTINCT FROM
          NEW.implementation_bundle_sha256 THEN
        RAISE EXCEPTION 'release contract snapshot does not match purpose contract';
    END IF;

    PERFORM validate_release_review_evidence(
        NEW.source_id, NEW.review_evidence_status, NEW.review_campaign_id
    );
    RETURN NEW;
END;
$$;

REVOKE ALL ON FUNCTION pretrain_review_threshold_active(text, numeric) FROM PUBLIC;
REVOKE ALL ON FUNCTION source_document_review_gate_passes(text, numeric, bigint, bigint, bigint, bigint) FROM PUBLIC;
REVOKE ALL ON FUNCTION lock_pretrain_review_threshold() FROM PUBLIC;
