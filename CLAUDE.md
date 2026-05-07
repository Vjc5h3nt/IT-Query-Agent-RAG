# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

IT Query Agent RAG — an enterprise RAG system for IT knowledge management. Uses hybrid search (dense vectors + BM25) with cross-encoder reranking, backed by AWS Bedrock (Claude 3 Haiku LLM, Amazon Titan embeddings) and ChromaDB.

## Commands

### Backend (managed with uv)
```bash
cd backend
uv sync                                                                     # Install/sync deps
uv run uvicorn app.main:app --reload --reload-include=".env" --host 0.0.0.0 --port 8000  # Dev server (watches .env so credential refreshes auto-reload)
uv run python scripts/ingest_jira.py --xml path/to/export.xml              # CLI JIRA ingestion
uv run python scripts/reset_data.py                                         # Reset vector stores
```

### Frontend (managed with bun)
```bash
cd frontend
bun install      # Install deps
bun run dev      # Dev server on http://localhost:5173
bun run build    # Production build to dist/
bun run lint     # ESLint
```

### Docker (full stack)
```bash
docker compose up --build              # Backend + Frontend + OpenSearch
docker compose --profile debug up      # Include OpenSearch Dashboards
docker compose down                    # Stop all
```

### Local development (two terminals)
```bash
# Terminal 1 — Backend
cd backend && uv run uvicorn app.main:app --reload --reload-include=".env" --host 0.0.0.0 --port 8000

# Terminal 2 — Frontend
cd frontend && bun run dev
```

## Project Structure

```
IT-Query-Agent-RAG/
├── backend/
│   ├── app/                    # FastAPI application
│   │   ├── main.py             # Entry point, lifespan, route mounting
│   │   ├── config.py           # Pydantic Settings (all tunables centralized)
│   │   ├── models.py           # Request/response Pydantic models
│   │   └── api/                # Route handlers
│   ├── services/               # Business logic
│   │   ├── rag_engine.py       # RAG orchestration (retrieve + generate)
│   │   ├── bedrock_client.py   # AWS Bedrock LLM/embedding client
│   │   ├── embedding_helpers.py # Shared retry + normalize utilities
│   │   ├── vector_store.py     # ChromaDB wrapper
│   │   ├── hybrid_retriever.py # Dense + BM25 RRF fusion
│   │   ├── retriever.py        # Retriever abstractions (Strategy pattern)
│   │   ├── bm25_store.py       # OpenSearch BM25 store
│   │   └── jira/               # JIRA-specific parsing pipeline
│   ├── database/               # SQLAlchemy models + session DB
│   ├── scripts/                # CLI tools (ingest, reset, eval, test)
│   ├── Dockerfile              # Production container
│   └── pyproject.toml          # Dependencies (uv)
├── frontend/
│   ├── src/
│   │   ├── App.jsx             # Root component (state orchestration)
│   │   ├── components/         # UI components
│   │   └── services/api.js     # Axios client
│   ├── Dockerfile              # Multi-stage build (node → nginx)
│   └── nginx.conf              # Production reverse proxy config
├── docker-compose.yml          # Full-stack orchestration
└── data/                       # Document drop folder for ingestion
```

## Architecture

### Backend (FastAPI + Python)

**Two vector collections** with different retrieval strategies:
- `document_chunks` — general docs (PDF, DOCX, TXT, MD). Dense vector search only.
- `jira_tickets` — JIRA tickets. Hybrid: dense + BM25 (OpenSearch) → RRF fusion → cross-encoder reranking.

**Request flow for `/chat`:**
1. `api/chat.py` → casual detection → query contextualization
2. `services/rag_engine.py` → hybrid retrieval → context assembly
3. `services/bedrock_client.py` → LLM generation with strict grounding
4. `database/session_db.py` → persist with rolling 5-message memory window

**Configuration:** All tunables (batch sizes, retry delays, LLM temperature, query thresholds) are centralized in `app/config.py`. No magic numbers in service code.

**Database:** `database/session_db.py` uses a `@contextmanager`-based `_session()` pattern. SQL-level LIMIT for message queries.

### Frontend (React 19 + Vite)

SPA with vanilla CSS. State lives in `App.jsx`. API client at `services/api.js` uses Axios with error interceptor. JIRA ingestion uses SSE streaming.

### Docker Deployment

- **backend** container: `uv run uvicorn` on port 8000
- **frontend** container: nginx on port 80, proxies `/chat`, `/sessions`, `/ingest`, `/health` to backend
- **opensearch** container: BM25 index on port 9200
- Volumes: `app_data`, `app_storage`, `opensearch_data` for persistence

## API Endpoints

- `POST /chat` — RAG query with session context
- `POST/GET/PATCH/DELETE /sessions` — session CRUD
- `POST /ingest` — document ingestion (scans `data/` folder)
- `GET /ingest/status` | `GET /ingest/vector-stats` — metadata/counts
- `DELETE /ingest/vector-store` | `DELETE /ingest/jira-vector-store` — reset collections
- `POST /ingest/jira/{upload,extract,clean,index}` — streaming JIRA pipeline
- `GET /health` — health check

## Important Behaviors

- RAG engine boosts `top_k` for listing queries (configurable via `listing_query_boost`)
- Strict grounding: system prompts enforce answering only from ingested knowledge
- Ingestion is incremental (SHA-256 dedup). Only new/modified files processed.
- All regex patterns compiled at module level for performance
- AWS credential expiration detected and surfaced as 401
