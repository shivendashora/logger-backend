from sqlalchemy.ext.asyncio import AsyncSession,create_async_engine,async_sessionmaker
from sqlalchemy.orm import declarative_base


DB_URL = "postgresql+asyncpg://postgres:postgres@localhost:5432/logger-db"

engine = create_async_engine(DB_URL)


async_sessionLocal = async_sessionmaker(engine, expire_on_commit=False)

async def get_db_session():
    async with async_sessionLocal() as session:
        yield session

Base = declarative_base()
