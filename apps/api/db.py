from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from config import get_settings

settings = get_settings()

# Supabase's DATABASE_URL uses the standard postgresql:// scheme.
# SQLAlchemy's async engine requires the driver named explicitly.
_async_url = settings.database_url.replace("postgresql://", "postgresql+asyncpg://", 1)

engine = create_async_engine(_async_url, pool_size=5, max_overflow=10, pool_pre_ping=True)

async_session_factory = async_sessionmaker(engine, expire_on_commit=False)


async def get_db_session() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency — yields a session, used by BACK-2.4's route handlers."""
    async with async_session_factory() as session:
        yield session