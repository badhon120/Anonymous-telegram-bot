from aiogram import Router, types, F, Bot
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from database.models import User
from utils.texts import Texts
from datetime import datetime, timedelta
from urllib.parse import quote

router = Router()

from aiogram.fsm.context import FSMContext

@router.message(F.text == Texts.REFERRAL_MENU)
async def view_referrals(message: types.Message, db: AsyncSession, db_user: User, bot: Bot, state: FSMContext):
    # Clear any previous state
    await state.clear()
    
    # Count referrals (Strict: Only confirmed)
    from sqlalchemy import and_
    
    # We need to ensure we count confirmed only if column exists, but we added migration.
    # Logic: count where refered_by_id == user.id AND referral_confirmed is TRUE
    res = await db.execute(select(func.count(User.id)).where(and_(User.referred_by_id == db_user.id, User.referral_confirmed == True)))
    referral_count = res.scalar() or 0
    
    # Calculate rewards: 30 referrals = 1 hour bonus
    # Determine if eligible for reward
    has_reward = referral_count >= 30
    
    bot_info = await bot.get_me()
    
    if not db_user.link_token:
        import uuid
        db_user.link_token = str(uuid.uuid4())[:8]
        await db.commit()
    
    referral_link = f"https://t.me/{bot_info.username}?start={db_user.link_token}"
    
    # Format text
    text = Texts.REFERRAL_INFO.format(
        link=referral_link,
        count=referral_count
    )
    
    # Build keyboard
    from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
    
    buttons = []
    # Share Button with proper URL encoding
    share_text = quote("پیام ناشناس به من بفرستید! 👇")
    share_url = f"https://t.me/share/url?url={referral_link}&text={share_text}"
    buttons.append([InlineKeyboardButton(text="اشتراک گذاری 📤", url=share_url)])

    
    if has_reward:
        buttons.append([InlineKeyboardButton(text=Texts.CLAIM_REWARD, callback_data="claim_reward")])
        
    kb = InlineKeyboardMarkup(inline_keyboard=buttons)
    
    await message.answer(text, parse_mode="HTML", reply_markup=kb)

@router.callback_query(F.data == "claim_reward")
async def process_claim_reward(callback: types.CallbackQuery, db: AsyncSession, db_user: User):
    """
    Handle claim reward button click.
    Checks strict referral count.
    """
    # Double check eligibility
    from sqlalchemy import and_
    res = await db.execute(select(func.count(User.id)).where(and_(User.referred_by_id == db_user.id, User.referral_confirmed == True)))
    referral_count = res.scalar() or 0
    
    if referral_count >= 30:
        await callback.message.answer(Texts.CLAIM_REWARD_MSG, parse_mode="HTML")
        await callback.answer()
    else:
        await callback.answer("❌ شما هنوز به تعداد لازم نرسیده‌اید.", show_alert=True)
