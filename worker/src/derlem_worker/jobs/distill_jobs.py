from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

import psycopg
from psycopg.rows import dict_row

from derlem_worker.distillation import (
    DISTILLATION_VERSION,
    PROVIDERS,
    DistillationError,
    build_prompts,
    distill_documents,
)
from derlem_worker.jobs.queue import Job, JobLeaseLost


class DistillJobsMixin:
    def _distill_source(self, job: Job) -> dict:
        """Dış LLM'den sentetik metin üretir, immutable manifest saklar ve
        üretilen dosyayı normal staged-ingest zincirine sokar."""
        payload = job.payload
        source_id = str(payload.get("source_id", "")).strip()
        if not source_id:
            raise ValueError("distill_source requires source_id")
        production_run_id = str(payload.get("production_run_id", "")).strip()
        if not production_run_id:
            raise DistillationError("distill_source requires production_run_id")
        provider_key = str(payload.get("provider", "")).strip()
        spec = PROVIDERS.get(provider_key)
        if spec is None:
            raise DistillationError(f"Bilinmeyen sağlayıcı: {provider_key}")
        model = str(payload.get("model") or spec.default_model).strip()
        # Credential selection is worker-owned. Never honor an environment
        # variable name carried by a job, including legacy or forged payloads.
        api_key_env = spec.api_key_env.strip()
        system_prompt = str(payload.get("system_prompt") or "")
        prompt_template = str(payload.get("prompt_template") or "")
        topics = payload.get("topics") or []
        if not isinstance(topics, list):
            topics = []
        count = int(payload.get("count") or 0)
        max_tokens = int(payload.get("max_tokens") or 2000)
        temperature = float(payload.get("temperature") or 1.0)

        self._validate_distillation_provenance(
            source_id, production_run_id, payload
        )

        api_key = ""
        if spec.style != "echo":
            if not api_key_env:
                raise DistillationError(
                    f"{spec.key} sağlayıcısı için worker anahtar eşlemesi tanımlı değil."
                )
            api_key = os.environ.get(api_key_env, "").strip()
            if not api_key:
                raise DistillationError(
                    f"{api_key_env} ortam değişkeni worker'da tanımlı değil; "
                    "API anahtarını worker ortamına ekleyin (veritabanına yazılmaz)."
                )

        prompts = build_prompts(prompt_template, [str(t) for t in topics], count)

        with psycopg.connect(self.config.database_url) as progress_connection:
            documents = distill_documents(
                spec, model, api_key, system_prompt, prompts,
                max_tokens=max_tokens, temperature=temperature,
                progress_callback=lambda progress: self._write_job_progress(
                    progress_connection, job, "distilling", progress,
                ),
            )

        staged_path: Path | None = None
        handed_off = False
        try:
            # Üretilen belgeleri satır-belge dosyasına yaz (LF).
            descriptor, staged_path = self._new_attempt_artifact(
                job, suffix=".distilled.txt"
            )
            output_digest = hashlib.sha256()
            output_byte_size = 0
            with os.fdopen(descriptor, "wb") as handle:
                for document in documents:
                    encoded = document.encode("utf-8") + b"\n"
                    handle.write(encoded)
                    output_digest.update(encoded)
                    output_byte_size += len(encoded)
                handle.flush()
                os.fsync(handle.fileno())
            output_sha256 = output_digest.hexdigest()
            output_object = self.store.ingest_file(staged_path)
            if (
                output_object.sha256 != output_sha256
                or output_object.byte_size != output_byte_size
            ):
                raise DistillationError(
                    "Distillation output changed before immutable publication"
                )

            # Üretim manifesti immutable depoya alınır; API anahtarı ASLA yazılmaz.
            manifest = {
                "distillation_version": DISTILLATION_VERSION,
                "provider": spec.key,
                "provider_style": spec.style,
                "model": model,
                "api_base": spec.api_base,
                "api_key_env": api_key_env,
                "document_count": len(documents),
                "prompt_count": len(prompts),
                "max_tokens": max_tokens,
                "temperature": temperature,
                "system_prompt": system_prompt,
                "prompt_template": prompt_template,
                "topic_count": len([t for t in topics if str(t).strip()]),
                "output_sha256": output_sha256,
                "output_byte_size": output_byte_size,
            }
            manifest_object = self.store.ingest_bytes(
                json.dumps(manifest, ensure_ascii=False, sort_keys=True).encode("utf-8")
            )
            result = {
                "provider": spec.key,
                "model": model,
                "document_count": len(documents),
                "output_record_count": len(documents),
                "manifest_sha256": manifest_object.sha256,
                "output_manifest_sha256": manifest_object.sha256,
                "production_run_id": production_run_id,
                "output_sha256": output_sha256,
                "output_byte_size": output_byte_size,
            }

            original_filename = (
                str(payload.get("source_name") or "distilled") + ".distilled.txt"
            )
            with psycopg.connect(self.config.database_url) as connection:
                with connection.transaction():
                    # Child creation and parent success are one atomic handoff.
                    # A recovered attempt cannot publish either half.
                    self._assert_job_ownership(connection, job)
                    connection.execute(
                        """
                        INSERT INTO storage_objects(sha256, storage_key, byte_size, media_type)
                        VALUES (%s, %s, %s, 'application/json')
                        ON CONFLICT (sha256) DO NOTHING
                        """,
                        (
                            manifest_object.sha256,
                            manifest_object.storage_key,
                            manifest_object.byte_size,
                        ),
                    )
                    connection.execute(
                        """
                        INSERT INTO storage_objects(sha256, storage_key, byte_size, media_type)
                        VALUES (%s, %s, %s, 'text/plain; charset=utf-8')
                        ON CONFLICT (sha256) DO NOTHING
                        """,
                        (
                            output_object.sha256,
                            output_object.storage_key,
                            output_object.byte_size,
                        ),
                    )
                    connection.execute(
                        """
                        INSERT INTO audit_events(actor_type, action, entity_type, entity_id, details)
                        VALUES (
                            'system', 'source.distilled', 'source', %s,
                            jsonb_build_object(
                                'job_id', %s::text,
                                'production_run_id', %s::text,
                                'document_count', %s::bigint,
                                'manifest_sha256', %s::text,
                                'output_sha256', %s::text,
                                'output_byte_size', %s::bigint,
                                'distillation_version', %s::text
                            )
                        )
                        """,
                        (
                            source_id,
                            str(job.id),
                            production_run_id,
                            len(documents),
                            manifest_object.sha256,
                            output_sha256,
                            output_byte_size,
                            DISTILLATION_VERSION,
                        ),
                    )
                    created_by_row = connection.execute(
                        "SELECT created_by FROM background_jobs WHERE id = %s",
                        (job.id,),
                    ).fetchone()
                    if created_by_row is None:
                        raise RuntimeError("Distillation job disappeared during handoff")
                    created_by = created_by_row[0]
                    child_job_row = connection.execute(
                        """
                        INSERT INTO background_jobs(job_type, payload, created_by)
                        VALUES (
                            'ingest_staged_file',
                            jsonb_build_object(
                                'source_id', %s::text,
                                'staged_path', %s::text,
                                'original_filename', %s::text,
                                'uploaded_bytes', %s::bigint,
                                'distillation_job_id', %s::text,
                                'production_run_id', %s::text,
                                'distillation_output_sha256', %s::text,
                                'distillation_output_byte_size', %s::bigint
                            ),
                            %s
                        )
                        RETURNING id::text
                        """,
                        (
                            source_id,
                            str(staged_path),
                            original_filename,
                            staged_path.stat().st_size,
                            str(job.id),
                            production_run_id,
                            output_sha256,
                            output_byte_size,
                            created_by,
                        ),
                    ).fetchone()
                    if child_job_row is None:
                        raise RuntimeError("Distillation ingest handoff was not created")
                    child_job_id = str(child_job_row[0])
                    result["ingest_job_id"] = child_job_id
                    updated = connection.execute(
                        """
                        UPDATE background_jobs
                        SET status = 'succeeded', result = %s::jsonb,
                            completed_at = now(), updated_at = now()
                        WHERE id = %s AND status = 'running'
                          AND locked_by IS NOT DISTINCT FROM %s
                          AND attempts = %s
                        RETURNING completed_at
                        """,
                        (
                            json.dumps(result, ensure_ascii=False),
                            job.id,
                            job.lease_owner,
                            job.attempts,
                        ),
                    )
                    completed_row = updated.fetchone()
                    if completed_row is None:
                        raise JobLeaseLost(
                            f"Distillation job lease was lost during handoff: {job.id}"
                        )
                    connection.execute(
                        """
                        INSERT INTO production_run_completions(
                            production_run_id, job_id,
                            output_manifest_sha256, output_sha256,
                            output_byte_size, output_record_count, completed_at
                        )
                        VALUES (%s, %s, %s, %s, %s, %s, %s)
                        """,
                        (
                            production_run_id,
                            job.id,
                            manifest_object.sha256,
                            output_sha256,
                            output_byte_size,
                            len(documents),
                            completed_row[0],
                        ),
                    )
            handed_off = True
            return result
        except Exception as error:
            if staged_path is not None and not handed_off:
                # A psycopg error while leaving the transaction can mean the
                # server committed but the acknowledgement was lost. Never
                # delete the child's input on that ambiguous path. The guarded
                # fail/retry transition (or stale DB-aware sweeper) removes it
                # only after proving that this attempt did not commit.
                if not isinstance(error, psycopg.Error):
                    staged_path.unlink(missing_ok=True)
            raise

    def _validate_distillation_provenance(
        self,
        source_id: str,
        production_run_id: str,
        payload: dict[str, object],
    ) -> None:
        with psycopg.connect(
            self.config.database_url, row_factory=dict_row
        ) as connection:
            evidence = connection.execute(
                """
                SELECT source.data_origin,
                    source.production_run_id::text AS source_production_run_id,
                    run.run_kind, run.origin_kind, run.implementation_key,
                    run.implementation_digest, run.config_sha256
                FROM sources AS source
                JOIN production_runs AS run ON run.id = source.production_run_id
                WHERE source.id = %s
                """,
                (source_id,),
            ).fetchone()

        expected_config_sha256 = _distillation_config_sha256(payload)
        if (
            evidence is None
            or str(evidence["source_production_run_id"]) != production_run_id
            or evidence["data_origin"] != "model"
            or evidence["run_kind"] != "model_generation"
            or evidence["origin_kind"] != "model"
            or evidence["implementation_key"] != DISTILLATION_IMPLEMENTATION_KEY
            or str(evidence["implementation_digest"])
            != DISTILLATION_IMPLEMENTATION_DIGEST
            or str(evidence["config_sha256"]) != expected_config_sha256
        ):
            raise DistillationError("distillation production provenance mismatch")


DISTILLATION_IMPLEMENTATION_KEY = "derlem.worker.distill_source.v1"
DISTILLATION_IMPLEMENTATION_CONTRACT = (
    "derlem.worker.distill_source.v1\n"
    "provider-registry-http-json\n"
    "jsonl-output"
)
DISTILLATION_IMPLEMENTATION_DIGEST = hashlib.sha256(
    DISTILLATION_IMPLEMENTATION_CONTRACT.encode("utf-8")
).hexdigest()


def _distillation_config_sha256(payload: dict[str, object]) -> str:
    temperature = float(payload.get("temperature") or 1.0)
    temperature_text = (
        str(int(temperature)) if temperature.is_integer() else repr(temperature)
    )
    config = {
        "schema_version": "derlem.distillation-config.v1",
        "provider": str(payload.get("provider") or ""),
        "model": str(payload.get("model") or ""),
        "system_prompt": str(payload.get("system_prompt") or ""),
        "prompt_template": str(payload.get("prompt_template") or ""),
        "topics": payload.get("topics") or [],
        "count": int(payload.get("count") or 0),
        "max_tokens": int(payload.get("max_tokens") or 2000),
        "temperature": temperature_text,
        "source_name": str(payload.get("source_name") or ""),
    }
    canonical_text = json.dumps(
        config, ensure_ascii=False, separators=(",", ":")
    ).replace("\u2028", "\\u2028").replace("\u2029", "\\u2029")
    canonical_bytes = canonical_text.encode("utf-8")
    return hashlib.sha256(canonical_bytes).hexdigest()
