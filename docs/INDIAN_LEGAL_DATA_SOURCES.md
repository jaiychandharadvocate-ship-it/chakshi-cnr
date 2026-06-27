# 🇮🇳 Indian Legal Data Sources — Master Catalog

> A curated, verified collection of data sources, datasets, tools, and APIs for
> building an Indian legal knowledge base, search/RAG system, and for fine-tuning
> language models on Indian law. This is the "collections" reference for the
> **Chakshi** project (the eCourts assistant in this repo).
>
> **Goal:** assemble the raw material for "almighty Indian law knowledge" — bare
> acts, judgments (Supreme Court, High Courts, district courts), tribunals,
> gazette notifications, legislative debates, and the Indic-language corpora
> needed to train models that read and reason in Indian languages.

**Last updated:** 2026-06-27

---

## ⚖️ How to read this catalog

Each entry notes **what it contains**, **format**, **license**, **how to access**, and
**suitability** (database vs. fine-tuning). Licensing is the single most important
column — many sources are public-domain government works, but a few aggregators and
journals are paywalled and **must not be used for unlicensed training/redistribution**.

Legend:
- ✅ **Open / permissive** — safe to ingest and (with attribution) redistribute.
- 🟡 **Open data, verify terms** — government/public works; reuse generally fine, license not always explicit.
- 🔴 **Paid / proprietary** — reference or licensed-integration only; not redistributable.
- ⚠️ **Unverified** — could not be confirmed during research; check manually before relying on it.

> 🛠️ **Want to just download everything and dedup it for fine-tuning?** Use
> [`../scripts/download_sources.sh`](../scripts/download_sources.sh) (bulk pull,
> overlap-aware) then [`../scripts/dedup_clean.py`](../scripts/dedup_clean.py)
> (dedup + noise/license/language filtering). See [`../scripts/README.md`](../scripts/README.md).

> **Source note:** Entries marked ⚠️ (e.g. the KanoonGPT HF dataset, the Kaggle SC
> dataset license, IL-TUR's exact license, and the two Indic items below) returned
> HTTP 403 to automated fetching and were not in the search index. Open them in a
> browser to confirm size/license before use. Document stats are quoted from project
> READMEs / papers / the AWS Open Data Registry, not independently re-counted.

---

## 1. 📜 Court Judgments & Case-Law Datasets (bulk text)

These are the backbone for both a case-law database and LLM pretraining.

### 1.1 Indian High Court Judgments (vanga / OpenJustice / AWS Open Data) — ✅
- **URL:** https://github.com/vanga/indian-high-court-judgments · doc: `opendata/docs/dataset.md` · AWS: https://registry.opendata.aws/indian-high-court-judgments/
- **Contains:** ~**17.8 million** judgments from **25 High Courts (45 benches)**, scraped from the eCourts Judgments & Orders portal + mobile API. Coverage ~1950–2025, updated daily.
- **Format:** PDF (text) + JSON (raw metadata) + **Parquet** (queryable metadata) + tar bulk archives. ~**1.25 TiB** total.
- **License:** **CC-BY-4.0**.
- **Access:** Public AWS S3, no credentials: `aws s3 sync --no-sign-request s3://...` on `data/tar/`, `metadata/tar/`, `metadata/parquet/`. Query metadata with Athena / DuckDB / pandas. Dedupe by `(cnr, decision_date, order_number)`.
- **Suitability:** **Best large-scale HC corpus.** Excellent for DB + pretraining. Text is in PDFs → OCR/extraction needed; very large.

### 1.2 Indian Supreme Court Judgments (vanga / AWS) — ✅
- **URL:** https://github.com/vanga/indian-supreme-court-judgments · tutorials: `opendata/tutorials/` · AWS: https://registry.opendata.aws/indian-supreme-court-judgments/ · Kaggle mirror: https://www.kaggle.com/datasets/vangap/indian-supreme-court-judgments
- **Contains:** ~**35,000** SC judgments, 1950–present (some regional-language versions). ~**52 GB**.
- **Format:** PDF + JSON per year; **Parquet** metadata (19 fields: title, parties, decision date, judges, citations, disposal nature, languages…); tar bulk.
- **License:** **CC-BY-4.0**.
- **Access:** Public AWS S3 `--no-sign-request`; direct HTTPS to S3 objects; Athena for metadata.
- **Suitability:** Clean, well-structured, metadata-rich SC corpus. Strong DB + fine-tuning base. *(This is the "repetitive" one you flagged — it's the SC sibling of 1.1, same lineage/tooling, not a duplicate.)*

### 1.3 OpenJustice India + `ecourts` toolkit — ✅ (data) / GPL (code)
- **URLs:** org https://github.com/openjustice-in · site https://openjustice-in.github.io/ · scraper https://github.com/openjustice-in/ecourts · API docs https://openjustice-in.github.io/ecourts/ecourts.html
- **Contains:** Project to open up Indian law datasets, "Common-Crawl-style" periodic releases. Hosts the HC set (same lineage as 1.1) **and a lower-court dataset of ~81M e-Courts case records** (district & sessions courts and below).
- **`ecourts` repo:** Python IR toolkit/CLI to scrape case info, orders, judgments, cause lists from `ecourts.gov.in`; search by case type / FIR / filing number / act type / date; `courts.csv` lists supported courts. Intentionally single-threaded (rate-limit friendly).
- **Format:** Python lib (PyPI) + CLI; datasets in PDF/JSON/Parquet/tar.
- **License:** Tool **GPL-3.0-or-later** (applies to code, not scraped output); datasets follow CC-BY-4.0.
- **Access:** `pip install ecourts`; `ecourts --help`.
- **Suitability:** Best route to **fresh/custom scraping incl. district courts** (hard to get in bulk elsewhere). Mind CAPTCHAs/rate limits.

### 1.4 KanoonGPT — `indian-case-laws` (HuggingFace) — ⚠️
- **URL:** https://huggingface.co/datasets/KanoonGPT/indian-case-laws
- **Status:** **UNVERIFIED.** Page returned 403 and isn't in search indexes. KanoonGPT (kanoongpt.in) is an Indian legal-AI platform; whether this dataset is public and its size/courts/license **could not be confirmed**. Check the card manually before use.

### 1.5 Kaggle — SC Judgments India 1950–2024 (adarshsingh0903) — ⚠️ license
- **URL:** https://www.kaggle.com/datasets/adarshsingh0903/legal-dataset-sc-judgments-india-19502024
- **Contains:** SC judgments 1950–2024/25, collected from Indian Kanoon; claims ~98% coverage of IK's SC section. Per-year folders of **PDFs**.
- **License:** **⚠️ Unverified** — confirm on the Kaggle page (and IK's terms, since sourced from Indian Kanoon) before any redistribution/training.
- **Access:** `kaggle datasets download ...` (Kaggle account/API key).
- **Suitability:** Convenient SC bulk; **overlaps heavily with 1.2** — prefer 1.2 (clear CC-BY) unless you need this specific packaging.

---

## 2. 🧪 Legal NLP Benchmarks & Labeled Datasets (fine-tuning / eval)

### 2.1 ILDC / CJPE — Court Judgment Prediction & Explanation (ACL 2021) — research use
- **Paper:** https://aclanthology.org/2021.acl-long.313/ · **Code/data:** https://github.com/Exploration-Lab/CJPE
- **Contains:** **ILDC** (Indian Legal Documents Corpus) — ~**35,000** SC documents annotated with the original decision (accepted/rejected); ILDC-single & ILDC-multi variants; expert-annotated test set with gold explanations. Task: **CJPE** (prediction + explanation).
- **Suitability:** Widely-cited supervised benchmark for judgment-prediction fine-tuning/eval. License: check repo (academic/research typical).

### 2.2 IL-TUR — Indian Legal Text Understanding & Reasoning benchmark (ACL 2024) — ⚠️ NC license
- **URL:** https://huggingface.co/datasets/Exploration-Lab/IL-TUR · paper https://aclanthology.org/2024.acl-long.618/ · site https://exploration-lab.github.io/IL-TUR/
- **Contains:** Unified **8-task** benchmark: L-NER, Rhetorical Role (RR), CJPE, Bail Prediction (Hindi), Legal Statute Identification, Prior Case Retrieval, Summarization, Legal MT (En→Indic). Mono (En/Hi) + multilingual (9 Indian languages). Public leaderboard.
- **License:** Reported **CC BY-NC-SA** (non-commercial) — **verify before any commercial fine-tuning**.
- **Suitability:** The standard Indian-legal-NLP eval/fine-tuning suite.

### 2.3 HLDC — Hindi Legal Documents Corpus (Findings of ACL 2022) — research use
- **URL:** https://github.com/Exploration-Lab/HLDC · paper https://aclanthology.org/2022.findings-acl.278/
- **Contains:** **912,568** Hindi legal documents (UP district courts) with bail-prediction and summarization tasks.
- **Suitability:** Leading open **Hindi** legal corpus; great for Hindi/multilingual legal NLP. License: check repo.

### 2.4 OpenNyAI — InJudgements + Legal NER / Rhetorical Roles — ⚠️ verify
- **URL:** https://huggingface.co/datasets/opennyaiorg/InJudgements_dataset (+ OpenNyAI's Legal-NER and rhetorical-role datasets/tooling)
- **Contains:** Representative sample of Indian judgments (full text + Indian Kanoon URLs). Row count/license unverified.
- **Suitability:** HF-native judgment text for RAG/fine-tuning prototyping; OpenNyAI's NER + rhetorical-role data are valuable companions.

### 2.5 Indian legal encoder models (ready-made backbones) — MIT (verify)
- **InLegalBERT:** https://huggingface.co/law-ai/InLegalBERT · **InCaseLawBERT:** https://huggingface.co/law-ai/InCaseLawBERT (law-ai, IIT-KGP). Paper: arXiv:2209.06049.
- **Contains:** BERT-base (~110M) pretrained on ~**5.4M** Indian legal docs (~**27 GB**, SC + many HCs, 1950–2019, all domains). InLegalBERT generally outperforms InCaseLawBERT on the benchmark tasks.
- **Suitability:** Drop-in **encoders** for embeddings / classification / NER / retrieval. Not generative — for a generative LLM, rebuild a corpus from §1 sources.

### 2.6 Community HF datasets (low confidence — vet each) — ⚠️
`viber1/indian-law-dataset`, `ninadn/indian-legal`, `nisaar/Lawyer_GPT_India`, `harshitv804/Indian_Penal_Code`, `vihaannnn/Indian-Supreme-Court-Judgements-Chunked` — instruction/QA or chunked-text formats for LLM fine-tuning/RAG. **Sizes & licenses unverified; check provenance.**

---

## 3. 🏛️ Official / Government Primary Sources

### 3.1 India Code — bare acts (Central + State) — 🟡
- **URL:** https://www.indiacode.nic.in/
- **Contains:** All enforced **Central, State & UT Acts** + subordinate legislation (rules, regulations, notifications, ordinances), kept amendment-current (incl. Bharatiya Nyaya Sanhita 2023). DSpace-based, searchable.
- **Format:** Bare-act text + PDFs (DSpace; OAI-PMH harvest often technically possible — unverified).
- **License:** Government content; formal reuse license not explicit (🟡 presumed reusable).
- **Suitability:** **Best authoritative statutory backbone** for DB + LLM corpus. Acquire via scraping/DSpace harvest.

### 3.2 Indian Kanoon API — 🔴 paid (public-domain judgments)
- **URL:** https://indiankanoon.org/ · API https://api.indiankanoon.org/
- **Contains:** Largest aggregated Indian case-law DB — **30M+** orders/judgments (SC, HCs, tribunals) + central acts. Offers enriched HTML + **paragraph-level classification** into 8 categories (Facts, Issues, Arguments, Precedent/Law Analysis, Conclusion, …).
- **License/cost:** **Commercial paid API** (free ₹500 credit; non-commercial use may get ₹10,000/mo free after verification). Underlying judgments are public-domain govt works, but API access is contractual — confirm redistribution rights for training.
- **Access:** REST API + `ikapi.py` client.
- **Suitability:** **Excellent** programmatic bulk-text route; paragraph classification is gold for structured training. Budget for cost.

### 3.3 eCourts Services / Judgment Search — 🟡 (CAPTCHA-gated)
- **URL:** https://services.ecourts.gov.in/ · High Courts https://hcservices.ecourts.gov.in/ (NIC)
- **Contains:** Real-time case status, orders, **final judgments**, cause lists, caveats (District + High Courts). *(This is what the Chakshi backend in this repo automates.)*
- **License/access:** Public judgments; no open-data license; CAPTCHA-gated, no official public citizen API. For bulk, prefer DevDataLab (metadata, §3.7) or Indian Kanoon (text, §3.2).

### 3.4 e-Gazette (Gazette of India) — 🟡
- **URL:** https://egazette.gov.in/
- **Contains:** Official Central Govt gazette notifications, regulations, notices (legally admissible). States run parallel portals.
- **Format:** Digitally-signed PDFs (need OCR/parse). No public API; bulk = scraping.
- **Suitability:** Delegated-legislation / notifications layer of the KB.

### 3.5 PRS Legislative Research — ✅ CC BY 4.0
- **URL:** https://prsindia.org/ (Bills `/billtrack`, Acts `/acts/parliament`, report summaries `/policy/report-summaries`)
- **Contains:** Thousands of **Bills & Acts**, one-page bill/committee-report **summaries**, legislative & budget analyses, state briefs, monthly policy reviews.
- **License:** **CC BY 4.0** — cleanest reuse license in this catalog.
- **Suitability:** **Very high** — ideal for KB + fine-tuning (esp. legislative summarization). Scrape under CC BY.

### 3.6 National Judicial Data Grid (NJDG) — 🟡 (gov API)
- **URL:** https://njdg.ecourts.gov.in/
- **Contains:** Official **case statistics** (instituted/disposed/pending) for SC, HCs, District & Taluka courts; civil/criminal, age-wise; updated daily (~2018–present).
- **Access:** Open API, but provisioned to **Central/State Govt departments** via department IDs/keys (not fully self-serve). Dashboards public.
- **Suitability:** Judicial **statistics/analytics** layer. Not a text corpus.

### 3.7 Development Data Lab — Judicial Data (eCourts) — ✅ ODbL
- **URL:** https://www.devdatalab.org/judicial-data
- **Contains:** **~81.2M** lower-judiciary cases (all District & Sessions courts), scraped from eCourts, **2010–2018**. Per-case fields: state/district/court, case type, filing/registration/hearing/decision dates, parties, judge position, acts & sections, disposition, inferred gender. Fully anonymized.
- **License:** **ODbL** (contents under DbCL). Extended (non-anonymized) access by application.
- **Access:** Bulk download, no account.
- **Suitability:** **Excellent** structured judicial DB + analytics. Metadata-rich but **not full judgment text** — pair with §1/§3.2 for training text.

### 3.8 Law Commission of India — Reports — 🟡
- **URL:** https://lawcommissionofindia.nic.in/law-commission-reports/
- **Contains:** **277 reports** (1955–present) on legal reform, English + Hindi. PDFs.
- **Suitability:** Rich **secondary/reasoning corpus** (reform rationale). Needs OCR/parse.

### 3.9 Parliament Debates — Digital Sansad / eParlib / RS Debates — 🟡
- **URLs:** https://eparlib.sansad.in/ · https://sansad.in/ · https://rsdebate.nic.in/ · https://videolibrary.sansad.in/
- **Contains:** Lok Sabha debates 1952–2025 (text, En/Hi), Rajya Sabha debates to 2025, committee reports, budget speeches, session videos.
- **Format:** eParlib on DSpace (text + scans). No documented public API.
- **Suitability:** Large **deliberative/legislative-intent corpus**. Mixed text/scan quality.

### 3.10 Open Government Data (OGD) Platform — data.gov.in — 🟡 (API key)
- **URL:** https://www.data.gov.in/apis
- **Contains:** Single point for GoI ministry datasets (100k+ resources). Law/court/gazette datasets are scattered by ministry — search **Ministry of Law & Justice** for current holdings.
- **Format:** CSV/XLS/JSON/XML/RDF. **License:** Government Open Data License – India (NDSAP), commercial use allowed.
- **Access:** **API key** (register → My Account). Python helper: `datagovindia`.
- **Suitability:** Structured govt/statistical enrichment. *(You shared login creds for this — see "Account access" note at the bottom; I did not log in.)*

---

## 4. 🌐 Open-Data Platforms & Aggregators

### 4.1 JusticeHub (CivicDataLab) — 🟡 per-dataset
- **URL:** https://justicehub.in/dataset?groups=laws · docs https://docs.justicehub.in/ · GitHub https://github.com/justicehub-in
- **Contains:** Curated open justice datasets. Flagships: **KHOJ — "Know Your High Court Judges"** (1,700+ HC judges 1993–2021, 43 variables) and **Budgets for Justice**. The "laws" group curates law-related sets (exact list unverified).
- **Format:** CSV/tabular on **CKAN** (typically has a data API + bulk download). **Suitability:** Structured **metadata/reference tables** (judges, budgets), not raw text for fine-tuning.

### 4.2 Indian Kanoon — see §3.2 (the dominant free aggregator).

### 4.3 e-SCR (Electronic Supreme Court Reports) — 🟡
- Official SC portal of free, PDF-downloadable SC judgments **with neutral citations** and search. Good authoritative citation source.

### 4.4 eCourtsIndia.com / NJDG / vLex Open — mixed
- Secondary aggregators surfaced by the JuriGram listicle (§6). Authoritative free options are India Code (statutes), e-SCR (SC), Indian Kanoon (everything), NJDG (stats).

### 4.5 US Library of Congress — South Asian / India law guides — 🟡 (discovery only)
- **URLs:** https://guides.loc.gov/south-asian-collection/e-resources · https://guides.loc.gov/law-india
- **Contains:** Research *guides* (pointer lists), not datasets — Indian case law, statutes, Constituent Assembly Debates, commission reports, treaties. Many linked DBs are subscription/on-site.
- **Suitability:** **Discovery/roadmap only** to identify primary sources to acquire elsewhere.

---

## 5. 🗣️ Indic-Language Corpora (for multilingual fine-tuning)

To make the model read/reason in Indian languages, pair the legal corpora above with
general Indic-language pretraining + instruction data. **AI4Bharat (IIT Madras)** is the
center of gravity here.

### 5.1 Sangraha (AI4Bharat / IndicLLMSuite) — pretraining — ✅ (verify card)
- **URL:** https://huggingface.co/datasets/ai4bharat/sangraha · suite https://github.com/AI4Bharat/IndicLLMSuite
- **Contains:** Largest cleaned Indic pretraining corpus — **≈251B tokens, 22 languages** (Verified web + OCR'd Indic PDFs + transcribed audio/video + translations).
- **Suitability:** **Best for continued pretraining** of Indic LLMs.

### 5.2 IndicAlign (AI4Bharat) — instruction tuning — ✅ (verify card)
- **URL:** https://huggingface.co/datasets/ai4bharat/indic-align
- **Contains:** Largest Indic SFT set — **≈74.7M** prompt-response pairs (IndicAlign-Instruct + IndicAlign-Toxic safety), 22 languages.
- **Suitability:** **Primary SFT / instruction-tuning** resource for Indic chat models.

### 5.3 IndicCorp v1/v2 (AI4Bharat) — pretraining — ✅
- **URL:** https://ai4bharat.iitm.ac.in/ · IndicBERT repo https://github.com/AI4Bharat/IndicBERT
- **Contains:** Monolingual crawl: **v1 ≈9B tokens (~12 langs)**, **v2 ≈20.9B tokens (24 langs)**.
- **Suitability:** Strong pretraining; v2 broadest coverage.

### 5.4 Samanantar (AI4Bharat) — parallel/MT — ✅ CC-BY-4.0
- **URL:** https://huggingface.co/datasets/ai4bharat/samanantar
- **Contains:** Largest public parallel corpus — **≈49.7M** En↔Indic sentence pairs (11 languages).
- **Suitability:** **MT fine-tuning**, cross-lingual alignment, back-translation.

### 5.5 Naamapadam (AI4Bharat) — NER — ✅ (verify)
- **URL:** https://huggingface.co/datasets/ai4bharat/naamapadam (+ model `ai4bharat/IndicNER`)
- **Contains:** Largest Indic **NER** set, 11 languages; manual test sets for 8. CoNLL scheme.
- **Suitability:** NER fine-tuning/eval (useful for extracting parties/courts/acts).

### 5.6 IndicGLUE / IndicXTREME (AI4Bharat) — benchmarks — ✅
- **URL:** https://huggingface.co/datasets/ai4bharat/indic_glue
- **Contains:** NLU benchmark across 11 Indian languages (IndicXTREME is the newer 9-task / 105-eval-set successor, paired with IndicCorp v2 / IndicBERT v2).
- **Suitability:** **Evaluation** of fine-tuned Indic models.

### 5.7 Indic-HPLT v1 (`ashtok897/indic-hplt-v1`) — pretraining — ⚠️
- **URL:** https://huggingface.co/datasets/ashtok897/indic-hplt-v1
- **Contains:** Community Indic subset of the **HPLT** web-crawl corpus (Hindi, Bengali, Tamil, Telugu, Marathi, Gujarati, Punjabi, Nepali, Odia, Sanskrit, etc.).
- **Size/format/license:** **⚠️ Unverified** (HF blocked in research). Upstream HPLT text is typically **CC0**, web-crawl scale — confirm on the card; dedup/filter before use.
- **Suitability:** Continued pretraining (raw web text), not instruction data.

### 5.8 BIP39 display wordlists in ~31 Indian languages — lexical — ⚠️
- **Reddit:** https://www.reddit.com/r/datasets/comments/1u0dli1/opensourcing_bip39_display_wordlists_in_31/
- **What it is:** The 2048-word BIP39 mnemonic standard localized into ~31 Indian languages — a small, clean, **aligned wordlist** (one concept per row across languages).
- **Status:** **⚠️ Unverified** — hosting repo, exact language list, format, and license could not be confirmed (Reddit blocked in research). Open the link to capture the canonical repo + license.
- **Suitability:** Niche auxiliary resource for **transliteration / lexicon coverage / UI localization**, not pretraining.

---

## 6. 🛠️ Tools — ingestion, scraping, citation, OCR, redaction

### 6.1 Free Law Project suite (free.law) — ✅ BSD-2-Clause
US nonprofit; battle-tested Python toolchain (powers CourtListener). Permissive and reusable, but parsers are **US-court-specific** — reuse the architecture, rewrite India-specific rules.
- **eyecite** — https://github.com/freelawproject/eyecite — citation extraction (full/short/`id.`/`supra`/statutory). Adapt regexes for AIR/SCC/neutral citations.
- **juriscraper** — https://github.com/freelawproject/juriscraper — court-scraper framework pattern (target eCourts/HC portals/IK for India).
- **doctor** — https://github.com/freelawproject/doctor — **directly reusable** Django OCR/extraction microservice (PDF/DOC/RTF/HTML, Tesseract OCR, redaction detection, thumbnails). Add Indic Tesseract packs.
- **x-ray** — https://github.com/freelawproject/x-ray — detects bad PDF redactions (PII leakage). Format-agnostic; use as a privacy QA gate.
- **inception** — https://github.com/freelawproject/inception — embeddings microservice for legal docs (SentenceTransformers, chunking). Pair with a multilingual/Indic encoder for RAG.

### 6.2 openjustice-in/ecourts — ✅ (GPL) — see §1.3
The most **India-specific open scraper** — better starting point than juriscraper for eCourts ingestion.

### 6.3 Indic text-processing — ✅
- **Indic NLP Library** — https://github.com/anoopkunchukuttan/indic_nlp_library (MIT) — normalization, script ID/conversion, tokenization, transliteration.
- **AI4Bharat IndicNLP / catalog** — https://indicnlp.ai4bharat.org/ · https://ai4bharat.github.io/indicnlp_catalog/ — Indic models/datasets index + IndicBERT.
- **Indic OCR** — https://github.com/indic-ocr — OCR for Indian scripts where vanilla Tesseract underperforms.

### 6.4 Apify court-scraping actors — 🔴 hosted/paid
- The console link you shared (`actors/zKl0dXKIK7XwViLCX`) needs login — exact actor **unverified**. Closest public match: **India Court Judgments Scraper** (`apify.com/jungle_synthesizer/india-ecourts-judgments-scraper`) — a hosted wrapper around the Indian Kanoon API (needs your own IK API token + Apify account). Also `codingfrontend/ecourts-case-scraper`, `parseforge/court-records-ecourt-india-scraper` (CNR lookup via Playwright + OCR).
- **Trade-off:** fast managed bulk ingestion, but cost stacks (Apify + IK fees) and depends on IK's terms.

---

## 7. 📚 Academic & Reference (read, mostly not bulk-ingestible)

### 7.1 Economic & Political Weekly (EPW) on JSTOR — 🔴
- **URL:** https://www.jstor.org/journal/econpoliweek
- High-quality legal/policy commentary (from 1966). **Paywalled**; JSTOR restricts bulk/automated download — **text mining needs explicit permission** (JSTOR Constellate/TDM). Not for unlicensed training.

### 7.2 Key Indian legal-NLP papers
- **ILDC/CJPE** (ACL 2021) — §2.1 · **IL-TUR** (ACL 2024) — §2.2 · **HLDC** (Findings ACL 2022) — §2.3 · **InLegalBERT** (arXiv:2209.06049) — §2.5.

---

## 8. 🔴 Commercial databases (reference / licensed integration only)

- **AIR Online (All India Reporter)** — https://www.aironline.in/ — digital AIR since 1922; SC (1950–), all HCs (stated 1904–), Privy Council (1900–1950), bare acts, headnotes, citation cross-indexing. **Subscription; copyrighted headnotes.** Authoritative **AIR citation standard** — use as a validation/reference target, not redistributable data.
- **Vaquill** — https://vaquill.com/ (AI at https://www.vaquill.ai/) — AI legal research (cited Q&A, contract review, citation-graph/treatment, export to Bluebook/OSCOLA/Indian standards). Claims 20M+ cases, **open REST API + MCP connector** (vendor figures unverified). Potential **data-API/MCP integration partner**. *(Vaquill-AI also publishes an `awesome-legaltech` list on GitHub.)*
- **JuriGram listicle** — https://jurigram.com/advocates/resources/legal-research/free-legal-open-source-databases-india — a roundup that points to Indian Kanoon, e-SCR, India Code, eCourts, NJDG, eCourtsIndia.com, vLex Open (premium: SCC Online, Manupatra).

---

## 9. 🎯 Recommended build strategy ("almighty Indian law knowledge")

**Priority by licensing + readiness:**
- **Cleanest license + ready text:** PRS (CC BY 4.0, §3.5), DevDataLab eCourts (ODbL, §3.7).
- **Best bulk judgment text:** vanga/OpenJustice **HC + SC** on AWS (CC-BY-4.0, §1.1/1.2); Indian Kanoon API for enriched/classified text (paid, §3.2).
- **Statute backbone:** India Code bare acts (§3.1) + e-Gazette notifications (§3.4).
- **Statistics layer:** NJDG (§3.6), data.gov.in (§3.10), JusticeHub (§4.1).
- **Secondary reasoning:** Law Commission reports (§3.8), Parliament debates (§3.9).
- **Avoid for unlicensed training:** EPW/JSTOR (§7.1), AIR Online / Vaquill (§8).

**Suggested pipeline:**
1. **Ingest** — pull AWS HC/SC corpora (1.1/1.2) + India Code (3.1) + PRS (3.5); scrape gaps (district courts) via `openjustice-in/ecourts` (1.3).
2. **Extract/OCR** — Free Law `doctor` (6.1) + Indic OCR (6.3) for scanned PDFs; normalize with Indic NLP Library.
3. **Structure** — Parquet metadata + paragraph/rhetorical-role labels (OpenNyAI 2.4, IK classification 3.2); citation graph via adapted `eyecite` (6.1).
4. **Privacy QA** — run `x-ray` (6.1) to catch bad redactions/PII before publishing.
5. **Index/RAG** — embeddings via `inception` (6.1) + an Indic/legal encoder (InLegalBERT 2.5).
6. **Fine-tune** — continued pretraining on Sangraha + IndicCorp v2 (5.1/5.3) + the legal corpus; SFT on IndicAlign (5.2); supervised on ILDC/CJPE + HLDC (2.1/2.3); **evaluate** on IL-TUR + IndicGLUE/IndicXTREME (2.2/5.6).

**License hygiene:** keep a per-document provenance + license field. Don't mix NC-licensed
(IL-TUR), paid-API (Indian Kanoon), or paywalled (EPW/AIR) material into a corpus you intend
to redistribute or use commercially. When in doubt, treat government primary works as the
safe base and aggregator/journal content as reference only.

---

## 📌 Account access note

You shared a data.gov.in login (and offered to provide an OTP). **I have not logged in** —
credentials shouldn't be used or stored by an automated agent, and an OTP-gated session
isn't something to script. To use data.gov.in programmatically, the clean path is: register,
generate an **API key** under *My Account*, and call the dataset APIs (or use the
`datagovindia` Python helper) — no interactive login needed. If you want, I can wire a small
fetcher around a specific data.gov.in resource ID once you have the API key.

---

*Contributions: add new sources under the right section with the same fields
(URL · contains · format · license · access · suitability), and mark anything
unverified with ⚠️ until confirmed.*
