# IT Query Agent RAG

An enterprise-grade Retrieval-Augmented Generation system for IT knowledge management. Combines hybrid search (dense vectors + BM25), cross-encoder reranking, and AWS Bedrock to deliver grounded, citation-backed answers from your organization's documents and JIRA tickets.

---

## Table of Contents

- [Overview](#overview)
- [Architecture](#architecture)
- [Features](#features)
- [Tech Stack](#tech-stack)
- [Prerequisites](#prerequisites)
- [Getting Started](#getting-started)
- [Configuration](#configuration)
- [Usage](#usage)
- [API Reference](#api-reference)
- [Project Structure](#project-structure)
- [Contributing](#contributing)
- [License](#license)

---

## Overview

IT Query Agent RAG solves a common enterprise challenge: knowledge is scattered across documents, wikis, and issue trackers, making it difficult for teams to find accurate answers quickly. This system ingests your organization's documents (PDF, DOCX, TXT, Markdown) and JIRA ticket exports, then provides a conversational interface that retrieves and synthesizes information with full source attribution.

Every answer is strictly grounded in ingested content. If the system lacks sufficient context, it says so rather than fabricating a response.

---

## Architecture

```
                         +------------------+
                         |   React 19 SPA   |
                         |   (Vite + Nginx) |
                         +--------+---------+
                                  |
                            HTTP / SSE
                                  |
                         +--------v---------+
                         |   FastAPI Backend |
                         |                   |
                         |  +-------------+  |
                         |  | RAG Engine  |  |
                         |  +------+------+  |
                         |         |         |
                    +----v----+  +-v-------+ |
                    | ChromaDB|  |OpenSearch| |
                    | (Dense) |  | (BM25)  | |
                    +---------+  +---------+ |
                         |                   |
                    +----v----------------+  |
                    | AWS Bedrock         |  |
                    | Claude 3 | Titan    |  |
                    +-------------------------+
```

**Request flow:**

1. User submits a query through the chat interface
2. The backend contextualizes the query using session history (rolling 5-message window)
3. Retrieval runs in parallel: dense vector search (ChromaDB) + BM25 keyword search (OpenSearch)
4. Results are fused via Reciprocal Rank Fusion (RRF) and reranked with a cross-encoder model
5. Top chunks are assembled into a grounded prompt sent to AWS Bedrock (Claude)
6. The response is returned with source citations, latency metrics, and token usage

---

## Features

**Retrieval & Search**
- Hybrid search combining semantic embeddings (ChromaDB) with lexical matching (BM25 via OpenSearch)
- Cross-encoder reranking (`cross-encoder/ms-marco-MiniLM-L-6-v2`) for precision at the top of the results list
- Reciprocal Rank Fusion for combining heterogeneous ranking signals
- Configurable `top_k`, similarity thresholds, and chunk parameters

**Document Ingestion**
- Supports PDF, DOCX, TXT, and Markdown via Docling
- JIRA XML import with full metadata preservation (priority, status, assignee, resolution)
- Incremental processing with SHA-256 deduplication -- only new or modified content is indexed
- Streaming progress for JIRA pipeline stages (upload, extract, clean, index)

**Conversation & Memory**
- Multi-turn sessions with persistent storage (SQLite via SQLAlchemy)
- Rolling context window (configurable, default 5 messages) for memory-efficient conversations
- Session management: create, rename, delete, and switch between conversations

**Observability**
- Source citations with document name and page references
- Reranking audit logs showing candidate reordering
- Per-turn latency breakdown (retrieval vs. generation)
- Token usage tracking (input, output, total)

**Interface**
- Responsive design with dark and light theme support
- Glassmorphism-styled header elements
- System font stack (San Francisco, Segoe UI, Roboto) for native feel

---

## Tech Stack

| Layer | Technology |
|---|---|
| **LLM** | AWS Bedrock (Claude 3 Haiku / Sonnet) |
| **Embeddings** | Amazon Titan Embed Text v1 (1536-dim) |
| **Vector Store** | ChromaDB (L2-normalized cosine similarity) |
| **Keyword Search** | OpenSearch 2.13 (BM25) |
| **Reranker** | Sentence-Transformers Cross-Encoder |
| **Backend** | FastAPI, Python 3.12+, LangChain, SQLAlchemy |
| **Frontend** | React 19, Vite 7, Axios, react-markdown |
| **Tooling** | uv (Python), Bun (JS), Docker Compose |
| **Deployment** | Nginx reverse proxy, multi-stage Docker builds |

---

## Prerequisites

- **AWS Account** with Bedrock access enabled for Claude 3 and Amazon Titan models
- **AWS credentials** configured locally (`~/.aws/credentials` or environment variables)
- **Python 3.12+**
- **Node.js 18+** or **Bun 1.0+**
- **Docker & Docker Compose** (for containerized deployment)

---

## Getting Started

### Option 1: Docker (Recommended)

The fastest way to run the full stack:

```bash
# Clone the repository
git clone https://github.com/Vjc5h3nt/IT-Query-Agent-RAG.git
cd IT-Query-Agent-RAG

# Copy environment files
cp backend/.env.example backend/.env
cp .env.example .env

# Edit backend/.env with your AWS configuration

# Start all services
docker compose up --build
```

The application will be available at `http://localhost`. OpenSearch Dashboards can be enabled for debugging:

```bash
docker compose --profile debug up
```

### Option 2: Local Development

**Backend** (requires [uv](https://docs.astral.sh/uv/)):

```bash
cd backend
uv sync
cp .env.example .env    # Edit with your AWS credentials
uv run uvicorn app.main:app --reload --reload-include=".env" --host 0.0.0.0 --port 8000
```

**Frontend** (requires [Bun](https://bun.sh/)):

```bash
cd frontend
bun install
bun run dev
```

The frontend dev server runs at `http://localhost:5173` and proxies API requests to the backend.

---

## Configuration

All backend settings are centralized in `backend/app/config.py` and can be overridden via environment variables in `backend/.env`:

| Variable | Default | Description |
|---|---|---|
| `AWS_REGION` | `us-east-1` | AWS region for Bedrock |
| `AWS_BEDROCK_MODEL_ID` | `anthropic.claude-3-haiku-20240307-v1:0` | LLM model identifier |
| `AWS_BEDROCK_EMBEDDING_MODEL_ID` | `amazon.titan-embed-text-v1` | Embedding model |
| `TOP_K_RESULTS` | `5` | Number of retrieval candidates |
| `RERANK_TOP_K` | `5` | Chunks passed to the LLM after reranking |
| `SIMILARITY_THRESHOLD` | `0.7` | Minimum relevance score for inclusion |
| `CHUNK_SIZE` | `1000` | Document chunk size (characters) |
| `CHUNK_OVERLAP` | `200` | Overlap between adjacent chunks |
| `MAX_MEMORY_MESSAGES` | `5` | Session context window depth |
| `LLM_TEMPERATURE` | `0.1` | Generation temperature |
| `LLM_MAX_TOKENS` | `4096` | Maximum output tokens |

---

## Usage

### Ingesting Documents

1. Place PDF, DOCX, TXT, or Markdown files in the `data/` directory
2. Open the application and click **Ingest Documents** in the sidebar
3. Only new or modified files will be processed (SHA-256 deduplication)

### Ingesting JIRA Tickets

Use the JIRA Ingest workflow in the sidebar, or the CLI:

```bash
cd backend
uv run python scripts/ingest_jira.py --xml path/to/export.xml
```

The pipeline streams progress through four stages: upload, extract, clean, and index.

### Querying

Type a question in the chat interface. The system retrieves relevant content from your ingested knowledge base, reranks candidates, and generates a grounded answer with source citations.

Click the **Reranking** or **Metrics** chips below a response to inspect retrieval details, latency breakdown, and token consumption.

### Managing Sessions

Sessions persist across browser reloads. Use the sidebar to create, rename, switch between, or delete conversations.

### Resetting Data

```bash
cd backend
uv run python scripts/reset_data.py
```

Vector stores and the session database can also be reset individually through the UI or the API.

---

## API Reference

### Chat

| Method | Endpoint | Description |
|---|---|---|
| `POST` | `/chat` | Submit a query with session context |

### Sessions

| Method | Endpoint | Description |
|---|---|---|
| `POST` | `/sessions` | Create a new session |
| `GET` | `/sessions` | List all sessions |
| `GET` | `/sessions/{id}` | Retrieve session details |
| `PATCH` | `/sessions/{id}` | Update session metadata |
| `DELETE` | `/sessions/{id}` | Delete a session |

### Ingestion

| Method | Endpoint | Description |
|---|---|---|
| `POST` | `/ingest` | Ingest documents from `data/` |
| `GET` | `/ingest/status` | Ingestion metadata and status |
| `GET` | `/ingest/vector-stats` | Collection statistics |
| `DELETE` | `/ingest/vector-store` | Reset document collection |
| `DELETE` | `/ingest/jira-vector-store` | Reset JIRA collection |

### JIRA Pipeline (SSE Streaming)

| Method | Endpoint | Description |
|---|---|---|
| `POST` | `/ingest/jira/upload` | Upload JIRA XML file |
| `POST` | `/ingest/jira/extract` | Extract tickets from XML |
| `POST` | `/ingest/jira/clean` | Clean HTML content |
| `POST` | `/ingest/jira/index` | Index tickets to vector store |

### System

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/health` | Health check |
| `GET` | `/settings` | Server configuration |

---

## Project Structure

```
IT-Query-Agent-RAG/
├── backend/
│   ├── app/
│   │   ├── main.py                 # Application entry point and route mounting
│   │   ├── config.py               # Centralized settings (Pydantic BaseSettings)
│   │   ├── models.py               # Request/response schemas
│   │   └── api/                    # Route handlers (chat, sessions, ingestion)
│   ├── services/
│   │   ├── rag_engine.py           # RAG orchestration: retrieve, rerank, generate
│   │   ├── bedrock_client.py       # AWS Bedrock LLM and embedding client
│   │   ├── vector_store.py         # ChromaDB collection management
│   │   ├── hybrid_retriever.py     # Dense + BM25 fusion via RRF
│   │   ├── retriever.py            # Retriever strategy abstractions
│   │   ├── bm25_store.py           # OpenSearch BM25 integration
│   │   ├── document_processor.py   # Multi-format document chunking
│   │   ├── embedding_helpers.py    # Retry and normalization utilities
│   │   └── jira/                   # JIRA XML parsing and preparation
│   ├── database/
│   │   └── session_db.py           # SQLAlchemy session persistence
│   ├── scripts/                    # CLI tools (ingest, reset, evaluate)
│   ├── Dockerfile
│   └── pyproject.toml
├── frontend/
│   ├── src/
│   │   ├── App.jsx                 # Root component and state management
│   │   ├── components/             # UI components (chat, sidebar, modals)
│   │   └── services/api.js         # Axios HTTP client
│   ├── nginx.conf                  # Production reverse proxy configuration
│   ├── Dockerfile                  # Multi-stage build (Bun -> Nginx)
│   └── package.json
├── docker-compose.yml              # Full-stack orchestration
├── data/                           # Document drop folder for ingestion
└── storage/                        # Persistent data (vector DB, sessions)
```

---

## Contributing

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/your-feature`)
3. Commit your changes
4. Push to your branch and open a pull request

---

## License

This project is provided as-is for educational and internal use. See the repository for any applicable license terms.
