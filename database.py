"""
Database module for AI Voice Assistant
Handles call logging, conversation storage, and analytics
"""

import os
import logging
from datetime import datetime, timezone
from typing import Optional, List, Dict, Any
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from sqlalchemy import String, DateTime, Text, Integer, Float, Boolean, JSON, Index, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
import uuid
from contextlib import asynccontextmanager

logger = logging.getLogger(__name__)

# Database configuration
DATABASE_URL = os.getenv('DATABASE_URL')
GOOGLE_CLOUD_SQL_CONNECTION_NAME = os.getenv('GOOGLE_CLOUD_SQL_CONNECTION_NAME')
DB_USER = os.getenv('DB_USER', 'postgres')
DB_PASSWORD = os.getenv('DB_PASSWORD')
DB_NAME = os.getenv('DB_NAME', 'voice_assistant')

class Base(DeclarativeBase):
    pass

class CallLog(Base):
    __tablename__ = "call_logs"
    
    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4()))
    call_sid: Mapped[str] = mapped_column(String(50), unique=True, index=True)
    phone_number: Mapped[str] = mapped_column(String(20), index=True)
    caller_name: Mapped[Optional[str]] = mapped_column(String(100))
    
    # Call metadata
    initiated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    connected_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    ended_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    duration_seconds: Mapped[Optional[int]] = mapped_column(Integer)
    
    # Call status and details
    status: Mapped[str] = mapped_column(String(20), default="initiated")  # initiated, connected, completed, failed
    direction: Mapped[str] = mapped_column(String(10), default="outbound")  # outbound, inbound
    stream_sid: Mapped[Optional[str]] = mapped_column(String(50))
    
    # AI Configuration
    ai_voice: Mapped[str] = mapped_column(String(20), default="alloy")
    system_message: Mapped[Optional[str]] = mapped_column(Text)
    
    # Analytics
    total_ai_responses: Mapped[int] = mapped_column(Integer, default=0)
    total_user_inputs: Mapped[int] = mapped_column(Integer, default=0)
    conversation_rating: Mapped[Optional[float]] = mapped_column(Float)
    
    # Error tracking
    error_message: Mapped[Optional[str]] = mapped_column(Text)
    error_count: Mapped[int] = mapped_column(Integer, default=0)
    
    # Relationships
    conversation_logs: Mapped[List["ConversationLog"]] = relationship("ConversationLog", back_populates="call_log", cascade="all, delete-orphan")
    
    # Indexes for performance
    __table_args__ = (
        Index('idx_call_logs_phone_initiated', 'phone_number', 'initiated_at'),
        Index('idx_call_logs_status_initiated', 'status', 'initiated_at'),
    )

class ConversationLog(Base):
    __tablename__ = "conversation_logs"
    
    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4()))
    call_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("call_logs.id"), index=True)  # Foreign key to call_logs.id
    
    # Message details
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    speaker: Mapped[str] = mapped_column(String(10))  # 'user' or 'ai'
    message_type: Mapped[str] = mapped_column(String(20))  # 'audio', 'text', 'event'
    
    # Content
    text_content: Mapped[Optional[str]] = mapped_column(Text)
    audio_duration_ms: Mapped[Optional[int]] = mapped_column(Integer)
    
    # OpenAI specific data
    openai_response_type: Mapped[Optional[str]] = mapped_column(String(50))
    openai_response_id: Mapped[Optional[str]] = mapped_column(String(100))
    
    # Metadata
    message_metadata: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON)
    
    # Relationship
    call_log: Mapped["CallLog"] = relationship("CallLog", back_populates="conversation_logs")
    
    # Indexes for performance
    __table_args__ = (
        Index('idx_conversation_logs_call_timestamp', 'call_id', 'timestamp'),
        Index('idx_conversation_logs_speaker_timestamp', 'speaker', 'timestamp'),
    )

class DatabaseManager:
    def __init__(self):
        self.engine = None
        self.async_session = None
        
    async def initialize(self):
        """Initialize database connection"""
        try:
            # Build connection string
            if GOOGLE_CLOUD_SQL_CONNECTION_NAME and not DATABASE_URL:
                # Google Cloud SQL with Cloud SQL Python Connector
                connection_string = self._build_cloud_sql_connection_string()
                logger.info(f"Using Google Cloud SQL connection: {GOOGLE_CLOUD_SQL_CONNECTION_NAME}")
            elif DATABASE_URL:
                # Use provided DATABASE_URL
                connection_string = DATABASE_URL
                logger.info("Using provided DATABASE_URL")
            else:
                # Local development fallback
                connection_string = f"postgresql+asyncpg://{DB_USER}:{DB_PASSWORD}@localhost:5432/{DB_NAME}"
                logger.info("Using local PostgreSQL connection")
            
            logger.info(f"Initializing database connection...")
            logger.info(f"Database configuration:")
            logger.info(f"  - DB_USER: {DB_USER}")
            logger.info(f"  - DB_NAME: {DB_NAME}")
            logger.info(f"  - GOOGLE_CLOUD_SQL_CONNECTION_NAME: {GOOGLE_CLOUD_SQL_CONNECTION_NAME or 'Not set'}")
            logger.info(f"  - Running in Cloud Run: {bool(os.getenv('K_SERVICE'))}")
            
            # Create async engine
            self.engine = create_async_engine(
                connection_string,
                echo=os.getenv('DB_ECHO', 'false').lower() == 'true',
                pool_size=10,
                max_overflow=20,
                pool_pre_ping=True,
                pool_recycle=3600,
            )
            
            # Create session factory
            self.async_session = async_sessionmaker(
                bind=self.engine,
                class_=AsyncSession,
                expire_on_commit=False
            )
            
            # Create tables
            await self._create_tables()
            logger.info("Database initialized successfully")
            
        except Exception as e:
            logger.error(f"Failed to initialize database: {e}")
            raise
    
    def _build_cloud_sql_connection_string(self) -> str:
        """Build connection string for Google Cloud SQL"""
        try:
            # For Cloud Run, use the unix socket connection
            if os.getenv('K_SERVICE'):  # Running in Cloud Run
                return f"postgresql+asyncpg://{DB_USER}:{DB_PASSWORD}@/{DB_NAME}?host=/cloudsql/{GOOGLE_CLOUD_SQL_CONNECTION_NAME}"
            else:
                # For local development with Cloud SQL Proxy
                return f"postgresql+asyncpg://{DB_USER}:{DB_PASSWORD}@127.0.0.1:5432/{DB_NAME}"
        except Exception as e:
            logger.error(f"Error building Cloud SQL connection string: {e}")
            raise
    
    async def _create_tables(self):
        """Create database tables and run migrations"""
        try:
            logger.info("Creating database tables...")
            # Always try to create tables directly first
            async with self.engine.begin() as conn:
                await conn.run_sync(Base.metadata.create_all)
            logger.info("Database tables created successfully")
        except Exception as e:
            logger.error(f"Failed to create tables: {e}")
            # Try migrations as fallback
            try:
                logger.info("Attempting to run migrations...")
                await self._run_migrations()
            except Exception as migration_error:
                logger.error(f"Migration also failed: {migration_error}")
                # Final attempt - create tables again
                try:
                    async with self.engine.begin() as conn:
                        await conn.run_sync(Base.metadata.create_all)
                    logger.info("Tables created on final attempt")
                except Exception as final_error:
                    logger.error(f"All table creation attempts failed: {final_error}")
                    raise
    
    async def _run_migrations(self):
        """Run Alembic migrations"""
        try:
            import subprocess
            import sys
            
            # Run alembic upgrade head
            result = subprocess.run(
                [sys.executable, "-m", "alembic", "upgrade", "head"],
                capture_output=True,
                text=True,
                cwd=os.getcwd()
            )
            
            if result.returncode != 0:
                logger.error(f"Migration failed: {result.stderr}")
                raise Exception(f"Migration failed: {result.stderr}")
            else:
                logger.info("Database migrations completed successfully")
                
        except Exception as e:
            logger.error(f"Error running migrations: {e}")
            raise
    
    @asynccontextmanager
    async def get_session(self):
        """Get database session context manager"""
        async with self.async_session() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise
            finally:
                await session.close()
    
    async def close(self):
        """Close database connections"""
        if self.engine:
            await self.engine.dispose()

# Global database manager
db_manager = DatabaseManager()

class CallLogger:
    """Service for logging call data"""
    
    @staticmethod
    async def create_call_log(
        call_sid: str,
        phone_number: str,
        caller_name: Optional[str] = None,
        direction: str = "outbound",
        ai_voice: str = "alloy",
        system_message: Optional[str] = None
    ) -> str:
        """Create a new call log entry"""
        try:
            async with db_manager.get_session() as session:
                call_log = CallLog(
                    call_sid=call_sid,
                    phone_number=phone_number,
                    caller_name=caller_name,
                    initiated_at=datetime.now(timezone.utc),
                    direction=direction,
                    ai_voice=ai_voice,
                    system_message=system_message,
                    status="initiated"
                )
                
                session.add(call_log)
                await session.flush()  # Get the ID
                
                logger.info(f"Created call log for {call_sid}")
                return call_log.id
                
        except Exception as e:
            logger.error(f"Failed to create call log for {call_sid}: {e}")
            raise
    
    @staticmethod
    async def update_call_status(
        call_sid: str,
        status: str,
        stream_sid: Optional[str] = None,
        error_message: Optional[str] = None
    ):
        """Update call status"""
        try:
            async with db_manager.get_session() as session:
                from sqlalchemy import select, update
                
                # Build update data
                update_data = {"status": status}
                
                if status == "connected" and stream_sid:
                    update_data["connected_at"] = datetime.now(timezone.utc)
                    update_data["stream_sid"] = stream_sid
                elif status == "completed":
                    update_data["ended_at"] = datetime.now(timezone.utc)
                elif status == "failed" and error_message:
                    update_data["error_message"] = error_message
                    update_data["error_count"] = CallLog.error_count + 1
                
                # Update the call log
                stmt = (
                    update(CallLog)
                    .where(CallLog.call_sid == call_sid)
                    .values(**update_data)
                )
                
                await session.execute(stmt)
                logger.info(f"Updated call {call_sid} status to {status}")
                
        except Exception as e:
            logger.error(f"Failed to update call status for {call_sid}: {e}")
    
    @staticmethod
    async def log_conversation(
        call_sid: str,
        speaker: str,
        message_type: str,
        text_content: Optional[str] = None,
        audio_duration_ms: Optional[int] = None,
        openai_response_type: Optional[str] = None,
        openai_response_id: Optional[str] = None,
        message_metadata: Optional[Dict[str, Any]] = None
    ):
        """Log conversation message"""
        try:
            async with db_manager.get_session() as session:
                from sqlalchemy import select
                
                # Get call_log id from call_sid
                stmt = select(CallLog.id).where(CallLog.call_sid == call_sid)
                result = await session.execute(stmt)
                call_id = result.scalar_one_or_none()
                
                if not call_id:
                    logger.warning(f"Call log not found for {call_sid}")
                    return
                
                conversation_log = ConversationLog(
                    call_id=call_id,
                    timestamp=datetime.now(timezone.utc),
                    speaker=speaker,
                    message_type=message_type,
                    text_content=text_content,
                    audio_duration_ms=audio_duration_ms,
                    openai_response_type=openai_response_type,
                    openai_response_id=openai_response_id,
                    message_metadata=message_metadata
                )
                
                session.add(conversation_log)
                
                # Update analytics counters
                if speaker == "ai":
                    stmt = (
                        update(CallLog)
                        .where(CallLog.call_sid == call_sid)
                        .values(total_ai_responses=CallLog.total_ai_responses + 1)
                    )
                elif speaker == "user":
                    stmt = (
                        update(CallLog)
                        .where(CallLog.call_sid == call_sid)
                        .values(total_user_inputs=CallLog.total_user_inputs + 1)
                    )
                
                await session.execute(stmt)
                
        except Exception as e:
            logger.error(f"Failed to log conversation for {call_sid}: {e}")
    
    @staticmethod
    async def finalize_call(call_sid: str):
        """Finalize call and calculate duration"""
        try:
            async with db_manager.get_session() as session:
                from sqlalchemy import select, update
                
                # Get call log
                stmt = select(CallLog).where(CallLog.call_sid == call_sid)
                result = await session.execute(stmt)
                call_log = result.scalar_one_or_none()
                
                if not call_log:
                    return
                
                # Calculate duration if we have both timestamps
                duration_seconds = None
                if call_log.connected_at and call_log.ended_at:
                    duration = call_log.ended_at - call_log.connected_at
                    duration_seconds = int(duration.total_seconds())
                
                # Update final status
                update_data = {
                    "status": "completed",
                    "ended_at": datetime.now(timezone.utc)
                }
                
                if duration_seconds is not None:
                    update_data["duration_seconds"] = duration_seconds
                
                stmt = (
                    update(CallLog)
                    .where(CallLog.call_sid == call_sid)
                    .values(**update_data)
                )
                
                await session.execute(stmt)
                logger.info(f"Finalized call {call_sid} with duration {duration_seconds}s")
                
        except Exception as e:
            logger.error(f"Failed to finalize call {call_sid}: {e}")

class AnalyticsService:
    """Service for call analytics and reporting"""
    
    @staticmethod
    async def get_call_history(limit: int = 50, offset: int = 0) -> List[Dict]:
        """Get call history with pagination"""
        try:
            async with db_manager.get_session() as session:
                from sqlalchemy import select, desc
                
                stmt = (
                    select(CallLog)
                    .order_by(desc(CallLog.initiated_at))
                    .limit(limit)
                    .offset(offset)
                )
                
                result = await session.execute(stmt)
                call_logs = result.scalars().all()
                
                return [
                    {
                        "call_sid": log.call_sid,
                        "phone_number": log.phone_number,
                        "caller_name": log.caller_name,
                        "initiated_at": log.initiated_at.isoformat(),
                        "duration_seconds": log.duration_seconds,
                        "status": log.status,
                        "total_ai_responses": log.total_ai_responses,
                        "total_user_inputs": log.total_user_inputs
                    }
                    for log in call_logs
                ]
                
        except Exception as e:
            logger.error(f"Failed to get call history: {e}")
            return []
    
    @staticmethod
    async def get_call_analytics() -> Dict[str, Any]:
        """Get call analytics and metrics"""
        try:
            async with db_manager.get_session() as session:
                from sqlalchemy import select, func
                
                # Total calls
                total_calls_stmt = select(func.count(CallLog.id))
                total_calls = await session.scalar(total_calls_stmt)
                
                # Calls by status
                status_stmt = (
                    select(CallLog.status, func.count(CallLog.id))
                    .group_by(CallLog.status)
                )
                status_result = await session.execute(status_stmt)
                calls_by_status = dict(status_result.all())
                
                # Average duration
                avg_duration_stmt = select(func.avg(CallLog.duration_seconds)).where(
                    CallLog.duration_seconds.is_not(None)
                )
                avg_duration = await session.scalar(avg_duration_stmt)
                
                # Recent activity (last 24 hours)
                from datetime import timedelta
                recent_cutoff = datetime.now(timezone.utc) - timedelta(hours=24)
                recent_calls_stmt = select(func.count(CallLog.id)).where(
                    CallLog.initiated_at >= recent_cutoff
                )
                recent_calls = await session.scalar(recent_calls_stmt)
                
                return {
                    "total_calls": total_calls or 0,
                    "calls_by_status": calls_by_status,
                    "average_duration_seconds": float(avg_duration) if avg_duration else 0,
                    "recent_calls_24h": recent_calls or 0
                }
                
        except Exception as e:
            logger.error(f"Failed to get analytics: {e}")
            return {} 