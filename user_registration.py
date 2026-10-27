from aiogram import BaseMiddleware
from aiogram.types import TelegramObject, User as TgUser
from typing import Callable, Dict, Any, Awaitable
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from database.models import User
import logging
import random
import uuid

class UserRegistrationMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any]
    ) -> Any:
        # Get tg_user from event
        tg_user: TgUser = data.get("event_from_user")
        if not tg_user:
            return await handler(event, data)

        db: AsyncSession = data.get("db")
        if not db:
            return await handler(event, data)

        # Fetch or create user
        res = await db.execute(select(User).where(User.tg_id == tg_user.id))
        user = res.scalar_one_or_none()

        if not user:
            try:
                # Generate random display ID like U84921
                random_id = f"U{random.randint(10000, 99999)}"
                # Generate persistent link token
                token = str(uuid.uuid4())[:8]
                
                new_user = User(
                    tg_id=tg_user.id,
                    username=tg_user.username,
                    full_name=tg_user.full_name,
                    display_id=random_id,
                    link_token=token
                )
                db.add(new_user)
                await db.commit()
                # Refresh to get ID
                await db.refresh(new_user)
                user = new_user
                logging.info(f"Registered new user: {tg_user.id}")
            except IntegrityError:
                # Race condition or user already exists
                await db.rollback()
                res = await db.execute(select(User).where(User.tg_id == tg_user.id))
                user = res.scalar_one_or_none()
                if not user:
                    logging.error(f"Failed to register user {tg_user.id} even after rollback.")
            except Exception as e:
                logging.error(f"Error during user registration: {e}")
                await db.rollback()
                # Try to fetch again in case of other errors
                res = await db.execute(select(User).where(User.tg_id == tg_user.id))
                user = res.scalar_one_or_none()

        # Inject user into data for handlers to use
        data["db_user"] = user
        
        return await handler(event, data)
