# Quick Start Guide

## Installation & Setup (First Time Only)

### 1. Backend Setup
```powershell
cd backend
python -m venv venv
.\venv\Scripts\activate
pip install -r requirements.txt
```

### 2. Configure Environment
```powershell
# Backend is already configured with .env file
# Update AWS_REGION in backend/.env if needed (default: us-east-1)
```

### 3. Frontend Setup
```powershell
cd ../frontend
npm install
```

## Running the Application

### Start Backend (Terminal 1)
```powershell
cd backend
.\venv\Scripts\activate
python -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

### Start Frontend (Terminal 2)
```powershell
cd frontend
npm run dev
```

### Access Application
Open browser to: **http://localhost:5173**

## First Steps

1. **Ingest Documents**
   - Place documents in `data/` folder (PDF, TXT, MD, DOCX)
   - Click "📥 Ingest Documents" in the sidebar
   - Wait for confirmation

2. **Create Session**
   - Click "+ New Chat" button
   - Session appears in sidebar

3. **Start Chatting**
   - Type your question
   - Press Enter or click Send
   - Answers will include source citations

## Ingestion Notes

- **First Run**: All documents in `data/` will be processed
- **Subsequent Runs**: Only new/modified files will be processed
- **Vector Store**: Persists across restarts (no re-ingestion needed)
- **Progress**: Check terminal for processing logs

## Troubleshooting

### AWS Credentials
```powershell
# Verify AWS CLI is configured
aws sts get-caller-identity

# Check Bedrock access
aws bedrock list-foundation-models --region us-east-1
```

### Port Already in Use
```powershell
# Find process using port 8000
netstat -ano | findstr :8000

# Kill process (replace PID)
taskkill /PID <PID> /F
```

### Dependencies Missing
```powershell
# Backend
cd backend
.\venv\Scripts\activate
pip install -r requirements.txt

# Frontend
cd frontend
npm install
```

## Features to Try

1. **Multi-turn Conversation**: Ask follow-up questions (5-message memory)
2. **Multiple Sessions**: Create different sessions for different topics
3. **Source Verification**: Check sources to verify grounding
4. **Document Updates**: Modify a document and re-ingest (only that file is reprocessed)

## Default Configuration

- **LLM**: Claude 3 Haiku (cost-effective, fast)
- **Embeddings**: Amazon Titan Embeddings
- **Memory**: Last 5 messages per session
- **Top-K**: 5 most relevant chunks
- **Chunk Size**: 1000 characters
- **Backend**: http://localhost:8000
- **Frontend**: http://localhost:5173
