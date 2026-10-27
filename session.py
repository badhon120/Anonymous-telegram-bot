from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from .models import Base
from config import config
import os

# Ensure data directory exists
db_path = config.DB_URL.replace("sqlite:///", "")
db_dir = os.path.dirname(db_path)
if db_dir and not os.path.exists(db_dir):
    os.makedirs(db_dir)

# We'll use aiosqlite for async sqlite
engine = create_async_engine(config.DB_URL.replace("sqlite:///", "sqlite+aiosqlite:///"))
async_session = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)

async def init_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
