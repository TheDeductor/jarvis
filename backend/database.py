import os
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from sqlalchemy.orm import declarative_base

DB_PATH = "sqlite+aiosqlite:///./digital_twin.db"

# Create async engine
engine = create_async_engine(
    DB_PATH,
    connect_args={"check_same_thread": False},
    echo=False
)

# Create async session factory
AsyncSessionLocal = async_sessionmaker(
    engine, 
    expire_on_commit=False
)

Base = declarative_base()

async def init_db():
    async with engine.begin() as conn:
        # Create all tables if they don't exist
        await conn.run_sync(Base.metadata.create_all)
