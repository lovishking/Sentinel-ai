from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base
from app.core.config import settings

# For alembic we can use sync engine, or just use sync engine overall since it's a 2-day build and we might not need async DB right now.
# Let's stick to sync engine for simplicity and speed, as async requires asyncpg. The user didn't specify async DB.
# Wait, let's just use standard psycopg2.

engine = create_engine(settings.DATABASE_URL, pool_pre_ping=True)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
