"""
Chakshi — LLMClient adapter (live extraction)
=============================================

``extraction.py`` depends only on the :class:`~intelligence.extraction.LLMClient`
protocol — one method, ``complete_json(prompt, schema) -> dict``. This module
provides a concrete implementation over the OpenAI client the project already
wires in ``backend/app.py`` (``from openai import OpenAI``), so the refinery can
actually run against a model.

It is intentionally small and robust:

* **JSON-mode + schema in the prompt.** The model is asked to return a single
  JSON object conforming to the provided JSON Schema. The schema is embedded in
  the message so the model knows the exact field names/enums to produce.
* **Validation + retry.** If the model returns invalid JSON, the client retries
  with a terse "return valid JSON only" nudge, up to ``max_retries``.
* **Array schemas.** OpenAI JSON mode returns objects, not bare arrays, so when
  an array schema is requested the model is asked for ``{"items": [...]}`` and
  the list is unwrapped (the pipeline accepts either shape).
* **Testable.** The OpenAI client is injected, so unit tests pass a stub and
  exercise the parsing/retry logic with no network.

Provider-neutral by construction: anything exposing the same
``chat.completions.create(...)`` surface (e.g. an OpenAI-compatible gateway)
works. A different SDK (e.g. Anthropic) can be wrapped behind the same
``complete_json`` method without touching the pipeline.
"""

import json
import os
from typing import Any, Dict, List, Optional, Union


_DEFAULT_MODEL = os.getenv("CHAKSHI_EXTRACTION_MODEL", "gpt-4o-mini")
_JSON_NUDGE = (
    "Your previous reply was not valid JSON. Reply with ONE valid JSON object "
    "only — no prose, no markdown fences."
)


class OpenAILLMClient:
    """An :class:`LLMClient` backed by the OpenAI Chat Completions API.

    Parameters
    ----------
    client:
        An ``openai.OpenAI`` instance (or any object exposing the same
        ``chat.completions.create`` surface). Injected for testability.
    model:
        Model id. Defaults to ``$CHAKSHI_EXTRACTION_MODEL`` or ``gpt-4o-mini``.
    max_retries:
        How many times to re-ask on invalid JSON before giving up.
    temperature:
        Low by default — extraction wants determinism, not creativity.
    """

    def __init__(
        self,
        client: Any,
        *,
        model: str = _DEFAULT_MODEL,
        max_retries: int = 2,
        temperature: float = 0.0,
    ):
        if client is None:
            raise ValueError("OpenAILLMClient needs an OpenAI client instance.")
        self.client = client
        self.model = model
        self.max_retries = max_retries
        self.temperature = temperature

    # -- LLMClient protocol ------------------------------------------------- #
    def complete_json(
        self, prompt: str, schema: Dict[str, Any], *, system: Optional[str] = None
    ) -> Union[Dict[str, Any], List[Any]]:
        is_array = schema.get("type") == "array"
        wire_schema = (
            {"type": "object", "properties": {"items": schema}, "required": ["items"]}
            if is_array
            else schema
        )
        system_msg = (system or "You are a precise JSON-producing assistant.") + (
            "\nYou must reply with a single JSON object that conforms exactly to "
            "the provided JSON Schema. Use only the allowed enum values. Do not "
            "invent fields. Leave unknowns null/empty rather than guessing."
        )
        user_msg = (
            f"{prompt}\n\n"
            f"Return JSON conforming to this JSON Schema:\n"
            f"```json\n{json.dumps(wire_schema)}\n```"
        )
        messages = [
            {"role": "system", "content": system_msg},
            {"role": "user", "content": user_msg},
        ]

        last_err: Optional[Exception] = None
        for attempt in range(self.max_retries + 1):
            content = self._call(messages)
            try:
                data = _loads_lenient(content)
            except (json.JSONDecodeError, ValueError) as exc:
                last_err = exc
                messages.append({"role": "assistant", "content": content})
                messages.append({"role": "user", "content": _JSON_NUDGE})
                continue
            if is_array:
                if isinstance(data, list):
                    return data
                return data.get("items", data.get("issues", []))
            return data

        raise ValueError(
            f"Model did not return valid JSON after {self.max_retries + 1} attempts: "
            f"{last_err}"
        )

    # -- internals ---------------------------------------------------------- #
    def _call(self, messages: List[Dict[str, str]]) -> str:
        kwargs: Dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "temperature": self.temperature,
            "response_format": {"type": "json_object"},
        }
        try:
            resp = self.client.chat.completions.create(**kwargs)
        except TypeError:
            # Older/stub clients may not accept response_format — degrade gracefully.
            kwargs.pop("response_format", None)
            resp = self.client.chat.completions.create(**kwargs)
        return resp.choices[0].message.content or ""


def _loads_lenient(content: str) -> Any:
    """Parse JSON, tolerating accidental ```json fences or surrounding prose."""
    content = content.strip()
    if content.startswith("```"):
        content = content.strip("`")
        if content.lstrip().lower().startswith("json"):
            content = content.lstrip()[4:]
    content = content.strip()
    try:
        return json.loads(content)
    except json.JSONDecodeError:
        # last resort: grab the outermost {...} or [...]
        start = min(
            (i for i in (content.find("{"), content.find("[")) if i != -1),
            default=-1,
        )
        end = max(content.rfind("}"), content.rfind("]"))
        if start != -1 and end > start:
            return json.loads(content[start : end + 1])
        raise


def build_default_llm_client(
    *, model: str = _DEFAULT_MODEL
) -> Optional["OpenAILLMClient"]:
    """Construct an OpenAILLMClient from the environment, or None if unconfigured.

    Reuses the project's ``OPENAI_API_KEY_MY`` convention (see backend/app.py),
    falling back to the standard ``OPENAI_API_KEY``. Returns None when no key is
    set so callers can degrade gracefully instead of crashing on import.
    """
    api_key = os.getenv("OPENAI_API_KEY_MY") or os.getenv("OPENAI_API_KEY")
    if not api_key:
        return None
    try:
        from openai import OpenAI
    except ImportError:
        return None
    return OpenAILLMClient(OpenAI(api_key=api_key), model=model)


__all__ = ["OpenAILLMClient", "build_default_llm_client"]
