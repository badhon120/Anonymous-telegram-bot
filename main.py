import asyncio
import logging
from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage
from config import config
from database.session import init_db, async_session
from middlewares.db_session import DbSessionMiddleware
from middlewares.user_registration import UserRegistrationMiddleware
from middlewares.check_sub import ChannelLockMiddleware
from handlers import start, profile, relay, match, admin, referral

async def main():
    logging.basicConfig(level=logging.INFO)
    
    # Initialize DB
    await init_db()
    
    # [FIX] Backfill link_token for existing users
    async with async_session() as db:
        from database.models import User
        import uuid
        from sqlalchemy import select
        
        # Check users with null link_token
        res = await db.execute(select(User).where(User.link_token == None))
        users = res.scalars().all()
        
        if users:
            logging.info(f"Backfilling link_token for {len(users)} users...")
            for u in users:
                u.link_token = str(uuid.uuid4())[:8]
            await db.commit()
            logging.info("Backfill complete.")
            
    # [FIX] Migration for new columns (Age, ReferralConfirmed)
    async with async_session() as db:
        from sqlalchemy import text
        try:
            await db.execute(text("ALTER TABLE users ADD COLUMN age INTEGER"))
            logging.info("Added 'age' column.")
        except Exception:
            pass # Already exists

        try:
            await db.execute(text("ALTER TABLE users ADD COLUMN referral_confirmed BOOLEAN DEFAULT 0"))
            logging.info("Added 'referral_confirmed' column.")
        except Exception:
            pass # Already exists
        await db.commit()
    
    bot = Bot(token=config.BOT_TOKEN)
    dp = Dispatcher(storage=MemoryStorage())
    
    # Register Middleware
    dp.update.middleware(DbSessionMiddleware(async_session))
    dp.update.middleware(UserRegistrationMiddleware())
    dp.message.middleware(ChannelLockMiddleware())
    dp.callback_query.middleware(ChannelLockMiddleware())
    
    # Register Routers
    dp.include_router(referral.router)  # High priority to catch menu clicks in any state
    dp.include_router(admin.router)     # [FIX] Admin high priority
    dp.include_router(start.router)
    dp.include_router(profile.router)
    dp.include_router(relay.router)
    dp.include_router(match.router)
    
    logging.info("Starting bot...")
    await dp.start_polling(bot)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logging.info("Bot stopped.")
