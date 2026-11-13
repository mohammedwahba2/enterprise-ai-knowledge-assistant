# Enterprise AI Knowledge Assistant

Ask questions of your organization's documents and get answers that cite the exact document and page. English and Arabic (RTL) from day one. Runs entirely on open-source components and local models.

**Status: stage 1 of 12 (foundations).** See [`docs/PLAN.md`](docs/PLAN.md) for architecture, roadmap and decisions, and [`docs/design/final/`](docs/design/final/) for the approved UI mockup. Nothing beyond the foundations is implemented yet.

## Quick start

Requirements: Docker, plus Node 22 + pnpm 10 and Python 3.11+ with [uv](https://docs.astral.sh/uv/) for local development.

```bash
./scripts/init-env.sh          # generates .env with random secrets (never committed)
docker compose up -d --build --wait
open http://localhost:8080     # UI (redirects to /en); /ar for Arabic
curl http://localhost:8080/api/health/ready
```

## Development

```bash
cd backend  && uv sync && uv run ruff check . && uv run mypy && uv run pytest
cd frontend && pnpm install && pnpm lint && pnpm typecheck && pnpm test && pnpm build
```

## Rules that matter

- **No secrets in the repo.** `.env` is ignored; gitleaks runs in CI. Demo data will be synthetic only.
- **RTL is enforced:** physical CSS properties and Tailwind utilities (`left`, `ml-*`, `text-left`, …) fail lint. Use logical ones.
- Western digits (0-9) are the default in every language.

License: [Apache-2.0](LICENSE).
