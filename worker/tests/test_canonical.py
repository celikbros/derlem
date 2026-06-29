from __future__ import annotations

import json
from pathlib import Path

import pytest

from derlem_worker.canonical import CanonicalSampleError, parse_canonical_sample


def test_plain_text_and_unversioned_json_are_not_canonical_samples() -> None:
    assert parse_canonical_sample("düz metin", "pretrain") is None
    assert parse_canonical_sample('{"messages":[]}', "instruction") is None


def test_conversation_preserves_structure_and_filters_private_reasoning() -> None:
    sample = {
        "schema_version": "derlem.canonical-sample.v1",
        "record_type": "conversation",
        "sample_id": "sample-1",
        "content_purpose": "instruction",
        "train_policy": "assistant_only",
        "tools": [
            {
                "name": "hava",
                "description": "Hava durumunu getirir",
                "input_schema": {
                    "type": "object",
                    "properties": {"şehir": {"type": "string"}},
                    "required": ["şehir"],
                },
                "strict": True,
            }
        ],
        "messages": [
            {"role": "user", "content": "Ankara'da hava nasıl?"},
            {
                "role": "assistant",
                "reasoning_content": "Gizli değerlendirme",
                "reasoning_visibility": "review_only",
                "tool_calls": [{"id": "call-1", "name": "hava", "arguments": {"şehir": "Ankara"}}],
            },
            {"role": "tool", "tool_call_id": "call-1", "content": '{"derece":24}'},
            {"role": "assistant", "content": "Ankara 24 derece."},
        ],
    }

    parsed = parse_canonical_sample(json.dumps(sample, ensure_ascii=False), "instruction")

    assert parsed is not None
    assert parsed.record_type == "conversation"
    assert parsed.sample_id == "sample-1"
    assert "reasoning_content" not in parsed.value["messages"][1]
    assert "Ankara'da hava nasıl?" in parsed.semantic_texts
    assert "Gizli değerlendirme" not in parsed.semantic_texts
    assert any("şehir" in text for text in parsed.semantic_texts)


def test_export_allowed_reasoning_is_preserved() -> None:
    sample = {
        "schema_version": "derlem.canonical-sample.v1",
        "record_type": "conversation",
        "sample_id": "sample-2",
        "content_purpose": "instruction",
        "messages": [
            {"role": "user", "content": "Çöz"},
            {
                "role": "assistant",
                "content": "Yanıt",
                "reasoning_content": "Yayımlanabilir gerekçe",
                "reasoning_visibility": "export_allowed",
            },
        ],
    }

    parsed = parse_canonical_sample(json.dumps(sample, ensure_ascii=False), "instruction")

    assert parsed is not None
    assert parsed.value["messages"][1]["reasoning_content"] == "Yayımlanabilir gerekçe"
    assert "Yayımlanabilir gerekçe" in parsed.semantic_texts


def test_preference_requires_two_message_branches() -> None:
    sample = {
        "schema_version": "derlem.canonical-sample.v1",
        "record_type": "preference",
        "sample_id": "pref-1",
        "content_purpose": "preference",
        "messages": [{"role": "user", "content": "Kısa cevap ver"}],
        "preference": {
            "chosen": [{"role": "assistant", "content": "Olur."}],
            "rejected": [{"role": "assistant", "content": "Çok uzun ve ilgisiz bir cevap."}],
        },
    }

    parsed = parse_canonical_sample(json.dumps(sample, ensure_ascii=False), "preference")

    assert parsed is not None
    assert parsed.record_type == "preference"
    assert parsed.value["preference"]["chosen"][0]["content"] == "Olur."


@pytest.mark.parametrize(
    ("mutation", "reason"),
    [
        ({"content_purpose": "eval"}, "content_purpose_mismatch"),
        ({"model_compatibility": ["glm"]}, "sample_unknown_fields:model_compatibility"),
    ],
)
def test_canonical_sample_rejects_purpose_mismatch_and_model_fields(
    mutation: dict[str, object],
    reason: str,
) -> None:
    sample = {
        "schema_version": "derlem.canonical-sample.v1",
        "record_type": "conversation",
        "sample_id": "sample-3",
        "content_purpose": "instruction",
        "messages": [{"role": "user", "content": "Merhaba"}],
    }
    sample.update(mutation)

    with pytest.raises(CanonicalSampleError, match=reason):
        parse_canonical_sample(json.dumps(sample), "instruction")


def test_tool_result_must_reference_a_known_call() -> None:
    sample = {
        "schema_version": "derlem.canonical-sample.v1",
        "record_type": "conversation",
        "sample_id": "sample-4",
        "content_purpose": "instruction",
        "messages": [{"role": "tool", "tool_call_id": "missing", "content": "sonuç"}],
    }

    with pytest.raises(CanonicalSampleError, match="tool_result_references_unknown_call"):
        parse_canonical_sample(json.dumps(sample), "instruction")


def test_repository_examples_follow_the_runtime_contract() -> None:
    sample_root = Path(__file__).parents[2] / "data_samples"
    examples = [
        sample_root / "example_canonical_conversations.jsonl",
        sample_root / "example_canonical_preferences.jsonl",
    ]
    parsed = []
    for example in examples:
        for line in example.read_text(encoding="utf-8").splitlines():
            parsed.append(parse_canonical_sample(line, json.loads(line)["content_purpose"]))

    assert [sample.record_type for sample in parsed if sample is not None] == [
        "conversation",
        "preference",
    ]
