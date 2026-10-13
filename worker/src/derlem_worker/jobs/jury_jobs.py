"""``jury_sample`` isi (TASK-047): hakem orneklemesi standart kaynak kapisi.

Is yuku: ``source_id`` (zorunlu), ``seed`` (zorunlu, tamsayi), ``n`` (varsayilan
200), ``object_sha256`` (verilirse nesne degismemis olmali), ``retest``
(varsayilan true: ayni satirlarda ikinci gecis), ``rule_policy`` (varsayilan
tr-web-v3).

Akis: orneklem -> kor dosya + cevap anahtari (gecici dizinde) -> hakem (anahtar
varsa, butce on-kontrolu ve cagri basi ayirma ile) -> karar parquet'i -> nesne
deposu -> ``sources.source_metadata.quality_numbers`` + denetim olayi + is
sonucu, tek islemde. Anahtar yoksa durum ``judge_unavailable``: kor dosya ve
anahtar yine depoya girer, PII ve kural sayilari yazilir; hukumler
``python -m derlem_worker.jury score --verdicts ... --apply-db`` ile gelir.

Butce asimi (``JuryBudgetExhausted``) ve hakem hatasi kalici hatadir: yeniden
deneme ucretli cagrilari tekrarlar (worker.py bunu ``permanent`` sayar).
"""

from __future__ import annotations

import json
from pathlib import Path
import tempfile

import psycopg

from derlem_worker.jobs.queue import Job, JobLeaseLost
from derlem_worker.jury import (
    DEFAULT_RULE_POLICY,
    DEFAULT_SAMPLE_SIZE,
    BudgetLedger,
    BudgetLimits,
    JuryBudget,
    JuryError,
    anthropic_judge_caller,
    default_ledger_dir,
    draw_sample,
    load_source_context,
    prepare_run,
    publish_run_artifacts,
    record_quality_numbers,
    resolve_judge,
    rubric_text,
    run_judge,
    score_run,
)

MAX_JURY_SAMPLE_SIZE = 2000


class JuryJobsMixin:
    def _jury_sample(self, job: Job) -> dict:
        payload = job.payload
        source_id = str(payload.get("source_id", "")).strip()
        if not source_id:
            raise JuryError("jury_sample requires source_id")
        seed = payload.get("seed")
        if isinstance(seed, bool) or not isinstance(seed, int):
            raise JuryError("jury_sample requires an integer seed")
        n = payload.get("n", DEFAULT_SAMPLE_SIZE)
        if isinstance(n, bool) or not isinstance(n, int) or not 1 <= n <= MAX_JURY_SAMPLE_SIZE:
            raise JuryError(f"jury_sample n must be an integer in [1, {MAX_JURY_SAMPLE_SIZE}]")
        retest = bool(payload.get("retest", True))
        rule_policy = str(payload.get("rule_policy") or DEFAULT_RULE_POLICY)
        expected_sha256 = str(payload.get("object_sha256", "")).strip()

        with psycopg.connect(self.config.database_url) as connection:
            context = load_source_context(connection, source_id)
        if expected_sha256 and expected_sha256 != context["object_sha256"]:
            raise JuryError("Source object changed before jury sampling")
        object_path = self._stored_object_path(context["storage_key"])

        staging = self.config.staging_root.resolve()
        staging.mkdir(parents=True, exist_ok=True)
        with psycopg.connect(self.config.database_url) as progress_connection, \
                tempfile.TemporaryDirectory(prefix=f"jury-{job.id}-", dir=staging) as temp_name:
            run_dir = Path(temp_name)

            def progress(phase: str):
                return lambda values: self._write_job_progress(progress_connection, job, phase, values)

            draw = draw_sample(
                object_path,
                n=n,
                seed=seed,
                store_root=self.config.storage_root,
                max_document_bytes=self.config.max_document_bytes,
                progress_callback=progress("jury_sampling"),
            )
            run = prepare_run(
                draw, run_dir, source_id=source_id, object_sha256=context["object_sha256"],
                language=context["language"], rule_policy=rule_policy,
            )
            settings, api_key = resolve_judge()
            pass1 = pass2 = None
            cost = None
            label = None
            if api_key is not None:
                budget = JuryBudget(
                    BudgetLedger(default_ledger_dir(self.config.storage_root)),
                    BudgetLimits.from_env(),
                    # Kosu basi sayac ise baglidir, kosuya degil: bir yeniden deneme
                    # (or. tamamlama aninda DB hatasi) ayni kosu sinirini paylasir ve
                    # ucretli cagrilari ikinci kez yapamaz.
                    f"job-{job.id}",
                )
                caller = anthropic_judge_caller(settings, api_key, rubric_text())
                judged1, judged2, cost = run_judge(
                    run_dir, caller, budget, settings=settings, retest=retest, progress_callback=progress("judging"),
                )
                pass1 = judged1.verdicts
                pass2 = judged2.verdicts if judged2 is not None else None
                label = settings.label
            numbers = score_run(
                run_dir,
                pass1=pass1,
                pass2=pass2,
                judge_label=label,
                judge_model=settings.model if pass1 is not None else None,
                human=context["human"],
                population_pii=context["population_pii"],
                cost=cost,
            )
            artifacts = publish_run_artifacts(self.store, run_dir)

        result = {
            "run_id": numbers["run_id"],
            "jury_status": numbers["jury"]["status"],
            "judge_id": numbers["judge_id"],
            "sample_n": numbers["sample"]["n"],
            "population_documents": numbers["sample"]["population_documents"],
            "pii_rate": numbers["pii"]["rate"],
            "rule_drop_rate": numbers["rule"]["rate"],
            "jury_junk_rate": numbers["jury"].get("rate"),
            "decisions_sha256": (numbers.get("decisions") or {}).get("sha256"),
            "blind_sha256": numbers["blind_sha256"],
            "key_sha256": numbers["key_sha256"],
            "calls": (cost or {}).get("calls", 0),
            "estimated_usd": (cost or {}).get("estimated_usd"),
        }
        if numbers["jury"]["status"] == "judge_unavailable":
            result["next_step"] = (
                f"{settings.api_key_env} is not set in the worker: verdicts come from "
                "`python -m derlem_worker.jury score --verdicts ... --apply-db`"
            )
        with psycopg.connect(self.config.database_url) as connection:
            with connection.transaction():
                self._assert_job_ownership(connection, job)
                record_quality_numbers(
                    connection, source_id=source_id, numbers=numbers, artifacts=artifacts, actor_job_id=str(job.id),
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
                    (json.dumps(result, ensure_ascii=False), job.id, job.lease_owner, job.attempts),
                )
                if updated.rowcount != 1:
                    raise JobLeaseLost(f"Jury job lease was lost while completing: {job.id}")
        return result
