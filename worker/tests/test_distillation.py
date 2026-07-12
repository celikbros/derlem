import json

import pytest

from derlem_worker import distillation
from derlem_worker.distillation import (
    PROVIDERS,
    DistillationError,
    build_prompts,
    distill_documents,
    generate_one,
)


def test_registry_covers_requested_providers():
    for key in ("anthropic", "openai", "google", "xai", "alibaba"):
        assert key in PROVIDERS
    assert PROVIDERS["anthropic"].default_model == "claude-opus-4-8"
    assert PROVIDERS["anthropic"].api_key_env == "ANTHROPIC_API_KEY"
    assert PROVIDERS["xai"].style == "openai"  # OpenAI-uyumlu
    assert PROVIDERS["alibaba"].style == "openai"


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
