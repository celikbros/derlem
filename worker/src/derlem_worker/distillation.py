"""Distilasyon: dış LLM sağlayıcılarından kontrollü sentetik metin üretimi.

Sağlayıcıdan bağımsız tek tip bir HTTP katmanıdır (stdlib urllib): Claude,
ChatGPT, Gemini, Grok, Qwen ve OpenAI-uyumlu diğer sağlayıcılar aynı arayüzle
çağrılır. API anahtarları YALNIZCA worker ortam değişkeninden okunur; ne
veritabanına ne üretim manifestine yazılır (yalnız değişken ADI kaydedilir).

Üretilen her belge bir satırdır; çıktı normal Derlem kapılarından (PII, dedup,
örneklem, insan incelemesi) geçer. Sentetik olmak kapı muafiyeti getirmez.
"""

from __future__ import annotations

from dataclasses import dataclass
import json
import re
from typing import Callable
import urllib.error
import urllib.request

DISTILLATION_VERSION = "distillation-v1"
_WHITESPACE_RE = re.compile(r"\s+")
DEFAULT_MAX_TOKENS = 2000
DEFAULT_TEMPERATURE = 1.0
REQUEST_TIMEOUT_SECONDS = 120


class DistillationError(RuntimeError):
    """Distilasyon üretimi başarısız oldu."""


@dataclass(frozen=True)
class ProviderSpec:
    key: str
    label: str
    style: str  # "anthropic" | "openai" | "google" | "echo"
    api_base: str
    default_model: str
    api_key_env: str


# Model kimlikleri hızlı değişir; varsayılanlar arayüzde düzenlenebilir.
PROVIDERS: dict[str, ProviderSpec] = {
    "anthropic": ProviderSpec(
        "anthropic", "Claude (Anthropic)", "anthropic",
        "https://api.anthropic.com/v1/messages", "claude-opus-4-8", "ANTHROPIC_API_KEY",
    ),
    "openai": ProviderSpec(
        "openai", "ChatGPT (OpenAI)", "openai",
        "https://api.openai.com/v1/chat/completions", "gpt-4o", "OPENAI_API_KEY",
    ),
    "google": ProviderSpec(
        "google", "Gemini (Google)", "google",
        "https://generativelanguage.googleapis.com/v1beta", "gemini-1.5-pro", "GEMINI_API_KEY",
    ),
    "xai": ProviderSpec(
        "xai", "Grok (xAI)", "openai",
        "https://api.x.ai/v1/chat/completions", "grok-2-latest", "XAI_API_KEY",
    ),
    "alibaba": ProviderSpec(
        "alibaba", "Qwen (Alibaba)", "openai",
        "https://dashscope-intl.aliyuncs.com/compatible-mode/v1/chat/completions", "qwen-plus", "DASHSCOPE_API_KEY",
    ),
    # Ağ/anahtar gerektirmeyen deterministik sağlayıcı: test ve güvenli demo için.
    "echo": ProviderSpec("echo", "Echo (test)", "echo", "", "echo", ""),
}


def _http_post_json(url: str, headers: dict[str, str], payload: dict) -> dict:
    request = urllib.request.Request(
        url, data=json.dumps(payload).encode("utf-8"), headers={"Content-Type": "application/json", **headers}, method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=REQUEST_TIMEOUT_SECONDS) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as error:
        body = error.read().decode("utf-8", errors="replace")[:500]
        raise DistillationError(f"Sağlayıcı HTTP {error.code}: {body}") from error
    except urllib.error.URLError as error:
        raise DistillationError(f"Sağlayıcıya ulaşılamadı: {error.reason}") from error


def generate_one(
    spec: ProviderSpec, model: str, api_key: str, system_prompt: str, user_prompt: str,
    *, max_tokens: int, temperature: float,
) -> str:
    if spec.style == "echo":
        head = (system_prompt.strip() + "\n") if system_prompt.strip() else ""
        return f"{head}{user_prompt.strip()}"

    if spec.style == "anthropic":
        messages = [{"role": "user", "content": user_prompt}]
        body: dict = {"model": model, "max_tokens": max_tokens, "messages": messages}
        if system_prompt.strip():
            body["system"] = system_prompt
        data = _http_post_json(
            spec.api_base,
            {"x-api-key": api_key, "anthropic-version": "2023-06-01"},
            body,
        )
        blocks = [b.get("text", "") for b in data.get("content", []) if b.get("type") == "text"]
        text = "".join(blocks)
    elif spec.style == "openai":
        messages = []
        if system_prompt.strip():
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": user_prompt})
        data = _http_post_json(
            spec.api_base,
            {"Authorization": f"Bearer {api_key}"},
            {"model": model, "messages": messages, "max_tokens": max_tokens, "temperature": temperature},
        )
        choices = data.get("choices", [])
        text = choices[0].get("message", {}).get("content", "") if choices else ""
    elif spec.style == "google":
        url = f"{spec.api_base}/models/{model}:generateContent?key={api_key}"
        body = {
            "contents": [{"role": "user", "parts": [{"text": user_prompt}]}],
            "generationConfig": {"maxOutputTokens": max_tokens, "temperature": temperature},
        }
        if system_prompt.strip():
            body["systemInstruction"] = {"parts": [{"text": system_prompt}]}
        data = _http_post_json(url, {}, body)
        candidates = data.get("candidates", [])
        parts = candidates[0].get("content", {}).get("parts", []) if candidates else []
        text = "".join(p.get("text", "") for p in parts)
    else:
        raise DistillationError(f"Desteklenmeyen sağlayıcı stili: {spec.style}")

    if not text.strip():
        raise DistillationError("Sağlayıcı boş yanıt döndürdü.")
    return text


def build_prompts(prompt_template: str, topics: list[str], count: int) -> list[str]:
    """Konu listesi verilmişse her konu için bir prompt; yoksa count kadar tekrar."""
    template = prompt_template.strip()
    if not template:
        raise DistillationError("Prompt şablonu boş olamaz.")
    cleaned_topics = [t.strip() for t in topics if t.strip()]
    if cleaned_topics:
        return [
            template.replace("{konu}", topic).replace("{topic}", topic)
            for topic in cleaned_topics
        ]
    if count < 1:
        raise DistillationError("Belge sayısı en az 1 olmalıdır.")
    return [template] * count


ProgressCallback = Callable[[dict[str, int]], None]


def distill_documents(
    spec: ProviderSpec, model: str, api_key: str, system_prompt: str, prompts: list[str],
    *, max_tokens: int, temperature: float, progress_callback: ProgressCallback | None = None,
) -> list[str]:
    documents: list[str] = []
    total = len(prompts)
    for index, prompt in enumerate(prompts, start=1):
        raw = generate_one(
            spec, model, api_key, system_prompt, prompt,
            max_tokens=max_tokens, temperature=temperature,
        )
        normalized = _WHITESPACE_RE.sub(" ", raw).strip()
        if normalized:
            documents.append(normalized)
        if progress_callback is not None:
            progress_callback({"generated": index, "total": total, "kept": len(documents)})
    if not documents:
        raise DistillationError("Hiç kullanılabilir belge üretilemedi.")
    return documents
