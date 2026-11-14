# Third-party licenses

The project is licensed under Apache-2.0 (see `LICENSE`). This file tracks notable third-party components. It is reviewed at each stage that adds dependencies.

| Component | Use | License |
|---|---|---|
| Geist, Geist Mono (via `@fontsource-variable/*`) | UI fonts | SIL OFL 1.1 |
| Newsreader (via `@fontsource-variable/newsreader`) | Answer typeface | SIL OFL 1.1 |
| IBM Plex Sans Arabic (via `@fontsource/*`) | Arabic UI font | SIL OFL 1.1 |
| Noto Naskh Arabic (via `@fontsource/*`) | Arabic reading font | SIL OFL 1.1 |
| Next.js, React, next-intl, Tailwind CSS | Frontend | MIT |
| FastAPI, Starlette, Pydantic, structlog, uvicorn | Backend | MIT / BSD |
| asyncpg, redis-py, httpx | Backend | Apache-2.0 / MIT / BSD |
| PostgreSQL, pgvector | Database | PostgreSQL License |
| Redis 7 (image) | Cache/broker | BSD-3-Clause |
| SeaweedFS (image) | S3-compatible object storage | Apache-2.0 |
| Caddy (image) | Reverse proxy | Apache-2.0 |
| Celery, kombu | Background worker | BSD-3-Clause |
| pypdfium2 / PDFium | PDF text extraction (chosen over AGPL PyMuPDF) | Apache-2.0 or BSD-3-Clause / BSD-3-Clause |
| pypdf, Hypothesis (dev only) | Test fixtures and property tests | BSD-3-Clause / MPL-2.0 |
| LibreOffice (worker image only, run as a separate process, not linked) | DOCX/PPTX to PDF conversion | MPL-2.0 |
| Noto fonts, DejaVu fonts (worker image) | Arabic and Latin glyph coverage for conversion | SIL OFL 1.1 / Bitstream Vera-derived |
| Ollama (runs natively on the host, not distributed with this repository) | Local model server | MIT (verified from the upstream repository) |
| BAAI bge-m3 (downloaded by the user through Ollama, not distributed with this repository) | Multilingual embedding model, 1024 dimensions | MIT (verified from the model card) |

Licenses of the remaining AI models (the other embedding candidates in the stage 7 bake-off, Qwen3, Llama, the reranker) will be recorded here when they are adopted in stages 7 and 8. Verify each license before adopting.
