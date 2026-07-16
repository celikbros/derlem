from contextlib import contextmanager
import json
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import psycopg
import pytest

from derlem_worker import distillation
from derlem_worker.distillation import (
    PROVIDERS,
    DistillationError,
    build_prompts,
    distill_documents,
    generate_one,
)
from derlem_worker.jobs import Worker
from derlem_worker.jobs import distill_jobs
from derlem_worker.jobs.distill_jobs import DistillJobsMixin
from derlem_worker.jobs.queue import Job, JobLeaseLost


class FakeDBResult:
    def __init__(self, row=None, *, rowcount: int = 1) -> None:
        self.row = row
        self.rowcount = rowcount

    def fetchone(self):
        return self.row


class FakeDistillConnection:
    def __init__(
        self, *, parent_update_count: int = 1, parent_update_error: Exception | None = None
    ) -> None:
        self.parent_update_count = parent_update_count
        self.parent_update_error = parent_update_error
        self.in_transaction = False
        self.calls: list[tuple[str, tuple, bool]] = []
        self.rolled_back = False

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return None

    @contextmanager
    def transaction(self):
        self.in_transaction = True
        try:
            yield
        except Exception:
            self.rolled_back = True
            raise
        finally:
            self.in_transaction = False

    def execute(self, sql: str, params=()):
        self.calls.append((sql, tuple(params), self.in_transaction))
        if "SELECT 1" in sql and "FOR UPDATE" in sql:
            return FakeDBResult((1,))
        if "SELECT created_by" in sql:
            return FakeDBResult(("creator-id",))
        if "SET status = 'succeeded'" in sql:
            if self.parent_update_error is not None:
                raise self.parent_update_error
            return FakeDBResult(rowcount=self.parent_update_count)
        return FakeDBResult()


def make_distill_worker(tmp_path: Path) -> Worker:
    config = SimpleNamespace(
        database_url="postgresql://unused",
        storage_root=tmp_path / "store",
        staging_root=(tmp_path / "staging").resolve(),
    )
    config.staging_root.mkdir(parents=True)
    return Worker(config, worker_id="distill-test")


def test_registry_covers_requested_providers():
    expected_key_env = {
        "anthropic": "ANTHROPIC_API_KEY",
        "openai": "OPENAI_API_KEY",
        "google": "GEMINI_API_KEY",
        "xai": "XAI_API_KEY",
        "alibaba": "DASHSCOPE_API_KEY",
    }
    for key, api_key_env in expected_key_env.items():
        assert PROVIDERS[key].api_key_env == api_key_env
    assert PROVIDERS["anthropic"].default_model == "claude-opus-4-8"
    assert PROVIDERS["xai"].style == "openai"  # OpenAI-uyumlu
    assert PROVIDERS["alibaba"].style == "openai"


def test_worker_rejects_provider_outside_registry():
    job = Job(
        id=uuid4(), job_type="distill_source",
        payload={"source_id": "source-id", "provider": "custom"},
        attempts=1, max_attempts=3,
    )

    with pytest.raises(DistillationError, match="Bilinmeyen sağlayıcı: custom"):
        DistillJobsMixin()._distill_source(job)


def test_worker_ignores_forged_api_key_env_in_legacy_job(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.setenv("DATABASE_URL", "must-not-be-used-as-provider-key")
    job = Job(
        id=uuid4(), job_type="distill_source",
        payload={
            "source_id": "source-id",
            "provider": "anthropic",
            "api_key_env": "DATABASE_URL",
            "prompt_template": "fizik hakkında yaz",
            "count": 1,
        },
        attempts=1, max_attempts=3,
    )

    with pytest.raises(DistillationError) as captured:
        DistillJobsMixin()._distill_source(job)

    assert "ANTHROPIC_API_KEY" in str(captured.value)
    assert "DATABASE_URL" not in str(captured.value)


def test_echo_provider_needs_no_network():
    text = generate_one(
        PROVIDERS["echo"], "echo", "", "Sistem yönergesi", "Konu: fizik",
        max_tokens=100, temperature=1.0,
    )
    assert "Sistem yönergesi" in text
    assert "Konu: fizik" in text


def test_build_prompts_uses_topics_when_present():
    prompts = build_prompts("{konu} hakkında bir ders paragrafı yaz.", ["fizik", "kimya", ""], count=99)
    assert prompts == [
        "fizik hakkında bir ders paragrafı yaz.",
        "kimya hakkında bir ders paragrafı yaz.",
    ]


def test_build_prompts_repeats_when_no_topics():
    prompts = build_prompts("Rastgele bir soru yaz.", [], count=3)
    assert prompts == ["Rastgele bir soru yaz."] * 3


def test_build_prompts_rejects_empty_template():
    with pytest.raises(DistillationError):
        build_prompts("   ", ["fizik"], count=1)


def test_distill_documents_normalizes_and_reports_progress():
    events = []
    docs = distill_documents(
        PROVIDERS["echo"], "echo", "", "",
        ["satır1\n\n  satır2", "tek satır"],
        max_tokens=100, temperature=1.0,
        progress_callback=events.append,
    )
    assert docs == ["satır1 satır2", "tek satır"]
    assert events[-1] == {"generated": 2, "total": 2, "kept": 2}


def test_anthropic_request_shape(monkeypatch):
    captured = {}

    def fake_post(url, headers, payload):
        captured["url"] = url
        captured["headers"] = headers
        captured["payload"] = payload
        return {"content": [{"type": "text", "text": "üretilen metin"}]}

    monkeypatch.setattr(distillation, "_http_post_json", fake_post)
    text = generate_one(
        PROVIDERS["anthropic"], "claude-opus-4-8", "secret-key",
        "Sen bir öğretmensin.", "Fizik konusu yaz.",
        max_tokens=1500, temperature=1.0,
    )
    assert text == "üretilen metin"
    assert captured["url"] == "https://api.anthropic.com/v1/messages"
    assert captured["headers"]["x-api-key"] == "secret-key"
    assert captured["headers"]["anthropic-version"] == "2023-06-01"
    assert captured["payload"]["model"] == "claude-opus-4-8"
    assert captured["payload"]["system"] == "Sen bir öğretmensin."
    assert captured["payload"]["messages"][0]["role"] == "user"


def test_openai_request_shape(monkeypatch):
    captured = {}

    def fake_post(url, headers, payload):
        captured.update(url=url, headers=headers, payload=payload)
        return {"choices": [{"message": {"content": "cevap"}}]}

    monkeypatch.setattr(distillation, "_http_post_json", fake_post)
    text = generate_one(
        PROVIDERS["openai"], "gpt-4o", "sk-test", "sistem", "kullanıcı",
        max_tokens=1000, temperature=0.7,
    )
    assert text == "cevap"
    assert captured["headers"]["Authorization"] == "Bearer sk-test"
    assert captured["payload"]["messages"][0] == {"role": "system", "content": "sistem"}
    assert captured["payload"]["messages"][1] == {"role": "user", "content": "kullanıcı"}
    assert captured["payload"]["max_tokens"] == 1000


def test_google_request_shape(monkeypatch):
    captured = {}

    def fake_post(url, headers, payload):
        captured.update(url=url, headers=headers, payload=payload)
        return {"candidates": [{"content": {"parts": [{"text": "gemini metni"}]}}]}

    monkeypatch.setattr(distillation, "_http_post_json", fake_post)
    text = generate_one(
        PROVIDERS["google"], "gemini-1.5-pro", "AIza-key", "sistem", "istem",
        max_tokens=800, temperature=0.9,
    )
    assert text == "gemini metni"
    assert "models/gemini-1.5-pro:generateContent?key=AIza-key" in captured["url"]
    assert captured["payload"]["systemInstruction"]["parts"][0]["text"] == "sistem"
    assert captured["payload"]["contents"][0]["parts"][0]["text"] == "istem"


def test_empty_provider_response_raises(monkeypatch):
    monkeypatch.setattr(distillation, "_http_post_json", lambda *a, **k: {"content": []})
    with pytest.raises(DistillationError):
        generate_one(
            PROVIDERS["anthropic"], "claude-opus-4-8", "k", "", "x",
            max_tokens=10, temperature=1.0,
        )


def test_manifest_never_contains_api_key():
    # Manifest üretim mantığının anahtar İSMİNİ tuttuğunu, değerini tutmadığını doğrular.
    manifest = {
        "provider": "anthropic",
        "api_key_env": "ANTHROPIC_API_KEY",
        "model": "claude-opus-4-8",
    }
    serialized = json.dumps(manifest)
    assert "ANTHROPIC_API_KEY" in serialized  # yalnız değişken adı
    assert "sk-" not in serialized  # anahtar değeri yok


def test_distillation_child_handoff_and_parent_success_are_atomic(
    tmp_path: Path, monkeypatch
) -> None:
    worker = make_distill_worker(tmp_path)
    job = Job(
        uuid4(),
        "distill_source",
        {
            "source_id": str(uuid4()),
            "provider": "echo",
            "prompt_template": "fizik hakkında yaz",
            "count": 1,
            "source_name": "sentetik",
        },
        1,
        3,
        "distill-test",
    )
    progress = FakeDistillConnection()
    publish = FakeDistillConnection()
    connections = iter([progress, publish])
    monkeypatch.setattr(
        distill_jobs.psycopg,
        "connect",
        lambda *_args, **_kwargs: next(connections),
    )
    monkeypatch.setattr(
        distill_jobs,
        "distill_documents",
        lambda *_args, **_kwargs: ["üretilen belge"],
    )

    result = worker._distill_source(job)

    child_calls = [call for call in publish.calls if "'ingest_staged_file'" in call[0]]
    parent_calls = [call for call in publish.calls if "SET status = 'succeeded'" in call[0]]
    assert len(child_calls) == len(parent_calls) == 1
    assert child_calls[0][2] is True
    assert parent_calls[0][2] is True
    parent_sql, parent_params, _ = parent_calls[0]
    assert "locked_by IS NOT DISTINCT FROM %s" in parent_sql
    assert "attempts = %s" in parent_sql
    assert parent_params[-2:] == ("distill-test", 1)
    staged_path = Path(child_calls[0][1][1])
    assert staged_path.exists()
    assert f"job-{job.id}-attempt-1-" in staged_path.name
    assert result["document_count"] == 1
    staged_path.unlink()


def test_lost_distillation_lease_rolls_back_handoff_and_removes_stage(
    tmp_path: Path, monkeypatch
) -> None:
    worker = make_distill_worker(tmp_path)
    job = Job(
        uuid4(),
        "distill_source",
        {
            "source_id": str(uuid4()),
            "provider": "echo",
            "prompt_template": "kimya hakkında yaz",
            "count": 1,
        },
        2,
        3,
        "expired-worker",
    )
    progress = FakeDistillConnection()
    publish = FakeDistillConnection(parent_update_count=0)
    connections = iter([progress, publish])
    monkeypatch.setattr(
        distill_jobs.psycopg,
        "connect",
        lambda *_args, **_kwargs: next(connections),
    )
    monkeypatch.setattr(
        distill_jobs,
        "distill_documents",
        lambda *_args, **_kwargs: ["üretilen belge"],
    )

    with pytest.raises(JobLeaseLost):
        worker._distill_source(job)

    assert publish.rolled_back is True
    assert list(worker.config.staging_root.glob(f"job-{job.id}-attempt-2-*")) == []


def test_ambiguous_database_commit_error_preserves_child_input(
    tmp_path: Path, monkeypatch
) -> None:
    worker = make_distill_worker(tmp_path)
    job = Job(
        uuid4(),
        "distill_source",
        {
            "source_id": str(uuid4()),
            "provider": "echo",
            "prompt_template": "biyoloji hakkında yaz",
            "count": 1,
        },
        1,
        3,
        "worker",
    )
    progress = FakeDistillConnection()
    publish = FakeDistillConnection(
        parent_update_error=psycopg.OperationalError("commit acknowledgement lost")
    )
    connections = iter([progress, publish])
    monkeypatch.setattr(
        distill_jobs.psycopg,
        "connect",
        lambda *_args, **_kwargs: next(connections),
    )
    monkeypatch.setattr(
        distill_jobs,
        "distill_documents",
        lambda *_args, **_kwargs: ["üretilen belge"],
    )

    with pytest.raises(psycopg.OperationalError, match="acknowledgement"):
        worker._distill_source(job)

    staged = list(worker.config.staging_root.glob(f"job-{job.id}-attempt-1-*"))
    assert len(staged) == 1
    staged[0].unlink()
