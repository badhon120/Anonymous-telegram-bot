from aiogram import Router, types, F, Bot
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from database.models import User, MessageLog
from utils.texts import Texts
from aiogram.fsm.context import FSMContext
from urllib.parse import quote

from aiogram.fsm.state import State, StatesGroup
from aiogram.types import BotCommand

class RelayStates(StatesGroup):
    relay_flow = State()
    reply_flow = State()

router = Router()

def get_relay_kb(sender_internal_id: int):
    from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text=Texts.REPLY, callback_data=f"reply_{sender_internal_id}"),
            InlineKeyboardButton(text=Texts.CLOSE_RELAY, callback_data="close_relay")
        ]
    ])

@router.message(F.text == Texts.MY_LINK)
async def get_my_link(message: types.Message, db_user: User, db: AsyncSession, bot: Bot):
    if not db_user.link_token:
        import uuid
        db_user.link_token = str(uuid.uuid4())[:8]
        await db.commit()
        
    bot_info = await bot.get_me()
    link = f"https://t.me/{bot_info.username}?start={db_user.link_token}"
    
    from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
    # Fix: Proper URL encoding for share text
    share_text = quote("حرفی تو دلت مونده؟ ناشناس بهم بگو! 👇")
    share_url = f"https://t.me/share/url?url={link}&text={share_text}"
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="اشتراک گذاری 📤", url=share_url)]
    ])
    
    await message.answer(f"🔗 {Texts.YOUR_LINK.format(link=link)}", reply_markup=kb)

@router.message(RelayStates.relay_flow)
async def process_relay(message: types.Message, db: AsyncSession, state: FSMContext, bot: Bot, db_user: User):
    data = await state.get_data()
    target_internal_id = data.get("target_id")
    
    res_target = await db.execute(select(User).where(User.id == target_internal_id))
    target = res_target.scalar_one_or_none()
    
    if not target:
        await message.answer("❌ خطایی رخ داد. مخاطب یافت نشد.")
        await state.clear()
        return
    
    # Generate Anonymous ID (Changes every 3 days)
    import time
    period_salt = int(time.time() / (86400 * 3)) # 3 days window
    # Simple consistent hash
    raw_id = f"{db_user.id}:{target.id}:{period_salt}"
    # Use built-in hash or hashlib
    import hashlib
    hash_obj = hashlib.md5(raw_id.encode())
    # Take last 6 digits of int value
    anon_id = int(hash_obj.hexdigest(), 16) % 1000000
    
    # Relay message
    try:
        await bot.send_message(target.tg_id, f"🔔 <b>پیام ناشناس جدید!</b>\n👤 فرستنده: <code>#{anon_id}</code>", parse_mode="HTML")
        await bot.copy_message(
            chat_id=target.tg_id,
            from_chat_id=message.chat.id,
            message_id=message.message_id,
            reply_markup=get_relay_kb(db_user.id)
        )
        await message.answer("✅ پیام شما به صورت ناشناس ارسال شد!")
    except Exception as e:
        await message.answer("⚠️ پیام ارسال نشد. شاید مخاطب ربات را مسدود کرده است.")
    
    # Log message
    log = MessageLog(
        sender_id=db_user.id,
        receiver_id=target.id,
        content_type=message.content_type,
        content=message.text or message.caption or f"[{message.content_type}]",
        context="link"
    )
    db.add(log)
    await db.commit()
    
    await state.clear()

@router.callback_query(F.data.startswith("reply_"))
async def start_reply(callback: types.CallbackQuery, state: FSMContext):
    target_id = int(callback.data.split("_")[1])
    await state.update_data(target_id=target_id)
    await state.set_state(RelayStates.reply_flow)
    await callback.message.answer(f"✍️ {Texts.REPLY_PROMPT}")
    await callback.answer()

@router.callback_query(F.data == "close_relay")
async def close_relay_msg(callback: types.CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.edit_reply_markup(reply_markup=None)
    await callback.message.answer("❌ چت بسته شد.")
    await callback.answer()

@router.message(RelayStates.reply_flow)
async def process_reply(message: types.Message, db: AsyncSession, state: FSMContext, bot: Bot, db_user: User):
    data = await state.get_data()
    target_internal_id = data.get("target_id")
    
    res_target = await db.execute(select(User).where(User.id == target_internal_id))
    target = res_target.scalar_one_or_none()
    
    if not target:
        await message.answer("❌ متأسفانه مخاطب دیگر در دسترس نیست.")
        await state.clear()
        return
    
    try:
        await bot.send_message(target.tg_id, "💬 <b>پاسخ جدید از طرف فرد ناشناس:</b>", parse_mode="HTML")
        await bot.copy_message(
            chat_id=target.tg_id,
            from_chat_id=message.chat.id,
            message_id=message.message_id,
            reply_markup=get_relay_kb(db_user.id) # Link owners can keep replying
        )
        await message.answer("✅ پاسخ شما با موفقیت ارسال شد.")
    except Exception:
        await message.answer("⚠️ پاسخ ارسال نشد.")
    
    log = MessageLog(
        sender_id=db_user.id,
        receiver_id=target.id,
        content_type=message.content_type,
        content=message.text or message.caption or f"[{message.content_type}]",
        context="reply"
    )
    db.add(log)
    await db.commit()
    await state.clear()

@router.message(F.text == "انصراف ❌")
async def cancel_relay(message: types.Message, state: FSMContext, db: AsyncSession):
    """Handle cancel button during relay flow"""
    current_state = await state.get_state()
    
    # Only handle if in relay or reply flow
    if current_state in [RelayStates.relay_flow, RelayStates.reply_flow]:
        await state.clear()
        
        from keyboards.reply import main_menu_kb
        from utils.helpers import get_admin_status
        
        is_admin = await get_admin_status(message.from_user.id, db)
        await message.answer("❌ ارسال پیام لغو شد.", reply_markup=main_menu_kb(is_admin=is_admin), parse_mode="HTML")

