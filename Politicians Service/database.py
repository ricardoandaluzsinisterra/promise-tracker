from typing import AsyncGenerator
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy.orm import DeclarativeBase

DATABASE_URL = "postgresql+asyncpg://postgres:postgres@postgres-politicians:5432/politicians_db"

# Connection pool for incoming calls
engine = create_async_engine(DATABASE_URL, echo=True)

# expire_on_commit=False means objects stay usable after commit.
AsyncSessionFactory = async_sessionmaker(engine, expire_on_commit=False)


class Base(DeclarativeBase):
	pass


async def get_db() -> AsyncGenerator[AsyncSession, None]:
	async with AsyncSessionFactory() as session:
		yield session
