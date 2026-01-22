"""Database session configuration"""

import os
import logging
from typing import AsyncGenerator
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from dotenv import load_dotenv

load_dotenv(dotenv_path=".env")

logger = logging.getLogger(__name__)

# Get database URL from environment
# Supabase PostgreSQL connection string format:
# postgresql://postgres:[PASSWORD]@[HOST]:[PORT]/postgres
DATABASE_URL = os.getenv("DATABASE_URL")

if not DATABASE_URL:
    raise ValueError("DATABASE_URL environment variable is not set")

# Convert to async URL format (postgresql+psycopg://...)
# Handle both postgresql:// and postgresql+psycopg:// formats
if DATABASE_URL.startswith("postgresql://"):
    ASYNC_DATABASE_URL = DATABASE_URL.replace("postgresql://", "postgresql+psycopg://", 1)
elif DATABASE_URL.startswith("postgresql+psycopg://"):
    ASYNC_DATABASE_URL = DATABASE_URL
elif DATABASE_URL.startswith("postgresql+asyncpg://"):
    # Legacy support: convert asyncpg URLs to psycopg
    ASYNC_DATABASE_URL = DATABASE_URL.replace("postgresql+asyncpg://", "postgresql+psycopg://", 1)
else:
    raise ValueError(f"Unsupported database URL format: {DATABASE_URL}")

# Connection pool configuration
POOL_SIZE = int(os.getenv("DB_POOL_SIZE", "5"))  # Default 5 connections
MAX_OVERFLOW = int(os.getenv("DB_MAX_OVERFLOW", "10"))  # Default 10 overflow
POOL_TIMEOUT = int(os.getenv("DB_POOL_TIMEOUT", "30"))  # Default 30 seconds
POOL_RECYCLE = int(os.getenv("DB_POOL_RECYCLE", "3600"))  # Default 1 hour

# Create async SQLAlchemy engine with connection pooling
engine = create_async_engine(
    ASYNC_DATABASE_URL,
    pool_pre_ping=True,  # Verify connections before using them
    pool_size=POOL_SIZE,
    max_overflow=MAX_OVERFLOW,
    pool_timeout=POOL_TIMEOUT,
    pool_recycle=POOL_RECYCLE,
    echo=False,  # Set to True to see SQL queries in logs
)

# Create async session factory
SessionLocal = async_sessionmaker(
    engine,
    class_=AsyncSession,
    autocommit=False,
    autoflush=False,
    expire_on_commit=False,
)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """
    Dependency function for FastAPI routes.
    
    Usage:
        @app.get("/example")
        async def example(db: AsyncSession = Depends(get_db)):
            ...
    """
    async with SessionLocal() as session:
        try:
            yield session
        finally:
            await session.close()


def get_pool_stats() -> dict:
    """
    Get current connection pool statistics.
    
    Returns:
        Dictionary with pool statistics:
        - size: Total pool size
        - checked_in: Connections currently checked in (available)
        - checked_out: Connections currently checked out (in use)
        - overflow: Overflow connections
        - invalid: Invalid connections
    """
    try:
        # For async engines, access the underlying sync pool
        sync_pool = engine.sync_engine.pool
        
        # Get pool stats using getattr with safe defaults
        size_func = getattr(sync_pool, "size", None)
        checkedin_func = getattr(sync_pool, "checkedin", None)
        checkedout_func = getattr(sync_pool, "checkedout", None)
        overflow_func = getattr(sync_pool, "overflow", None)
        invalid_func = getattr(sync_pool, "invalid", None)
        
        # Call functions if they exist, otherwise use defaults
        size_val = size_func() if callable(size_func) else POOL_SIZE
        checked_in_val = checkedin_func() if callable(checkedin_func) else 0
        checked_out_val = checkedout_func() if callable(checkedout_func) else 0
        overflow_val = overflow_func() if callable(overflow_func) else 0
        invalid_val = invalid_func() if callable(invalid_func) else 0
        max_overflow_val = getattr(sync_pool, "_max_overflow", MAX_OVERFLOW)
        
        # Convert to ints and ensure overflow is never negative
        size_int = int(size_val) if size_val is not None else POOL_SIZE  # type: ignore
        checked_in_int = int(checked_in_val) if checked_in_val is not None else 0  # type: ignore
        checked_out_int = int(checked_out_val) if checked_out_val is not None else 0  # type: ignore
        overflow_int = max(0, int(overflow_val)) if overflow_val is not None else 0  # type: ignore
        invalid_int = int(invalid_val) if invalid_val is not None else 0  # type: ignore
        max_overflow_int = int(max_overflow_val) if max_overflow_val is not None else MAX_OVERFLOW  # type: ignore
        
        return {
            "size": size_int,
            "checked_in": checked_in_int,
            "checked_out": checked_out_int,
            "overflow": overflow_int,
            "invalid": invalid_int,
            "max_overflow": max_overflow_int,
        }
    except Exception as e:
        logger.warning(f"Error getting pool stats: {e}")
        # Return safe defaults if pool stats can't be accessed
        return {
            "size": POOL_SIZE,
            "checked_in": 0,
            "checked_out": 0,
            "overflow": 0,
            "invalid": 0,
            "max_overflow": MAX_OVERFLOW,
        }


def log_pool_stats(context: str = ""):
    """
    Log current connection pool statistics.
    
    Args:
        context: Optional context string to include in log message
    """
    stats = get_pool_stats()
    available = stats["checked_in"]
    in_use = stats["checked_out"]
    overflow = stats["overflow"]
    total_capacity = stats["size"] + stats["max_overflow"]
    utilization = (in_use / total_capacity * 100) if total_capacity > 0 else 0
    
    context_str = f" [{context}]" if context else ""
    logger.info(
        f"Connection pool stats{context_str}: "
        f"available={available}, in_use={in_use}, overflow={overflow}, "
        f"utilization={utilization:.1f}%"
    )
    
    # Warn if pool is getting full
    if utilization > 80:
        logger.warning(
            f"Connection pool utilization is high ({utilization:.1f}%)! "
            f"Consider increasing pool size or investigating slow queries."
        )


# Add event listeners to monitor connection pool activity
# Note: For async engines, we listen to the sync_engine
from sqlalchemy import event  # noqa: E402

@event.listens_for(engine.sync_engine, "connect")
def on_connect(dbapi_conn, connection_record):
    """Log when a new connection is created"""
    logger.debug("New database connection created")


@event.listens_for(engine.sync_engine, "checkout")
def on_checkout(dbapi_conn, connection_record, connection_proxy):
    """Log when a connection is checked out from the pool"""
    stats = get_pool_stats()
    if stats["checked_out"] > stats["size"]:
        logger.debug(
            f"Connection checked out (using overflow pool): "
            f"{stats['checked_out']}/{stats['size'] + stats['max_overflow']}"
        )


@event.listens_for(engine.sync_engine, "checkin")
def on_checkin(dbapi_conn, connection_record):
    """Log when a connection is returned to the pool"""
    pass  # Usually not needed, but available if you want to log


@event.listens_for(engine.sync_engine, "invalidate")
def on_invalidate(dbapi_conn, connection_record, exception):
    """Log when a connection is invalidated"""
    logger.warning(
        f"Database connection invalidated: {exception}",
        exc_info=exception
    )
