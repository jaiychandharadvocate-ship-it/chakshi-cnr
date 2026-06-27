"""
Chakshi — Structured Legal Intelligence Schemas
================================================

This module is the "crown" of Chakshi: the layer that turns *raw* legal
documents (crude oil) into *structured legal intelligence* (refined product).

A raw judgment is just text. These Pydantic models describe what Chakshi
*extracts* from it — facts, issues, the section interpreted, what the court
actually held, whether that holding is ratio or obiter, the relief, the
procedural posture, how the case was later treated, and whether it is still
safe to cite. The same layer carries issue maps, risk assessments, litigation
strategy, the citation/knowledge graph, the Chakshi Digest, and the unified
answer object the product returns to a user.

Design rules
------------
* **Provider-agnostic.** Nothing here calls an LLM or a database. These are
  pure data contracts; extraction lives in ``extraction.py``.
* **Paragraph-level provenance.** Every extracted fact carries a
  :class:`SourceRef` so answers can cite "para 14 of <case>", never a vibe.
* **Public/private separation.** Every record carries ``visibility``. The
  Private Office Brain (30 years of office files) must never leak into public
  training or public answers — the field makes that boundary explicit and
  enforceable.
* **Honest uncertainty.** Statuses default to ``UNKNOWN`` rather than guessing.
  An extractor that is not sure must say so, not invent good-law status.

Maps to the 7-brains vision:
    Brain 1 Corpus      -> SourceRef, LegalProvision, RawDocument
    Brain 2 Ratio       -> Issue, Holding, Treatment, CaseIntelligence
    Brain 3 Issue       -> IssueMap, IssueMapEntry
    Brain 4 Strategy    -> RiskAssessment, CaseStrategy
    Brain 5 Drafting    -> DraftRequest, DraftArtifact
    Brain 6 Graph       -> GraphNode, GraphEdge
    Brain 7 Private     -> PrivateMatter (+ visibility on every model)
    Output layer        -> ChakshiDigest, ChakshiAnswer

Note: this module intentionally does NOT use ``from __future__ import annotations``.
All models are defined before they are referenced (no forward refs needed), and
PEP 563 string annotations trigger a ref-generation recursion bug in pydantic
2.5.x. Keep concrete annotations here.
"""

# `date` is imported under an alias so model fields can be *named* ``date``
# (a natural JSON key) without shadowing the type — that shadowing breaks
# pydantic schema generation.
from datetime import date as date_type, datetime
from enum import Enum
from typing import List, Optional

from pydantic import BaseModel, Field


# --------------------------------------------------------------------------- #
# Enumerations — the controlled vocabulary of Indian litigation intelligence
# --------------------------------------------------------------------------- #
class Visibility(str, Enum):
    """Public datasets vs. the private office brain. Never mix the two."""

    PUBLIC = "public"
    PRIVATE = "private"


class CourtLevel(str, Enum):
    SUPREME_COURT = "supreme_court"
    HIGH_COURT = "high_court"
    TRIBUNAL = "tribunal"
    DISTRICT_COURT = "district_court"
    SUBORDINATE_COURT = "subordinate_court"
    OTHER = "other"


class RatioType(str, Enum):
    """Was the statement the binding reason, or a passing remark?"""

    RATIO = "ratio"
    OBITER = "obiter"
    UNCLEAR = "unclear"


class TreatmentType(str, Enum):
    """How a later case treated this case — the citation-treatment graph."""

    FOLLOWED = "followed"
    AFFIRMED = "affirmed"
    APPLIED = "applied"
    EXPLAINED = "explained"
    DISTINGUISHED = "distinguished"
    DOUBTED = "doubted"
    CRITICISED = "criticised"
    OVERRULED = "overruled"
    PARTIALLY_OVERRULED = "partially_overruled"
    DISSENTED_FROM = "dissented_from"
    REFERRED = "referred"
    NEUTRAL = "neutral"


class GoodLawStatus(str, Enum):
    """Is it still safe to cite? The single most useful flag for a litigator."""

    GOOD_LAW = "good_law"
    DOUBTFUL = "doubtful"
    PARTIALLY_OVERRULED = "partially_overruled"
    OVERRULED = "overruled"
    SUPERSEDED_BY_STATUTE = "superseded_by_statute"
    UNKNOWN = "unknown"


class ReliefOutcome(str, Enum):
    ALLOWED = "allowed"
    PARTLY_ALLOWED = "partly_allowed"
    DISMISSED = "dismissed"
    GRANTED = "granted"
    PARTLY_GRANTED = "partly_granted"
    REFUSED = "refused"
    REMANDED = "remanded"
    SETTLED = "settled"
    WITHDRAWN = "withdrawn"
    DISPOSED = "disposed"
    UNKNOWN = "unknown"


class ProceduralStage(str, Enum):
    PRE_FILING = "pre_filing"
    INTERIM = "interim"
    TRIAL = "trial"
    FIRST_APPEAL = "first_appeal"
    SECOND_APPEAL = "second_appeal"
    REVISION = "revision"
    WRIT = "writ"
    WRIT_APPEAL = "writ_appeal"
    SLP = "slp"
    APPEAL = "appeal"
    REVIEW = "review"
    EXECUTION = "execution"
    OTHER = "other"


class RiskLevel(str, Enum):
    LOW = "low"
    MODERATE = "moderate"
    HIGH = "high"
    CRITICAL = "critical"
    UNKNOWN = "unknown"


class Probability(str, Enum):
    """Practical relief probability — deliberately coarse, never a fake %."""

    VERY_LOW = "very_low"
    LOW = "low"
    MODERATE = "moderate"
    HIGH = "high"
    VERY_HIGH = "very_high"
    UNKNOWN = "unknown"


class DraftType(str, Enum):
    PLAINT = "plaint"
    WRITTEN_STATEMENT = "written_statement"
    COUNTER = "counter"
    REJOINDER = "rejoinder"
    AFFIDAVIT = "affidavit"
    PROOF_AFFIDAVIT = "proof_affidavit"
    CHIEF_EXAMINATION = "chief_examination"
    CROSS_EXAMINATION = "cross_examination"
    INTERIM_APPLICATION = "interim_application"
    INJUNCTION_APPLICATION = "injunction_application"
    VACATE_INJUNCTION = "vacate_injunction"
    CMA = "cma"
    CRP = "crp"
    WRIT_PETITION = "writ_petition"
    WRIT_APPEAL = "writ_appeal"
    SLP = "slp"
    LEGAL_NOTICE = "legal_notice"
    REPLY_NOTICE = "reply_notice"
    SETTLEMENT_PROPOSAL = "settlement_proposal"
    CASE_SYNOPSIS = "case_synopsis"
    LIST_OF_DATES = "list_of_dates"
    WRITTEN_ARGUMENTS = "written_arguments"


class GraphRelation(str, Enum):
    """Edge types for the Legal Graph Brain (Brain 6)."""

    CITES = "cites"
    INTERPRETS = "interprets"
    DECIDED_BY_JUDGE = "decided_by_judge"
    IN_COURT = "in_court"
    INVOLVES_PARTY = "involves_party"
    ARGUED_BY = "argued_by"
    RAISES_ISSUE = "raises_issue"
    GRANTS_RELIEF = "grants_relief"
    TREATS = "treats"  # carries a TreatmentType in edge.attributes
    SAME_FACT_PATTERN = "same_fact_pattern"
    EARLIER_LITIGATION = "earlier_litigation"
    ENCUMBERS = "encumbers"
    CONTRADICTS = "contradicts"


# --------------------------------------------------------------------------- #
# Brain 1 — Corpus primitives: references & provenance
# --------------------------------------------------------------------------- #
class SourceRef(BaseModel):
    """A pinpoint reference back into the corpus. Enables paragraph-level cites."""

    document_id: Optional[str] = Field(
        None, description="Internal corpus id of the cited document."
    )
    title: Optional[str] = Field(None, description="Case title or statute name.")
    citation: Optional[str] = Field(
        None, description="Reported citation, e.g. AIR / SCC / neutral citation."
    )
    neutral_citation: Optional[str] = Field(None)
    court: Optional[str] = Field(None)
    court_level: Optional[CourtLevel] = Field(None)
    date: Optional[date_type] = Field(None)
    url: Optional[str] = Field(None, description="Source URL (e.g. Indian Kanoon).")
    paragraphs: List[int] = Field(
        default_factory=list,
        description="Pinpoint paragraph numbers the statement is drawn from.",
    )


class LegalProvision(BaseModel):
    """A statutory hook: Act + section (+ subsection/clause)."""

    act: str = Field(..., description="e.g. 'Code of Civil Procedure, 1908'.")
    section: Optional[str] = Field(None, description="e.g. '92', 'Order XXXIX Rule 1'.")
    subsection: Optional[str] = Field(None)
    clause: Optional[str] = Field(None)
    short_label: Optional[str] = Field(
        None, description="Human label, e.g. 'S.92 CPC'."
    )


class RawDocument(BaseModel):
    """A document as ingested, before refinement. Brain 1 input."""

    document_id: str
    doc_type: str = Field(..., description="judgment | order | act | rule | notification | circular | form")
    title: Optional[str] = None
    court: Optional[str] = None
    court_level: Optional[CourtLevel] = None
    jurisdiction: Optional[str] = Field(None, description="e.g. 'Tamil Nadu', 'India'.")
    date: Optional[date_type] = None
    citation: Optional[str] = None
    neutral_citation: Optional[str] = None
    language: str = Field("en")
    source_url: Optional[str] = None
    source_dataset: Optional[str] = Field(
        None, description="Provenance, e.g. 'vanga/indian-high-court-judgments'."
    )
    license: Optional[str] = Field(None, description="License of the source material.")
    text: Optional[str] = Field(None, description="Extracted full text (may be large).")
    visibility: Visibility = Visibility.PUBLIC


# --------------------------------------------------------------------------- #
# Brain 2 — Ratio & Principle: the structured judgment
# --------------------------------------------------------------------------- #
class Issue(BaseModel):
    """A legal question the case turned on."""

    question: str = Field(..., description="The legal issue, phrased as a question.")
    fact_trigger: Optional[str] = Field(
        None, description="The fact pattern that raised this issue."
    )
    provisions: List[LegalProvision] = Field(default_factory=list)
    issue_tags: List[str] = Field(
        default_factory=list,
        description="Canonical issue ids for the Issue Brain, e.g. 'delay_condonation'.",
    )
    source: Optional[SourceRef] = None


class Holding(BaseModel):
    """What the court actually decided on an issue."""

    issue: str = Field(..., description="The issue this holding answers.")
    held: str = Field(..., description="What the court held, in plain terms.")
    ratio_type: RatioType = RatioType.UNCLEAR
    provisions: List[LegalProvision] = Field(default_factory=list)
    reasoning_summary: Optional[str] = None
    source: Optional[SourceRef] = Field(
        None, description="Paragraphs the holding is drawn from."
    )


class Argument(BaseModel):
    side: str = Field(..., description="petitioner | respondent | appellant | intervenor")
    contention: str
    provisions: List[LegalProvision] = Field(default_factory=list)
    authorities: List[SourceRef] = Field(default_factory=list)
    accepted: Optional[bool] = Field(
        None, description="Did the court accept this argument? None if unclear."
    )


class Treatment(BaseModel):
    """How this case treated an *earlier* case (one edge of the treatment graph)."""

    case: SourceRef = Field(..., description="The earlier case being treated.")
    treatment: TreatmentType = TreatmentType.NEUTRAL
    note: Optional[str] = None
    source: Optional[SourceRef] = None


class CaseIntelligence(BaseModel):
    """The refined judgment — Brain 2's core output.

    This is what makes Chakshi different from a search box: the judgment is
    decomposed into what it *does*, not just what it *says*.
    """

    document_id: str
    title: str
    court: Optional[str] = None
    court_level: Optional[CourtLevel] = None
    jurisdiction: Optional[str] = None
    bench: List[str] = Field(default_factory=list, description="Judges on the bench.")
    decision_date: Optional[date_type] = None
    citation: Optional[str] = None
    neutral_citation: Optional[str] = None

    # The decomposition
    facts: List[str] = Field(default_factory=list, description="Material facts.")
    procedural_stage: Optional[ProceduralStage] = None
    issues: List[Issue] = Field(default_factory=list)
    arguments: List[Argument] = Field(default_factory=list)
    provisions_interpreted: List[LegalProvision] = Field(default_factory=list)
    cases_cited: List[SourceRef] = Field(default_factory=list)
    holdings: List[Holding] = Field(default_factory=list)
    relief_outcome: ReliefOutcome = ReliefOutcome.UNKNOWN
    relief_detail: Optional[str] = None

    # Treatment & currency
    treats_earlier_cases: List[Treatment] = Field(default_factory=list)
    good_law_status: GoodLawStatus = GoodLawStatus.UNKNOWN
    good_law_note: Optional[str] = None

    # Retrieval aids
    fact_pattern_tags: List[str] = Field(default_factory=list)
    issue_tags: List[str] = Field(default_factory=list)

    # Pipeline bookkeeping
    visibility: Visibility = Visibility.PUBLIC
    extraction_model: Optional[str] = Field(
        None, description="Model/version that produced this extraction."
    )
    extracted_at: Optional[datetime] = None
    confidence: Optional[float] = Field(
        None, ge=0.0, le=1.0, description="Extractor self-reported confidence."
    )
    needs_human_review: bool = Field(
        False, description="Flag low-confidence or high-stakes extractions."
    )


# --------------------------------------------------------------------------- #
# Output layer — Chakshi Digest (the proprietary publication layer)
# --------------------------------------------------------------------------- #
class ChakshiDigest(BaseModel):
    """A senior-lawyer's case note. The 'gold' layer (Phase 6)."""

    document_id: str
    headnote: str = Field(..., description="The Chakshi headnote.")
    catchwords: List[str] = Field(default_factory=list)
    facts_in_five_lines: str
    issue: str
    held: str
    ratio: str
    practical_use: str = Field(..., description="How a litigator actually uses this.")
    when_to_cite: List[str] = Field(default_factory=list)
    when_not_to_cite: List[str] = Field(default_factory=list)
    similar_cases: List[SourceRef] = Field(default_factory=list)
    adverse_cases: List[SourceRef] = Field(default_factory=list)
    drafting_use: List[str] = Field(default_factory=list)
    court_level: Optional[CourtLevel] = None
    binding_value: Optional[str] = Field(
        None, description="Binding within which jurisdiction / on whom."
    )
    good_law_status: GoodLawStatus = GoodLawStatus.UNKNOWN
    visibility: Visibility = Visibility.PUBLIC


# --------------------------------------------------------------------------- #
# Brain 3 — Issue maps: think like a lawyer preparing a case note
# --------------------------------------------------------------------------- #
class IssueMapEntry(BaseModel):
    """One line of authority within an issue map."""

    case: SourceRef
    note: Optional[str] = Field(None, description="Why it matters / proposition.")
    favourable: Optional[bool] = Field(
        None, description="Favourable (True) / adverse (False) / neutral (None)."
    )
    good_law_status: GoodLawStatus = GoodLawStatus.UNKNOWN


class IssueMap(BaseModel):
    """Everything a lawyer needs on one issue (Brain 3, Phase 3)."""

    issue_id: str = Field(..., description="Canonical id, e.g. 'delay_condonation'.")
    title: str
    description: Optional[str] = None
    provisions: List[LegalProvision] = Field(default_factory=list)

    binding_cases: List[IssueMapEntry] = Field(default_factory=list)
    recent_cases: List[IssueMapEntry] = Field(default_factory=list)
    favourable_line: List[IssueMapEntry] = Field(default_factory=list)
    adverse_line: List[IssueMapEntry] = Field(default_factory=list)
    split_of_opinion: Optional[str] = None
    supreme_court_position: Optional[str] = None
    jurisdiction_positions: dict = Field(
        default_factory=dict,
        description="Map of jurisdiction -> position, e.g. {'Madras HC': '...'}.",
    )

    documents_required: List[str] = Field(default_factory=list)
    drafting_grounds: List[str] = Field(default_factory=list)
    likely_objections: List[str] = Field(default_factory=list)
    counter_objections: List[str] = Field(default_factory=list)
    evidence_required: List[str] = Field(default_factory=list)
    relief_probability: Probability = Probability.UNKNOWN
    visibility: Visibility = Visibility.PUBLIC


# --------------------------------------------------------------------------- #
# Brain 4 — Litigation strategy & risk (the real money feature)
# --------------------------------------------------------------------------- #
class RiskItem(BaseModel):
    """A single danger to flag *before* filing."""

    risk_type: str = Field(
        ...,
        description="limitation | maintainability | jurisdiction | evidence_gap | "
        "interim_relief | suppression | res_judicata | non_joinder | "
        "cause_of_action | statutory_bar | alternate_remedy",
    )
    level: RiskLevel = RiskLevel.UNKNOWN
    explanation: str
    triggering_facts: List[str] = Field(default_factory=list)
    mitigation: Optional[str] = None
    authorities: List[SourceRef] = Field(default_factory=list)


class RiskAssessment(BaseModel):
    """Practical risk intelligence (Phase 4) — never a naive win/lose model."""

    matter_id: Optional[str] = None
    risks: List[RiskItem] = Field(default_factory=list)
    overall_note: Optional[str] = None
    visibility: Visibility = Visibility.PRIVATE


class CaseStrategy(BaseModel):
    """Litigation intelligence for a specific matter (Brain 4)."""

    matter_id: Optional[str] = None
    strongest_grounds: List[str] = Field(default_factory=list)
    weakest_points: List[str] = Field(default_factory=list)
    likely_opponent_arguments: List[str] = Field(default_factory=list)
    documents_needed: List[str] = Field(default_factory=list)
    evidence_strategy: List[str] = Field(default_factory=list)
    recommended_filing: Optional[str] = Field(
        None, description="e.g. 'CMA', 'CRP', 'Writ', 'Appeal', 'Review'."
    )
    recommended_forum: Optional[str] = None
    interim_relief_probability: Probability = Probability.UNKNOWN
    interim_relief_reasoning: Optional[str] = None
    do_not_rely_on: List[SourceRef] = Field(
        default_factory=list, description="Cases that were distinguished/overruled."
    )
    rely_on: List[SourceRef] = Field(default_factory=list)
    risk_assessment: Optional[RiskAssessment] = None
    visibility: Visibility = Visibility.PRIVATE


# --------------------------------------------------------------------------- #
# Brain 5 — Drafting
# --------------------------------------------------------------------------- #
class TimelineEvent(BaseModel):
    date: Optional[date_type] = None
    description: str
    source_document: Optional[str] = None


class MatterFacts(BaseModel):
    """The case-papers input to the drafting & strategy pipeline."""

    matter_id: str
    parties: dict = Field(
        default_factory=dict,
        description="e.g. {'petitioner': '...', 'respondent': '...'}.",
    )
    narrative: Optional[str] = None
    timeline: List[TimelineEvent] = Field(default_factory=list)
    documents: List[str] = Field(default_factory=list)
    jurisdiction: Optional[str] = None
    court_level: Optional[CourtLevel] = None
    visibility: Visibility = Visibility.PRIVATE


class DraftRequest(BaseModel):
    matter_id: str
    draft_type: DraftType
    facts: MatterFacts
    issues: List[Issue] = Field(default_factory=list)
    strategy: Optional[CaseStrategy] = None
    relief_sought: Optional[str] = None
    instructions: Optional[str] = Field(
        None, description="Free-form advocate instructions / house style."
    )


class DraftArtifact(BaseModel):
    matter_id: str
    draft_type: DraftType
    body: str = Field(..., description="The generated draft text.")
    citations_used: List[SourceRef] = Field(default_factory=list)
    citations_verified: bool = Field(
        False, description="True only after the citation-verifier confirmed each cite."
    )
    warnings: List[str] = Field(default_factory=list)
    based_on_strategy: bool = False
    generated_at: Optional[datetime] = None
    visibility: Visibility = Visibility.PRIVATE


# --------------------------------------------------------------------------- #
# Brain 6 — Legal graph
# --------------------------------------------------------------------------- #
class GraphNode(BaseModel):
    node_id: str
    node_type: str = Field(
        ..., description="case | statute | section | judge | court | advocate | party | "
        "issue | relief | fact_pattern | document | company | property | witness"
    )
    label: str
    attributes: dict = Field(default_factory=dict)
    visibility: Visibility = Visibility.PUBLIC


class GraphEdge(BaseModel):
    source_id: str
    target_id: str
    relation: GraphRelation
    attributes: dict = Field(
        default_factory=dict,
        description="e.g. {'treatment': 'distinguished', 'paragraph': 14}.",
    )
    weight: Optional[float] = None
    visibility: Visibility = Visibility.PUBLIC


# --------------------------------------------------------------------------- #
# Brain 7 — Private office (your unfair advantage)
# --------------------------------------------------------------------------- #
class PrivateMatter(BaseModel):
    """An office file. Always private; powers matter memory, not public training."""

    matter_id: str
    title: str
    client_ref: Optional[str] = None
    court: Optional[str] = None
    jurisdiction: Optional[str] = Field(None, description="e.g. 'Coimbatore, TN'.")
    matter_type: Optional[str] = Field(
        None, description="property | banking | family | trust_suit | arbitration | ..."
    )
    facts: Optional[MatterFacts] = None
    drafts: List[DraftArtifact] = Field(default_factory=list)
    strategy: Optional[CaseStrategy] = None
    outcome: Optional[str] = None
    settlement_pattern: Optional[str] = None
    lessons: List[str] = Field(default_factory=list)
    visibility: Visibility = Field(
        Visibility.PRIVATE,
        description="Always private. Enforced by policy; never set to PUBLIC.",
    )


# --------------------------------------------------------------------------- #
# Output layer — the unified Chakshi answer
# --------------------------------------------------------------------------- #
class AnswerCitation(BaseModel):
    proposition: str = Field(..., description="The legal point this cite supports.")
    source: SourceRef
    good_law_status: GoodLawStatus = GoodLawStatus.UNKNOWN


class ChakshiAnswer(BaseModel):
    """What Chakshi returns to a query — like a senior lawyer's case note.

    Not a list of links. A structured opinion: the law, the best cases, the
    *adverse* cases, the procedural/limitation risks, the evidence needed, a
    drafting strategy, paragraph-level citations, and an explicit warning when
    the law is doubtful.
    """

    query: str
    relevant_law: List[LegalProvision] = Field(default_factory=list)
    summary: str = Field(..., description="Direct answer in plain language.")
    best_cases: List[AnswerCitation] = Field(default_factory=list)
    adverse_cases: List[AnswerCitation] = Field(default_factory=list)
    risks: List[RiskItem] = Field(default_factory=list)
    evidence_required: List[str] = Field(default_factory=list)
    drafting_strategy: List[str] = Field(default_factory=list)
    citations: List[AnswerCitation] = Field(default_factory=list)
    warnings: List[str] = Field(
        default_factory=list,
        description="Surfaced when cited law is doubtful/overruled or facts are thin.",
    )
    jurisdiction: Optional[str] = None
    confidence: Optional[float] = Field(None, ge=0.0, le=1.0)


__all__ = [
    # enums
    "Visibility", "CourtLevel", "RatioType", "TreatmentType", "GoodLawStatus",
    "ReliefOutcome", "ProceduralStage", "RiskLevel", "Probability", "DraftType",
    "GraphRelation",
    # primitives
    "SourceRef", "LegalProvision", "RawDocument",
    # brain 2
    "Issue", "Holding", "Argument", "Treatment", "CaseIntelligence",
    # digest
    "ChakshiDigest",
    # brain 3
    "IssueMapEntry", "IssueMap",
    # brain 4
    "RiskItem", "RiskAssessment", "CaseStrategy",
    # brain 5
    "TimelineEvent", "MatterFacts", "DraftRequest", "DraftArtifact",
    # brain 6
    "GraphNode", "GraphEdge",
    # brain 7
    "PrivateMatter",
    # output
    "AnswerCitation", "ChakshiAnswer",
]
