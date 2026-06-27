# 🧠 Chakshi — Indian Legal Intelligence Engine (Architecture)

> **We are not building an Indian legal database. We are building an Indian legal
> intelligence refinery.** Raw judgments are crude oil. Chakshi's value is what it
> *extracts*: law → ratio → issue → relief → strategy → probability → drafting →
> argument → counter-argument → judge/court pattern → client action.

This document turns that vision into an engineering plan and records what is
**already implemented in this repo** versus what is **planned**.

- **Data sources** (the crude oil): [`INDIAN_LEGAL_DATA_SOURCES.md`](INDIAN_LEGAL_DATA_SOURCES.md)
- **The refinery contracts** (the implemented "crown"): [`../backend/intelligence/`](../backend/intelligence/)

---

## The 7 Brains → components

| # | Brain | What it does | Implemented in this repo | Status |
|---|-------|--------------|--------------------------|--------|
| 1 | **Corpus** | Base memory: judgments, acts, rules, notifications, GOs, court rules, limitation/stamp/registration law | `schemas.RawDocument`, `SourceRef`, `LegalProvision`; ingestion via data sources catalog | 🟡 contracts done; ingestion pipeline TODO |
| 2 | **Ratio & Principle** | Per judgment: issue, fact trigger, section interpreted, holding, ratio-vs-obiter, relief, stage, later treatment, good-law status | `schemas.CaseIntelligence`, `Issue`, `Holding`, `Argument`, `Treatment`; `extraction.ExtractionPipeline.extract_case()`; **live via `llm.OpenAILLMClient` + `run_extraction.py`** | 🟢 contracts + pipeline + **live LLM extraction** |
| 3 | **Legal Issue** | Issue-first retrieval: leading/recent/favourable/adverse cases, drafting points, evidence, objections, relief probability | `schemas.IssueMap`, `IssueMapEntry` | 🟢 contract; population pipeline TODO |
| 4 | **Litigation Strategy** | Strongest ground, weakest point, opponent's likely arguments, documents needed, filing/forum, interim-relief probability, **risk before filing** | `schemas.CaseStrategy`, `RiskAssessment`, `RiskItem`; `extraction.DraftingPipeline.build_strategy()` | 🟢 contracts + interface + prompts |
| 5 | **Drafting** | Court-ready drafts *from* facts/timeline/issues/law/strategy — not boilerplate | `schemas.DraftRequest`, `DraftArtifact`, `MatterFacts`, `TimelineEvent`; `extraction.DraftingPipeline` (6-stage flow) | 🟢 contracts + pipeline interface + prompts |
| 6 | **Legal Graph** | case↔case↔statute↔judge↔court↔party↔issue↔relief↔treatment; the "sixth sense" | `schemas.GraphNode`, `GraphEdge`, `GraphRelation`; `extraction.ExtractionPipeline.to_graph_edges()` | 🟢 contracts + edge derivation; graph store TODO |
| 7 | **Private Office** | 30 years of office files as private matter memory / drafting & argument bank — **never** leaked into public training | `schemas.PrivateMatter` + `Visibility` on every model | 🟢 contract + enforced public/private boundary |
| — | **Output layer** | The Chakshi Digest (proprietary headnotes) + the unified answer object | `schemas.ChakshiDigest`, `ChakshiAnswer`, `AnswerCitation`; `ExtractionPipeline.build_digest()` | 🟢 contracts + digest pipeline |

Legend: 🟢 contract + interface implemented · 🟡 contract only · ⬜ not started.

---

## What "implemented" means here

This PR ships the **intelligence layer's data contracts and pipeline interfaces** —
the hardest part to get right and the thing everything else depends on. It is
runnable and tested, but provider/storage-agnostic:

```
backend/intelligence/
├── __init__.py          # package exports
├── schemas.py           # all data contracts (Pydantic v2) — the "crown"
├── extraction.py        # ExtractionPipeline + DraftingPipeline + prompt templates
├── llm.py               # OpenAILLMClient adapter (live extraction) + factory
├── run_extraction.py    # end-to-end CLI: judgment text -> intelligence + digest
└── example_case.json    # a worked, illustrative structured judgment
test_intelligence.py     # validates schemas, graph derivation, pipeline wiring
test_llm_client.py       # offline tests for the LLM adapter (stubbed model)
```

**Live extraction is wired (one document end-to-end).** `llm.OpenAILLMClient`
implements the `LLMClient` protocol over the OpenAI client the project already
uses (JSON mode + schema-in-prompt + validate/retry). Run it:

```bash
export OPENAI_API_KEY_MY=sk-...          # the key convention from backend/app.py
python -m intelligence.run_extraction judgment.txt --title "X v. Y" --out result.json
# -> result.json: { case: CaseIntelligence, graph_edges: [...], digest: ChakshiDigest }
```

Without a key the CLI explains how to set one and exits cleanly.

**Design decisions baked in:**

1. **Provider-agnostic.** `extraction.py` depends only on a one-method
   `LLMClient` protocol (`complete_json(prompt, schema) -> dict`). The existing
   OpenAI client in `backend/app.py` — or an Anthropic/Claude client — satisfies
   it. No model is hard-wired into the intelligence layer.
2. **Storage-agnostic retrieval.** Hybrid retrieval (keyword + vector + citation
   graph) is expressed as an `AuthorityRetriever` protocol, so the store
   (OpenSearch / pgvector / a graph table) is a later, swappable choice.
3. **Paragraph-level provenance everywhere.** Every extracted fact/holding
   carries a `SourceRef` with `paragraphs`, so Chakshi cites "para 14 of X",
   never a vibe. This is the antidote to LLM hallucinated citations.
4. **Honest uncertainty.** `good_law_status`, `relief_outcome`, `ratio_type`,
   `relief_probability` default to `UNKNOWN`. Extractors flag
   `needs_human_review`; drafts are not "court-ready" until
   `citations_verified` is true.
5. **Public/private firewall.** Every model has a `visibility` field. Office
   files default to `PRIVATE`; the boundary is a first-class data attribute so it
   can be enforced in retrieval, training-set assembly, and answers.

---

## The unified answer contract (`ChakshiAnswer`)

For every query, Chakshi should answer like a senior lawyer's case note, not a
list of links:

- **relevant law** (`relevant_law: [LegalProvision]`)
- **best cases** + **adverse cases** (`best_cases`, `adverse_cases`)
- **risks** — limitation / maintainability / jurisdiction / evidence-gap (`risks`)
- **evidence required** (`evidence_required`)
- **drafting strategy** (`drafting_strategy`)
- **paragraph-level citations** (`citations`)
- **warnings** when the cited law is doubtful/overruled or facts are thin (`warnings`)

---

## The drafting flow (Brain 5, `DraftingPipeline`)

The founder brief's flow, encoded as pipeline methods:

```
upload case papers
   ↓  extract_facts()          → MatterFacts (parties, narrative, timeline)
   ↓  identify_issues()        → [Issue]  (tagged, with provisions)
   ↓  (retrieve law + adverse law via AuthorityRetriever)
   ↓  build_strategy()         → CaseStrategy + RiskAssessment
   ↓  generate_draft()         → DraftArtifact (citations NOT yet verified)
   ↓  verify_citations()       → DraftArtifact (citations_verified=True / warnings)
court-ready draft
```

Drafting comes **after** analysis — a draft inherits the strategy's spine.

---

## Build roadmap (the 6 phases)

- **Phase 1 — Build the Indian legal universe.** Ingest SC/HC (AWS open data),
  India Code (bare acts), tribunals, notifications, court rules, limitation/stamp/
  registration law. Target: retrieve Indian law with paragraph-level citations.
  → uses the data-sources catalog; needs an ingestion + OCR + chunking pipeline.
- **Phase 2 — Convert judgments to structured intelligence.** Run
  `ExtractionPipeline` over the corpus → `CaseIntelligence` + graph edges.
  → contracts ✅; needs an `LLMClient` impl + batch orchestration + storage.
- **Phase 3 — Build issue-wise legal maps.** Aggregate `CaseIntelligence` by
  `issue_tags` into `IssueMap`s (binding/recent/favourable/adverse, Madras-
  specific vs SC position, required docs, objections, relief probability).
- **Phase 4 — Litigation risk intelligence.** Not a naive win/lose model —
  `RiskAssessment` flags danger (limitation, maintainability, jurisdiction,
  evidence gap, suppression, res judicata, non-joinder, alternate remedy) before
  filing.
- **Phase 5 — Drafting from strategy.** Wire `DraftingPipeline` end-to-end with
  retrieval + the citation verifier.
- **Phase 6 — Chakshi Digest.** Generate `ChakshiDigest` per important case — the
  proprietary publication layer (headnote, catchwords, when to / not to cite).

---

## Next implementation steps (concrete)

1. ~~**`LLMClient` adapter**~~ — ✅ done (`llm.OpenAILLMClient`, JSON mode +
   validate/retry; `run_extraction.py` runs one document end-to-end).
2. **Ingestion service** — pull from the AWS HC/SC corpora + India Code; OCR via a
   `doctor`-style microservice; emit `RawDocument`s.
3. **Storage** — a document store + vector index + a graph/edge table; implement
   `AuthorityRetriever`.
4. **Batch extraction** — run `ExtractionPipeline.extract_case` + `to_graph_edges`
   across the corpus; queue low-confidence items for human review.
5. **FastAPI endpoints** — `/intelligence/extract`, `/issues/{id}`, `/answer`,
   `/draft`, mounted alongside the existing eCourts chatbot in `backend/app.py`.
6. **Citation verifier** — resolve every cite against the corpus + treatment graph
   before any draft is marked court-ready.

---

## Guardrails (non-negotiable)

- **No invented citations.** Drafts insert `[VERIFY: ...]` placeholders rather
  than fabricate; `verify_citations()` must pass before "court-ready".
- **Good-law before reliance.** Never rely on a case without checking treatment.
- **Private stays private.** `Visibility.PRIVATE` records never enter public
  training sets or public answers. Enforce at retrieval and corpus-assembly time.
- **Licensing hygiene.** Keep per-document provenance + license (see the data
  sources catalog); don't mix NC/paywalled material into redistributable corpora.
