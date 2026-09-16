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
    from sqlalchemy.future import select
    from .db_models import User
    import bcrypt
    
    async with engine.begin() as conn:
        # Create all tables if they don't exist
        await conn.run_sync(Base.metadata.create_all)
        
    async with AsyncSessionLocal() as session:
        # Check if users exist
        result = await session.execute(select(User).limit(1))
        if not result.scalars().first():
            # Seed users
            admin = User(
                username="admin", 
                hashed_password=bcrypt.hashpw(b"admin", bcrypt.gensalt()).decode('utf-8'), 
                role="FacilityManager"
            )
            occupant = User(
                username="occupantA", 
                hashed_password=bcrypt.hashpw(b"occupant", bcrypt.gensalt()).decode('utf-8'), 
                role="Occupant", 
                assigned_room="A"
            )
            session.add_all([admin, occupant])
            await session.commit()
