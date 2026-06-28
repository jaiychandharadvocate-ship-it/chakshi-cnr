# Chakshi — Security & Data Foundation: Implementation Report

**Date:** 2026-06-28
**Branch:** `claude/chakshi-security-foundation-b3lhcs`
**Scope:** Vetting of the proposed 19-point security foundation against the *actual* codebase, plus a concrete, ordered implementation plan.
**Status:** Analysis only. Nothing built, committed, or deployed.

---

## 0. Executive summary

The proposal describes Chakshi as a multi-tenant legal-AI SaaS (offices, matters, RAG, Sixth Sense, payments, desktop app) and instructs the developer to "harden the current codebase."

**The current codebase is not that system.** It is a single-file, stateless **eCourts scraper chatbot**:

- `backend/app.py` (~4,060 lines) + `frontend/index.html` (~1,287 lines).
- FastAPI drives a headless Playwright Chromium against `services.ecourts.gov.in`, walks the CAPTCHA flow, scrapes case details/orders, and returns them.
- OpenAI `gpt-4o-mini` is used only to parse the user's chat intent.
- **No database, no auth, no users, no tenancy, no file storage, no RAG, no audit log.** State lives in two in-process Python dicts (`SESSIONS`, `CONVERSATIONS`).

**Consequence:** ~80% of the proposal cannot be "hardened" because the thing to harden does not exist. RLS needs tables; RAG isolation needs RAG; storage rules need uploads. The proposal is a correct **destination**, but the wrong **starting instruction**.

This report therefore splits work into:
- **Track A** — fix what is actually live today (the scraper).
- **Track B** — build the foundation the proposal wants, in buildable order.
- **Track C** — the advanced layers, gated behind B.

---

## 1. Reality check: proposal vs. repo

| Proposal assumes | Actually in the repo |
|---|---|
| Supabase / Postgres, tables, RLS | **No database.** State = `SESSIONS`, `CONVERSATIONS` dicts in memory |
| office / matter / client / user / role models | **None** — no concept of a user |
| Auth, JWT, RBAC | **None** — every endpoint anonymous |
| Document upload / private storage / signed URLs | **None** (it downloads court PDFs from eCourts; no user store) |
| RAG, embeddings, chunks, vector search | **None** |
| AI gateway | Backend-only OpenAI call exists (good), but no formal gateway |
| Audit logs | **None** |
| Secrets manager, staging/prod split, monitoring | **None** |

---

## 2. Real risks in the code that exists TODAY (fix regardless of the big plan)

| # | Issue | Location | Severity |
|---|---|---|---|
| A1 | **Entire API unauthenticated** — all routes take anonymous input | all `@app.*` routes | High |
| A2 | **CORS wildcard + credentials** — `allow_origins=["*"]` with `allow_credentials=True` (invalid/unsafe combo) | `app.py:37` | High |
| A3 | **Anonymous server-side browser proxy, no rate limiting** — anyone can drive your paid Chromium against eCourts (cost / IP-ban / ToS risk) | search routes | High |
| A4 | **JS injection into Playwright context** — user `party_name`/`year` interpolated into `page.evaluate(f"...'{party_name}'...")` | `app.py:687–702`, `791–855` | Medium |
| A5 | **All state in-memory** — restart wipes sessions; no horizontal scaling; litigant PII held unencrypted in process | `SESSIONS`/`CONVERSATIONS` globals | Medium |
| A6 | **Secret name mismatch** — code reads `OPENAI_API_KEY_MY`, `.env.example` documents `OPENAI_API_KEY` → silent AI degradation | `app.py:26` vs `.env.example` | Low |
| A7 | **PII / DPDP exposure** — Indian litigant data handled with no consent record, retention limit, or access log | whole flow | Medium (legal) |

**Currently OK (preserve):** `.env` is git-ignored; no secrets are tracked in git history; the frontend embeds no keys and only calls relative backend paths; the OpenAI key never reaches the browser.

---

## 3. What to implement — full list, by track

### TRACK A — Harden the live scraper (do now; days)

1. **Lock CORS** to explicit known origins; remove wildcard-with-credentials.
2. **Gate the API** — minimum an API key or Cloudflare Access in front; ideally fold into Track B auth once it exists.
3. **Rate-limit** the browser-driving routes per IP / per key (protect cost + eCourts relationship).
4. **Parameterize `page.evaluate`** — pass values as arguments, never f-string interpolation.
5. **Validate & bound inputs** — length/charset limits on `party_name`, `year`, CNR format check before use.
6. **Fix the env var mismatch** (`OPENAI_API_KEY_MY` → `OPENAI_API_KEY`) and document it.
7. **PII retention policy** — drop scraped personal data when the session ends; don't log it.
8. **Structured request logging** (without PII) for abuse detection.

### TRACK B — The foundation the proposal wants (buildable order)

> Each step is a precondition for the next. Do not skip ahead.

**B1. Database + tenancy model (the true Requirement #1)**
Introduce Supabase/Postgres. Core tables:
```
offices(id, name, created_at)
users(id, office_id, email, ... , created_at)
roles(id, key, label)                 -- Owner, Advocate Admin, Advocate,
user_roles(user_id, role_id, office_id)   Junior, Clerk, Intern, Client, SuperAdmin
matters(id, office_id, title, created_by, created_at, updated_at)
clients(id, office_id, matter_id, ...)
```
Every sensitive table carries: `office_id`, `matter_id` (where applicable), `created_by`, `created_at`, `updated_at`.

**B2. Authentication**
Supabase Auth (or equivalent). Issue JWTs carrying `user_id` + `office_id`. Frontend → backend → DB; no anonymous write paths.

**B3. RBAC**
Role → permission matrix enforced server-side. Default-deny. Clerk/Intern must NOT see strategy notes, Sixth Sense findings, billing.

**B4. RLS on every private table — "no RLS = no prod table"**
Policies keyed on `office_id` (and `matter_id` / role where needed). Add from the first table so it's never retrofitted.

**B5. API permission helpers**
```
assertUserCanAccessOffice(user_id, office_id, action)
assertUserCanAccessMatter(user_id, matter_id, action)
assertUserCanAccessDocument(user_id, document_id, action)
```
Called by every route touching private data — defense in depth behind RLS.

**B6. Append-only audit log**
```
audit_logs(id, office_id, matter_id, user_id, action, target_type,
           target_id, timestamp, ip_address, metadata)
```
Log actions, never full case content. Append-only (no UPDATE/DELETE grant), especially for Sixth Sense.

**B7. Secrets & environment separation**
Move all keys to a secret manager; separate dev/staging/prod keys; never expose the service-role key to the frontend; enable GitHub secret scanning; define a rotation policy.

### TRACK C — Advanced layers (only after B is green)

**C1. Private document storage** — private buckets, short-lived signed URLs, server-side permission check before any URL is minted, file-type/size validation, malware scan, upload audit. Schema:
```
documents(id, office_id, matter_id, uploaded_by, file_path, file_type,
          file_size, storage_bucket, ocr_status, classification_status,
          access_level, created_at)
```
Rule: a document is not AI-readable until linked to `office_id` + `matter_id`.

**C2. Document pipeline** — upload → validate → store private → record → OCR → extract → clean → classify → legal chunk → embed → store chunks with tenancy → expose to RAG.

**C3. RAG isolation** — every chunk carries `office_id`/`matter_id`/`source_type`; every query filters by `office_id` + `matter_id` + permitted scope + role. Split shared legal corpus (Bare Acts, public judgments) from private matter corpus; private corpus is never globally searchable.

**C4. AI gateway (formalized)** — single backend path: permission check → matter access → RAG retrieval → model routing → token/cost limits → output verification → citation enforcement → prompt-injection defense → non-sensitive logging.

**C5. Payments access control**, **C6. Sixth Sense controls** (no matter→no dossier, no source→no finding, unconfirmed cannot export, audit cannot be deleted), then desktop app / Qwen workstation.

### TRACK D — Cross-cutting (start in B, mature through C)

- **Automated security test suite:** Office A cannot read Office B's matters/docs/chats/chunks/drafts/findings; user cannot reach unassigned matter; clerk cannot reach restricted finding; guessed document ID fails; expired signed URL fails; revoked user loses access; private chunks never leak into another matter's answer; prompt-injection inside an uploaded PDF fails; AI refuses unsupported legal claims (no source → no conclusion).
- **Monitoring:** error tracking (Sentry), failed-login/unusual-download/payment-webhook alerts, AI cost + RAG-failure + document-pipeline alerts. Scale to the app's size — don't stand up Grafana for one endpoint.
- **Secure dev workflow:** issue → branch → tests → security review for sensitive code → review → merge. Mandatory review for auth, RLS, payments, file access, RAG filters, AI gateway, Sixth Sense, migrations.

---

## 4. Priority ordering (corrected for this repo)

1. **Track A** — secure the live scraper (open API, CORS, rate limit, injection, PII). *Now.*
2. **B1 → B2 → B3 → B4 → B5 → B6 → B7** — DB + tenancy, auth, RBAC, RLS, API helpers, audit, secrets. *This is the real foundation; nothing in the proposal is buildable before B1.*
3. **C1 → C2 → C3 → C4** — storage, pipeline, RAG isolation, AI gateway.
4. **D** test suite + monitoring — begin alongside B, mature through C.
5. **C5+** payments, Sixth Sense, desktop, Qwen — last.

---

## 5. What NOT to do yet (premature for current state)

- RLS policies / cross-office test users — **needs B1 first.**
- RAG isolation, chunk/embedding tables, Trust Cards — **needs documents + RAG first.**
- OCR, classification, malware scanning — **needs an upload feature first.**
- Sixth Sense dossier/export controls — **needs Sixth Sense first.**
- Full Grafana/Prometheus/PostHog stack — **disproportionate** for one scraper; add with real users.

---

## 6. One-line verdict

The proposal's thesis — *foundation before fancy features* — is correct, and its destination architecture is sound. But the honest first move is **not "harden the codebase"**; it is **build the tenancy + auth + database layer that everything else depends on**, while separately fixing the handful of real issues in the scraper running today (open + uncORS'd API, no auth, JS injection, in-memory PII).
