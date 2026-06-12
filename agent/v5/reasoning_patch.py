"""Preserve reasoning deltas from the AI gateway.

Reasoning models (e.g. deepseek-v4-pro) stream their chain of thought in a
non-standard `reasoning` delta field. langchain-openai's converter only keeps
content / tool_calls, dropping it. This wraps the converter so reasoning text
survives into AIMessageChunk.additional_kwargs["reasoning"], which
/api/v5/stream forwards to the frontend as reasoning frames.

Targeted at langchain-openai 1.1.5 (pinned in both local and prod builds).
"""
from langchain_openai.chat_models import base as _oai_base

_PATCH_FLAG = "_v5_reasoning_patch"


def apply_reasoning_patch() -> None:
    if getattr(_oai_base._convert_delta_to_message_chunk, _PATCH_FLAG, False):
        return

    original = _oai_base._convert_delta_to_message_chunk

    def patched(_dict, default_class):
        chunk = original(_dict, default_class)
        reasoning = _dict.get("reasoning")
        if reasoning and isinstance(reasoning, str) and hasattr(chunk, "additional_kwargs"):
            chunk.additional_kwargs["reasoning"] = reasoning
        return chunk

    setattr(patched, _PATCH_FLAG, True)
    _oai_base._convert_delta_to_message_chunk = patched
