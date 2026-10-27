from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_
from database.models import User
from config import config

async def get_admin_status(tg_id: int, db: AsyncSession) -> bool:
    if tg_id in config.ADMIN_IDS:
        return True
    res = await db.execute(select(User).where(and_(User.tg_id == tg_id, User.is_admin == True)))
    return res.scalar_one_or_none() is not None
