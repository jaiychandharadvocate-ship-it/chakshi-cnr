"""
Offline tests for the OpenAI-backed LLMClient adapter.

No network: a stub client mimics the ``chat.completions.create`` surface and
returns scripted strings, so we can exercise JSON parsing, the invalid-JSON
retry, array unwrapping, fence tolerance, and a full ExtractionPipeline
round-trip — all deterministically.
"""

import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "backend"))

from intelligence import schemas as S  # noqa: E402
from intelligence.extraction import ExtractionPipeline, LLMClient  # noqa: E402
from intelligence.llm import OpenAILLMClient, build_default_llm_client  # noqa: E402

EXAMPLE = os.path.join(
    os.path.dirname(__file__), "backend", "intelligence", "example_case.json"
)


class _Msg:
    def __init__(self, content):
        self.content = content


class _Choice:
    def __init__(self, content):
        self.message = _Msg(content)


class _Resp:
    def __init__(self, content):
        self.choices = [_Choice(content)]


class StubCompletions:
    """Returns scripted contents in order; records calls."""

    def __init__(self, scripted):
        self._scripted = list(scripted)
        self.calls = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        content = self._scripted.pop(0) if self._scripted else "{}"
        return _Resp(content)


class StubChat:
    def __init__(self, scripted):
        self.completions = StubCompletions(scripted)


class StubOpenAI:
    def __init__(self, scripted):
        self.chat = StubChat(scripted)


def test_adapter_satisfies_protocol():
    client = OpenAILLMClient(StubOpenAI(["{}"]))
    assert isinstance(client, LLMClient)


def test_valid_json_first_try():
    client = OpenAILLMClient(StubOpenAI(['{"a": 1, "b": "x"}']))
    out = client.complete_json("prompt", {"type": "object"})
    assert out == {"a": 1, "b": "x"}
    # response_format json_object should be requested
    assert client.client.chat.completions.calls[0]["response_format"] == {
        "type": "json_object"
    }


def test_retry_on_invalid_then_succeeds():
    stub = StubOpenAI(["not json at all", '{"ok": true}'])
    client = OpenAILLMClient(stub, max_retries=2)
    out = client.complete_json("p", {"type": "object"})
    assert out == {"ok": True}
    assert len(stub.chat.completions.calls) == 2  # retried once


def test_gives_up_after_retries():
    stub = StubOpenAI(["nope", "still nope", "nada"])
    client = OpenAILLMClient(stub, max_retries=2)
    try:
        client.complete_json("p", {"type": "object"})
    except ValueError as exc:
        assert "valid JSON" in str(exc)
    else:
        raise AssertionError("expected ValueError after exhausting retries")


def test_array_schema_unwraps_items():
    stub = StubOpenAI(['{"items": [{"x": 1}, {"x": 2}]}'])
    client = OpenAILLMClient(stub)
    out = client.complete_json("p", {"type": "array", "items": {"type": "object"}})
    assert out == [{"x": 1}, {"x": 2}]


def test_tolerates_code_fences():
    stub = StubOpenAI(['```json\n{"a": 2}\n```'])
    client = OpenAILLMClient(stub)
    assert client.complete_json("p", {"type": "object"}) == {"a": 2}


def test_pipeline_round_trip_with_adapter():
    """ExtractionPipeline drives the real adapter against a stubbed model."""
    with open(EXAMPLE, encoding="utf-8") as fh:
        fixture = json.load(fh)
    fixture.pop("_note", None)
    stub = StubOpenAI([json.dumps(fixture)])
    pipe = ExtractionPipeline(llm=OpenAILLMClient(stub))
    doc = S.RawDocument(document_id="ILLUS-0001", doc_type="judgment", text="...")
    case = pipe.extract_case(doc)
    assert isinstance(case, S.CaseIntelligence)
    assert case.holdings[0].ratio_type == S.RatioType.RATIO
    edges = pipe.to_graph_edges(case)
    assert any(e.relation == S.GraphRelation.CITES for e in edges)


def test_build_default_returns_none_without_key(monkeypatch=None):
    for var in ("OPENAI_API_KEY_MY", "OPENAI_API_KEY"):
        os.environ.pop(var, None)
    assert build_default_llm_client() is None


def _run_all():
    tests = [v for k, v in sorted(globals().items())
             if k.startswith("test_") and callable(v)]
    for t in tests:
        t()
        print(f"  PASS  {t.__name__}")
    print(f"\n{len(tests)}/{len(tests)} LLM-adapter tests passed.")


if __name__ == "__main__":
    _run_all()
