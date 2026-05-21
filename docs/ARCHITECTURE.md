# Architecture

## Overview

SmartVoucherDetection is an OCR-based bank voucher validation service. Users upload payment slips (comprobantes) as images or PDFs via a Next.js dashboard or directly through the REST API. The system extracts structured fields (bank name, amount, reference number, date) using a locally-hosted multimodal language model (GLM-OCR via llama.cpp), then runs three layers of duplicate detection before persisting the result.

## Components

| Component | Role | Internal Port | Image / Runtime |
|-----------|------|--------------|-----------------|
| api | FastAPI REST + OCR pipeline | 8000 | python:3.12-slim |
| webapp | Next.js 15 dashboard | 3000 | node:22-alpine |
| postgres | Primary database | 5432 | postgres:16-alpine |
| redis | Cache + Celery broker | 6379 | redis:7-alpine |
| celery-worker | Async OCR tasks | — | python:3.12-slim |
| llama-server | GLM-OCR inference | 8080 | ubuntu:24.04 (custom) |
| nginx | Reverse proxy + rate limiting | 80 | nginx:alpine |
| cloudflared | Cloudflare Tunnel agent | — | cloudflare/cloudflared |

## Data Flow: Upload Pipeline

1. User uploads image or PDF via webapp (Next.js) or directly to the API endpoint
2. **nginx** rate-limits the request and proxies to `api:8000` (100 req/min for API paths, 300 req/min for web)
3. **api** validates the MIME type (`image/jpeg`, `image/png`, `application/pdf`) and preprocesses the image using OpenCV (deskew + adaptive threshold)
4. **api** calls `llama-server:8080` with the base64-encoded image — GLM-OCR extracts structured fields from the voucher
5. **api** normalizes extracted fields: `parse_monto` (decimal parsing), `parse_fecha` (date normalization), `normalize_banco` (canonical bank name)
6. **Duplicate detection** runs in sequence:
   - **Layer 1** — SHA-256 hash exact match via Redis (`<10 ms`)
   - **Layer 2** — exact field match (referencia + monto + fecha) via PostgreSQL (`<50 ms`)
   - **Layer 3** — weighted fuzzy scoring using Levenshtein distance, TF-IDF, numeric comparison, and date proximity (`<200 ms`)
7. A **state machine** transitions the comprobante to a final state: `valido`, `sospechoso`, or `duplicado`
8. Result is persisted to PostgreSQL and the JSON response is returned to the client

## Duplicate Detection Layers

| Layer | Method | Threshold | Typical Speed |
|-------|--------|-----------|--------------|
| 1 — Hash | SHA-256 exact match (Redis) | Exact | < 10 ms |
| 2 — Fields | referencia + monto + fecha exact (PostgreSQL) | Exact | < 50 ms |
| 3 — Scoring | Weighted: Levenshtein + TF-IDF + numeric + date | ≥ 0.90 → duplicado / ≥ 0.75 → sospechoso | < 200 ms |

Layer 3 scoring weights (stored in `configuracion_sistema`, loaded at startup):

| Weight key | Default | Description |
|-----------|---------|-------------|
| `W_REF` | 0.35 | Reference number similarity |
| `W_TEXT` | 0.30 | Full-text similarity (TF-IDF) |
| `W_MONTO` | 0.20 | Amount proximity |
| `W_FECHA` | 0.15 | Date proximity |

## Database Schema

Key tables in the PostgreSQL database:

| Table | Description |
|-------|-------------|
| `organizaciones` | Tenant organizations that own API keys and comprobantes |
| `usuarios` | Users belonging to an organization (linked to WP via `wp_user_id`) |
| `comprobantes` | Core voucher records: raw fields, normalized fields, hash, current state |
| `validaciones` | Duplicate detection results per comprobante (one row per layer that ran) |
| `log_procesamiento` | Append-only audit log: every state transition with timestamp and actor |
| `configuracion_sistema` | Key-value store for scoring weights and system parameters |

## Scoring Weights (configuracion_sistema)

Weights for the Layer 3 fuzzy scorer are stored in the `configuracion_sistema` table as VARCHAR key-value pairs. They are loaded once at API startup into an in-process cache (`ScoringWeights` dataclass in `api/services/config_service.py`). The cache is invalidated and reloaded on the next request after a DB update, so weights can be changed without restarting the API.

## Network Topology

```
[Cloudflare CDN]
       │
[cloudflared] ─── cloudflared-network ───► [nginx:80]
                                                │
                                    ┌───────────┴───────────┐
                                    │                       │
                              webapp:3000              api:8000
                                                           │
                                              smartvoucher-net
                                    ┌──────────────┬────────┴──────────────┐
                                    │              │                       │
                              postgres:5432   redis:6379         llama-server:8080
                                                   │
                                           celery-worker
```

All internal services share the `smartvoucher-net` bridge network. Only `nginx` is also attached to `cloudflared-network`, ensuring that no internal service is directly reachable from the tunnel.
