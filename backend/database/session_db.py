"""SQLite database for session and document metadata storage."""
import json
import logging
from contextlib import contextmanager
from datetime import datetime
from typing import Iterator, List, Optional

from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, Text, create_engine, text
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import Session as DBSession, relationship, sessionmaker

from app.config import settings

logger = logging.getLogger(__name__)

Base = declarative_base()


class ChatSession(Base):
    """Chat session model."""
    __tablename__ = 'chat_sessions'

    id = Column(String, primary_key=True)
    name = Column(String, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    messages = relationship("Message", back_populates="session", cascade="all, delete-orphan")


class Message(Base):
    """Message model."""
    __tablename__ = 'messages'

    id = Column(Integer, primary_key=True, autoincrement=True)
    session_id = Column(String, ForeignKey('chat_sessions.id', ondelete='CASCADE'), nullable=False)
    role = Column(String, nullable=False)
    content = Column(Text, nullable=False)
    timestamp = Column(DateTime, default=datetime.utcnow)
    rerank_summary = Column(Text, nullable=True)
    metrics = Column(Text, nullable=True)
    citations = Column(Text, nullable=True)

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
        import uuid
        self._uuid = uuid
        db_path = settings.get_absolute_path(settings.session_db_path)
        self.engine = create_engine(f'sqlite:///{db_path}', echo=False)
        Base.metadata.create_all(self.engine)
        self.SessionLocal = sessionmaker(bind=self.engine)
        self._run_migrations()
        logger.info(f"Initialized database at {db_path}")

    def _run_migrations(self) -> None:
        """Add columns that may be missing from older schemas."""
        try:
            with self.engine.connect() as conn:
                result = conn.execute(text("PRAGMA table_info(messages)"))
                existing_columns = {row[1] for row in result}
                for col in ('rerank_summary', 'metrics', 'citations'):
                    if col not in existing_columns:
                        logger.info(f"Migrating database: adding {col} column to messages table")
                        conn.execute(text(f"ALTER TABLE messages ADD COLUMN {col} TEXT"))
                conn.commit()
        except Exception as e:
            logger.warning(f"Database migration check failed: {e}")

    @contextmanager
    def _session(self) -> Iterator[DBSession]:
        """Context manager for database sessions with auto-commit/rollback."""
        db = self.SessionLocal()
        try:
            yield db
            db.commit()
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()

    # ===== Session Methods =====

    def create_session(self, name: Optional[str] = None) -> ChatSession:
        """Create a new chat session."""
        with self._session() as db:
            if name is None:
                name = f"Chat Session {datetime.utcnow().strftime('%Y-%m-%d %H:%M')}"
            session = ChatSession(id=str(self._uuid.uuid4()), name=name)
            db.add(session)
            db.flush()
            db.refresh(session)
            logger.info(f"Created session: {session.id}")
            # Expunge so the object survives session close
            db.expunge(session)
            return session

    def get_all_sessions(self) -> List[ChatSession]:
        """Get all chat sessions ordered by most recently updated."""
        with self._session() as db:
            sessions = db.query(ChatSession).order_by(ChatSession.updated_at.desc()).all()
            db.expunge_all()
            return sessions

    def get_session_by_id(self, session_id: str) -> Optional[ChatSession]:
        """Get a specific session by ID."""
        with self._session() as db:
            session = db.query(ChatSession).filter(ChatSession.id == session_id).first()
            if session:
                db.expunge(session)
            return session

    def delete_session(self, session_id: str) -> bool:
        """Delete a session and all its messages."""
        with self._session() as db:
            session = db.query(ChatSession).filter(ChatSession.id == session_id).first()
            if session:
                db.delete(session)
                logger.info(f"Deleted session: {session_id}")
                return True
            return False

    def delete_all_sessions(self) -> int:
        """Delete all chat sessions and their messages."""
        with self._session() as db:
            count = db.query(ChatSession).delete()
            logger.info(f"Deleted all sessions: {count} sessions removed")
            return count

    # ===== Message Methods =====

    def add_message(
        self,
        session_id: str,
        role: str,
        content: str,
        rerank_summary: list = None,
        metrics: dict = None,
        citations: list = None
    ) -> Message:
        """Add a message to a session with optional metadata."""
        with self._session() as db:
            message = Message(
                session_id=session_id,
                role=role,
                content=content,
                rerank_summary=json.dumps(rerank_summary) if rerank_summary else None,
                metrics=json.dumps(metrics) if metrics else None,
                citations=json.dumps(citations) if citations else None
            )
            db.add(message)

            # Update session timestamp
            session = db.query(ChatSession).filter(ChatSession.id == session_id).first()
            if session:
                session.updated_at = datetime.utcnow()

            db.flush()
            db.refresh(message)
            db.expunge(message)
            return message

    def update_session_name(self, session_id: str, name: str) -> bool:
        """Update the name of a chat session."""
        with self._session() as db:
            session = db.query(ChatSession).filter(ChatSession.id == session_id).first()
            if session:
                session.name = name
                session.updated_at = datetime.utcnow()
                return True
            return False

    def get_session_messages(self, session_id: str, limit: int = None) -> List[Message]:
        """Get messages for a session, optionally limited to most recent."""
        with self._session() as db:
            query = db.query(Message).filter(Message.session_id == session_id).order_by(Message.timestamp)

            if limit:
                # Use SQL-level ordering + limit instead of Python slicing
                total = query.count()
                if total > limit:
                    query = query.offset(total - limit)

            messages = query.all()
            db.expunge_all()
            return messages

    # ===== Document Metadata Methods =====

    def get_document_by_filename(self, filename: str) -> Optional[DocumentMetadata]:
        """Get document metadata by filename."""
        with self._session() as db:
            doc = db.query(DocumentMetadata).filter(DocumentMetadata.filename == filename).first()
            if doc:
                db.expunge(doc)
            return doc

    def get_document_by_hash(self, file_hash: str) -> Optional[DocumentMetadata]:
        """Get document metadata by file hash."""
        with self._session() as db:
            doc = db.query(DocumentMetadata).filter(DocumentMetadata.file_hash == file_hash).first()
            if doc:
                db.expunge(doc)
            return doc

    def add_document_metadata(self, filename: str, file_hash: str, file_path: str, chunk_count: int) -> DocumentMetadata:
        """Add or update document metadata."""
        with self._session() as db:
            doc = db.query(DocumentMetadata).filter(DocumentMetadata.filename == filename).first()

            if doc:
                doc.file_hash = file_hash
                doc.file_path = file_path
                doc.chunk_count = chunk_count
                doc.ingestion_date = datetime.utcnow()
            else:
                doc = DocumentMetadata(
                    filename=filename,
                    file_hash=file_hash,
                    file_path=file_path,
                    chunk_count=chunk_count
                )
                db.add(doc)

            db.flush()
            db.refresh(doc)
            db.expunge(doc)
            return doc

    def get_all_documents(self) -> List[DocumentMetadata]:
        """Get all ingested document metadata."""
        with self._session() as db:
            docs = db.query(DocumentMetadata).order_by(DocumentMetadata.ingestion_date.desc()).all()
            db.expunge_all()
            return docs

    def delete_all_documents(self) -> int:
        """Delete all document metadata records."""
        with self._session() as db:
            count = db.query(DocumentMetadata).delete()
            logger.info(f"Deleted all document metadata: {count} records removed")
            return count


# Global database instance
session_db = SessionDatabase()
