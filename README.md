# 🧙‍♂️ IT Query Agent RAG — Production-Grade AI Assistant

A high-performance RAG (Retrieval Augmented Generation) system designed for deep document grounding and enterprise IT knowledge management. Leverages **AWS Bedrock**, **Hybrid Search**, and **Cross-Encoder Reranking** to provide hallucination-free answers with precise citations.

---

## 🌟 Key Features

### 🔍 Advanced Retrieval & Grounding
- **Hybrid Search Architecture**: Combines semantic vector search (**ChromaDB**) with traditional keyword search (**BM25**) for robust multi-modal retrieval.
- **Cross-Encoder Reranking**: Utilizes an enterprise-grade reranker (`cross-encoder/ms-marco-MiniLM-L-6-v2`) to prioritize the most semantically relevant chunks before generation.
- **JIRA XML Integration**: Deep parsing and ingestion of JIRA tickets, including metadata like Priority, Status, Assignee, and Resolution.
- **Incremental Ingestion**: Smart deduplication via SHA-256 hashing—only processes new or modified files.

### 🧠 Modern AI Stack
- **AWS Bedrock Integration**: Powered by **Claude 3 Haiku** for high-speed, cost-effective generation and **Amazon Titan** for high-dimensional embeddings.
- **Rolling Session Memory**: Maintains conversation context via persistent session storage (SQLite) with automatic context window management (k=5).
- **Strict Grounding Enforcement**: Advanced system prompting ensures the agent answers ONLY from ingested knowledge, preventing hallucinations.

### 🎨 Premium User Experience
- **ChatGPT-Inspired UI**: Sleek, modern interface using an adaptive system font stack (**San Francisco**, **Segoe UI**, **Roboto**).
- **RAG Audit & Transparency**:
  - **Reranking Logs**: View a real-time audit of how candidates were re-ordered by the AI.
  - **Latency Metrics**: Detailed breakdown of retrieval vs. generation time.
  - **Token Usage**: Track input, output, and total token consumption per turn.
- **Source Citations**: Interactive citations with direct links to the source document and page number.
- **Theme Support**: Fully polished Dark and Light modes with "Glassmorphism" headers.

---

## 🛠️ Technology Stack

### Backend (**FastAPI + Python**)
- **Vector Database**: ChromaDB (L2-normalized cosine similarity)
- **Search**: BM25 (Rank-BM25) for lexical matching
- **Reranking**: Sentence-Transformers (Cross-Encoder)
- **Database**: SQLAlchemy + SQLite for session persistence
- **Frameworks**: LangChain & LangGraph for advanced RAG piping and memory
- **Document Parsing**: Docling for high-quality multi-format extraction

### Frontend (**React + Vite**)
- **Framework**: React 18+
- **Styling**: Vanilla CSS with a tailored Design System (HSL tokens, system font stacks)
- **Markdown**: `react-markdown` with GFM and custom citation badges

---

## 🚀 Installation & Setup

### 1. Backend Configuration
```bash
cd backend
python -m venv venv
source venv/bin/activate  # Windows: .\venv\Scripts\activate
pip install -r requirements.txt
```

**Configure Environment (`backend/.env`):**
```env
AWS_REGION=us-east-1
AWS_BEDROCK_MODEL_ID=anthropic.claude-3-haiku-20240307-v1:0
AWS_BEDROCK_EMBEDDING_MODEL_ID=amazon.titan-embed-text-v1

# RAG Settings
TOP_K_RESULTS=15          # Candidates for reranking
RERANK_TOP_N=5           # Final context count
SIMILARITY_THRESHOLD=0.7
```

### 2. Frontend Configuration
```bash
cd frontend
npm install
npm run dev
```

---

## 📁 System Architecture & Directory Structure

```
IT-Query-Agent-RAG/
├── backend/
│   ├── app/                # FastAPI main logic & endpoints
│   ├── services/           # The Engine
│   │   ├── jira/           # JIRA XML parsing & vector preparation
│   │   ├── hybrid_retriever.py # Vector + BM25 fusion
│   │   ├── rag_engine.py   # Reranking & LLM orchestration
│   │   └── vector_store.py # ChromaDB management
│   └── database/           # SQLite session storage
├── frontend/
│   ├── src/
│   │   ├── components/     # UI Elements (Modals, Chat, Sidebar)
│   │   └── services/       # API client logic
├── data/                   # Document Drop Folder (PDF, TXT, MD, DOCX)
└── storage/                # Persistent Storage (Databases & Vector Index)
```

---

## � How to Use

1. **Ingest Knowledge**: Place your PDFs, Docs, or JIRA XMLs in the `data/` folder and click **📥 Ingest Documents** in the sidebar.
2. **JIRA Specific Ingest**: Use the **JIRA Ingest** tool to specifically process ticket exports.
3. **Knowledge Base Toggle**: Use the book icon in the header to switch between **RAG Mode** (answers from docs) and **General Mode**.
4. **Audit Performance**: Click on the **Reranking** or **Metics** chips below an AI message to see the "why" behind the answer.

---

## 🔒 Security & Best Practices
- **No Hallucination**: The system uses a strict "I don't know" fallback if the context score is too low.
- **Privacy**: All vector stores and session databases are stored locally on your machine.
- **Cost Control**: Claude 3 Haiku ensures high performance with minimal AWS token costs.

---
**Built with ❤️ for IT Teams & Developers.**
