# SmartVoucherDetection

![Python 3.12](https://img.shields.io/badge/Python-3.12-blue?style=flat-square&logo=python)
![FastAPI](https://img.shields.io/badge/FastAPI-0.115-009688?style=flat-square&logo=fastapi)
![Next.js 15](https://img.shields.io/badge/Next.js-15-black?style=flat-square&logo=next.js)
![PostgreSQL 16](https://img.shields.io/badge/PostgreSQL-16-336791?style=flat-square&logo=postgresql)
![License MIT](https://img.shields.io/badge/License-MIT-green?style=flat-square)

OCR-based bank voucher validation system with 3-layer duplicate detection. Processes payment slips (comprobantes) via multimodal AI, extracts structured fields, and classifies each voucher as valid, suspicious, or duplicate using hash matching, exact field comparison, and weighted fuzzy scoring.

## Tech Stack

| Component | Technology | Version |
|-----------|-----------|---------|
| Backend API | FastAPI + Python | 3.12 |
| Database | PostgreSQL + pg_trgm | 16 |
| Cache / Queue | Redis + Celery | 7 |
| OCR Model | GLM-OCR (llama.cpp) | b9264 |
| Frontend | Next.js + Tailwind | 15 + 4 |
| WordPress Plugin | PHP | 8.1+ |
| Container | Docker + Cloudflare Tunnel | — |

## Quick Start (Dev)

```bash
# 1. Start infrastructure
cd infra && docker compose up -d

# 2. Run migrations
cd api && uv run alembic upgrade head

# 3. Start llama-server (in separate terminal)
bash llama.cpp/GLM-OCR.sh

# 4. Start API
cd api && uv run fastapi dev main.py

# 5. Start webapp
cd webapp && pnpm dev
```

## Quick Start (Production)

See [DEPLOYMENT.md](docs/DEPLOYMENT.md) for full production setup.

Key steps:

1. Configure `.env` — copy `.env.example` and fill in all required values
2. Start the stack:

```bash
docker compose -f infra/docker-compose.prod.yml up -d
```

## Architecture

```
Internet
   │
Cloudflare Tunnel
   │
nginx:alpine ──────────────────────┐
   │                               │
webapp:3000 (Next.js)        api:8000 (FastAPI)
                                   │
                  ┌────────────────┼────────────────┐
                  │                │                │
             postgres:5432    redis:6379    llama-server:8080
                                   │                │
                             celery-worker     GLM-OCR model
                                                (volume mount)
```

## Documentation

- [Architecture](docs/ARCHITECTURE.md)
- [Deployment](docs/DEPLOYMENT.md)
- [Dataset Evaluation](docs/dataset-evaluation.md)
- [llama-server Setup](docs/llama-server.md)

## License

[MIT](LICENSE)
