"""SQLite database for session and document metadata storage."""
from sqlalchemy import create_engine, Column, String, Integer, DateTime, ForeignKey, Text
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, relationship
from datetime import datetime
import uuid
from app.config import settings
import logging

logger = logging.getLogger(__name__)

Base = declarative_base()


class ChatSession(Base):
    """Chat session model."""
    __tablename__ = 'chat_sessions'
    
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    name = Column(String, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationship to messages
    messages = relationship("Message", back_populates="session", cascade="all, delete-orphan")


class Message(Base):
    """Message model."""
    __tablename__ = 'messages'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    session_id = Column(String, ForeignKey('chat_sessions.id', ondelete='CASCADE'), nullable=False)
    role = Column(String, nullable=False)  # 'user' or 'assistant'
    content = Column(Text, nullable=False)
    timestamp = Column(DateTime, default=datetime.utcnow)
    rerank_summary = Column(Text, nullable=True)  # JSON string of auditing data
    
    # Relationship to session
    session = relationship("ChatSession", back_populates="messages")


class DocumentMetadata(Base):
    """Document metadata for tracking ingested files."""
    __tablename__ = 'document_metadata'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    filename = Column(String, nullable=False, unique=True)
    file_hash = Column(String, nullable=False)
    file_path = Column(String, nullable=False)
    ingestion_date = Column(DateTime, default=datetime.utcnow)
    chunk_count = Column(Integer, nullable=False)


class SessionDatabase:
    """Database manager for sessions, messages, and document metadata."""
    
    def __init__(self):
        """Initialize database connection and create tables."""
        db_path = settings.get_absolute_path(settings.session_db_path)
        self.engine = create_engine(f'sqlite:///{db_path}', echo=False)
        Base.metadata.create_all(self.engine)
        self.SessionLocal = sessionmaker(bind=self.engine)
        
        # Simple migration: add rerank_summary column if it doesn't exist
        try:
            from sqlalchemy import text
            with self.engine.connect() as conn:
                # Check if column exists
                result = conn.execute(text("PRAGMA table_info(messages)"))
                columns = [row[1] for row in result]
                if 'rerank_summary' not in columns:
                    logger.info("Migrating database: adding rerank_summary column to messages table")
                    conn.execute(text("ALTER TABLE messages ADD COLUMN rerank_summary TEXT"))
                    conn.commit()
        except Exception as e:
            logger.warning(f"Database migration check failed (might be fine if already migrated): {e}")

        logger.info(f"Initialized database at {db_path}")
    
    def get_session(self):
        """Get a new database session."""
        return self.SessionLocal()
    
    # ===== Session Methods =====
    
    def create_session(self, name: str = None) -> ChatSession:
        """Create a new chat session."""
        db = self.get_session()
        try:
            if name is None:
                name = f"Chat Session {datetime.utcnow().strftime('%Y-%m-%d %H:%M')}"
            
            session = ChatSession(name=name)
            db.add(session)
            db.commit()
            db.refresh(session)
            logger.info(f"Created session: {session.id}")
            return session
        finally:
            db.close()
    
    def get_all_sessions(self):
        """Get all chat sessions."""
        db = self.get_session()
        try:
            sessions = db.query(ChatSession).order_by(ChatSession.updated_at.desc()).all()
            return sessions
        finally:
            db.close()
    
    def get_session_by_id(self, session_id: str):
        """Get a specific session by ID."""
        db = self.get_session()
        try:
            session = db.query(ChatSession).filter(ChatSession.id == session_id).first()
            return session
        finally:
            db.close()
    
    def delete_session(self, session_id: str) -> bool:
        """Delete a session and all its messages."""
        db = self.get_session()
        try:
            session = db.query(ChatSession).filter(ChatSession.id == session_id).first()
            if session:
                db.delete(session)
                db.commit()
                logger.info(f"Deleted session: {session_id}")
                return True
            return False
        finally:
            db.close()
            
    def delete_all_sessions(self) -> int:
        """Delete all chat sessions and their messages."""
        db = self.get_session()
        try:
            count = db.query(ChatSession).delete()
            db.commit()
            logger.info(f"Deleted all sessions: {count} sessions removed")
            return count
        finally:
            db.close()
    
    # ===== Message Methods =====
    
    def add_message(self, session_id: str, role: str, content: str, rerank_summary: list = None) -> Message:
        """Add a message to a session with optional reranking audit data."""
        import json
        db = self.get_session()
        try:
            summary_json = json.dumps(rerank_summary) if rerank_summary else None
            message = Message(
                session_id=session_id, 
                role=role, 
                content=content,
                rerank_summary=summary_json
            )
            db.add(message)
            
            # Update session's updated_at timestamp
            session = db.query(ChatSession).filter(ChatSession.id == session_id).first()
            if session:
                session.updated_at = datetime.utcnow()
            
            db.commit()
            db.refresh(message)
            return message
        finally:
            db.close()

    def update_session_name(self, session_id: str, name: str) -> bool:
        """Update the name of a chat session."""
        db = self.get_session()
        try:
            session = db.query(ChatSession).filter(ChatSession.id == session_id).first()
            if session:
                session.name = name
                session.updated_at = datetime.utcnow()
                db.commit()
                return True
            return False
        finally:
            db.close()
    
    def get_session_messages(self, session_id: str, limit: int = None):
        """Get messages for a session, optionally limited to most recent."""
        db = self.get_session()
        try:
            query = db.query(Message).filter(Message.session_id == session_id).order_by(Message.timestamp)
            
            if limit:
                # Get the last N messages
                all_messages = query.all()
                return all_messages[-limit:] if len(all_messages) > limit else all_messages
            else:
                return query.all()
        finally:
            db.close()
    
    # ===== Document Metadata Methods =====
    
    def get_document_by_filename(self, filename: str):
        """Get document metadata by filename."""
        db = self.get_session()
        try:
            doc = db.query(DocumentMetadata).filter(DocumentMetadata.filename == filename).first()
            return doc
        finally:
            db.close()
    
    def get_document_by_hash(self, file_hash: str):
        """Get document metadata by file hash."""
        db = self.get_session()
        try:
            doc = db.query(DocumentMetadata).filter(DocumentMetadata.file_hash == file_hash).first()
            return doc
        finally:
            db.close()
    
    def add_document_metadata(self, filename: str, file_hash: str, file_path: str, chunk_count: int):
        """Add or update document metadata."""
        db = self.get_session()
        try:
            # Check if document already exists
            doc = db.query(DocumentMetadata).filter(DocumentMetadata.filename == filename).first()
            
            if doc:
                # Update existing document
                doc.file_hash = file_hash
                doc.file_path = file_path
                doc.chunk_count = chunk_count
                doc.ingestion_date = datetime.utcnow()
            else:
                # Create new document metadata
                doc = DocumentMetadata(
                    filename=filename,
                    file_hash=file_hash,
                    file_path=file_path,
                    chunk_count=chunk_count
                )
                db.add(doc)
            
            db.commit()
            db.refresh(doc)
            return doc
        finally:
            db.close()
    
    def get_all_documents(self):
        """Get all ingested document metadata."""
        db = self.get_session()
        try:
            docs = db.query(DocumentMetadata).order_by(DocumentMetadata.ingestion_date.desc()).all()
            return docs
        finally:
            db.close()


# Global database instance
session_db = SessionDatabase()
