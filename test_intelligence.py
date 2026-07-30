"""
Validation tests for the Chakshi intelligence layer.

Runnable directly (`python test_intelligence.py`) or under pytest. No network,
no LLM, no DB — these confirm the data contracts and pipeline wiring hold.
"""

import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "backend"))

from intelligence import schemas as S  # noqa: E402
from intelligence.extraction import (  # noqa: E402
    DraftingPipeline,
    ExtractionPipeline,
    LLMClient,
)

EXAMPLE = os.path.join(
    os.path.dirname(__file__), "backend", "intelligence", "example_case.json"
)


def test_example_case_validates():
    """The worked example parses into CaseIntelligence."""
    with open(EXAMPLE, encoding="utf-8") as fh:
        data = json.load(fh)
    data.pop("_note", None)
    case = S.CaseIntelligence.model_validate(data)
    assert case.document_id == "ILLUS-0001"
    assert case.holdings[0].ratio_type == S.RatioType.RATIO
    assert case.relief_outcome == S.ReliefOutcome.ALLOWED
    assert "delay_condonation" in case.issue_tags
    assert case.visibility == S.Visibility.PUBLIC
    return case


def test_graph_edges_derived():
    """Graph edges derive from a case with no LLM call (pure function)."""
    case = test_example_case_validates()
    edges = ExtractionPipeline().to_graph_edges(case)
    relations = {e.relation.value for e in edges}
    assert "cites" in relations
    assert "treats" in relations
    assert "interprets" in relations
    assert "raises_issue" in relations
    # the treatment edge carries its treatment type
    treats = [e for e in edges if e.relation.value == "treats"]
    assert treats and treats[0].attributes.get("treatment") == "followed"


def test_pipelines_require_llm():
    """Pipelines refuse to run without an injected LLM, but import cleanly."""
    doc = S.RawDocument(document_id="x", doc_type="judgment", text="...")
    try:
        ExtractionPipeline().extract_case(doc)
    except RuntimeError as exc:
        assert "LLMClient" in str(exc)
    else:
        raise AssertionError("expected RuntimeError without an LLMClient")


def test_private_visibility_defaults():
    """Private-office and matter constructs default to PRIVATE, not PUBLIC."""
    matter = S.PrivateMatter(matter_id="m1", title="Office file")
    assert matter.visibility == S.Visibility.PRIVATE
    facts = S.MatterFacts(matter_id="m1")
    assert facts.visibility == S.Visibility.PRIVATE
    strat = S.CaseStrategy(matter_id="m1")
    assert strat.visibility == S.Visibility.PRIVATE


def test_fake_llm_round_trips_extraction():
    """A stub LLMClient drives the pipeline end-to-end, proving the contract."""
    with open(EXAMPLE, encoding="utf-8") as fh:
        fixture = json.load(fh)
    fixture.pop("_note", None)

    class FakeLLM:
        def complete_json(self, prompt, schema, *, system=None):
            return fixture

    assert isinstance(FakeLLM(), LLMClient)  # structural protocol check
    pipe = ExtractionPipeline(llm=FakeLLM())
    doc = S.RawDocument(document_id="ILLUS-0001", doc_type="judgment", text="full text")
    case = pipe.extract_case(doc)
    assert case.title.startswith("ILLUSTRATIVE")


def test_schemas_export_json_schema():
    """Every public model can emit a JSON Schema (needed for tool-calling)."""
    for name in S.__all__:
        obj = getattr(S, name)
        if isinstance(obj, type) and issubclass(obj, S.BaseModel):
            assert obj.model_json_schema()["type"] == "object"


def _run_all():
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    passed = 0
    for t in tests:
        t()
        print(f"  PASS  {t.__name__}")
        passed += 1
    print(f"\n{passed}/{len(tests)} intelligence-layer tests passed.")


if __name__ == "__main__":
    _run_all()
