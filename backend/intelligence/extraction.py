"""
Chakshi — Refinery Pipeline (extraction, digest, strategy, drafting)
====================================================================

If ``schemas.py`` is the *shape* of refined legal intelligence, this module is
the *refinery*: the steps that turn a raw document into that shape.

It is deliberately **provider-agnostic**. Nothing here imports ``openai`` or
``anthropic``. Instead it depends on a tiny :class:`LLMClient` protocol — one
method, ``complete_json(prompt, schema) -> dict`` — that you implement once with
whichever model you run (the repo already wires OpenAI in ``backend/app.py``;
an Anthropic/Claude client satisfies the same protocol). This keeps the
intelligence layer testable without network access and lets the model be swapped
without touching the pipeline.

The prompt templates below are the real product knowledge — they encode *what*
to extract and *how* to be honest about uncertainty. They are intended to be
iterated on; treat them as living assets.

Pipelines
---------
* :class:`ExtractionPipeline` — Brain 2/6: raw judgment -> CaseIntelligence,
  ChakshiDigest, graph edges.
* :class:`DraftingPipeline` — Brain 4/5: case papers -> facts -> timeline ->
  issues -> law -> adverse law -> relief -> draft -> verified draft
  (the 6-stage flow from the founder brief).

Both raise clear errors until an ``LLMClient`` is supplied, so importing this
module never performs I/O.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Protocol, runtime_checkable

from .schemas import (
    CaseIntelligence,
    ChakshiAnswer,
    ChakshiDigest,
    DraftArtifact,
    DraftRequest,
    GraphEdge,
    Issue,
    MatterFacts,
    RawDocument,
    RiskAssessment,
    CaseStrategy,
    Visibility,
)


# --------------------------------------------------------------------------- #
# The one dependency: a JSON-returning LLM client
# --------------------------------------------------------------------------- #
@runtime_checkable
class LLMClient(Protocol):
    """Minimal contract the pipeline needs from any LLM provider.

    Implementations must return a dict that validates against ``schema``
    (a JSON Schema, e.g. ``CaseIntelligence.model_json_schema()``). How that is
    achieved — function/tool calling, JSON mode, retries — is the
    implementation's concern.
    """

    def complete_json(
        self, prompt: str, schema: Dict[str, Any], *, system: Optional[str] = None
    ) -> Dict[str, Any]:
        ...


# --------------------------------------------------------------------------- #
# Prompt templates — the encoded product knowledge
# --------------------------------------------------------------------------- #
SYSTEM_LEGAL_ANALYST = (
    "You are Chakshi, a meticulous Indian legal analyst. You read judgments and "
    "extract structured intelligence. You never invent citations, paragraph "
    "numbers, holdings, or good-law status. When the text does not support a "
    "field, leave it empty or mark it UNKNOWN. You distinguish ratio from obiter. "
    "You always pin facts and holdings to the paragraph numbers they come from."
)

EXTRACT_CASE_PROMPT = """\
Analyse the following Indian judgment and extract structured legal intelligence
that conforms to the provided JSON schema.

Rules:
- Decompose into material facts, issues (as questions), arguments by each side,
  the statutory provisions interpreted, the cases cited, and the holdings.
- For every holding, decide whether it is RATIO (the binding reason for the
  decision) or OBITER (a passing observation). If unclear, say UNCLEAR.
- Record how this judgment TREATS each earlier case it discusses
  (followed / distinguished / overruled / doubted / referred ...).
- Pin facts and holdings to paragraph numbers via the `source.paragraphs` field.
- Set `good_law_status` only from what THIS document shows; otherwise UNKNOWN.
- Add `fact_pattern_tags` and `issue_tags` (canonical snake_case ids) so the
  case can be retrieved by issue and fact pattern later.
- Report `confidence` (0-1) and set `needs_human_review` true if the document is
  garbled, OCR-noisy, truncated, or the stakes/ambiguity are high.

JUDGMENT METADATA:
{metadata}

JUDGMENT TEXT:
{text}
"""

DIGEST_PROMPT = """\
Write a Chakshi Digest for the case below — a senior advocate's case note, not a
summary. Conform to the provided JSON schema.

Include: a crisp headnote, catchwords, the facts in five lines, the issue, what
was held, the ratio, the PRACTICAL USE for a litigator, when to cite and
(critically) when NOT to cite, drafting uses, the binding value, and the
good-law status. Be concrete and useful; avoid decorative language.

STRUCTURED CASE INTELLIGENCE:
{case_json}
"""

ISSUE_TAG_PROMPT = """\
From the case intelligence below, list the canonical legal issues it bears on,
as snake_case ids (e.g. delay_condonation, lis_pendens_purchaser,
section_138_limitation). Only issues actually decided or seriously discussed.

STRUCTURED CASE INTELLIGENCE:
{case_json}
"""

# Drafting pipeline (the 6-stage flow)
EXTRACT_FACTS_PROMPT = """\
From the uploaded case papers below, extract the matter facts conforming to the
schema: parties, a clean narrative, and a dated timeline of events. Do not infer
dates that are not present. Flag missing documents you would expect.

CASE PAPERS:
{papers}
"""

IDENTIFY_ISSUES_PROMPT = """\
Given these matter facts and timeline, identify the legal issues that arise,
phrased as questions, each tagged with canonical issue ids and the statutory
provisions involved. Conform to the schema.

MATTER FACTS:
{facts_json}
"""

STRATEGY_PROMPT = """\
You are a senior litigator. Given the matter facts, the identified issues, and
the issue-maps / authorities provided, produce a litigation strategy conforming
to the schema:
- strongest grounds and weakest points (be candid),
- the opponent's likely arguments,
- documents and evidence needed,
- the correct filing (CMA/CRP/Writ/Appeal/Review) and forum given the posture,
- interim-relief probability WITH reasoning (balance of convenience, prima
  facie case, possession, irreparable injury),
- cases to RELY ON and cases to NOT rely on (distinguished/overruled),
- a practical risk assessment (limitation, maintainability, jurisdiction,
  evidence gap, suppression, res judicata, non-joinder, alternate remedy,
  statutory bar). Never output a naive win/lose prediction.

MATTER FACTS:
{facts_json}

ISSUES:
{issues_json}

AUTHORITIES / ISSUE MAPS:
{authorities_json}
"""

DRAFT_PROMPT = """\
Draft a court-ready {draft_type} for the matter below. The draft must have legal
spine: it must follow from the facts, timeline, issues, selected relief and
strategy — not generic boilerplate. Use only the authorities provided; cite them
precisely. Where a citation is essential but not provided, insert a clearly
marked [VERIFY: ...] placeholder rather than inventing a citation.

DRAFT REQUEST:
{request_json}

SELECTED AUTHORITIES:
{authorities_json}
"""


# --------------------------------------------------------------------------- #
# Extraction pipeline — Brain 2 / 6
# --------------------------------------------------------------------------- #
class ExtractionPipeline:
    """Raw document -> structured intelligence -> digest -> graph edges."""

    def __init__(self, llm: Optional[LLMClient] = None):
        self.llm = llm

    def _require_llm(self) -> LLMClient:
        if self.llm is None:
            raise RuntimeError(
                "ExtractionPipeline needs an LLMClient. Inject one that implements "
                "complete_json(prompt, schema). See backend/intelligence/extraction.py."
            )
        return self.llm

    @staticmethod
    def _metadata_block(doc: RawDocument) -> str:
        keys = ("title", "court", "court_level", "jurisdiction", "date", "citation",
                "neutral_citation", "language")
        data = doc.model_dump()
        return "\n".join(f"{k}: {data.get(k)}" for k in keys)

    def extract_case(self, doc: RawDocument) -> CaseIntelligence:
        """Brain 2 core: judgment text -> CaseIntelligence."""
        llm = self._require_llm()
        if not doc.text:
            raise ValueError(f"RawDocument {doc.document_id} has no text to extract.")
        prompt = EXTRACT_CASE_PROMPT.format(
            metadata=self._metadata_block(doc), text=doc.text
        )
        raw = llm.complete_json(
            prompt, CaseIntelligence.model_json_schema(), system=SYSTEM_LEGAL_ANALYST
        )
        raw.setdefault("document_id", doc.document_id)
        raw.setdefault("title", doc.title or doc.document_id)
        raw.setdefault("visibility", doc.visibility.value)
        return CaseIntelligence.model_validate(raw)

    def build_digest(self, case: CaseIntelligence) -> ChakshiDigest:
        """Phase 6: structured case -> Chakshi Digest (the publication layer)."""
        llm = self._require_llm()
        prompt = DIGEST_PROMPT.format(case_json=case.model_dump_json(indent=2))
        raw = llm.complete_json(
            prompt, ChakshiDigest.model_json_schema(), system=SYSTEM_LEGAL_ANALYST
        )
        raw.setdefault("document_id", case.document_id)
        raw.setdefault("good_law_status", case.good_law_status.value)
        raw.setdefault("visibility", case.visibility.value)
        return ChakshiDigest.model_validate(raw)

    @staticmethod
    def to_graph_edges(case: CaseIntelligence) -> List[GraphEdge]:
        """Brain 6: derive citation/treatment/issue edges. Pure, no LLM."""
        from .schemas import GraphRelation

        edges: List[GraphEdge] = []
        src = case.document_id
        for cited in case.cases_cited:
            tgt = cited.document_id or (cited.citation or cited.title or "unknown")
            edges.append(GraphEdge(source_id=src, target_id=tgt,
                                   relation=GraphRelation.CITES,
                                   visibility=case.visibility))
        for t in case.treats_earlier_cases:
            tgt = t.case.document_id or (t.case.citation or t.case.title or "unknown")
            edges.append(GraphEdge(
                source_id=src, target_id=tgt, relation=GraphRelation.TREATS,
                attributes={"treatment": t.treatment.value}, visibility=case.visibility,
            ))
        for prov in case.provisions_interpreted:
            edges.append(GraphEdge(
                source_id=src, target_id=prov.short_label or f"{prov.act} {prov.section}",
                relation=GraphRelation.INTERPRETS, visibility=case.visibility,
            ))
        for tag in case.issue_tags:
            edges.append(GraphEdge(source_id=src, target_id=f"issue:{tag}",
                                   relation=GraphRelation.RAISES_ISSUE,
                                   visibility=case.visibility))
        return edges


# --------------------------------------------------------------------------- #
# Drafting pipeline — Brain 4 / 5 (the 6-stage flow)
# --------------------------------------------------------------------------- #
class DraftingPipeline:
    """Case papers -> facts -> issues -> strategy -> draft -> verified draft.

    Mirrors the founder brief's flow:
        upload -> extract facts -> timeline -> identify issues -> map evidence
        -> find law -> find adverse law -> select relief -> generate draft
        -> verify citations -> final court-ready version.

    ``find_law`` / ``find_adverse_law`` are retrieval steps; inject a retriever
    (keyword + vector + citation-graph) that returns authorities. Left abstract
    here so the contract is explicit without pinning a storage choice.
    """

    def __init__(
        self,
        llm: Optional[LLMClient] = None,
        retriever: Optional["AuthorityRetriever"] = None,
    ):
        self.llm = llm
        self.retriever = retriever

    def _require_llm(self) -> LLMClient:
        if self.llm is None:
            raise RuntimeError("DraftingPipeline needs an LLMClient.")
        return self.llm

    def extract_facts(self, papers: str, matter_id: str) -> MatterFacts:
        llm = self._require_llm()
        raw = llm.complete_json(
            EXTRACT_FACTS_PROMPT.format(papers=papers),
            MatterFacts.model_json_schema(),
            system=SYSTEM_LEGAL_ANALYST,
        )
        raw.setdefault("matter_id", matter_id)
        raw.setdefault("visibility", Visibility.PRIVATE.value)
        return MatterFacts.model_validate(raw)

    def identify_issues(self, facts: MatterFacts) -> List[Issue]:
        llm = self._require_llm()
        raw = llm.complete_json(
            IDENTIFY_ISSUES_PROMPT.format(facts_json=facts.model_dump_json(indent=2)),
            {"type": "array", "items": Issue.model_json_schema()},
            system=SYSTEM_LEGAL_ANALYST,
        )
        items = raw if isinstance(raw, list) else raw.get("issues", [])
        return [Issue.model_validate(i) for i in items]

    def build_strategy(
        self, facts: MatterFacts, issues: List[Issue], authorities_json: str = "[]"
    ) -> CaseStrategy:
        llm = self._require_llm()
        raw = llm.complete_json(
            STRATEGY_PROMPT.format(
                facts_json=facts.model_dump_json(indent=2),
                issues_json=_dump_list(issues),
                authorities_json=authorities_json,
            ),
            CaseStrategy.model_json_schema(),
            system=SYSTEM_LEGAL_ANALYST,
        )
        raw.setdefault("matter_id", facts.matter_id)
        raw.setdefault("visibility", Visibility.PRIVATE.value)
        return CaseStrategy.model_validate(raw)

    def generate_draft(
        self, request: DraftRequest, authorities_json: str = "[]"
    ) -> DraftArtifact:
        """Generate a draft. Citations are NOT marked verified here — run
        ``verify_citations`` before the draft is court-ready."""
        llm = self._require_llm()
        raw = llm.complete_json(
            DRAFT_PROMPT.format(
                draft_type=request.draft_type.value,
                request_json=request.model_dump_json(indent=2),
                authorities_json=authorities_json,
            ),
            DraftArtifact.model_json_schema(),
            system=SYSTEM_LEGAL_ANALYST,
        )
        raw.setdefault("matter_id", request.matter_id)
        raw.setdefault("draft_type", request.draft_type.value)
        raw["citations_verified"] = False
        raw.setdefault("based_on_strategy", request.strategy is not None)
        raw.setdefault("visibility", Visibility.PRIVATE.value)
        return DraftArtifact.model_validate(raw)

    def verify_citations(self, draft: DraftArtifact) -> DraftArtifact:
        """Confirm every cited authority exists and is good law.

        Requires a retriever. Marks citations_verified only when every cite
        resolves; surfaces a warning for any that are doubtful/overruled/missing.
        """
        if self.retriever is None:
            raise RuntimeError(
                "verify_citations needs an AuthorityRetriever to resolve cites."
            )
        warnings = list(draft.warnings)
        all_ok = True
        for cite in draft.citations_used:
            status = self.retriever.verify(cite)
            if not status.get("exists"):
                all_ok = False
                warnings.append(f"Unresolved citation: {cite.title or cite.citation}")
            elif status.get("good_law_status") in ("overruled", "doubtful"):
                warnings.append(
                    f"Doubtful authority: {cite.title or cite.citation} "
                    f"({status.get('good_law_status')})"
                )
        draft.citations_verified = all_ok
        draft.warnings = warnings
        return draft


@runtime_checkable
class AuthorityRetriever(Protocol):
    """Hybrid retrieval contract (keyword + vector + citation graph).

    Implement against your store (e.g. OpenSearch/pgvector + a graph table).
    """

    def search(self, query: str, *, jurisdiction: Optional[str] = None,
               court_level: Optional[str] = None, limit: int = 20) -> List[dict]:
        ...

    def verify(self, citation) -> dict:
        """Return {'exists': bool, 'good_law_status': str, 'document_id': str|None}."""
        ...


def _dump_list(models) -> str:
    import json
    return json.dumps([m.model_dump(mode="json") for m in models], indent=2, default=str)


__all__ = [
    "LLMClient", "AuthorityRetriever",
    "ExtractionPipeline", "DraftingPipeline",
    "SYSTEM_LEGAL_ANALYST",
]
