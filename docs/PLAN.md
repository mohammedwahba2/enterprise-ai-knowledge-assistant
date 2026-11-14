# Enterprise AI Knowledge Assistant — Product & Architecture Plan

**Status: planning only. Nothing is implemented.** Every feature below is marked **[planned]**. This document is the proposal for your approval (see §14).

Dev machine detected: Apple Silicon (arm64), 10 cores, **16 GB unified RAM**. Several decisions below are driven by that.

## Decision log — approved by you (revision 3)

| # | Decision |
|---|---|
| D1 | **Arabic + English from day one.** Full RTL across navigation, chat, document metadata, search. Multilingual embeddings; Arabic retrieval quality is measured, not assumed (§7.5, §11). |
| D2 | **No LangChain**; custom lightweight RAG. **Ollama runs natively on macOS**, not in Docker. |
| D3 | PostgreSQL + pgvector, hybrid retrieval, S3-compatible object store (originally MinIO, see D12), Caddy, Postgres RLS. **Authorization before retrieval; document-level permissions enforced** (§2, §9). |
| D4 | **Out of initial release:** SSO, billing, external connectors. **OCR postponed**, but scanned/unreadable documents are *detected and surfaced*, never silently dropped (§7.1, §7.6). |
| D5 | **Single monorepo, public on GitHub.** Synthetic demo data only; no private data, credentials or secrets ever committed (§12.1). |
| D6 | **Design reference audit done, 3 mockup directions produced; frontend implementation is blocked until you approve a direction** (§14, `docs/design/AUDIT.md`, `docs/design/mockups/`). |
| D7 | Quality plan expanded: unit, integration, tenant isolation, document permissions, Arabic/English retrieval eval, answer quality eval, hallucination/unsupported-answer tests, performance (§11). |

| D8 | **Design direction: A — The Reading Room**, refined with B's ⌘K palette + dense library table and C's "Needs attention" section + support-state indicators (§14, `docs/design/final/`). |
| D9 | **License: Apache-2.0.** |
| D10 | **Embedding bake-off includes an Arabic-focused embedding model** alongside multilingual ones (§7.5, §11.5). |
| D11 | **Western digits (0-9) are the default** everywhere in the UI; **Arabic-Indic (٠-٩) and Persian digits are normalized to Western in search *and* input**, and are a per-user display option (§7.5). |
| D12 | **Object store changed from MinIO to SeaweedFS** (S3 API, Apache-2.0) during stage 1, with your approval: MinIO no longer publishes pull-able container images and its community edition is unmaintained/archived upstream. Application code only depends on the S3 API, so the store stays swappable. |

Still **[planned]**: all product code. **[done]**: plan, design audit, final refined mockup. **Awaiting your approval of the final mockup before any application code.**

---

## 0. Recommended changes to your proposed stack (explained first)

| Your proposal | Recommendation | Why |
|---|---|---|
| LangChain or alternative | **No LangChain. A thin, hand-written RAG pipeline** (plain Python modules, Pydantic models, official `ollama` client). | The product's core promise is *exact page-level provenance and refusal when unsupported*. That requires control over chunk metadata, filtering, scoring thresholds and prompt assembly. LangChain would sit between us and each of those, add churn (its APIs change often) and make tests harder. The pipeline is ~6 small functions; the abstraction cost exceeds the benefit. For a portfolio, showing you understand the mechanics is also stronger. |
| Ollama in Docker Compose | **Run Ollama natively on the host on macOS**; containerize it only on Linux/NVIDIA. | Docker Desktop on Mac cannot access Metal GPU; containerized Ollama is CPU-only and several times slower. Compose reaches the host via `host.docker.internal`. Config: `OLLAMA_BASE_URL`. |
| pgvector | Keep. **Add Postgres full-text search** in the same DB for hybrid retrieval. | Pure vector search misses exact identifiers (policy numbers, clause IDs). Hybrid (vector + BM25-style FTS, fused with RRF) is the single biggest quality win and costs no new infrastructure. |
| Celery + Redis | Keep. | Fits: long CPU/IO ingestion jobs, retries, progress. Redis also serves rate limiting and SSE pub/sub for ingestion progress. Alternative (Postgres-backed queue) is simpler but Celery is a recognized skill and you asked for it. |
| (not mentioned) | **Add SeaweedFS** (S3-compatible) for original files. | Do not store PDFs on the API container's disk or in Postgres. S3 API means production can swap to real S3 with config only. |
| (not mentioned) | **Add a reranker** (cross-encoder) in stage 6, behind a feature flag. | Cheap precision gain; measurable with the eval harness, so we keep it only if numbers justify it. |
| Next.js | Next.js App Router, but **FastAPI is the only API**; Next.js does not hold business logic. | Avoids two backends. Auth cookies are set by FastAPI behind one origin (reverse proxy). |

Everything else (FastAPI, PostgreSQL, TypeScript, Tailwind, Docker Compose) stays as proposed.

---

## 1. Product requirements and core features

**Vision:** an organization uploads internal documents; employees ask questions; the assistant answers *only* from those documents, citing document + page, and says "I can't find this in your documents" when evidence is insufficient.

### 1.1 MVP features (stages 1–10) — all [planned]
1. **Workspaces (organizations)** with isolated data.
2. **Authentication**: email + password, sessions, password reset, invitations.
3. **Roles & permissions** (§2).
4. **Document ingestion**: PDF, DOCX, PPTX, TXT/MD, (HTML optional). Drag-drop, multi-file, size limits, duplicate detection by SHA-256.
5. **Processing pipeline** with visible per-document status: `uploaded → parsing → chunking → embedding → ready | failed`, with retry and error reason.
6. **Collections** (folders/tags) and per-collection access control, so HR docs are not visible to everyone.
7. **Chat**: streamed answers, conversation history, follow-up questions (with query rewriting).
8. **Citations**: every claim linked to document, page, and the exact passage; clicking opens the source viewer at that page with the passage highlighted.
9. **Grounded refusal**: explicit "not found" answer when retrieval evidence is below threshold or the model reports no support.
10. **Answer feedback** (helpful / wrong / missing source) stored for evaluation.
11. **Admin**: members, roles, collections, document management, audit log, basic usage stats.

### 1.2 Explicitly out of scope (to avoid overengineering)
SSO/SAML, billing, OCR for scanned PDFs (stage 12 stretch, via Tesseract), connectors (SharePoint/Drive), agents/tool use, multi-LLM routing, mobile app, real-time collaboration.

### 1.3 Non-functional targets (initial, measured in stage 11)
- Time to first token < 3 s on the 16 GB reference machine (8B model, warm).
- Ingestion: 100-page PDF ready in < 3 min on CPU parsing + local embedding.
- Citation precision (cited passage actually supports the claim) ≥ 90 % on our eval set; refusal recall on unanswerable questions ≥ 90 %.
- Zero cross-tenant leakage in an automated test suite.

---

## 2. User roles and permission model

Roles are per-organization (a user may belong to several orgs).

| Capability | Owner | Admin | Editor | Member | Viewer |
|---|:-:|:-:|:-:|:-:|:-:|
| Delete org / transfer ownership | ✔ | | | | |
| Manage members & roles | ✔ | ✔ | | | |
| Manage collections & collection ACLs | ✔ | ✔ | | | |
| Upload / delete documents (in permitted collections) | ✔ | ✔ | ✔ | | |
| Ask questions, view sources | ✔ | ✔ | ✔ | ✔ | ✔ |
| View audit log, usage | ✔ | ✔ | | | |
| Give feedback on answers | ✔ | ✔ | ✔ | ✔ | |

**Document-level access:** each collection has visibility `org` (everyone) or `restricted` (listed users/groups). Retrieval **filters by accessible collection IDs in SQL before ranking**, so restricted content can never reach the LLM prompt of an unauthorized user. This is the most important security property of the product.

Implementation: a single `authorize(principal, action, resource)` policy module (pure functions, unit-tested), not scattered `if role ==` checks.

---

## 3. System architecture

```
 Browser ── HTTPS ──► Caddy (reverse proxy, one origin)
                       ├─ /        ► Next.js (SSR/UI)
                       └─ /api/*   ► FastAPI (REST + SSE)
                                      │
            ┌─────────────────────────┼───────────────────────────┐
            ▼                         ▼                           ▼
     PostgreSQL 16 + pgvector     Redis                      SeaweedFS (S3)
     (data, vectors, FTS, RLS)    (broker, rate-limit,       (original files,
                                   progress pub/sub)          page images)
            ▲                         ▲
            │                         │
        Celery workers ───────────────┘
        (parse → chunk → embed → index)
            │
            ▼
        Ollama (host-native on macOS) — LLM + embedding models
```

- **Modular monolith**, not microservices: one FastAPI codebase, one worker image (same code, different entrypoint). Right-sized for the team and goals.
- **Streaming** chat answers over **SSE** (simpler than WebSockets, proxy-friendly, one-directional is all we need).
- **Clean Architecture layering** per module: `api` (routers, schemas) → `application` (use cases) → `domain` (entities, policies) → `infrastructure` (SQLAlchemy repos, Ollama client, S3 client). Dependencies point inward; AI and storage are behind small `Protocol` interfaces *only where we actually have two implementations or need a test fake* (LLM client, embedder, blob store).

---

## 4. Database schema (PostgreSQL 16 + pgvector)

Conventions: UUIDv7 primary keys, `created_at/updated_at timestamptz`, soft delete only for documents (for audit), every tenant table has `organization_id NOT NULL`.

**Identity & tenancy**
- `users` (id, email citext unique, password_hash [argon2id], display_name, is_active, email_verified_at)
- `organizations` (id, name, slug unique, settings jsonb)
- `memberships` (id, organization_id, user_id, role enum, status; unique(org,user))
- `invitations` (id, organization_id, email, role, token_hash, expires_at, accepted_at)
- `refresh_tokens` (id, user_id, family_id, token_hash, expires_at, revoked_at, user_agent, ip) — rotation with reuse detection
- `password_resets` (id, user_id, token_hash, expires_at, used_at)

**Knowledge**
- `collections` (id, organization_id, name, description, visibility enum[org|restricted])
- `collection_members` (collection_id, user_id, organization_id) — for restricted collections
- `documents` (id, organization_id, collection_id, title, original_filename, mime_type, size_bytes, sha256, storage_key, status enum, error_code, error_detail, page_count, uploaded_by, deleted_at; unique(org, collection, sha256) where not deleted)
- `ingestion_jobs` (id, organization_id, document_id, stage, attempt, started_at, finished_at, error) — one row per run; supports retries/observability
- `document_pages` (id, organization_id, document_id, page_number, text, char_count, extraction_state enum[text|image_only|garbled], image_area_ratio) — kept so the viewer and re-chunking do not require re-parsing; `documents.status` also includes `ready_partial`, `unsupported_scanned`, `unsupported_garbled`, and `documents.error_code` is one of `NO_TEXT_LAYER|GARBLED_TEXT|ENCRYPTED|CORRUPT|UNSUPPORTED_TYPE`
- `users.locale` (`en|ar`), `users.digit_style`; `organizations.default_locale`. `chunks.lang` (`ar|en|mixed`) and `chunks.content_search` (normalized text used for lexical search; original `content` is what is displayed and quoted)
- `chunks` (id, organization_id, document_id, collection_id [denormalized for fast ACL filter], page_start, page_end, chunk_index, heading_path text, content text, token_count, content_tsv tsvector generated, embedding vector(1024), embedding_model text, bbox jsonb nullable)
  - Indexes: HNSW on `embedding` (cosine), GIN on `content_tsv`, btree (organization_id, collection_id)

**Conversations**
- `conversations` (id, organization_id, user_id, title, created_at)
- `messages` (id, conversation_id, organization_id, role enum[user|assistant], content, status enum[streaming|complete|refused|error], model, retrieval_params jsonb, latency_ms, prompt_tokens, completion_tokens)
- `message_citations` (id, message_id, chunk_id, document_id, page_start, page_end, quote text, marker int, support_score real) — snapshot of what was cited, so history survives re-indexing
- `retrieval_logs` (id, message_id, chunk_id, rank, vector_score, fts_score, fused_score, rerank_score, used bool) — debugging and eval
- `feedback` (id, message_id, user_id, rating, reason enum, comment)

**Operations**
- `audit_events` (id, organization_id, actor_id, action, target_type, target_id, metadata jsonb, ip, created_at) — append-only
- `eval_sets`, `eval_questions`, `eval_runs`, `eval_results` — internal quality harness (stage 11); not a user feature

**Row-Level Security:** every tenant table has `ENABLE ROW LEVEL SECURITY` with policy `organization_id = current_setting('app.current_org')::uuid`. The API sets it per request/transaction. The application DB role is **not** a superuser and does not bypass RLS. Application-level filters remain as the first layer; RLS is the safety net.

**Embedding dimension note:** `bge-m3` = 1024 dims. Changing model requires re-embedding; `embedding_model` column plus a re-index job makes that a supported operation, not a migration crisis.

---

## 5. Backend module structure (`backend/`)

```
backend/
  app/
    main.py                  # app factory, middleware, routers
    core/                    # config (pydantic-settings), logging (structlog), errors, security, db session, rls context
    modules/
      identity/              # users, auth, sessions, password reset
      tenancy/               # organizations, memberships, invitations
      access/                # roles, policies (authorize()), collection ACLs
      documents/             # upload, storage, metadata, lifecycle
      ingestion/             # pipeline stages, Celery tasks, progress
      knowledge/             # chunks, embeddings, indexing, retrieval (hybrid, rerank)
      assistant/             # query rewrite, prompt assembly, generation, citation verification, refusal
      conversations/         # chats, messages, feedback
      audit/                 # audit events
      admin/                 # usage stats, settings
      evaluation/            # offline eval harness (CLI, not public API)
    infrastructure/
      llm/ (ollama client + fake)   embeddings/   storage/ (s3 + fake)   parsers/ (pdf, docx, pptx, text)
  migrations/ (Alembic)
  tests/ (unit, integration w/ testcontainers, e2e, security, eval)
  pyproject.toml (uv), Dockerfile
```

Stack: Python 3.12, FastAPI, Pydantic v2, SQLAlchemy 2 (async) + asyncpg, Alembic, Celery 5, structlog, `uv` for dependencies, Ruff + mypy (strict) for quality.

---

## 6. Frontend application structure (`frontend/`)

Next.js App Router, TypeScript strict, Tailwind v4 with design tokens as CSS variables, Radix primitives for accessible behavior (own styling, not a pre-skinned kit), TanStack Query for server state, `openapi-typescript` to generate types from FastAPI's OpenAPI schema (end-to-end typing without hand-writing DTOs), Zod for form validation, `react-pdf`/pdf.js for the source viewer.

```
frontend/src/
  app/
    (auth)/ sign-in, sign-up, accept-invite, reset
    (app)/[org]/
      ask/ [conversationId]        # primary surface
      library/ [collectionId]/[documentId]
      admin/ members, collections, audit, usage, settings
  features/ chat, citations, source-viewer, library, upload, members, audit
  components/ ui (own primitives), layout
  lib/ api client, sse, auth, formatting
  styles/ tokens.css
```

---

## 7. AI / RAG architecture and processing pipeline

### 7.1 Ingestion pipeline (Celery chain, each stage idempotent and retryable)
1. **Validate**: magic-byte MIME check, size/page limits, SHA-256 dedupe, (optional) ClamAV scan.
2. **Store** original in SeaweedFS under `org/{org}/doc/{id}`.
3. **Parse** per page → `document_pages`. PDF: PyMuPDF (fast, page-accurate); DOCX/PPTX: `python-docx`/`python-pptx` (DOCX has no real pages — we use rendered pagination via LibreOffice → PDF conversion so page numbers match what users see; this is a known risk, §10). Tables extracted as Markdown rows.
4. **Chunk**: structure-aware (headings first, then paragraphs), target ~400–600 tokens, ~12 % overlap, **never crossing page boundaries without recording `page_start/page_end`**. Each chunk carries `heading_path` and is embedded as `"{title} > {heading_path}\n{content}"` (contextual prefix).
5. **Embed** in batches with `bge-m3` via Ollama (multilingual, handles Arabic/English — relevant for your Serva context; falls back to `nomic-embed-text` if you want English-only and smaller).
6. **Index**: insert chunks + tsvector; mark document `ready`. Progress published to Redis → SSE → UI.
Failure at any stage sets `status=failed`, an `error_code` the UI can explain, and keeps earlier artifacts for retry from the failed stage.

### 7.2 Query pipeline
1. **Authorize**: compute accessible `collection_ids` for the principal (+ optional UI scope filter).
2. **Rewrite** (only when history exists): LLM turns a follow-up into a standalone query. Small prompt, low temperature.
3. **Hybrid retrieve**: top-40 vector (cosine, HNSW) ∪ top-40 FTS, **both filtered by `organization_id` and `collection_id IN (...)` in SQL**; fuse with Reciprocal Rank Fusion.
4. **Rerank** top-20 → top-6 with `bge-reranker-v2-m3` (flagged; kept only if eval shows gain).
5. **Gate**: if best rerank/fused score < calibrated threshold → **refuse without calling the generator** ("I couldn't find this in your documents"), return near-miss sources as "possibly related".
6. **Generate** with a strict prompt: numbered source blocks `[1] (Doc, p. 12) …`; instruct to answer only from sources, cite `[n]` per claim, and output the literal token `NO_ANSWER` if unsupported. Low temperature. Streamed.
7. **Verify citations** (deterministic): parse `[n]` markers, drop any that don't map to supplied chunks, and check each cited sentence has lexical/embedding overlap with its chunk above a threshold; unverifiable citations are removed and the answer flagged "partially supported" rather than silently trusted.
8. **Persist** message, citations (with quote snapshot), retrieval logs.

### 7.3 Models (16 GB machine)
- Generation: **Qwen3-8B (Q4)** primary candidate; Llama 3.1 8B as the comparison baseline. ~5–6 GB resident. We choose by running both on the eval set, not by reputation.
- Embeddings: `bge-m3` (~1.2 GB). Reranker ~1.1 GB, run via a small Python service/`sentence-transformers` on CPU/MPS.
- Context budget: ≤ 6 chunks × ~500 tokens + prompt ≈ 4–5k tokens; set `num_ctx` explicitly (Ollama's default is small and silently truncates — a classic silent-failure bug we guard against with a token-count assertion).

### 7.5 Arabic + English (D1)
**Parsing/normalization (high risk, tested explicitly)**
- PDF text extraction of Arabic often returns *presentation-form glyphs* (U+FB50–FEFF) and sometimes visual (reversed) order. Pipeline step: Unicode **NFKC** to fold presentation forms, then a bidi-order sanity check (detect reversed runs by comparing against a dictionary/common-word heuristic); golden-file tests with synthetic Arabic PDFs produced by at least two generators (Word, LibreOffice/Chromium).
- **Search normalization** applied identically to index and query text (stored alongside the original, which is what users see and what citations quote): strip tashkeel (diacritics) and tatweel, unify alef variants (أ إ آ → ا), ya/alef-maqsura (ى → ي), optionally ta-marbuta/ha, and map **Arabic-Indic and Persian digits ↔ ASCII digits** (so "٢٥" matches "25").
- Per-chunk **language detection** (`lang` column: `ar|en|mixed`). Mixed-language documents are normal in Gulf organizations, so chunk-level, not document-level.

**Retrieval**
- Embedding bake-off (D10), chosen by Arabic / English / cross-lingual recall@k, not by reputation:
  1. **bge-m3** (multilingual, 1024-d, cross-lingual; default candidate, available through Ollama).
  2. **multilingual-e5-large** (multilingual challenger).
  3. **An Arabic-focused embedding model.** Candidates to be verified at the start of stage 6 (license, size, dimension, RAM fit, serving path): e.g. the Arabic-tuned BERT-family sentence embedders such as GATE-AraBERT or Arabic-Triplet-Matryoshka variants. These are not in the Ollama library as far as I know, so they would be served through a small `sentence-transformers` embedding service behind the same `Embedder` interface. I have not yet verified any candidate's license or Arabic benchmark claims; that is a stage-6 task.
  A purely Arabic model may be weaker on English and cross-lingual queries; the eval tells us whether to use one model or route by language (the schema already stores `embedding_model` per chunk, so a two-model setup is possible but is only adopted if it wins by a clear margin, given the added complexity).
- Lexical leg: Postgres built-in **`arabic`** (Snowball) and **`english`** text-search configs. `content_tsv` is generated per chunk using the config matching `lang`; queries run against both configs and results are fused. Quality of the Snowball Arabic stemmer is limited, so the eval decides whether it beats `simple` + our normalization; this is an open measurement, not a promise.
- Reranker (`bge-reranker-v2-m3`) is multilingual; kept only if it improves Arabic *and* English metrics.

**Generation**
- Answer language follows the **question language** (override: user setting). Citations quote the source passage in its original language, never translated silently; a translated gloss, if shown, is labelled as such.
- Model shortlist must demonstrate acceptable Arabic fluency and faithfulness in the eval; Qwen3-8B vs Llama 3.1 8B vs (optional) an Arabic-focused model (e.g. Jais/ALLaM class, if it fits in 16 GB at Q4). Arabic faithfulness may be worse than English with small models; we will report both honestly.

**UI/RTL** — logical CSS properties only (no `left/right`), `dir` set per document from user locale and **per message** from detected text direction (mixed content uses `dir="auto"` / `<bdi>` for inline fragments such as English product names inside Arabic sentences), mirrored icons only where directional, Arabic-appropriate typography and leading, **Western digits by default** (user option: Arabic-Indic display), locale-aware dates (Gregorian default; Hijri deferred), source documents rendered in their own direction (an Arabic PDF page is RTL even in an English UI, and vice versa).

**Digits (D11):** (1) *Display:* Western by default, a per-user `digit_style` preference switches to Arabic-Indic. (2) *Input:* any of ٠١٢٣٤٥٦٧٨٩ / ۰۱۲۳۴۵۶۷۸۹ typed in the search box, ask box, filters or forms is normalized to 0-9 before use (and the original text is kept in the stored message). (3) *Search:* the normalizer maps all three digit sets to ASCII at index and query time so "٢٥ يوماً" matches "25 days", and Arabic decimal/thousands separators (٫ ٬) are mapped to `.`/`,`. (4) *Citations* quote the source passage verbatim, so a quote may contain Arabic-Indic digits even when the UI uses Western ones. Tested in §11.1 and §11.5. Verified in the mockups; automated in Playwright visual/RTL checks (§11).

### 7.6 Scanned and unreadable documents (D4)
During parsing, each page is classified: `text` (extractable characters ≥ threshold), `image_only` (≈ no text and images covering most of the page), or `garbled` (text present but failing a sanity check, e.g. high ratio of private-use/replacement characters, which is the typical broken-Arabic-font signature).
- Document status becomes `ready`, `ready_partial` (some pages unusable) or **`unsupported_scanned`** / `unsupported_garbled`. Never `ready` with silently missing pages.
- Unusable pages are **excluded from the index**, recorded in `document_pages.extraction_state`, and shown in the UI ("12 pages have no text layer. OCR isn't enabled.") with the exact page list.
- Answers never imply coverage of excluded pages. If a question's retrieval is empty *and* the library contains unsupported documents in the accessible scope, the "not found" state says that some documents couldn't be searched.
- Admins get a "Needs attention" list; the API returns a stable `error_code` (`NO_TEXT_LAYER`, `GARBLED_TEXT`, `ENCRYPTED`, `CORRUPT`, `UNSUPPORTED_TYPE`). Password-protected and corrupt files get the same treatment.
- Tests: fixtures for each failure class; assert status, excluded pages, UI/API messaging and absence from retrieval.

### 7.4 Honesty about limits
Small local models can still paraphrase beyond the sources. The gate + citation verification + eval harness reduce this; they do not make it zero. The UI will show confidence state (supported / partially supported / not found) rather than implying certainty.

---

## 8. API endpoint plan (REST, `/api/v1`, OpenAPI-documented)

**Auth** `POST /auth/sign-up` · `/auth/sign-in` · `/auth/refresh` · `/auth/sign-out` · `/auth/password/forgot` · `/auth/password/reset` · `GET /auth/me`
**Orgs** `POST /orgs` · `GET /orgs` · `GET/PATCH /orgs/{org}` · members: `GET/PATCH/DELETE /orgs/{org}/members/{id}` · `POST /orgs/{org}/invitations` · `POST /invitations/{token}/accept`
**Collections** `GET/POST /orgs/{org}/collections` · `PATCH/DELETE …/{id}` · `PUT …/{id}/members`
**Documents** `POST /orgs/{org}/documents` (multipart, multi-file) · `GET …/documents` (filter, paginate) · `GET/DELETE …/documents/{id}` · `POST …/{id}/reprocess` · `GET …/{id}/file` (short-lived signed URL) · `GET …/{id}/pages/{n}` · `GET …/documents/events` (SSE progress)
**Chat** `POST /orgs/{org}/conversations` · `GET …/conversations` · `GET/DELETE …/{id}` · `POST …/{id}/messages` (SSE stream: `retrieval`, `token`, `citations`, `done`, `error`) · `POST /messages/{id}/feedback`
**Admin** `GET /orgs/{org}/audit-events` · `GET /orgs/{org}/usage` · `GET /health/live|ready`

Conventions: cursor pagination, RFC 7807 problem+json errors with stable `code`s, idempotency key on upload, request IDs in every response and log line.

---

## 9. Security and multi-tenancy strategy

- **Isolation (defense in depth):** (1) tenant ID from the verified membership, never from client input; (2) explicit `organization_id` filters in repositories; (3) Postgres RLS; (4) object keys namespaced by org and only reachable via signed URLs minted after authorization; (5) vector/FTS queries always pre-filtered. A dedicated **cross-tenant test suite** attempts every endpoint with another org's IDs and must return 404.
- **Authn:** argon2id; short-lived access JWT (15 min) + rotating refresh token in `HttpOnly; Secure; SameSite=Lax` cookies; refresh reuse detection revokes the token family; login rate limiting and lockout backoff (Redis).
- **CSRF:** SameSite cookies + double-submit token on state-changing requests; strict CORS (single origin).
- **Uploads:** magic-byte validation, size/page caps, no execution, parsers run in the worker (not the API), optional ClamAV, filenames never used as paths.
- **Prompt injection from documents:** retrieved text is treated as data, delimited in the prompt, and the model has **no tools** — worst case is a bad answer, not an action. Documented as a residual risk.
- **Secrets & config:** env-only via pydantic-settings, `.env.example`, no secrets in images; dependency audit (`pip-audit`, `npm audit`) and Trivy image scan in CI.
- **Privacy:** all inference local; no document text leaves the deployment. Logs never contain document content or prompts by default (opt-in debug flag).
- **Auditability:** append-only `audit_events` for sign-ins, role changes, uploads, deletions, ACL changes, exports.

---

## 10. Technical risks and hardware requirements

| Risk | Impact | Mitigation |
|---|---|---|
| Page numbers for DOCX/PPTX don't exist natively | Wrong citations | Convert to PDF via LibreOffice headless for pagination; store the rendered PDF as the viewer source. Document the limitation. |
| Scanned PDFs have no text | Empty docs | Detect and flag `needs_ocr`; Tesseract OCR as stage-12 stretch. |
| Small local LLM hallucination / ignores instructions | Core promise at risk | Retrieval gate, `NO_ANSWER` protocol, citation verifier, eval-driven model choice, UI confidence states. |
| Ollama default context truncation | Silent quality loss | Explicit `num_ctx`, token budget assertions, test. |
| 16 GB RAM with LLM + embedder + reranker + Postgres + workers | Swapping, slow | Sequence model loads (`OLLAMA_KEEP_ALIVE`, one generation at a time), small quantized models, reranker optional, worker concurrency 1–2. |
| Docker on Mac has no GPU | Slow inference if containerized | Host-native Ollama (§0). |
| Ingestion of big files blocks others | Latency | Dedicated Celery queues (`ingest`, `embed`), per-org concurrency limits. |
| Embedding model change = re-index | Ops pain | `embedding_model` column + reindex task. |
| Retrieval quality unknown until measured | Shipping blind | Eval harness (stage 11) with a real public corpus and unanswerable questions; run in CI nightly. |

### 10.1 Performance considerations and budgets (targets until measured on the reference machine)
| Area | Budget / approach |
|---|---|
| Retrieval (excluding LLM) | p95 < 300 ms at 50k chunks, < 800 ms at 500k; HNSW (`m=16, ef_construction=64`, tune `ef_search`); the **ACL filter is the main hazard**: a restrictive filter with HNSW can return too few rows (post-filtering). Mitigation: `hnsw.iterative_scan` (pgvector ≥ 0.8) or partial/partitioned indexes by org; verified with a test that restricted users still get a full top-k. |
| Time to first token | < 3 s warm; model kept loaded (`OLLAMA_KEEP_ALIVE`); one generation at a time on the reference box with a bounded queue and a visible "waiting" state. |
| Generation | ~20–35 tok/s expected on 8B Q4; stream from first token; cap output tokens. |
| Ingestion | Parse/chunk/embed in separate queues; embedding batches sized to memory; target ≥ 5 pages/s parse, embedding throughput measured; per-org concurrency cap so one large upload can't starve others. |
| Memory (16 GB) | Budget: LLM ≈ 6 GB, embedder ≈ 1.2 GB, reranker ≈ 1.1 GB, Postgres 1–2 GB, rest for app/OS. Profile in stage 11; reranker is optional if it breaks the budget. |
| Database | Index build times and size tracked; `maintenance_work_mem` raised during bulk load; vacuum/analyze after reindex; embeddings stored as `halfvec` if size becomes an issue (decision gated on eval). |
| Caching | Query-embedding cache (short TTL) and per-org accessible-collections cache (invalidated on ACL change); no answer caching (staleness vs. permissions risk). |
| Frontend | Streaming render without layout shift, virtualized library tables, PDF pages rendered lazily, Arabic/Latin fonts subset and `font-display: swap`; budget: LCP < 2 s on LAN, JS < 200 KB gzip on the Ask route. |
| Measurement | Load tests (k6/Locust) for retrieval and ingestion, structured timing logs per pipeline step (rewrite/retrieve/rerank/generate), a stage-gated performance report in `docs/perf/`. |

**Hardware:** *Reference dev* (your Mac): 16 GB, works with 8B Q4 + bge-m3; expect ~20–35 tok/s generation. *Minimum:* 16 GB RAM, 4 cores, 30 GB disk. *Comfortable demo:* 32 GB or an NVIDIA GPU with 12 GB+ VRAM. 14B+ models are not realistic on the reference machine.

---

## 11. Testing and quality strategy (D7)

Layers run in CI in this order: static → unit → integration → security → e2e. The AI evaluation is separate (needs a local model), run on demand and nightly on the dev machine, with results committed as JSON so regressions are visible in diffs.

### 11.1 Unit tests
`authorize()` policy table (every role × action), chunker (Hypothesis properties: no chunk crosses a page without recording `page_start/page_end`, no text lost, size bounds), RRF fusion, Arabic normalizer (tashkeel/alef/digits, idempotence), language detector, page classifier (text/image_only/garbled), citation parser/verifier, prompt/token-budget builder, error-code mapping.

### 11.2 Integration tests (real Postgres+pgvector, Redis, SeaweedFS via testcontainers; no mocks of the database)
Repositories, migrations up/down, Celery pipeline end to end with a *deterministic test embedder* (tests only), HNSW/FTS queries, object-store round trip, SSE streaming contract, upload edge cases (duplicate, oversize, wrong magic bytes, encrypted, corrupt).

### 11.3 Tenant isolation tests (release-blocking)
- **Endpoint matrix**: auto-generated from the OpenAPI schema; for every route with a resource ID, call it as a user of org B with org A's IDs → must be 404 (never 403, to avoid existence leaks). A route missing from the matrix fails CI.
- **RLS tests**: connect as the non-superuser app role with `app.current_org` set to B; direct SQL `SELECT/UPDATE/DELETE` against every tenant table must see/affect zero org-A rows; a request with the setting unset must see nothing. A CI check fails if any table with `organization_id` lacks an RLS policy.
- **Retrieval isolation**: seed two orgs with near-identical documents; the same query as each org returns only its own chunks, in vector, FTS and hybrid paths; the reranker and the prompt builder receive only authorized chunks (asserted at the function boundary).
- **Storage isolation**: signed URLs for another org's object keys cannot be minted; keys outside the tenant prefix are rejected.
- **Cache/queue isolation**: Redis keys and Celery task payloads carry the org ID; a worker rejects tasks whose org doesn't match the document's.

### 11.4 Document permission tests
- Matrix over `collection.visibility` (org/restricted) × membership × role × operation (list, view metadata, download, retrieve, cite, delete, reprocess).
- **Pre-retrieval enforcement**: a restricted document's text must never appear in the *prompt sent to the LLM* for an unauthorized user (the LLM client is wrapped in a test recorder that fails the test if a forbidden chunk ID or canary string appears).
- **Canary strings**: every restricted test document embeds a unique canary phrase; assertions search responses, SSE streams, logs, citations, retrieval logs and conversation history.
- **Revocation**: removing a user from a collection immediately removes it from retrieval, and from *existing conversation citations* (citation quote hidden/redacted when the user loses access, re-checked on every read).
- Moving a document between collections updates the denormalized `chunks.collection_id` atomically (tested under concurrency).
- Deleted documents disappear from retrieval within one request and are purged from vectors/objects by a background job (tested).

### 11.5 Arabic and English retrieval evaluation
- **Corpus (synthetic, committed)**: ~15 documents in three groups: English-only, Arabic-only, and **parallel EN/AR versions of the same policies** (lets us isolate language effects), plus mixed-language documents and tables. Generated from templates + hand-written facts so every answer has a known page. No real company data.
- **Question set**: ≥ 150 questions, balanced: EN→EN, AR→AR, EN→AR and AR→EN (cross-lingual), exact-identifier lookups (policy numbers, Arabic-Indic digits), paraphrases, multi-passage questions, and typos/diacritic variants. Each has gold document + gold page(s).
- **Metrics per language pair**: recall@5/10, MRR, nDCG, page-level hit rate. Ablations: vector only vs FTS only vs hybrid; with/without normalization (including digit folding); `arabic` config vs `simple`; **bge-m3 vs multilingual-e5-large vs an Arabic-focused embedder** (and a language-routed pair if it earns its keep); reranker on/off. The question set includes digit-variant pairs (same question typed with Western / Arabic-Indic / Persian digits) that must return identical results. Output is a table committed to `docs/eval/`.
- **Acceptance gates (initial, to be revised with data):** Arabic recall@5 within 10 points of English; cross-lingual recall@5 ≥ 80 %; any ablation that doesn't earn its complexity is removed.
- **PDF extraction tests**: Arabic PDFs from different generators must round-trip to the expected normalized text (catches reversed/presentation-form output).

### 11.6 AI answer-quality evaluation
- Same question set with gold answers. Measured: **answer correctness** (key facts present), **faithfulness** (every claim supported by cited passages), **citation precision/recall** (cited page is a gold page; no gold evidence missing), **answer-language correctness**, latency.
- Judging: deterministic checks first (key facts via regex/normalized match, citation page ∈ gold set); an LLM judge only for faithfulness, run **offline with a model different from the generator**, with a hand-labelled calibration subset (~40 items) to report judge agreement. Judge limits are reported, not hidden.
- Model bake-off (Qwen3-8B, Llama 3.1 8B, optional Arabic-focused model) uses this exact set; the winner and its numbers are recorded in the repo.

### 11.7 Hallucination and unsupported-answer tests
- **Unanswerable set (≥ 60 questions, both languages)** in four kinds: topic not in the corpus; plausible-but-absent detail ("What is the maternity leave for contractors?" when only employees are covered); *near-miss* (the corpus contains related but not answering text); questions whose answer exists **only in a document the user cannot access** (must be "not found", with no hint of existence).
- **Metrics**: refusal recall (target ≥ 90 %), false-refusal rate on answerable questions (target ≤ 10 %), unsupported-claim rate in answered responses, citation-verifier catch rate (inject fabricated `[n]` markers and wrong-page citations; verifier must strip/flag them).
- **Adversarial**: prompt-injection text inside documents ("ignore previous instructions…"), conflicting documents (versions disagreeing: answer must surface both or flag the conflict), numeric traps (similar numbers on neighbouring pages), questions that pressure the model to guess.
- **Threshold calibration**: the retrieval gate threshold is set from the ROC of answerable vs unanswerable questions on a *calibration* split and verified on a held-out *test* split, never tuned on the test split.
- Scanned-document case: question answerable only from an unsupported scanned PDF → "not found" plus the "some documents couldn't be searched" notice.

### 11.8 API, end-to-end and UI tests
httpx API tests; **Playwright** flows (sign-in → upload → ready → ask → citation opens evidence at the right page) run in **EN/LTR and AR/RTL**; RTL checks assert `dir`, mirrored layout, no horizontal overflow, and logical-property lint (a Stylelint rule forbids `left/right/margin-left/padding-right…`); screenshot baselines for key screens in both directions; axe accessibility checks; keyboard-only path for the main flow.

### 11.9 Security tests
Authz matrix per role, refresh-token reuse, login rate limiting, CSRF, upload abuse (zip bombs, polyglot files, oversized PDFs, huge page counts), SSRF/path traversal in filenames, secrets scanning (gitleaks) in CI because the repo is public.

### 11.10 Performance tests (see also §10)
Defined in §10.1; run with Locust/k6 against the Compose stack, with budgets recorded and tracked per release.

### 11.11 Static quality and CI
Ruff, mypy strict, ESLint, `tsc --noEmit`, Stylelint, pre-commit, GitHub Actions; coverage gate on domain/application layers (not a vanity global number); dependency and image scanning. Fakes (fake LLM/embedder) exist **only in tests** and are unreachable from any runtime configuration — the shipped app cannot return canned AI answers.

---

## 12. Docker and deployment strategy

- `docker-compose.yml` services: `caddy`, `frontend`, `api`, `worker`, `beat` (if scheduled cleanups needed), `postgres` (pgvector image), `redis`, `minio`, optional `reranker`, optional `ollama` (profile `linux-gpu`).
- Profiles: `dev` (hot reload, mounted source), `prod` (multi-stage slim images, non-root users, read-only FS where possible, healthchecks, resource limits).
- Migrations run as a one-shot `migrate` service before `api`.
- Makefile/`just` targets: `up`, `down`, `migrate`, `seed`, `test`, `eval`, `pull-models`.
- Config via `.env` (documented `.env.example`); volumes for Postgres, SeaweedFS, Redis.
- CI: lint, typecheck, tests, image build, vulnerability scan. CD is out of scope; the README documents a single-VM deployment (Compose + Caddy auto-TLS) as the reference.

### 12.1 Public-repository rules (D5)
- Monorepo layout: `backend/`, `frontend/`, `infra/`, `docs/`, `eval/` (synthetic corpora + question sets), `scripts/`.
- **Only synthetic data.** All demo documents (EN and AR) are authored for the repo or generated from templates, under a stated license. No real company, employee or customer data; no scraped copyrighted material.
- **Secrets:** `.env` is gitignored; only `.env.example` with obviously fake placeholder values; secrets generated at first run by a setup script. CI runs **gitleaks** and a pre-commit hook blocks commits containing high-entropy strings. Demo credentials are generated at seed time and printed locally, never committed.
- Uploaded files, model weights, volumes and eval outputs containing model text are gitignored; large fixtures are generated by scripts rather than stored.
- License: **Apache-2.0** (D9): `LICENSE` and `NOTICE` at the root, SPDX headers, plus track third-party licenses (fonts, models: Qwen3 Apache-2.0, Llama community license, bge-m3 MIT) in `docs/LICENSES.md`.
- Security policy file and issue templates; no internal hostnames, no real emails in fixtures (use `example.com`/`.test`).

---

## 13. Development roadmap — 12 stages

Each stage ends with something runnable, tests, and a short update to this doc marking what became **[implemented]**. **Stage 1 does not begin until you approve a design direction** (§14). Arabic/RTL and the evaluation harness are built in early, not bolted on late.

1. **Foundations** — monorepo, `uv`/pnpm, Docker Compose skeleton (Postgres+pgvector, Redis, SeaweedFS, Caddy), FastAPI + Next.js through Caddy, CI (lint, types, gitleaks), structured logging, **i18n framework (en/ar), logical-property CSS, font setup, `dir` handling, Stylelint no-physical-properties rule**, design tokens from the approved direction.
2. **Identity** — users, argon2id, sign-up/in/out, rotating refresh cookies, password reset, locale preference, auth screens in both languages/directions.
3. **Tenancy & RBAC** — orgs, memberships, invitations, `authorize()`, RLS on every tenant table, org switcher, **tenant-isolation matrix (generated from OpenAPI) and RLS tests from day one**.
4. **Collections, permissions & documents** — collections with `org|restricted` visibility and member lists, multipart upload, SeaweedFS, dedupe, library UI with statuses, signed URLs, **document-permission test matrix**.
5. **Parsing, chunking & unsupported-document handling** — Celery pipeline, PDF/DOCX/PPTX/TXT parsers, LibreOffice pagination, **Arabic extraction normalization**, page classifier (`text/image_only/garbled`), `ready_partial`/`unsupported_*` states and UI, structure-aware chunker, progress SSE.
6. **Embeddings, indexing & eval foundation** — Ollama embedder (bge-m3), pgvector HNSW + language-aware FTS + Arabic normalization, reindex task; **synthetic bilingual corpus and question sets authored here**, retrieval metrics harness.
7. **Retrieval** — permission-prefiltered hybrid search, RRF, optional reranker, admin retrieval-debug view; **Arabic/English/cross-lingual retrieval evaluation and ablations; embedder decision recorded**.
8. **Grounded generation** — prompts, answer-language handling, `NO_ANSWER` protocol, retrieval gate calibration (calibration/test split), citation verification, SSE streaming, persistence; **hallucination/unsupported-answer suite, model bake-off**.
9. **Chat experience** — conversation UI (RTL-correct, mixed-direction text), streaming render, citations, follow-up rewriting, feedback, support-state/"not found"/"some documents unsearchable" states.
10. **Source viewer & library polish** — PDF viewer with passage highlight (RTL pages), document detail, collection ACL UI, "Needs attention" list, ⌘K palette, keyboard-first navigation.
11. **Admin, hardening & performance** — members/roles UI, audit log, usage, rate limits, security review, load tests against §10.1 budgets, memory profiling, observability.
12. **Production readiness** — prod Compose profile, backup/restore doc, synthetic demo dataset + seed script, README/architecture docs, screenshots (EN + AR), OCR stretch, accessibility audit, license/third-party notices, final design pass.

---

## 14. Approved design direction — The Reading Room (refined) (D8)

Evidence: [`docs/design/AUDIT.md`](design/AUDIT.md) (live audit and the three explored directions). **Final refined mockup: [`docs/design/final/index.html`](design/final/index.html)** (see its README; five screens, EN/AR, desktop/tablet/mobile frames, ⌘K palette). *The earlier a/b/c mockups used Arabic-Indic digits and are superseded by the final mockup, which uses Western digits per D11.*

### 14.1 Identity kept from Direction A
Warm paper surfaces (`#F7F5F0` / raised `#FFFFFF` / sunken `#EFECE5`), ink `#17181B`, hairline borders instead of shadows, one accent **verdigris `#1F6F63`**, highlighter amber `#F6E7B4` for matched passages, **serif answers** (Newsreader / Noto Naskh Arabic), Geist UI type (IBM Plex Sans Arabic for Arabic UI), Geist Mono for page references. **Margin-note citations** beside the prose and a **side-by-side evidence pane** showing the real page.

### 14.2 Elements adopted
| From | Element | Where it appears |
|---|---|---|
| B | **⌘K command palette** | Global: ask, jump to document/conversation, actions (upload, switch language); search field in the top bar and tab bar on mobile |
| B | **Dense library table** | Library: document + filename, collection (lock icon if restricted), language tag, pages, status, updated; sticky header; collapses to stacked rows on mobile |
| C | **"Needs attention" section** | Ruled amber panel on Home and Library; sidebar item with count; mobile tab with badge. Lists scanned/partial/failed documents with the reason and an action |
| C | **Support-state indicators** | One consistent glyph + label system: **Supported** (filled check), **Partially supported** (half-filled), **Not found** (dashed circle), **Needs attention** (brick "!"). Used in answers, recent list, sidebar, palette |

### 14.3 Interaction model for citations and the evidence pane (as prototyped)
1. Each claim carries a numbered marker; each marker has a margin note (document, page, section, verbatim excerpt).
2. Clicking a marker **or** its margin note activates both (accent border and wash) and moves the evidence pane to that source page with the matched passage highlighted.
3. The pane shows the document language tag, "Citation n of N" with prev/next, **Copy quote**, and **Open in viewer** (full viewer with page thumbnails, cited pages marked, list of passages cited elsewhere).
4. Responsive behavior: **desktop ≥ 1100 px** — rail + thread (+ margin lane) + persistent 400 px pane; **tablet 700–1099 px** — icon rail, pane becomes an inline-end drawer with scrim; **mobile < 700 px** — bottom tab bar, margin notes become compact source rows, pane becomes a bottom sheet (84 % height), library becomes stacked rows, palette is near-full width.
5. "Not found" is a calm designed state: explicit statement, no guess, closest passages labelled "related, doesn't answer", and a notice when some documents couldn't be searched (ties to §7.6).

### 14.4 RTL and typography decisions (reviewed in EN and AR on all five screens)
- Logical CSS everywhere; the whole layout mirrors (rail, drawer side, table columns, arrows). Prev/next chevrons and the half-filled "partial" glyph mirror; checks, locks and search icons do not.
- Arabic UI font stack IBM Plex Sans Arabic; answers Noto Naskh Arabic at 19 px / 2.05 leading (vs 18.5 / 1.7 Latin); Geist Mono is **not** used for Arabic labels (those fall back to the UI face); uppercase/letter-spaced labels are disabled for Arabic.
- Keyboard hints (`⌘K`, `esc`) are isolated LTR so they don't scramble in RTL lines. Mixed-script strings use Unicode isolates (planned: `<bdi>`/`dir="auto"` in components).
- The evidence page takes the **document's** direction, not the UI's.
- Western digits throughout (D11).
- Not yet verified: real Arabic PDF rendering in pdf.js, very long Arabic filenames, and mixed Arabic/English table cells under real data; those get Playwright RTL checks in stage 9–10.

### 14.5 Known limitations of the mockup
Static HTML with canned content; fonts load from Google Fonts at view time; interactions are simple show/hide (no real PDF, no streaming states, no loading/error skeletons, no dark mode yet). Dark mode is deferred to after the first release unless you want it earlier. Accessibility (focus rings, contrast verification, screen-reader labels) is specified for stage 1 but not demonstrated here.

### 14.6 Stage 1 UI deliverables once approved
Design tokens (color, type incl. Arabic, spacing, radius, motion), component inventory on Radix primitives with our own styling (button, input, chip, support-state, status, table, drawer/sheet, palette, evidence pane, citation marker/note), EN/AR visual baselines, Stylelint rule banning physical properties.

---

## 15. Implemented vs planned

| Area | State |
|---|---|
| **Stage 1 — Foundations** (repo layout, Compose stack, FastAPI health/logging/errors, Next.js shell with EN/AR + RTL guards, tokens, CI) | **[implemented]**, see below |
| **Stage 2 — Identity** (sign-up/in/out, refresh rotation, password reset, locale preference, auth screens EN/AR) | **[implemented]**, awaiting your review; see §19 |
| **Stage 3 — Tenancy & RBAC** (orgs, memberships, invitations, policy module, RLS, org switcher, isolation suites) | **[implemented]**, awaiting your review; see §20 |
| **Stage 4 — Collections, permissions & documents** (collections + ACLs, upload, storage, dedupe, library UI, access-aware RLS) | **[implemented]**, awaiting your review; see §21 |
| Stages 5–12 | **[planned]** |
| Plan, decision log, design audit | **[done]** |
| Three exploratory mockups + **final refined mockup** (throwaway HTML, synthetic content) | **[done]**, not product code; final one awaits your approval |
| Hardware check of the dev machine | **[done]**: Apple Silicon, 16 GB, 10 cores |
| Arabic retrieval quality, model choice, thresholds | **[unknown until measured]** (stages 7–8) |

---

## 16. Final architecture review — risks and open items

**Reviewed and unchanged:** modular monolith, custom RAG, FastAPI/Postgres/pgvector, Celery+Redis, SeaweedFS, Caddy, RLS + app-level filters, SSE streaming.

**Risks raised or sharpened by your decisions**
1. **Arabic PDF extraction** (presentation forms, reversed order) can corrupt both retrieval and citation quotes. Mitigated by NFKC + bidi checks + golden tests (§7.5); remains the single most likely source of surprises.
2. **Small local LLMs in Arabic** may be less faithful than in English. We measure both and report both; if no 8B model passes the gates, options are a larger quantized model (needs more RAM than the reference machine) or tightening the answer format to extractive-leaning answers.
3. **ACL filtering with HNSW** can starve results (§10.1). Needs the iterative-scan/partition strategy and a dedicated test.
4. **Citations vs. revocation**: stored quotes could leak revoked content in history; handled by re-authorizing on every read (§11.4).
5. **DOCX pagination** depends on LibreOffice rendering; page numbers may differ from Word's. Documented limitation.
6. **Public repo**: demo corpus must be authored by us (EN + AR), which is real work (stage 6); gitleaks and `.env` hygiene enforced from stage 1.
7. **Evaluation validity**: synthetic questions can flatter the system; the unanswerable/near-miss/adversarial sets and a held-out split are there to counter that, and judge agreement is reported.

## 17. Status and next approval

Resolved: design direction (D8), license (D9), Arabic-focused embedder in the bake-off (D10), digits policy (D11).
Open (small, none blocking): dark mode timing (proposal: post-v1); project/repo name.

**Needed from you: approval of the final refined mockup** (`docs/design/final/`). No application code will be written until you approve it.

---

## 18. Stage 1 report (implemented)

**Built:** monorepo; Compose (Postgres+pgvector 0.8.7, Redis, SeaweedFS S3, FastAPI, Next.js, Caddy single origin); `/api/health/live|ready`; JSON structured logs with request IDs; RFC 7807 errors with stable codes; Next.js 16 + next-intl with `/en` and `/ar`, `dir` per locale, approved tokens and fonts (self-hosted via Fontsource), shell matching the mockup (rail, tablet icon rail, mobile tab bar, empty Home); RTL guards (Stylelint + ESLint) with tests; CI workflow; Apache-2.0 `LICENSE`/`NOTICE`; `.env.example` + secret-generating `scripts/init-env.sh`.

**Verified locally:** backend ruff/mypy-strict/14 tests; frontend eslint+stylelint/tsc/21 tests/`next build`; `docker compose up --wait` all six services healthy; `/api/health/ready` returns pgvector 0.8.7 + Redis + object store OK; `/` → `/en`; `/ar` serves `<html lang="ar" dir="rtl">`; screenshots of `/en` and `/ar` at desktop and phone width.

**Deviations and caveats (all deliberate, none silent):**
- D12: MinIO → SeaweedFS (no MinIO image can be pulled; approved by you).
- Local Python is 3.11 (container and CI use 3.12); `requires-python >=3.11`.
- TypeScript pinned to 5.9 because typescript-eslint does not yet support TS 7.
- Readiness checks the SeaweedFS master health endpoint; the S3 gateway is confirmed up (anonymous request returns 403) but an authenticated S3 round trip is not tested until stage 4.
- CI workflow, gitleaks and pre-commit config are written but **not yet run** (no GitHub remote, gitleaks not installed locally). Nothing is committed.
- Palette, library and other nav targets are intentionally absent or disabled until their stages.

### 18.1 Outstanding items carried forward (must not be forgotten)
| Item | When |
|---|---|
| Run **gitleaks** locally and verify the **GitHub Actions workflow** (backend, frontend, secrets-scan, compose jobs) | Before the **first push** |
| Verify **authenticated SeaweedFS S3** upload/download round trip (readiness currently checks only the master health endpoint) | **Stage 4** (storage) |
| Python **3.11 (local) vs 3.12 (container/CI)**: run the test suite on both and fix incompatibilities | Each stage; CI runs 3.12, local runs 3.11; add a 3.11 CI job if they diverge |

---

## 19. Stage 2 report: Identity (implemented, awaiting review)

**Built (backend):** SQLAlchemy 2 async + Alembic (migration `0001`, with a Compose one-shot `migrate` service); tables `users`, `refresh_tokens`, `password_resets`; argon2id (64 MiB, t=3, p=1, NFKC-normalised, off the event loop, rehash on sign-in); password policy (10-128 chars, small common list, no email local-part); HS256 access JWT (15 min; pinned algorithm; `iss/aud/sub/sid/jti/typ` required); opaque 256-bit refresh and reset tokens stored only as SHA-256; refresh rotation with family-wide revocation on reuse, a 10 s benign-race grace window and a 30-day absolute family cap; session liveness checked against the database on every request (see §19.1), so sign-out/reset kill still-valid access tokens immediately; Redis rate limits (sign-in per ip+email and per ip, sign-up per ip, reset per ip and per email); double-submit CSRF + Origin/Sec-Fetch-Site checks; `Cache-Control: no-store` on auth responses; SMTP email sender (Mailpit in the `dev` profile); reset link carries the token in the URL fragment; prod config guards (refuses default JWT secret, non-secure cookies, non-https origin).
**Endpoints:** `POST /api/v1/auth/{sign-up,sign-in,refresh,sign-out,password/forgot,password/reset}`, `GET|PATCH /api/v1/auth/me`.
**Built (frontend):** API client with CSRF header, problem+json mapping, single-flight refresh (`navigator.locks`); sign-in, sign-up, forgot, reset pages (EN/AR, RTL); session provider and route gate; user menu with sign-out; locale preference saved on switch; proxy redirect using a non-sensitive `ka_session` hint cookie.

**Verification:**
- Backend: ruff, mypy strict, **88 tests** on real Postgres+pgvector and Redis (testcontainers), including migration up/down/up.
- Frontend: eslint, stylelint, tsc, **41 tests**, `next build` (inside the Docker build).
- Compose: all services healthy including `migrate` (exit 0); full flow exercised in the browser in Arabic through Caddy: sign-up (weak password rejected, then accepted), sign-out, wrong-password error, sign-in, forgot password, email captured in Mailpit (Arabic, token in fragment), fragment scrubbed from the address bar, reset, old password 401 / new password 200, reset token reuse 400.
- Bugs found by the tests/browser run and fixed: `replaced_by` was never set on rotation; lazy-load crash (500) in the reuse-detection path; request ID missing on 500 responses; missing CSS in the first Docker build; sign-out marked the UI signed-out even when the request failed.

**Decisions and trade-offs (please review):**
- **Sign-up reveals taken emails (409).** Accepted because email verification is deferred; mitigated by per-IP rate limiting. Sign-in, forgot-password and reset do not reveal existence.
- **No email verification, change-password, MFA or "sign out everywhere" button** (not in the stage 2 scope); `email_verified_at` exists unused.
- **Access cookie lifetime vs revocation:** access tokens are signed, but every request also confirms in the database that the session's refresh family still has a live token (superseded by §19.1; Redis is no longer involved in authentication).
- **Per-IP sign-in lockout** (not per-account) so a stranger cannot lock the owner out; trade-off: a distributed guesser is limited per IP only. `X-Forwarded-For` is trusted because only Caddy can reach the API.
- **Zod not used** for forms: server validation is authoritative and the client only checks length; revisit if forms grow.
- **Auth screens were not in the approved mockup**; they were designed from the approved tokens (paper, hairline fields, serif titles, ink primary button). Please review them as new design.
- **Digits:** error messages pass pre-formatted strings, so Arabic UI shows Western digits (D11).
- Database role is still the Postgres owner; the non-superuser app role and RLS arrive in stage 3.

**Still unverified / open:**
- Python 3.12: the container image (3.12) runs migrations and serves traffic, but the **test suite was only run on 3.11**; CI will run it on 3.12 (not yet exercised).
- GitHub Actions, gitleaks, pre-commit: written, not run (no remote).
- No Playwright E2E yet (planned stage 9); browser verification above was manual.
- Real SMTP delivery (STARTTLS/auth) is untested; only Mailpit.
- Rate-limit behaviour behind multiple API replicas is untested (single replica).
- Tablet-width auth screens not screenshotted; desktop (EN/AR) and mobile (AR) were.
- Nothing is committed.

### 19.1 Review round on stage 2 (concurrency, Redis failure, reset revocation, auth screens)

**Changes made in response to the review**
- **Redis is no longer part of authentication.** Previously, revocation lived in a Redis set. Testing showed two problems: with Redis down the API raised unhandled errors (500s), and a revocation whose Redis write was lost would let a revoked access token live out its 15 minutes. Now the **database is the single source of truth**: `current_user` grants access only if the token's session (refresh family) still has a non-revoked, unexpired refresh token (one indexed query; the user row is loaded anyway). Sign-out, password reset, reuse detection and expiry all work by updating `refresh_tokens`. The Redis revocation set was removed.
- **Rate limiting fails closed.** Every `RateLimiter` operation maps Redis failures to `503 SERVICE_UNAVAILABLE` with `Retry-After: 5` (short 2 s Redis timeouts), so sign-in, sign-up, forgot and reset are refused rather than running without brute-force protection. Verified: with Redis stopped, correct credentials get 503 and no cookies; an existing session still authenticates; sign-out still succeeds and revokes.
- **Password reset revocation is atomic.** The password change, token consumption and revocation of **all** the user's refresh families happen in one transaction (previously revocation ran after the commit).
- **Client convergence after `REFRESH_RACE`:** the client now polls `/auth/me` (4 attempts, 150-600 ms back-off) until the sibling's cookies land, then retries; it gives up cleanly rather than looping.
- UI maps `SERVICE_UNAVAILABLE` to a localized message (EN/AR).

**Concurrent refresh, exactly** (tested with 8 simultaneous requests carrying the same token against real Postgres): the refresh handler locks the presented token row (`SELECT ... FOR UPDATE`), so concurrent requests serialize. The first rotates (old token revoked, `replaced_by` set, one child token created). Each later request sees the old token revoked and rotated less than 10 s ago and returns `401 REFRESH_RACE` **without minting anything and without punishing the family**. Therefore there is never more than one live descendant: exactly one 200, seven `REFRESH_RACE`, two rows in the table, one live. Tabs converge through the shared cookie jar: in browsers the `navigator.locks` lock serializes tabs, and a tab that gets the lock first calls `/auth/me`, which already succeeds with the sibling's fresh cookies, so no second rotation happens; without locks (or non-browser clients) the `REFRESH_RACE` path plus the polling above converges on the single child. Trade-off: replaying a stolen token within 10 s of the legitimate rotation yields nothing but also does not trigger family revocation; after the window any replay revokes the whole family.

**Reset revocation** (tested with four sessions across four families, one rotated three times, plus two outstanding reset tokens and a bystander user): all four families' refresh tokens are revoked, every old access token returns 401, every old refresh token returns 401, all reset tokens are spent, and the other user's session is untouched.

**Auth screens:** 24 captures (4 screens x EN/AR x desktop 1280x800 / tablet 820x1180 / mobile 390x844) in `docs/design/auth-screens/` (`index.html` is a self-contained review page; `capture.cjs` regenerates them). Mobile and tablet captures use real DevTools device metrics because headless Chrome clamps window width to 500 px.

**Verification now:** backend **96 tests** (ruff, mypy strict clean), frontend **42 tests** (eslint, stylelint, tsc clean).

### 19.2 Outstanding verification items (stages 1 and 2), kept open
| Item | Status | When |
|---|---|---|
| gitleaks run locally; GitHub Actions workflow (backend, frontend, secrets-scan, compose jobs) verified | not done (no remote, gitleaks not installed) | before the first push |
| Authenticated SeaweedFS S3 upload/download round trip | not done (readiness checks master health only) | stage 4 |
| Python 3.12: run the test suite (container image runs on 3.12; tests only run on 3.11 locally) | not done | CI before first push; each stage |
| Real SMTP (STARTTLS/auth) delivery | not done (Mailpit only) | before any deployment |
| Rate limits and refresh locking with multiple API replicas | not done | stage 11 (performance/hardening) |
| Playwright end-to-end tests for the auth flows | not done (manual browser verification only) | stage 9 |
| Tablet-width live-browser review of the signed-in shell | not done (auth screens covered by the 24 captures) | stage 9/10 |
| Nothing committed | by instruction | until you ask |

---

## 20. Stage 3 report: Tenancy & RBAC (implemented, awaiting review)

### 20.1 What was built
**Data model** (migration `0002`): `organizations` (name, auto-generated slug `name-xxxxxx`, settings jsonb), `memberships` (unique per org+user, role check), `invitations` (token stored as SHA-256 only, role limited to admin/editor/member/viewer, one pending invitation per org+email). Differences from §4: no `memberships.status` column (it would be dead code until suspension exists); `users` stays global identity data without RLS.
**Roles and policy:** owner > admin > editor > member > viewer in one pure module (`app/modules/access/policies.py`) with an explicit action table, `require()` (403 `FORBIDDEN`), `check_role_change()`, `check_removal()`. Rules: only owners touch or grant owner; admins manage roles up to admin; nobody raises their own role; anyone may leave; the last owner can neither leave nor be demoted (enforced under a row lock on the organization, tested with two simultaneous demotions); member emails are visible to admins and owners only; owners are promoted, never invited.
**API:** `POST/GET /orgs`, `GET/PATCH/DELETE /orgs/{org_id}`, `GET /orgs/{org_id}/members`, `PATCH/DELETE /orgs/{org_id}/members/{member_id}`, `GET/POST /orgs/{org_id}/invitations`, `DELETE /orgs/{org_id}/invitations/{invitation_id}`, `POST /invitations/accept`. Deviation from §8: accept takes the token in the request **body**, not the URL path, so it never reaches access logs. Per-user cap of 10 owned workspaces; invitation rate limits (per org, per IP); invitation email (EN/AR) with the token in the URL fragment.
**Frontend:** workspace routes `/{locale}/{org-slug}`; create-workspace page (first sign-in); org switcher in the rail (accessible menu, per-user remembered last workspace); accept-invite page (parks the fragment token in `sessionStorage` across the sign-in detour); "workspace not found" view identical for nonexistent and foreign workspaces. Members/roles management UI is **not** built in this stage (it is stage 11); roles and invitations are API-only for now.

### 20.2 Tenant isolation: three independent layers
1. **Resolution:** the tenant is derived from the verified membership of the authenticated user, never from client input; a non-member and a nonexistent org get the **same 404** (identical bodies, asserted).
2. **PostgreSQL RLS, independent of the URL:** the API connects as `app_rw` (non-superuser, `NOBYPASSRLS`, owns no tables, cannot create objects or `SET ROLE`). Policies read transaction-local settings published on every transaction begin (`app.current_user`, `app.current_org`, `app.invite_hash`); no scope means every tenant table reads as empty. Crucially the policies also require the **authenticated user's membership** (SECURITY DEFINER helpers `app_is_member`, `app_org_has_members`, `app_invite_valid`), so naming an organization in the scope without belonging to it grants nothing at the database level. A user may read their own memberships across orgs (to list workspaces). Joining uses a per-transaction token-hash capability that must match an unexpired invitation addressed to the user's email; a brand-new organization can be bootstrapped only while it has no members.
3. **Explicit filters** in every query (`organization_id = ...`), including ID-addressed lookups (members, invitations).
**Scope plumbing guarantees:** the scope is re-published on every new transaction (tested across commits and pooled connections); `bind_scope()` refuses a session that already began a transaction, and handlers use their own session rather than the one shared with authentication (a first version silently saw empty results because of that sharing: caught by the tests).
**Known limits (documented, not hidden):** policies cannot express roles (members vs admins); roles are enforced in the application layer and tested there. RLS is enabled but **not forced** (the table owner used by migrations is exempt; forcing would also bind the definer helpers); the guarantee relies on the API never using the owner credentials, which the Compose setup and a catalog test enforce. `users` has no RLS: member listings join it, constrained by organization.

### 20.3 Tests (159 backend, 52 frontend; all green)
- **Policy matrix** (`test_policies.py`): hand-written role x action matrix plus role-change and removal rules.
- **Database level** (`test_rls.py`, raw SQL as `app_rw`): the role is not superuser/bypassrls and cannot DDL; every table with `organization_id` has RLS enabled and policies for all four commands (fails if a future table forgets); no scope reads nothing; another org's rows are invisible, cannot be updated/deleted (0 rows) or inserted/moved (error); a **spoofed org in the scope without membership** reads and changes nothing; invitation joins require the matching email and token; empty-org bootstrap only; scope never leaks through a single pooled connection and survives mid-request commits.
- **API matrix generated from the live OpenAPI schema** (`test_tenant_isolation_matrix.py`): every `/orgs/{org_id}/...` route is called as an outsider with the victim's real org id, with the victim's real member/invitation ids, with random ids: always the identical 404; the victim's data is unchanged afterwards; unauthenticated callers get 401/403; a new route that nobody classified (org-scoped or explicitly allow-listed with a reason) or a body-bearing route without a sample body fails the suite; the owner really reaches every GET route (guards against a vacuous pass).
- **Hand-written IDOR/abuse** (`test_tenant_idor.py`, `test_tenancy_api.py`): member and invitation ids from another org through your own org path; 25 guessed UUIDs; mass-assignment of `organization_id`/`id`/`slug`; invitation tokens replayed by strangers, by another org's owner, tampered, mismatched email (no membership created, invitation not consumed), reused, revoked, replaced, expired; an existing member cannot be escalated by an old invitation; removed members lose access immediately with a valid session; role-escalation attempts; last-owner invariants incl. a concurrent race.
- **Mutation checks** (in a scratch copy; nothing in the project was mutated): (M1) removing the explicit org filter on member lookup: all API/IDOR/matrix tests still pass because RLS holds; (M2) disabling RLS: the API suites still pass (layer 1/3 hold) and 17 DB-level RLS tests fail; (M3) removing the application membership check entirely: the matrix suite fails, and a probe showed the outsider received **no victim data and changed nothing** (org GET/PATCH 404, member and invitation lists empty, invitation creation rejected by the database, DELETE affected 0 rows).

### 20.4 Live verification (Docker Compose, through Caddy)
API running as `app_rw` (confirmed), migration run as owner; in the browser (Arabic): sign-in with no workspace redirects to create-workspace, creating a workspace with an Arabic name lands in it (slug `workspace-xxxxxx`); curl: an outsider gets 404 on GET/members/invitations/PATCH/DELETE of another org; invitation created, email captured (Arabic subject, fragment link), accepted by the invited user, who then sees only member names (no emails) as a viewer and gets 403 when trying to invite; switcher menu rendered (English, desktop). Found and fixed: the remembered last workspace was shared across accounts in one browser; it is now stored per user.

### 20.5 Decisions and trade-offs for your review
- Slugs are random-suffixed and immutable (no slug-existence oracle, no rename flow yet).
- A workspace owner can delete the workspace; storage cleanup of its future documents must be handled in stage 4.
- Invitation acceptance is bound to the invited **email address** of the signed-in account; since email verification is still deferred, possession of the emailed token is the real proof (as with password reset).
- Unauthenticated state-changing calls to org routes get 403 `CSRF_FAILED` rather than 401 (the CSRF guard runs first); nothing is processed either way.
- The 10-second refresh **grace-window trade-off** is unchanged and still documented in §19.1: replaying a stolen token within 10 s of the legitimate rotation yields nothing but also does not trigger family revocation; afterwards any replay revokes the whole family.
- Audit events are logged (structured `org.*`, `member.*`, `invitation.*`) but the append-only `audit_events` table is still stage 11.

### 20.6 Outstanding verification items (carried forward, still open)
| Item | Status | When |
|---|---|---|
| gitleaks locally; GitHub Actions workflow (backend, frontend, secrets-scan, compose) verified | not done (no remote, gitleaks not installed); the CI workflow does not yet provide Docker-in-CI settings for the testcontainers-based backend tests, to be confirmed on first run | before the first push |
| Authenticated SeaweedFS S3 upload/download round trip | not done | stage 4 |
| Python 3.12 test run (container image runs 3.12; tests only on 3.11 locally) | not done | CI before first push |
| Real SMTP (STARTTLS/auth) delivery | not done (Mailpit only) | before any deployment |
| Rate limits, refresh locking, and RLS helper performance with multiple replicas / large tables | not done | stage 11 |
| Playwright end-to-end tests (auth, workspace creation, invitations, switcher) | not done (manual browser verification only) | stage 9 |
| Tablet/mobile live review of the signed-in shell with the new org switcher | not done (desktop EN/AR verified; auth screens covered in §19.1) | stage 9/10 |
| Deleting a workspace with documents (storage cleanup) | n/a until documents exist | stage 4 |
| Nothing committed | by instruction | until you ask |

---

## 21. Stage 4 report: Collections, permissions & documents (implemented, awaiting review)

### 21.1 What was built
**Data model** (migration `0003`): `collections` (name unique per org case-insensitively, `org|restricted`), `collection_members`, `documents` (display filename, sniffed MIME, size, SHA-256, opaque storage key, status, soft delete + `purged_at`; partial unique index on (org, collection, sha256) among non-deleted rows = per-collection dedupe). The status check already lists every planned state; only `uploaded` is used until stage 5. Every workspace gets a "General" collection at creation (existing ones were backfilled by the migration).
**Access rules:** org-visible collections are visible to every member; restricted ones to listed users, plus owners and admins (who can access every collection; they could self-grant anyway). Viewing/downloading: viewer and above; upload/delete: editor and above; collection and ACL management: admin and above. Inaccessible collections and documents answer **404**, never 403 (role failures answer 403).
**API:** `GET/POST /orgs/{org}/collections`, `PATCH/DELETE .../collections/{id}`, `GET/PUT .../collections/{id}/members`, `POST/GET /orgs/{org}/documents` (multipart, up to 10 files of 50 MB, cursor pagination, filters), `GET/DELETE .../documents/{id}`, `GET .../documents/{id}/file`.
**Upload pipeline:** stream to a temp file while hashing and enforcing the size cap; sniff the type from CONTENT (PDF header; DOCX/PPTX must be a ZIP containing their main part, with entry-count/uncompressed-size/path-traversal guards; text/Markdown must be valid UTF-8 without NUL bytes) and require the extension to agree (type confusion, unsupported Office types, HTML, executables are refused); sanitize the display filename (path parts, control and bidi-override characters stripped, ZWNJ kept for Arabic-script text); dedupe; store the object under an opaque key `org/{org}/doc/{id}` (the filename never reaches storage); insert the row; on any failure after the object was stored the object is removed (no object without a row, no row without an object). Per-file results `created | duplicate | rejected` with stable codes (`UNSUPPORTED_TYPE`, `FILE_TOO_LARGE`, `EMPTY_FILE`, `CORRUPT_FILE`); `TOO_MANY_FILES` and `STORAGE_UNAVAILABLE` (503) fail the request. Concurrent identical uploads yield exactly one document.
**Download:** streamed through the API with authorization on **every** request; headers `nosniff`, `Content-Security-Policy: sandbox`, `Cache-Control: private, no-store`; only PDFs may render inline, everything else is an attachment, Markdown is served as plain text; RFC 6266 filename encoding that cannot inject headers.
**Deletion:** document delete is soft in the database and removes the object immediately (`purged_at` set; a failed purge is logged and swept later). Collection delete requires it to be empty. **Workspace delete now also deletes every object under `org/{id}/`** (carried-forward item from stage 3).
**Readiness** now performs an authenticated `HEAD` on the bucket (reachability, credentials and bucket existence), replacing the master health URL.
**Frontend:** Library page `/{org}/library` in the approved dense-table style: collection filter chips with lock icon for restricted ones, debounced search, "load more" pagination, drag-and-drop anywhere (overlay), upload with per-file outcomes, download, inline delete confirmation (editors and above), empty states by role, mobile stacked layout, Western digits and bdi-isolated mixed-direction names in Arabic. Collection and ACL management UI is **not** built (it is stage 10); collections are manageable through the API.

### 21.2 Document permissions at three layers
1. **Policy module** (`policies.py`): hand-written role x action matrix extended with `COLLECTION_MANAGE`, `DOCUMENT_VIEW/UPLOAD/DELETE`.
2. **Application layer:** `_accessible_ids()` computes the caller's accessible collections explicitly and every collection/document query filters by it.
3. **PostgreSQL RLS:** `documents`, `collections` and `collection_members` policies call SECURITY DEFINER helpers (`app_is_admin`, `app_in_collection`, `app_can_access_collection`), so a member who is not listed cannot read, update, delete, insert into, or move rows into a restricted collection even if every application filter were wrong. The same helper is what stage 6's `chunks` table must use (a catalog test fails if a table with `collection_id` lacks the access-aware policy).

### 21.3 Tests (261 backend, 57 frontend; all green; ruff, mypy strict, eslint, stylelint, tsc clean)
- **Real object store:** backend tests run against a real, authenticated SeaweedFS container: round trip incl. a 12 MB multipart object, wrong credentials refused, unreachable endpoint, missing bucket/object, prefix deletion that respects neighbour prefixes. This closes the stage 1 item "authenticated S3 round trip".
- **Permission matrix** (`test_document_permissions.py`, hand-written expectations): 5 roles x (org-visible, restricted-listed, restricted-unlisted) x list/get/download/upload/delete; unfiltered listings never include inaccessible collections; revocation and demotion take effect immediately; removed members lose every document.
- **DB level** (`test_rls_documents.py`, raw SQL as `app_rw`): reads follow collection access; unlisted members cannot update/delete/insert/move rows or add themselves to the list; a forged org scope without membership sees nothing; cross-tenant inserts are refused; access-function truth table.
- **Isolation matrix** (generated from OpenAPI) extended to collections and documents (multipart upload and file download included): outsiders get an identical 404 on all 18 org-scoped routes with real, random and mixed ids; a same-org editor without collection access gets 403/404 on every collection/document route; nothing changes.
- **Upload security:** disguised executables, HTML, polyglots, wrong-family Office files, zip path traversal / entry floods, NUL bytes, invalid UTF-8, empty files, oversize, too many files; traversal/control/bidi filenames; header-injection-proof Content-Disposition; storage keys never contain filenames; dedupe per collection only (no cross-tenant or cross-collection oracle); simultaneous identical uploads; storage outage (503, nothing left behind); database failure after the object was stored (object removed).
- **Mutation checks** (scratch copy): (D1) removing the application-layer access filter: the permission matrix still passes (RLS holds); (D2) disabling RLS on the three tables: the matrix still passes (application layer holds) and 8 DB-level tests fail; (D3) removing the orphan cleanup: the failure-path tests fail; (D4) weakening content sniffing: 22 tests fail.
- Bugs found by tests/runs and fixed: a collection `INSERT ... RETURNING` is invisible to a policy that re-reads the same table (policies now use the row's own columns); an orphan-object window if constructing the row failed after the object was stored; SeaweedFS refuses writes once many buckets exhaust its volumes (tests share one bucket; production uses one); transient `InternalError` on the first write to a new bucket (retried briefly; authentication errors never retried); status CSS class clash (`n`).

### 21.4 Live verification (Docker Compose, through Caddy)
Readiness reports `bucket knowledge-documents` after an authenticated check; migration `0003` applied on the existing database and backfilled "General". curl: good PDF created, disguised executable rejected (`UNSUPPORTED_TYPE`), re-upload deduplicated, download byte-identical with the safe headers, a viewer in another workspace gets 403 on upload and 404 for a foreign document id, the object store is not reachable from the host. Browser: drag-and-drop upload (overlay shown) of an Arabic-named Markdown file and an `.exe` (preflight rejection), Arabic RTL library, inline delete confirmation, row and object removed (verified in the bucket), mobile stacked layout.

### 21.5 Decisions and deviations for your review
- **No presigned URLs.** Downloads stream through the API with per-request authorization; the object store is never exposed to browsers, and revoked access takes effect immediately. Trade-off: file bytes pass through the API (no HTTP Range support yet; stage 10's viewer can add it).
- **No `Idempotency-Key`** (PLAN §8): content-hash dedupe already makes retries idempotent.
- **Upload size enforcement:** Starlette spools multipart bodies to disk before the handler runs, so the per-file limit is checked after spooling; Caddy caps the request body at 520 MB to bound disk use. Streaming enforcement would need a custom multipart parser. No antivirus scanning (ClamAV remains optional/future).
- **Admins and owners can access every collection**, including restricted ones.
- Collection delete requires an empty collection; changing a restricted collection to org-visible clears its member list.
- Documents stay `uploaded`: no parsing, page counts or language detection until stage 5, so the Library has no "Needs attention" panel, language or pages columns yet.
- Soft-deleted documents keep their rows (and hash) for a later sweep job; the sweeper itself belongs to stage 5's background worker.
- Per-org storage quotas are not implemented.

### 21.6 Outstanding verification items (carried forward, still open)
| Item | Status | When |
|---|---|---|
| gitleaks locally; GitHub Actions workflow verified (now also needs Docker-in-CI for the Postgres, Redis and SeaweedFS testcontainers) | not done (no remote, gitleaks not installed) | before the first push |
| ~~Authenticated SeaweedFS S3 round trip~~ | **done in this stage** (tests + readiness + live) | closed |
| Python 3.12 test run (container image runs 3.12; the suite only ran on 3.11 locally) | not done | CI before first push |
| Real SMTP (STARTTLS/auth) delivery | not done (Mailpit only) | before any deployment |
| Rate limits, refresh locking, RLS helper cost (`app_is_member` / `app_can_access_collection` per row) with multiple replicas and large tables | not done | stage 11 |
| Playwright end-to-end tests (auth, workspaces, invitations, upload, library) | not done (manual browser verification only) | stage 9 |
| Tablet width and signed-in shell review (org switcher, Library) | not done (desktop EN/AR and mobile verified) | stage 9/10 |
| Orphaned objects left by failed purges / failed workspace-delete cleanup | logged only; no sweeper yet | stage 5 (worker) |
| SeaweedFS capacity settings for production (`-volume.max`, volume size) | not tuned | before deployment |
| Collection and ACL management UI | not built | stage 10 |
| The 10-second refresh grace-window trade-off | unchanged and documented in §19.1 | n/a |
| Nothing committed | by instruction | until you ask |

## 22. Stage 5 report: Parsing, chunking & unsupported-document handling (implemented, awaiting review)

### 22.1 What was built
**Pipeline** (Celery, queue `ingest`, broker = Redis db 1): `uploaded → parsing → chunking → final status`. Final statuses: `ready`, `ready_partial`, `unsupported_scanned`, `unsupported_garbled`, `failed`. Every outcome carries a stable error code (`ENCRYPTED`, `CORRUPT`, `CONVERSION_FAILED`, `EMPTY_DOCUMENT`, `TOO_MANY_PAGES`, `NO_TEXT_LAYER`, `GARBLED_TEXT`, `PARTIAL_TEXT`, `PROCESSING_ERROR`, `PROCESSING_CRASHED`, `FILE_MISSING`, `STORAGE_UNAVAILABLE`) and nothing fails silently: a document never stays in a processing state without a job record and a sweeper that re-queues it (max 3 attempts, then `PROCESSING_CRASHED`).
**Parsers:** PDF via pypdfium2 (per-page text and image-coverage ratio); DOCX/PPTX converted to PDF by headless LibreOffice (so page numbers match what users see; the converted PDF is stored as `viewer_key` for the stage-10 viewer); TXT/MD split into virtual pages (~3,500 characters).
**Page classifier:** each page is `text`, `image_only` (scanned) or `garbled` (broken font encoding: replacement characters, private-use glyphs, low letter ratio). Unusable pages keep no text. The document outcome follows from the page mix: all good = `ready`; some unusable = `ready_partial` (the rest is searchable, unreadable page ranges are shown); none usable = `unsupported_scanned` / `unsupported_garbled`.
**Arabic extraction normalization:** NFKC folding of presentation forms; detection and repair of visually-ordered (reversed) Arabic runs; **repair of swapped lam-alef ligatures** (found by the live LibreOffice run, see 22.4); `search_normalize` for stage 6/7 (tashkeel and tatweel stripped, alef variants and ى folded, Arabic-Indic and Persian digits and separators to ASCII; ة is deliberately not folded).
**Chunker:** structure-aware (headings start chunks), target 500 / max 600 tokens, min 150, 12% overlap, oversized paragraphs split on sentences then word windows; every chunk records page span and heading path.
**Worker isolation:** a least-privilege role `worker_rw` (migration `0004`): its own RLS policies, column-level UPDATE on `documents` (status, error, page count, summary, language, pagination, viewer key, timestamps only), SELECT on `organizations(id)` only, no access to users, memberships, collections or sessions. The API role can only read `document_pages` and has no access to `chunks` or `ingestion_jobs`. Worker tables carry a denormalized `collection_id` and use the same access-aware RLS helper as stage 4.
**Sweeper** (Celery beat): re-queue stuck documents (`uploaded` > 120 s, running > 900 s), purge objects of soft-deleted documents, purge orphan workspace prefixes (min age 1 h). Closes the stage 4 item "orphaned objects".
**API additions:** `GET /documents/summary`, `GET /documents/events` (SSE), `GET /documents/{id}/pages[/{n}]`, `POST /documents/{id}/reprocess` (editor+, 202; 409 if already running); `DocumentOut` gains `language` and `page_summary`; upload enqueues after commit (a broker outage never fails an upload: the sweeper re-queues).
**SSE:** the worker publishes to Redis `docevents:{org}`; the API relays and **re-authorizes every event for each connected caller** (collection access, membership, session liveness), including on heartbeats, and stops the stream when access is revoked.
**Compose:** new `worker` image target (LibreOffice + Noto/DejaVu fonts, 851 MB; the API image stays 337 MB), `worker` and `beat` services (non-root, read-only-style limits: tmpfs `/tmp`, memory and pids limits, celery ping healthcheck); `WORKER_DB_PASSWORD` generated by `scripts/init-env.sh`.
**Frontend (Library):** status chips for all eight states (pulsing "busy" dot honours reduced motion), Language and Pages columns, the approved "Needs attention" panel (reason by error code, unreadable page ranges such as "3–4", Try again for editors, Download, inline-confirmed Delete), the rail/tab-bar "Needs attention" item with a count badge, live updates over EventSource with automatic polling fallback, English and Arabic messages (ICU plurals for Arabic), Western digits and logical CSS only.

### 22.2 Tests (393 backend, 69 frontend; all green; ruff, ruff format, mypy strict, eslint, stylelint, tsc clean)
- **Parsers/classifier/chunker:** hand-built PDFs (text, Arabic via ToUnicode, image-only, mixed, encrypted, truncated), Arabic golden tests for normalization, Hypothesis property tests for the chunker (token bounds, no lost text, page spans valid), classifier threshold tests.
- **Pipeline** (19 tests, real Postgres/Redis/SeaweedFS containers): every fixture ends in the right state; job records per attempt; stuck/duplicate delivery safe; missing object, storage outage and crashes handled; events published.
- **Worker role** (17 tests): the worker cannot read users, memberships or collections, cannot write outside its column grant, cannot touch another tenant's rows, API role cannot read chunks/jobs.
- **Isolation matrix** (generated from OpenAPI) now covers the new routes, including `pages`, `reprocess`, `summary` and the SSE route; the SSE generator is tested directly for per-event re-authorization and revocation (httpx's ASGI transport cannot stream, so the stream was also checked live, see 22.4).
- **Regression tests from live findings:** a real LibreOffice-produced Arabic PDF fixture (synthetic text) for the lam-alef repair; a fresh-interpreter test that the worker process resolves every foreign key (fails without the fix, verified by removing it).
- **Frontend:** page-range collapsing, status classification matching the backend sets, every status and every error code has English and Arabic text.
- Not done: **mutation checks for this stage** (only the worker-import regression test was proven by removing its fix). They should run in a scratch copy before stage 6.

### 22.3 Bugs only the live Compose run found (all fixed)
1. `packaging` is imported by kombu's Redis transport but not declared by it: the worker image crash-looped (it only existed locally as a dev transitive dependency). Now an explicit dependency; `uv.lock` updated.
2. The worker failed **every document** with `NoReferencedTableError` (`documents.uploaded_by → users`) because it never imported the identity models; in-process tests always load the whole app. Fixed with `app/db/registry.py` and a fresh-interpreter test.
3. Celery replaces `sys.stdout` with a proxy into its own logger; our JSON log handler wrote into it, so **all worker logs, including task failures, vanished**. The worker now logs to the real stdout.
4. `migrate` used a stale image (not rebuilt), so `0004` had not run; rebuilding and re-running applied `0004` on the existing stage-4 database, which also verifies the upgrade path on a database with data.
5. pdfium **swaps lam-alef ligature pairs** in LibreOffice-produced Arabic PDFs ("ثلاثين" → "ثالثين", "السلام" → "السالم", "لا إله إلا الله" → "ال إله إال الله"), which would silently break Arabic search. Detection: the two characters of a ligature share one glyph box while a genuine "ال" does not; only boxed-together (alef-form, lam) pairs are swapped.

### 22.4 Live verification (Docker Compose, through Caddy)
Sign-up, workspace, then one multipart upload of 8 files; all settled in **2 seconds**: good PDF `ready` (2 pages, en); Arabic DOCX converted by the real LibreOffice `ready` (3 pages, ar); LibreOffice Arabic PDF `ready`; Arabic Markdown `ready`; 5-page PDF with two scanned pages `ready_partial` / `PARTIAL_TEXT` with pages 3–4 `image_only`; scanned PDF `unsupported_scanned` / `NO_TEXT_LAYER`; encrypted PDF `failed` / `ENCRYPTED`; truncated PDF `failed` / `CORRUPT`. Real LibreOffice conversion measured at 0.6–0.7 s per small DOCX/PPTX (including an Arabic DOCX and a PPTX with an Arabic slide). SSE through Caddy delivered `parsing` then `failed/ENCRYPTED` for a reprocess; a second immediate reprocess returned 409. Browser: Library in English and Arabic (RTL, plural forms, Western digits) and at 375 px width; rail badge shows 4. Worker logs verified visible after fix 3.

### 22.5 Known limits, decisions and deviations for your review
- **Arabic extraction is good, not perfect.** After the ligature repair, words written with a separate tanween-alef glyph (e.g. "يوماً") can still be extracted scrambled from LibreOffice output, and fully visual-order (reversed) runs are detected by a common-word heuristic that can miss very short pages. Both are bounded (a few words per page) and the stage-6 Arabic retrieval evaluation should measure their effect before we decide whether to invest more (e.g. extracting DOCX text from the source XML instead of the converted PDF).
- **pypdfium2 instead of PyMuPDF** (Apache/BSD instead of AGPL), consistent with the Apache-2.0 decision; layout analysis is more basic.
- **"ready" in stage 5 means extraction complete**; stage 6 adds embeddings and will move documents through an `embedding` stage before `ready`.
- **Worker image is heavy** (851 MB with LibreOffice); only the worker carries it. No OCR yet (by decision): scanned pages are detected and surfaced, not silently dropped.
- The orphan sweeper lists the whole `org/` prefix; fine at current scale, needs paging/indexing at large scale.
- Acks are early, not late: a crashed worker does not redeliver a poison document forever; the sweeper re-queues lost work with a bounded attempt count.
- Tablet width of the Library has not been reviewed visually (desktop EN/AR and mobile were); on mobile the tab-bar badge sits under the label rather than beside it.
- Text and Markdown have no real pages: virtual pages are used for citations until the viewer exists.

### 22.6 Outstanding verification items (carried forward, still open)
| Item | Status | When |
|---|---|---|
| gitleaks locally; GitHub Actions workflow verified (needs Docker-in-CI for the Postgres, Redis and SeaweedFS testcontainers; CI also needs the LibreOffice-free test path, which it has) | not done (no remote, gitleaks not installed) | before the first push |
| Python 3.12 test run on the host-equivalent (the containers run 3.12 and the live flow worked there; the suite itself only ran on 3.11 locally) | partly (runtime verified in containers) | CI before first push |
| Real SMTP (STARTTLS/auth) delivery | not done (Mailpit only) | before any deployment |
| Rate limits, refresh locking, RLS helper cost with multiple replicas and large tables; worker concurrency and queue throughput under load | not done | stage 11 |
| Playwright end-to-end tests (auth, workspaces, invitations, upload, library, attention panel, SSE) | not done (manual browser verification only) | stage 9 |
| Tablet width and signed-in shell review | not done | stage 9/10 |
| Stage 5 mutation checks (scratch copy) | not done | before stage 6 |
| SeaweedFS capacity settings for production | not tuned | before deployment |
| Arabic extraction quality (tanween-alef words, reversed runs) measured by the retrieval evaluation | open | stage 6/11 |
| Collection and ACL management UI | not built | stage 10 |
| ~~Orphaned objects sweeper~~ | **done in this stage** | closed |
| The 10-second refresh grace-window trade-off | unchanged and documented in §19.1 | n/a |
| Nothing committed | by instruction | until you ask |

## 23. Stage 6 report: Embeddings, indexing & evaluation foundation (implemented, awaiting review)

### 23.1 What was built
**Embedder seam:** a small `Embedder` protocol (`model`, `dimensions`, `embed(texts)`) with one production implementation, `OllamaEmbedder` (`POST /api/embed`, `bge-m3`, 1024-d, bounded retries on transport errors and 502/503/504). Failures are classified: `EmbedderUnavailableError` (transient) and `EmbeddingFailedError` (unknown model, unusable answer, wrong dimensions: permanent). A deterministic fake exists **only in `tests/`**; no runtime setting can select it.
**Pipeline:** `uploaded → parsing → chunking → embedding → ready`. Chunks are embedded as `"{title} > {heading trail}\n{content}"` with digit scripts folded to ASCII (see 23.4), in bounded batches, **outside any database transaction and before the final write**, so a document is never `ready` without vectors and never half-indexed. Documents with nothing to embed (scanned, blank) skip the stage. New error codes `EMBEDDER_UNAVAILABLE` (retried automatically) and `EMBEDDING_FAILED` (not).
**Schema** (migration `0005`, applied on a database that already held data): `chunks.embedding vector(1024)` + `embedding_model` (both or neither, enforced by a CHECK), HNSW index (cosine, m=16, ef_construction=64), `content_tsv` (generated: `arabic` config for Arabic chunks, `english` for English, both for mixed, built from the already search-normalized text), `content_tsv_simple` (same text, `simple` config, so stage 7 can measure the Arabic stemmer instead of assuming it helps) with GIN indexes. The API role **still has no privileges on `chunks`**; retrieval grants arrive with stage 7. pgvector 0.8.7.
**Re-indexing:** `reindex_stale` re-embeds only chunks that lack a vector from the CURRENT model, idempotent and resumable, locks the document so it cannot race a re-process, never changes document status. It runs **periodically** (beat, every 5 min, 25 documents per run) so documents that predate embeddings and a changed `EMBEDDING_MODEL` heal on their own, and can be called by hand per workspace.
**Automatic retry of dependency outages:** documents that failed only because object storage or the embedder was down are re-queued after a pause (5 min), at most 6 attempts in total; permanent failures are never retried; "Try again" always works.
**Deleted documents leave nothing behind:** the sweeper now also removes the pages, chunks and vectors of soft-deleted documents (the API role cannot touch those tables, so the worker does it).
**Evaluation foundation** (`backend/evals/`, plus the committed report `docs/eval/stage6-baseline.md`): see 23.2.
**Frontend:** `embedding` status ("Indexing"; `chunking` is now "Preparing"), reasons for the two new error codes, English and Arabic.
**Operations:** Compose `worker` reaches Ollama through `host.docker.internal` (`EMBEDDER_URL`, `EMBEDDING_MODEL`); `beat` now runs the **same image** as the worker and has a healthcheck (see 23.5); `docs/LICENSES.md` records Ollama and bge-m3 (both verified MIT from their official sources) and the stage 5 components that were missing.

### 23.2 Evaluation foundation
- **Corpus:** 34 synthetic documents (no real data, every file states it is synthetic): 10 hand-written (English, Arabic, mixed Arabic/English procurement guide, and one restricted document carrying the canary `CANARY-7F3A-ZEBRA-LANTERN`), plus 24 deterministic **near-duplicate subsidiary variants** (same wording, different numbers). The variants are hard negatives: without them a 10-document corpus would make recall@5 meaningless.
- **Questions:** 69 (63 answerable): 12 English and 12 Arabic factoids, 8 Arabic-to-English and 8 English-to-Arabic cross-lingual (each fact lives in only one language), 4 mixed-language, 12 digit-variant (4 groups x Western / Arabic-Indic / Persian digits), 6 subsidiary-specific, 1 restricted, 6 unanswerable (for stage 8's gate calibration).
- **Gold and judging:** a retrieved chunk is relevant iff it comes from the gold document and contains the gold evidence phrase (search-normalized on both sides); each gold item is credited once. Tests enforce that every evidence phrase exists in its document, is **unique to the gold documents** (an unchanged fact in a variant would punish correct answers; three questions were rewritten because of this check), lies wholly inside one real chunk, and that digit-variant groups are identical once normalized.
- **Metrics:** recall@1/3/5/10, MRR@10, nDCG@10, page-hit@5, per category and per language pair, digit-variant consistency; hand-computed unit tests.
- **Baselines** (unfiltered, single-stage, **not** the product retrieval path): vector (HNSW), full text language-aware, full text `simple`.

### 23.3 First numbers (real bge-m3 through Ollama; foundation, not the stage-7 evaluation)
| Retriever | recall@1 | recall@5 | recall@10 | MRR@10 | ar→en recall@3 | en→ar recall@10 |
|---|---|---|---|---|---|---|
| vector, bge-m3 | 0.70 | 0.95 | 0.98 | 0.81 | 1.00 | 1.00 |
| full text, language-aware | 0.65 | 0.73 | 0.76 | 0.69 | 0.00 | 0.12 |
| full text, simple | 0.57 | 0.67 | 0.71 | 0.62 | 0.00 | 0.12 |

Read with care (small corpus; about one chunk per document, so page-level hit equals document-level hit): bge-m3 genuinely retrieves **across languages** (an Arabic question finds an English-only fact and the other way round) where lexical search cannot; lexical search is competitive or better at rank 1-3 on same-language Arabic factoids (Arabic factoids recall@3 1.00 vs 0.83), which is what hybrid fusion should exploit in stage 7. The language-aware config beat `simple` here (overall recall@5 0.73 vs 0.67, "mixed" 1.00 vs 0.50), but that is one small measurement, not a decision. One answerable question (`ar-06`) is missed by the vector retriever in the top 10. Ranking ties are now broken deterministically; the earlier tie-dependent lexical numbers moved by up to 9 points of recall@1, a reminder that rank-1 numbers on this corpus are fragile.

### 23.4 Findings that changed the design
1. **Digit scripts changed the embedding.** The same question with Western, Arabic-Indic or Persian digits found the answer every time but returned different top-10 orders (consistency 0.25), violating the §11.5 requirement of identical results. Digits (and Arabic decimal/thousands separators, not the Arabic comma) are now folded to ASCII in the text sent to the embedder, at index and query time; consistency is 1.00 and the live test enforces it. Stage 7's query path must apply `fold_digits` before embedding.
2. **Deleted documents left their text and vectors in the index.** Fixed by the periodic purge (23.1). Retrieval must still filter on `documents.deleted_at` (the purge is periodic, not inside the delete request): a stage 7 test requirement.
3. **Documents processed before this stage had no vectors.** Found live (14 chunks); fixed by the periodic re-index, which also covers model changes.

### 23.5 Defects in my own earlier work, found by this stage's live checks
- **`beat` had been crash-looping since stage 5.** It was built as a separate image that kept a stale copy from before the `packaging` fix, and my stage 5 live verification never checked it, so the periodic sweeper was never exercised live (it was unit tested only). `beat` now reuses the worker's image and has a healthcheck; this stage verified live that beat schedules tasks, that the transient-failure retry fired by itself (a document failed during an embedder outage reached `ready` automatically once beat ran), and that the delete purge works.
- The `migrate` image was once stale for the same reason (not rebuilt), so `0004` had not run; the stage 5 report already notes it. Worth a CI check later that every service image is built from the current tree.

### 23.6 Tests (575 backend + 1 opt-in live; 69 frontend; ruff, ruff format, mypy strict on `app`, `tests` and `evals`, eslint, stylelint, tsc clean)
- **Embedder:** against a mock HTTP transport: request shape, retry on 503 then success, outage reported unavailable, 404/400/unusable body are permanent and never retried, batching, wrong dimensions rejected.
- **Pipeline/indexing (real Postgres + pgvector):** every chunk stored with a 1024-d vector and the model name; nearest-neighbour finds the right chunk; title and heading prefix and bounded batches; documents without chunks never reach the embedder; outage fails the document recoverably and keeps nothing; automatic retry (too soon: nothing; after the pause: requeued; then succeeds); retry limit; misconfigured model not retried; re-index moves stale chunks, is idempotent, only embeds stale chunks, embeds never-embedded chunks, stops cleanly when the embedder is down, ignores non-ready documents; CHECK refuses a vector without its model; the API role still cannot read chunks or vectors; **HNSW and both GIN indexes are used by the planner** (`EXPLAIN` with sequential scans disabled); Arabic full text across hamza/digit variants including Arabic-Indic digits; mixed-language chunks indexed for both languages; deleting a document purges its pages, chunks and vectors.
- **Evaluation:** metrics and harness (hand-computed), corpus integrity (139 checks), baselines end to end on the real database.
- **Mutation checks** (scratch copy outside the repository; the 5 stage 5 checks I had left open and 6 new ones), **all 11 killed:** lam-alef repair removed; lam-alef swap without the shared-box check; partial documents reported `ready`; stuck-document retries that never give up; SSE that never re-checks access; digits not folded in search normalization; re-index ignoring a changed model; wrong vector dimensions accepted; permanent embedding failures retried automatically; chunks stored under the wrong model name; embedding text dropping the title.
- **One intermittent failure** of the baselines test in one full run, not reproducible in 7 isolated runs and 2 further full runs. Probable cause: tie ordering that depended on the query plan; both baselines now break ties by document and chunk. Not proven; flagged.

### 23.7 Live verification (Docker Compose, real bge-m3)
Migration `0005` applied on the existing database (pgvector 0.8.7, all indexes present). The worker container reached the host's loopback-only Ollama through `host.docker.internal`. 17 documents (fixtures, Arabic DOCX and PDF, corpus) settled in 6 s with vectors; real cross-lingual nearest-neighbour queries from the worker (an Arabic maternity-leave question returned the English leave policy first; an English truck-load question returned the Arabic fleet document first). Outage drill: Ollama stopped, two uploads failed with `EMBEDDER_UNAVAILABLE` (shown in the Library with the new reason), Ollama restarted, "Try again" brought one to `ready`, beat's automatic retry brought the other. Delete + purge removed chunks and vectors; no chunk belongs to a deleted document.

### 23.8 Decisions, deviations and limits for your review
- **Ollama was installed on the host** at your choice (official release tarball, SHA-256 checked against the published checksum, Developer-ID signed binary, user-level directory, no sudo), listening on loopback only; `bge-m3` (1.2 GB) pulled. Both are MIT.
- **Only bge-m3 has been run.** The bake-off candidates (multilingual-e5-large and an Arabic-focused embedder) are **not** evaluated yet: their licenses, sizes and serving path are still unverified, and the decision belongs to stage 7 on a larger corpus. D10 stays open.
- **The corpus is small** (34 documents, about one chunk each, 63 answerable questions): enough to validate the harness and to see large effects, not to rank models that differ by a few points. Stage 7 must grow it (multi-page PDFs through the real parser, longer documents) before any decision.
- **"ready" now means extracted, embedded and indexed.** A document is searchable only by the model that embedded it; a model change makes chunks stale and the periodic re-index heals them (retrieval in stage 7 must only use chunks whose `embedding_model` is the current one).
- **HNSW and permission pre-filtering:** a filtered HNSW search can return fewer than k rows (post-filtering). pgvector 0.8 has iterative scans; stage 7 must measure this with restricted collections.
- No retrieval API, no query embedding, no reranker yet (stage 7).

### 23.9 Outstanding verification items (carried forward, still open)
| Item | Status | When |
|---|---|---|
| gitleaks locally; GitHub Actions workflow verified (needs Docker-in-CI for the Postgres, Redis and SeaweedFS testcontainers; the live Ollama test stays opt-in) | not done (no remote, gitleaks not installed) | before the first push |
| Python 3.12 test run of the suite (containers run 3.12) | partly (runtime verified in containers) | CI before first push |
| Real SMTP (STARTTLS/auth) delivery | not done (Mailpit only) | before any deployment |
| Rate limits, refresh locking, RLS helper cost, worker concurrency and queue/embedding throughput under load | not done | stage 11 |
| Playwright end-to-end tests | not done | stage 9 |
| Tablet width and signed-in shell review | not done | stage 9/10 |
| ~~Stage 5 mutation checks~~ | **done in this stage** (5 killed, plus 6 for stage 6) | closed |
| Embedder bake-off (multilingual-e5-large, an Arabic-focused model: license, size, serving, quality) and a larger corpus | open | stage 7 |
| Arabic extraction quality (tanween-alef words, short reversed runs) measured through retrieval | open | stage 7/11 |
| Permission pre-filtered HNSW behaviour (iterative scans) and `deleted_at` filtering in retrieval | open | stage 7 |
| CI check that every Compose service image is built from the current tree | open | before the first push |
| SeaweedFS capacity settings for production | not tuned | before deployment |
| Collection and ACL management UI | not built | stage 10 |
| The 10-second refresh grace-window trade-off | unchanged and documented in §19.1 | n/a |
| Nothing committed by me (the repository shows commits authored as you during the work) | by instruction | until you ask |

## 24. Stage 7 report: Retrieval (implemented, awaiting review)

### 24.1 What was built
**`POST /orgs/{org}/search`** (viewer and above, rate limited per user, 60/min, fails closed if Redis is down). Order of operations: authorize; compute the caller's accessible collections (the same rule every document read uses); embed the query with digits folded to ASCII; **vector leg** (pgvector HNSW, cosine, top 40) and **lexical leg** (language-aware full text, top 40), **both filtered in SQL** by organization, accessible collections and `deleted_at IS NULL` (the vector leg also by the current embedding model: vectors of different models are never mixed, chunks still on an old model remain findable lexically); fuse; return the top results with document, collection, pages, heading trail, passage, cosine similarity and fused score. The detail rows re-apply the same scope (defense in depth). The session is scoped to (user, organization), so **PostgreSQL RLS applies the same rule independently**: migration `0006` gives the API role `SELECT` on `chunks` (the access-aware policy has existed since stage 4; writes stay worker-only).
**Filtered HNSW:** pgvector 0.8 iterative scans (`hnsw.iterative_scan = relaxed_order`) keep a filtered search from returning too few rows when the nearest vectors belong to collections the caller cannot access.
**Degraded mode:** if the embedding service is down, search answers from the lexical leg alone and says so (`degraded: true`); it never errors for that reason. The query embedder has an 8 s timeout (`keep_alive` keeps the model loaded between requests).
**Debug:** `POST /orgs/{org}/search/debug` (administrators only, new `RETRIEVAL_DEBUG` action) returns each leg's rank and score, the lexical query, counts, timings and the model; an admin-only page `/{org}/retrieval` renders it (English and Arabic, RTL checked). **This page is an addition to the approved design** (an administrator tool, reached from a rail item shown only to owners and admins); flag if you want it moved or restyled.
**Fusion:** Reciprocal Rank Fusion with **k = 3 and the vector leg weighted 2x** (settings `rrf_k`, `rrf_vector_weight`; a test pins the defaults to the evaluated cell). See 24.3 for why the textbook k = 60 is wrong here.
**Removed:** the `simple`-config full-text column and index added in stage 6 (migration `0007`): it was only there to be measured and did not earn its place (24.3). The query-embedding cache and the reranker are not built (24.5).

### 24.2 Evaluation setup (`backend/evals/`, report: `docs/eval/stage7-retrieval.md`, reproducible: a regenerated report was row-for-row identical)
- **Corpus:** 44 synthetic documents: 20 hand-written (English, Arabic, one mixed, one restricted with a canary phrase, one Arabic document written with Arabic-Indic digits) and 24 deterministic near-duplicate variants with different numbers (hard negatives). Each document is one chunk, so page-level hit still equals document-level hit.
- **Questions:** 151 (141 answerable): English and Arabic factoids, English-to-Arabic and Arabic-to-English (every such fact exists in only one language), mixed, digit variants in three scripts, identifiers (policy numbers, two typed with Arabic-Indic digits), paraphrases, typos and diacritics, multi-passage, subsidiary-specific, restricted, unanswerable. Gold evidence is validated to exist in its document and **only** in its gold documents.
- **Candidates** (served by a throwaway `sentence-transformers` server in an isolated environment outside the repository; licenses verified from the model pages): `bge-m3` (the product's), `multilingual-e5-large` (MIT, with its required `query:`/`passage:` prefixes), Arabic-Triplet-Matryoshka-V2 (Apache-2.0, Arabic-only, 768-d). Reranker: **not evaluated** (you chose not to download it).

### 24.3 Results and decisions (recall@5 over 141 answerable questions; full matrix in the report)
| Configuration | overall | ar | en | ar→en | en→ar | identifiers | paraphrase | typos | multi | MRR |
|---|---|---|---|---|---|---|---|---|---|---|
| **Product: hybrid, bge-m3, k=3, vector x2** | **0.94** | 0.96 | 0.97 | 0.94 | 0.75 | 1.00 | 0.83 | 0.88 | 1.00 | 0.81 |
| hybrid with the textbook k=60 | 0.77 | 1.00 | 0.93 | **0.00** | 0.12 | 1.00 | 1.00 | 0.88 | 1.00 | 0.71 |
| vector only, bge-m3 | 0.90 | 0.89 | 0.90 | 1.00 | 0.81 | 0.92 | 0.67 | 0.88 | 0.88 | 0.80 |
| vector only, multilingual-e5-large | 0.87 | 0.96 | 1.00 | 0.31 | 0.62 | 1.00 | 1.00 | 0.88 | 1.00 | 0.78 |
| vector only, Arabic-Triplet-Matryoshka-V2 | 0.60 | 0.89 | 0.72 | 0.06 | 0.00 | 0.50 | 0.67 | 0.62 | 0.62 | 0.48 |
| full text only, language-aware | 0.75 | 1.00 | 0.97 | 0.00 | 0.00 | 1.00 | 1.00 | 0.88 | 0.62 | 0.71 |

1. **Embedder decision (closes D10): keep `bge-m3`.** It is the only candidate that retrieves across languages (e5 is excellent within a language, 1.00 English, but 0.31 Arabic-to-English; the Arabic-only model is cross-lingually blind, 768-d, and worse even on English). Two-model setups did not earn their complexity: an ensemble of all three reached 0.92 and a language-routed pair 0.92, both below the single-model hybrid (0.94).
2. **The textbook RRF (k = 60) destroyed cross-language retrieval** (Arabic-to-English 1.00 for vector alone, 0.00 hybrid): a document found by both legs beats the right one found only by the vector leg, and the four near-duplicate Arabic documents about leave matched lexically. A grid over k and weight found a wide good region (every cell with k <= 5 and weight >= 2 scores 0.89 to 0.95); `k=3, weight=2` is the choice. The cell was first picked by looking at all questions, so the dev/test split in the report is a robustness check, not a clean hold-out: chosen on the 69 stage 6 questions (dev 0.92) it scores 0.95 on the 82 new ones, while the cells that look best on dev (0.94) fall to 0.89 on test, i.e. the exact optimum is within noise; the region is what matters.
3. **Normalization earns its place:** without it, full-text recall on typos falls from 0.88 to 0.62 and digit variants stop returning identical results (consistency 0.00 against 1.00); for the vector leg, not folding query digits breaks consistency too (0.00).
4. **Language-aware text config vs `simple`:** a tie inside the hybrid (0.94 vs 0.94, MRR 0.82 vs 0.81) but a clear win when full text answers alone (MRR 0.71 vs 0.61, which is what degraded mode does), so language-aware stays and the `simple` column was dropped.
5. **Hybrid beats vector alone** (0.94 vs 0.90): lexical evidence repairs paraphrases (0.67 to 0.83), identifiers (0.92 to 1.00), multi-passage (0.88 to 1.00).
6. **Gates (PLAN 11.5, initial):** Arabic within 10 points of English **pass** (0.96 vs 0.97); Arabic-to-English >= 0.80 **pass** (0.94); digit variants identical **pass**; **English-to-Arabic >= 0.80 fails at 0.75** (12 of 16): only one question misses the top 10 entirely, the others sit at ranks 6 to 10 behind the near-duplicate Arabic variants of the right document, so this is mostly the hard-negative design, but it is a miss and is reported as one.

### 24.4 Tests (770 backend + 2 opt-in live; 71 frontend; ruff, ruff format, mypy strict on `app`, `tests` and `evals`, eslint, stylelint, tsc clean)
- **Retrieval API (27 tests, real Postgres, pgvector, RLS, pipeline):** ranking and fields; limit and collection narrowing; every role can search, only owner and admin can use debug; invalid requests; **restricted text never reaches unlisted members** (canary phrase, "Cedar", titles absent from every response), listed members, admins and owners find it; naming an inaccessible or unknown collection leaks nothing and looks identical; **revocation is effective on the very next search**; **a deleted document disappears at once**, before the sweeper purges its chunks; tenants never see each other's chunks and a foreign organization id gets the same 404 as a nonexistent one; stale-model chunks are excluded from vectors but found by text; degraded mode when the embedder is down; digit scripts and spelling variants return identical results, and the lexical leg alone separates documents that differ only by a number typed in any digit script; per-user rate limit; the query reaches the embedder with ASCII digits; **RLS alone** hides restricted chunks and refuses writes; **filtered HNSW** still fills the candidate list (forced onto the index, small `ef_search`).
- **Fusion** (hand-computed), **metrics and harness**, **corpus integrity** (every gold phrase exists, is unique to its gold documents and lies wholly inside one real chunk; digit groups identical once normalized), the **ablation plumbing** with the product path scored by the same harness and checked against the in-memory hybrid (recall@1 excluded on purpose: tied scores are ordered differently).
- Existing suites updated for the new permission model: the isolation matrix (generated from OpenAPI) now covers both new routes; the worker-role and embedding tests state that the API role reads chunks only through RLS and never writes them.
- **Mutation checks** (scratch copy outside the repository): 11 mutations, **all handled as designed**: soft-deleted documents included; vector leg ignoring the model; embedder outage raising; rate limit removed; query digits not folded; vector weight ignored; debug open to viewers; lexical normalization removed; **defense in depth proven both ways**: removing the application filter alone survives (RLS holds), weakening RLS alone leaves only the RLS-specific test failing (the application layer holds), removing both fails. Two of my own tests were weak and were fixed because the mutations exposed them: the filtered-HNSW test passed even without iterative scans (it never used the index), and the lexical test passed with normalization removed (Postgres's Arabic stemmer already folds hamza, so only digits discriminate).

### 24.5 Live verification (Docker Compose, real bge-m3, through Caddy)
Migrations `0006` and `0007` applied on the existing database. 44 documents processed in 15 s. Owner finds the board minutes by canary phrase; the unlisted member gets 200 with **no canary and no "Cedar" in the body**; debug 200 for the owner and 403 for the member. **40 searches: p50 61 ms, p95 74 ms** (embedding included, model warm). Embedder stopped: search still answered, `degraded: true`, about 1.5 s (client retry backoff). Real cross-language queries, an Arabic question answered from the English document and an English question from the Arabic one, a typo-ridden Arabic query, and an identifier typed with Arabic-Indic digits all return the right document. The debug page was checked in English and Arabic (RTL) in a browser.

### 24.6 Decisions, deviations and limits for your review
- **Downloads:** after your approval, `multilingual-e5-large` (2.2 GB) and the Arabic model (0.5 GB) plus the Python libraries went into an isolated environment outside the repository. The Hugging Face route ran at about 140 KB/s for hours; e5 initially also fetched an unneeded duplicate `pytorch_model.bin`, which I stopped. Nothing from that environment ships in the product images.
- **No reranker:** not downloaded, so not evaluated; **no reranker seam was built** (it would be dead code). If you want it evaluated, it needs the 2.3 GB `bge-reranker-v2-m3` and a serving path (Ollama has no rerank API).
- **No query-embedding cache** (PLAN section 10): at p50 61 ms it is not needed yet; revisit in stage 11.
- **Small corpus:** 44 documents, one chunk each; page-level and multi-chunk behavior are still not measured, and real PDFs, long documents and tables are absent. Fusion parameters tuned on a corpus this size may move on a real one; the report's grid is the tool to re-tune.
- **The "hard negatives" make recall@5 harsh** (four near-identical documents per topic); the en-to-ar gate miss should be read in that light.
- Admin debug page and nav item added beyond the approved mockup (24.1).
- Ranking ties are broken by chunk id in the product and by document name in the harness.

### 24.7 Outstanding verification items (carried forward, still open)
| Item | Status | When |
|---|---|---|
| gitleaks locally; GitHub Actions workflow verified (needs Docker-in-CI for the Postgres, Redis and SeaweedFS testcontainers; live Ollama and bake-off tests stay opt-in) | not done (no remote, gitleaks not installed) | before the first push |
| Python 3.12 test run of the suite (containers run 3.12) | partly (runtime verified in containers) | CI before first push |
| Real SMTP (STARTTLS/auth) delivery | not done (Mailpit only) | before any deployment |
| Rate limits, refresh locking, RLS helper cost, worker and embedding throughput, search latency at scale (p95 measured only on 44 chunks) | not done | stage 11 |
| Playwright end-to-end tests | not done | stage 9 |
| Tablet width and signed-in shell review (including the new retrieval page) | not done | stage 9/10 |
| ~~Embedder bake-off (D10) and a larger corpus~~ | **bake-off done; corpus grown to 44 documents / 151 questions, still small** | larger corpus: stage 8/11 |
| Reranker evaluation | open (not downloaded) | your call |
| Arabic extraction quality (tanween-alef words, short reversed runs) measured through retrieval | open (corpus uses Markdown, not parsed PDFs) | stage 11 |
| ~~Permission pre-filtered HNSW behavior and `deleted_at` filtering in retrieval~~ | **done in this stage** (tests + mutation) | closed |
| Citation re-check when a user loses access (existing conversation citations), moving a document between collections | open (no conversations or move feature yet) | stage 8/9/10 |
| CI check that every Compose service image is built from the current tree | open | before the first push |
| SeaweedFS capacity settings for production | not tuned | before deployment |
| Collection and ACL management UI | not built | stage 10 |
| The 10-second refresh grace-window trade-off | unchanged and documented in §19.1 | n/a |
| Nothing committed by me (the repository shows commits authored as you during the work) | by instruction | until you ask |
