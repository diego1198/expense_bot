"""
Database connection and session management.
"""

import logging
from contextlib import asynccontextmanager
from typing import AsyncGenerator, Optional

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
    AsyncEngine
)

from src.config import config
from src.database.models import Base

logger = logging.getLogger(__name__)

# Engine and session factory will be created after ensuring data directory exists
engine: Optional[AsyncEngine] = None
async_session_factory: Optional[async_sessionmaker[AsyncSession]] = None


def _ensure_engine() -> AsyncEngine:
    """Ensure engine is created after data directory exists."""
    global engine, async_session_factory
    
    if engine is None:
        # First ensure the data directory exists
        logger.info(f"🔧 Creating database engine...")
        logger.info(f"🔧 DATABASE_URL: {config.DATABASE_URL}")
        config.ensure_data_dir()
        
        # Now create the engine
        engine = create_async_engine(
            config.DATABASE_URL,
            echo=False,  # Set to True for SQL debugging
            future=True
        )
        logger.info(f"✅ Engine created successfully")
        
        # Create async session factory
        async_session_factory = async_sessionmaker(
            engine,
            class_=AsyncSession,
            expire_on_commit=False
        )
    
    return engine


async def init_db() -> None:
    """Initialize database and create all tables."""
    eng = _ensure_engine()
    async with eng.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def close_db() -> None:
    """Close database connections."""
    if engine is not None:
        await engine.dispose()


@asynccontextmanager
async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """Get an async database session."""
    _ensure_engine()  # Ensure engine exists
    async with async_session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()
