"""
Chakshi Intelligence Layer
==========================

Turns raw Indian legal documents into structured legal intelligence:
law -> ratio -> issue -> relief -> strategy -> drafting -> citation graph.

Submodules:
    schemas     - the data contracts (CaseIntelligence, ChakshiDigest, IssueMap,
                  CaseStrategy, RiskAssessment, DraftArtifact, graph, ChakshiAnswer)
    extraction  - provider-agnostic refinery (ExtractionPipeline, DraftingPipeline)

Nothing here performs I/O on import; inject an LLMClient / retriever to run.
"""

from . import schemas  # noqa: F401
from .schemas import (  # noqa: F401
    CaseIntelligence,
    ChakshiAnswer,
    ChakshiDigest,
    CaseStrategy,
    DraftArtifact,
    DraftRequest,
    IssueMap,
    MatterFacts,
    PrivateMatter,
    RawDocument,
    RiskAssessment,
    Visibility,
)

__all__ = [
    "schemas",
    "CaseIntelligence",
    "ChakshiAnswer",
    "ChakshiDigest",
    "CaseStrategy",
    "DraftArtifact",
    "DraftRequest",
    "IssueMap",
    "MatterFacts",
    "PrivateMatter",
    "RawDocument",
    "RiskAssessment",
    "Visibility",
]
