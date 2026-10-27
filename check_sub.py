from aiogram import BaseMiddleware
from aiogram.types import TelegramObject, Message, CallbackQuery
from typing import Callable, Dict, Any, Awaitable
from config import config
from utils.texts import Texts
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from database.models import Settings, Gender
import logging

class ChannelLockMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any]
    ) -> Any:
        # [DEBUG] Log all events
        if isinstance(event, CallbackQuery):
            logging.info(f"[MIDDLEWARE] CallbackQuery received: {event.data}")
        elif isinstance(event, Message):
            logging.info(f"[MIDDLEWARE] Message received: {event.text}")
        
        db: AsyncSession = data.get("db")
        db_user = data.get("db_user")
        bot = data.get("bot")

        if not db or not db_user or not bot:
            logging.warning(f"[MIDDLEWARE] Missing dependencies: db={db is not None}, db_user={db_user is not None}, bot={bot is not None}")
            return await handler(event, data)

        # [NEW] Referral Bypass (Reward for referrals)
        from datetime import datetime
        if db_user.referral_bonus_until and db_user.referral_bonus_until > datetime.utcnow():
            logging.info(f"[MIDDLEWARE] Referral bypass for user {db_user.tg_id}")
            return await handler(event, data)

        # Get channel ID from dynamic settings
        res = await db.execute(select(Settings).where(Settings.key == "required_channel_id"))
        setting = res.scalar_one_or_none()
        channel_id = setting.value if setting else config.REQUIRED_CHANNEL_ID
            
        # Bypass if no channel is set
        if not channel_id or str(channel_id).strip() in ["", "0"]:
            logging.info(f"[MIDDLEWARE] No channel lock configured, bypassing")
            return await handler(event, data)
            
        user_id = data.get("event_from_user").id
        
        # Bypass for admins
        if user_id in config.ADMIN_IDS or db_user.is_admin:
            logging.info(f"[MIDDLEWARE] Admin bypass for user {user_id}")
            return await handler(event, data)

        # CRITICAL: Check if user clicked "join button" FIRST, before membership check
        # This prevents state conflicts with other handlers
        if isinstance(event, Message) and event.text == Texts.CHECK_JOIN:
            logging.info(f"[CHECK_JOIN_TEXT] User {user_id} clicked join button")
            
            # Re-check membership
            try:
                member = await bot.get_chat_member(chat_id=channel_id, user_id=user_id)
                is_member_now = member.status in ["member", "administrator", "creator"]
                
                if is_member_now:
                    logging.info(f"[CHECK_JOIN_TEXT] User {user_id} is now a member!")
                    
                    # Mark referral confirmed
                    if not db_user.referral_confirmed:
                        db_user.referral_confirmed = True
                        await db.commit()
                    
                    # Clear state (IMPORTANT!)
                    state = data.get("state")
                    if state:
                        await state.clear()
                        logging.info(f"[CHECK_JOIN_TEXT] State cleared")
                    
                    # Check if new or existing user
                    if db_user.gender == Gender.UNKNOWN:
                        # New user - show gender selection
                        from keyboards.reply import gender_kb
                        from handlers.start import Registration
                        
                        await event.answer(f"✅ عضویت شما تایید شد!\n\n👋 {Texts.START_WELCOME}", parse_mode="HTML")
                        await event.answer(Texts.CHOOSE_GENDER, reply_markup=gender_kb(), parse_mode="HTML")
                        
                        if state:
                            await state.set_state(Registration.choosing_gender)
                    else:
                        # Existing user - show main menu
                        from keyboards.reply import main_menu_kb
                        from utils.helpers import get_admin_status
                        
                        is_admin = await get_admin_status(user_id, db)
                        await event.answer("✅ عضویت شما تایید شد!\n\n🏠 " + Texts.MAIN_MENU, reply_markup=main_menu_kb(is_admin=is_admin), parse_mode="HTML")
                    
                    return None
                else:
                    logging.warning(f"[CHECK_JOIN_TEXT] User {user_id} not a member yet")
                    await event.answer("❌ هنوز در کانال عضو نشده‌اید! لطفاً ابتدا عضو شوید.", parse_mode="HTML")
                    return None
            except Exception as e:
                logging.error(f"[CHECK_JOIN_TEXT] Error checking membership: {e}")
                await event.answer("⚠️ خطا در بررسی عضویت. لطفاً دوباره تلاش کنید.", parse_mode="HTML")
                return None

        # Now do regular membership check
        try:
            member = await bot.get_chat_member(chat_id=channel_id, user_id=user_id)
            is_member = member.status in ["member", "administrator", "creator"]
            
            
            # 2. General Membership Check
            if is_member:
                if not db_user.referral_confirmed:
                    db_user.referral_confirmed = True
                    await db.commit()
                return await handler(event, data)
                
        except Exception as e:
            logging.error(f"Membership check error: {e}")
            if isinstance(event, CallbackQuery) and event.data.startswith("check_join_"):
                await event.answer("⚠️ خطا در بررسی عضویت. مطمئن شوید ربات در کانال ادمین است.", show_alert=True)
                return
            # On generic error, we usually block to be safe, but let code fall through
            pass

        # 3. Not a member - Block access and show join prompt
        channel_str = str(channel_id)
        if channel_str.startswith("-100"):
            link_part = channel_str.replace("-100", "")
            channel_url = f"https://t.me/c/{link_part}/1"
        elif channel_str.startswith("@"):
            channel_url = f"https://t.me/{channel_str[1:]}"
        else:
            channel_url = f"https://t.me/{channel_str}"

        # Use Reply Keyboard instead of Inline Keyboard for better reliability
        from aiogram.types import ReplyKeyboardMarkup, KeyboardButton
        
        keyboard = ReplyKeyboardMarkup(
            keyboard=[
                [KeyboardButton(text=Texts.CHECK_JOIN)]
            ],
            resize_keyboard=True,
            one_time_keyboard=True
        )

        if isinstance(event, Message):
            # Show join prompt
            msg_text = f"⚠️ <b>برای استفاده از ربات، ابتدا باید در کانال ما عضو شوید:</b>\n\n👇 <a href='{channel_url}'>عضویت در کانال</a>\n\nبعد از عضویت، دکمه زیر را بزنید:"
            await event.answer(msg_text, reply_markup=keyboard, parse_mode="HTML")
        elif isinstance(event, CallbackQuery):
            await event.answer("⚠️ برای استفاده از ربات، ابتدا باید در کانال عضو شوید!", show_alert=True)
            
        return None
