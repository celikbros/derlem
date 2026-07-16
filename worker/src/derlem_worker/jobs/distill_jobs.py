from __future__ import annotations

import json
import os
from pathlib import Path

import psycopg

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
            with os.fdopen(descriptor, "wb") as handle:
                for document in documents:
                    handle.write(document.encode("utf-8") + b"\n")
                handle.flush()
                os.fsync(handle.fileno())

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
            }
            manifest_object = self.store.ingest_bytes(
                json.dumps(manifest, ensure_ascii=False, sort_keys=True).encode("utf-8")
            )
            result = {
                "provider": spec.key,
                "model": model,
                "document_count": len(documents),
                "manifest_sha256": manifest_object.sha256,
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
                        INSERT INTO audit_events(actor_type, action, entity_type, entity_id, details)
                        VALUES (
                            'system', 'source.distilled', 'source', %s,
                            jsonb_build_object(
                                'job_id', %s::text,
                                'provider', %s::text,
                                'model', %s::text,
                                'document_count', %s::bigint,
                                'manifest_sha256', %s::text,
                                'distillation_version', %s::text
                            )
                        )
                        """,
                        (
                            source_id,
                            str(job.id),
                            spec.key,
                            model,
                            len(documents),
                            manifest_object.sha256,
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
                    connection.execute(
                        """
                        INSERT INTO background_jobs(job_type, payload, created_by)
                        VALUES (
                            'ingest_staged_file',
                            jsonb_build_object(
                                'source_id', %s::text,
                                'staged_path', %s::text,
                                'original_filename', %s::text,
                                'uploaded_bytes', %s::bigint,
                                'distillation_job_id', %s::text
                            ),
                            %s
                        )
                        """,
                        (
                            source_id,
                            str(staged_path),
                            original_filename,
                            staged_path.stat().st_size,
                            str(job.id),
                            created_by,
                        ),
                    )
                    updated = connection.execute(
                        """
                        UPDATE background_jobs
                        SET status = 'succeeded', result = %s::jsonb,
                            completed_at = now(), updated_at = now()
                        WHERE id = %s AND status = 'running'
                          AND locked_by IS NOT DISTINCT FROM %s
                          AND attempts = %s
                        """,
                        (
                            json.dumps(result, ensure_ascii=False),
                            job.id,
                            job.lease_owner,
                            job.attempts,
                        ),
                    )
                    if updated.rowcount != 1:
                        raise JobLeaseLost(
                            f"Distillation job lease was lost during handoff: {job.id}"
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
