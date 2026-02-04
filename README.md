# RAG Chatbot with Session Memory and AWS Bedrock

A production-ready RAG (Retrieval Augmented Generation) chatbot system with multi-session support, rolling memory management, and strict document grounding using AWS Bedrock.

## 🌟 Features

- **AWS Bedrock Integration**: Uses Claude 3 Haiku for responses and Titan for embeddings
- **Multi-Session Chat**: Create and manage multiple independent chat sessions
- **Rolling Memory**: Automatic 5-message conversation window using LangChain
- **Incremental Ingestion**: Smart document processing - only ingests new/modified files
- **Persistent Storage**: ChromaDB vector store and SQLite session database
- **Strict Grounding**: Responses only from ingested documents - no hallucination
- **Source Citations**: Every answer includes document sources
- **Modern UI**: Clean React interface with real-time updates

## 🏗️ Architecture

### Backend (FastAPI + Python)
- **Vector Database**: ChromaDB (persistent local storage)
- **Session Management**: SQLite with SQLAlchemy ORM
- **Memory**: LangChain ConversationBufferWindowMemory (k=5)
- **Document Processing**: SHA-256 hash-based incremental ingestion
- **LLM**: AWS Bedrock - Claude 3 Haiku
- **Embeddings**: AWS Bedrock - Amazon Titan Embeddings

### Frontend (React + Vite)
- Minimalistic, clean design
- Session sidebar with create/delete functionality
- Chat interface with message history
- Real-time loading states
- Responsive layout

## 📋 Prerequisites

1. **Python 3.10+**
2. **Node.js 18+**
3. **AWS CLI configured** with valid credentials
4. **AWS Bedrock Access** to:
   - `anthropic.claude-3-haiku-20240307-v1:0`
   - `amazon.titan-embed-text-v1`

### Verify AWS Access

```bash
aws bedrock list-foundation-models --region us-east-1
```

## 🚀 Quick Start

### 1. Clone/Navigate to Project

```bash
cd c:/Users/tejas/OneDrive/Desktop/ag
```

### 2. Backend Setup

```bash
cd backend

# Create virtual environment
python -m venv venv
.\\venv\\Scripts\\activate  # Windows
# source venv/bin/activate  # Linux/Mac

# Install dependencies
pip install -r requirements.txt

# Create .env file from example
copy .env.example .env

# Edit .env and configure (especially AWS_REGION if needed)
```

### 3. Frontend Setup

```bash
cd ../frontend

# Install dependencies
npm install
```

### 4. Add Documents

Place your documents in the `data/` folder (will be created automatically):

```bash
# Supported formats: PDF, TXT, MD, DOCX
cp your-documents.pdf ../data/
```

### 5. Start the Application

**Terminal 1 - Backend:**
```bash
cd backend
.\\venv\\Scripts\\activate
python -m uvicorn app.main:app --reload
```

**Terminal 2 - Frontend:**
```bash
cd frontend
npm run dev
```

### 6. Access the Application

Open your browser to: **http://localhost:5173**

### 7. Ingest Documents

1. Click "📥 Ingest Documents" button in the sidebar
2. Wait for confirmation
3. Start chatting!

## 📁 Project Structure

```
ag/
├── backend/
│   ├── app/
│   │   ├── config.py          # Settings & configuration
│   │   ├── models.py          # Pydantic models
│   │   ├── main.py            # FastAPI app
│   │   └── api/
│   │       ├── chat.py        # Chat endpoints
│   │       ├── sessions.py    # Session management
│   │       └── ingestion.py   # Document ingestion
│   ├── services/
│   │   ├── bedrock_client.py  # AWS Bedrock integration
│   │   ├── vector_store.py    # ChromaDB operations
│   │   ├── document_processor.py  # Document loading & chunking
│   │   ├── rag_engine.py      # RAG retrieval & generation
│   │   └── session_manager.py # Session & memory management
│   ├── database/
│   │   └── session_db.py      # SQLite database layer
│   └── requirements.txt
├── frontend/
│   ├── src/
│   │   ├── components/        # React components
│   │   ├── services/          # API client
│   │   └── App.jsx
│   └── package.json
├── data/                      # Place documents here
└── storage/                   # Auto-created
    ├── chroma_db/            # Vector database (persistent)
    └── sessions.db           # Session database (persistent)
```

## 🔧 Configuration

Edit `backend/.env`:

```env
# AWS Configuration
AWS_REGION=us-east-1
AWS_BEDROCK_MODEL_ID=anthropic.claude-3-haiku-20240307-v1:0
AWS_BEDROCK_EMBEDDING_MODEL_ID=amazon.titan-embed-text-v1

# RAG Settings
TOP_K_RESULTS=5
SIMILARITY_THRESHOLD=0.7
CHUNK_SIZE=1000
CHUNK_OVERLAP=200
MAX_MEMORY_MESSAGES=5
```

## 📚 API Endpoints

### Sessions
- `POST /sessions` - Create new session
- `GET /sessions` - List all sessions
- `GET /sessions/{id}` - Get session details
- `DELETE /sessions/{id}` - Delete session

### Chat
- `POST /chat` - Send message and get response

### Ingestion
- `POST /ingest` - Ingest documents (incremental)
- `GET /ingest/status` - Get ingestion history

### Health
- `GET /health` - Health check

## 💡 How It Works

### Incremental Ingestion
1. Files in `data/` folder are scanned
2. SHA-256 hash calculated for each file
3. Hash compared with database records
4. Only new/modified files are processed
5. Documents chunked semantically
6. Embeddings generated via Bedrock Titan
7. Stored in ChromaDB with metadata

### RAG Chat Flow
1. User sends message
2. LangChain memory retrieves last 5 messages
3. Query embedded using Bedrock Titan
4. Vector search in ChromaDB (top-k with relevance filtering)
5. Context + conversation history sent to Claude 3
6. Response generated with strict grounding
7. Message stored in database and memory
8. Sources returned to user

### Memory Management
- Uses LangChain's `ConversationBufferWindowMemory`
- Automatically maintains last 5 messages per session
- Oldest message auto-removed when 6th is added
- Memory persisted to SQLite
- Restored on session load

## 🎯 Key Design Principles

1. **No Hallucination**: Strict system prompt enforces grounding
2. **Efficiency**: Incremental ingestion saves time and resources
3. **Persistence**: Vector store and sessions survive restarts
4. **Simplicity**: Clean architecture, minimal dependencies
5. **Best Practices**: Semantic chunking, relevance filtering, context window control

## 🐛 Troubleshooting

### AWS Bedrock Access Denied
```bash
# Check your AWS credentials
aws sts get-caller-identity

# Verify Bedrock access
aws bedrock list-foundation-models --region us-east-1
```

### No Documents Found During Ingestion
- Ensure documents are in `data/` folder
- Check supported formats: PDF, TXT, MD, DOCX
- Verify file permissions

### Backend Won't Start
```bash
# Check if port 8000 is available
netstat -ano | findstr :8000

# Try different port in .env:
API_PORT=8001
```

### Frontend Can't Connect
- Verify backend is running on http://localhost:8000
- Check CORS settings in `backend/app/config.py`
- Ensure `API_BASE_URL` in `frontend/src/services/api.js` is correct

## 📊 Performance Tips

1. **Chunk Size**: Adjust `CHUNK_SIZE` based on document type (default: 1000)
2. **Top-K Results**: Increase `TOP_K_RESULTS` for more context (default: 5)
3. **Similarity Threshold**: Lower threshold for more results (default: 0.7)
4. **AWS Region**: Use closest region to reduce latency

## 🔒 Security Notes

- Never commit `.env` file
- AWS credentials should use principle of least privilege
- Consider using AWS IAM roles for production
- SQLite database contains chat history - secure appropriately

## 📝 License

This project is for educational and development purposes.

## 🤝 Contributing

This is a demonstration project showcasing RAG best practices with AWS Bedrock.

---

**Built with ❤️ using FastAPI, React, LangChain, ChromaDB, and AWS Bedrock**
