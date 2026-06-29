from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
import json
from typing import Iterable


CANONICAL_SCHEMA_VERSION = "derlem.canonical-sample.v1"
RECORD_TYPES = {"conversation", "preference"}
CONTENT_PURPOSES = {"pretrain", "instruction", "preference", "eval", "holdout", "post_training"}
MESSAGE_ROLES = {"system", "developer", "user", "assistant", "tool", "other"}
PART_TYPES = {
    "text",
    "image",
    "image_url",
    "video",
    "video_url",
    "audio",
    "audio_url",
    "tool_reference",
}
TRAIN_POLICIES = {"assistant_only", "full_dialogue", "no_train", "eval_only"}
REASONING_VISIBILITIES = {"hidden", "review_only", "export_allowed"}

TOP_LEVEL_FIELDS = {
    "schema_version",
    "record_type",
    "sample_id",
    "content_purpose",
    "task_type",
    "language",
    "domain",
    "train_policy",
    "messages",
    "tools",
    "preference",
    "metadata",
    "created_at",
    "created_by",
}
MESSAGE_FIELDS = {
    "message_id",
    "role",
    "name",
    "content",
    "reasoning_content",
    "reasoning_visibility",
    "tool_call_id",
    "tool_calls",
    "metadata",
}
PART_FIELDS = {"type", "text", "asset_ref", "url", "mime_type", "metadata"}
TOOL_FIELDS = {"name", "description", "input_schema", "strict", "defer_loading"}
TOOL_CALL_FIELDS = {"id", "name", "arguments"}
PREFERENCE_FIELDS = {"chosen", "rejected"}


class CanonicalSampleError(ValueError):
    pass


@dataclass(frozen=True)
class CanonicalSample:
    record_type: str
    sample_id: str
    value: dict[str, object]
    semantic_texts: tuple[str, ...]


def parse_canonical_sample(line: str, expected_purpose: str) -> CanonicalSample | None:
    try:
        parsed = json.loads(line)
    except json.JSONDecodeError:
        return None
    if not isinstance(parsed, dict) or "schema_version" not in parsed:
        return None
    if parsed.get("schema_version") != CANONICAL_SCHEMA_VERSION:
        raise CanonicalSampleError("unsupported_schema_version")

    _reject_unknown_fields(parsed, TOP_LEVEL_FIELDS, "sample")
    record_type = _required_string(parsed, "record_type", "sample")
    if record_type not in RECORD_TYPES:
        raise CanonicalSampleError("invalid_record_type")
    sample_id = _required_string(parsed, "sample_id", "sample")
    purpose = _required_string(parsed, "content_purpose", "sample")
    if purpose not in CONTENT_PURPOSES:
        raise CanonicalSampleError("invalid_content_purpose")
    if purpose != expected_purpose:
        raise CanonicalSampleError("content_purpose_mismatch")

    _optional_string_fields(
        parsed,
        ("task_type", "language", "domain", "created_at", "created_by"),
        "sample",
    )
    train_policy = parsed.get("train_policy")
    if train_policy is not None and train_policy not in TRAIN_POLICIES:
        raise CanonicalSampleError("invalid_train_policy")
    _optional_object(parsed, "metadata", "sample")

    value = deepcopy(parsed)
    tools, tool_texts = _validate_tools(value.get("tools", []))
    semantic_texts = list(tool_texts)

    if record_type == "conversation":
        if "preference" in value:
            raise CanonicalSampleError("conversation_has_preference")
        messages = value.get("messages")
        if not isinstance(messages, list) or not messages:
            raise CanonicalSampleError("conversation_messages_required")
        sanitized, message_texts = _validate_messages(messages, tools)
        value["messages"] = sanitized
        semantic_texts.extend(message_texts)
    else:
        if purpose != "preference":
            raise CanonicalSampleError("preference_record_requires_preference_purpose")
        context = value.get("messages", [])
        if not isinstance(context, list):
            raise CanonicalSampleError("preference_context_must_be_messages")
        preference = value.get("preference")
        if not isinstance(preference, dict):
            raise CanonicalSampleError("preference_branches_required")
        _reject_unknown_fields(preference, PREFERENCE_FIELDS, "preference")
        if set(preference) != PREFERENCE_FIELDS:
            raise CanonicalSampleError("preference_chosen_and_rejected_required")

        sanitized_context, _ = _validate_messages(context, tools, allow_empty=True)
        value["messages"] = sanitized_context
        sanitized_preference: dict[str, list[dict[str, object]]] = {}
        for branch in ("chosen", "rejected"):
            branch_messages = preference.get(branch)
            if not isinstance(branch_messages, list) or not branch_messages:
                raise CanonicalSampleError(f"preference_{branch}_required")
            combined, branch_texts = _validate_messages(context + branch_messages, tools)
            sanitized_branch = combined[len(context) :]
            sanitized_preference[branch] = sanitized_branch
            semantic_texts.extend(branch_texts)
        value["preference"] = sanitized_preference

    return CanonicalSample(
        record_type=record_type,
        sample_id=sample_id,
        value=value,
        semantic_texts=tuple(text for text in semantic_texts if text),
    )


def _validate_tools(value: object) -> tuple[set[str], list[str]]:
    if not isinstance(value, list):
        raise CanonicalSampleError("tools_must_be_array")
    names: set[str] = set()
    semantic_texts: list[str] = []
    for index, tool in enumerate(value):
        if not isinstance(tool, dict):
            raise CanonicalSampleError(f"tool_{index}_must_be_object")
        _reject_unknown_fields(tool, TOOL_FIELDS, f"tool_{index}")
        name = _required_string(tool, "name", f"tool_{index}")
        if name in names:
            raise CanonicalSampleError("duplicate_tool_name")
        names.add(name)
        input_schema = tool.get("input_schema")
        if not isinstance(input_schema, dict):
            raise CanonicalSampleError(f"tool_{index}_input_schema_required")
        for key in ("strict", "defer_loading"):
            if key in tool and not isinstance(tool[key], bool):
                raise CanonicalSampleError(f"tool_{index}_{key}_must_be_boolean")
        description = tool.get("description")
        if description is not None and (not isinstance(description, str) or not description.strip()):
            raise CanonicalSampleError(f"tool_{index}_description_must_be_string")
        semantic_texts.append(name)
        if isinstance(description, str):
            semantic_texts.append(description)
        semantic_texts.append(
            json.dumps(input_schema, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        )
    return names, semantic_texts


def _validate_messages(
    value: list[object],
    tool_names: set[str],
    *,
    allow_empty: bool = False,
) -> tuple[list[dict[str, object]], list[str]]:
    if not value and not allow_empty:
        raise CanonicalSampleError("messages_required")
    messages = deepcopy(value)
    call_ids: set[str] = set()
    result_ids: list[str] = []
    semantic_texts: list[str] = []

    for index, message in enumerate(messages):
        if not isinstance(message, dict):
            raise CanonicalSampleError(f"message_{index}_must_be_object")
        _reject_unknown_fields(message, MESSAGE_FIELDS, f"message_{index}")
        role = _required_string(message, "role", f"message_{index}")
        if role not in MESSAGE_ROLES:
            raise CanonicalSampleError(f"message_{index}_invalid_role")
        _optional_string_fields(message, ("message_id", "name"), f"message_{index}")
        _optional_object(message, "metadata", f"message_{index}")
        if isinstance(message.get("name"), str):
            semantic_texts.append(str(message["name"]))

        semantic_texts.extend(_validate_content(message.get("content"), index))
        reasoning = message.get("reasoning_content")
        visibility = message.get("reasoning_visibility")
        if reasoning is not None:
            if not isinstance(reasoning, str) or not reasoning.strip():
                raise CanonicalSampleError(f"message_{index}_reasoning_must_be_string")
            if visibility not in REASONING_VISIBILITIES:
                raise CanonicalSampleError(f"message_{index}_reasoning_visibility_required")
            if visibility == "export_allowed":
                semantic_texts.append(reasoning)
            else:
                message.pop("reasoning_content", None)
        elif visibility is not None and visibility not in REASONING_VISIBILITIES:
            raise CanonicalSampleError(f"message_{index}_invalid_reasoning_visibility")

        tool_calls = message.get("tool_calls", [])
        if not isinstance(tool_calls, list):
            raise CanonicalSampleError(f"message_{index}_tool_calls_must_be_array")
        if tool_calls and role != "assistant":
            raise CanonicalSampleError(f"message_{index}_tool_calls_require_assistant")
        for call_index, call in enumerate(tool_calls):
            if not isinstance(call, dict):
                raise CanonicalSampleError(f"message_{index}_tool_call_{call_index}_must_be_object")
            _reject_unknown_fields(call, TOOL_CALL_FIELDS, f"message_{index}_tool_call_{call_index}")
            call_id = _required_string(call, "id", f"message_{index}_tool_call_{call_index}")
            name = _required_string(call, "name", f"message_{index}_tool_call_{call_index}")
            if call_id in call_ids:
                raise CanonicalSampleError("duplicate_tool_call_id")
            if name not in tool_names:
                raise CanonicalSampleError("tool_call_references_unknown_tool")
            if not isinstance(call.get("arguments"), dict):
                raise CanonicalSampleError("tool_call_arguments_must_be_object")
            call_ids.add(call_id)
            semantic_texts.append(name)
            semantic_texts.append(
                json.dumps(call["arguments"], ensure_ascii=False, sort_keys=True, separators=(",", ":"))
            )

        tool_call_id = message.get("tool_call_id")
        if role == "tool":
            if not isinstance(tool_call_id, str) or not tool_call_id.strip():
                raise CanonicalSampleError(f"message_{index}_tool_call_id_required")
            result_ids.append(tool_call_id)
        elif tool_call_id is not None:
            raise CanonicalSampleError(f"message_{index}_tool_call_id_requires_tool_role")

    if any(call_id not in call_ids for call_id in result_ids):
        raise CanonicalSampleError("tool_result_references_unknown_call")
    return messages, semantic_texts


def _validate_content(value: object, message_index: int) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value] if value else []
    if not isinstance(value, list):
        raise CanonicalSampleError(f"message_{message_index}_invalid_content")
    semantic_texts: list[str] = []
    for part_index, part in enumerate(value):
        if not isinstance(part, dict):
            raise CanonicalSampleError(f"message_{message_index}_part_{part_index}_must_be_object")
        _reject_unknown_fields(part, PART_FIELDS, f"message_{message_index}_part_{part_index}")
        part_type = _required_string(part, "type", f"message_{message_index}_part_{part_index}")
        if part_type not in PART_TYPES:
            raise CanonicalSampleError(f"message_{message_index}_part_{part_index}_invalid_type")
        _optional_string_fields(
            part,
            ("text", "asset_ref", "url", "mime_type"),
            f"message_{message_index}_part_{part_index}",
        )
        _optional_object(part, "metadata", f"message_{message_index}_part_{part_index}")
        if part_type == "text":
            text = part.get("text")
            if not isinstance(text, str) or not text:
                raise CanonicalSampleError(f"message_{message_index}_part_{part_index}_text_required")
            semantic_texts.append(text)
        elif not any(part.get(key) for key in ("asset_ref", "url")):
            raise CanonicalSampleError(f"message_{message_index}_part_{part_index}_asset_required")
    return semantic_texts


def _required_string(value: dict[str, object], key: str, context: str) -> str:
    candidate = value.get(key)
    if not isinstance(candidate, str) or not candidate.strip():
        raise CanonicalSampleError(f"{context}_{key}_required")
    return candidate


def _optional_string_fields(value: dict[str, object], keys: Iterable[str], context: str) -> None:
    for key in keys:
        if key in value and (not isinstance(value[key], str) or not str(value[key]).strip()):
            raise CanonicalSampleError(f"{context}_{key}_must_be_string")


def _optional_object(value: dict[str, object], key: str, context: str) -> None:
    if key in value and not isinstance(value[key], dict):
        raise CanonicalSampleError(f"{context}_{key}_must_be_object")


def _reject_unknown_fields(value: dict[str, object], allowed: set[str], context: str) -> None:
    unknown = sorted(set(value) - allowed)
    if unknown:
        raise CanonicalSampleError(f"{context}_unknown_fields:{','.join(unknown)}")
