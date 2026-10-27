from aiogram import Router, types, F, Bot
import asyncio
from aiogram.filters import Command
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_, or_
from database.models import User, MessageLog, MatchSession, Settings
from config import config
from utils.texts import Texts
from utils.helpers import get_admin_status
from keyboards.reply import main_menu_kb
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import BufferedInputFile
import io

router = Router()

class AdminStates(StatesGroup):
    broadcasting = State()
    adding_admin = State()
    setting_channel = State()
    searching_logs = State()

@router.message(F.text == Texts.ADMIN_PANEL)
@router.message(Command("admin"))
async def admin_panel(message: types.Message, db: AsyncSession):
    if not await get_admin_status(message.from_user.id, db): return
    
    kb = types.ReplyKeyboardMarkup(
        keyboard=[
            [types.KeyboardButton(text=Texts.STATS), types.KeyboardButton(text=Texts.BROADCAST)],
            [types.KeyboardButton(text=Texts.ADD_ADMIN), types.KeyboardButton(text=Texts.SET_CHANNEL)],
            [types.KeyboardButton(text=Texts.SEARCH_LOGS), types.KeyboardButton(text=Texts.EXPORT_USERS)],
            [types.KeyboardButton(text=Texts.REFERRAL_MENU), types.KeyboardButton(text="بازگشت 🔙")]
        ],
        resize_keyboard=True
    )
    await message.answer("خوش آمدید قربان. پنل مدیریت فعال شد.", reply_markup=kb)

@router.message(F.text == Texts.SET_CHANNEL)
async def start_set_channel(message: types.Message, db: AsyncSession, state: FSMContext):
    if not await get_admin_status(message.from_user.id, db): return
    await message.answer(Texts.ENTER_CHANNEL_ID)
    await state.set_state(AdminStates.setting_channel)

@router.message(AdminStates.setting_channel)
async def process_set_channel(message: types.Message, db: AsyncSession, state: FSMContext):
    if not await get_admin_status(message.from_user.id, db): return
    
    channel_id = message.text.strip()
    # Store in Settings table
    res = await db.execute(select(Settings).where(Settings.key == "required_channel_id"))
    setting = res.scalar_one_or_none()
    
    if not setting:
        setting = Settings(key="required_channel_id", value=channel_id)
        db.add(setting)
    else:
        setting.value = channel_id
        
    await db.commit()
    await message.answer(Texts.CHANNEL_UPDATED)
    await state.clear()
    await admin_panel(message, db)

@router.message(F.text == Texts.SEARCH_LOGS)
async def start_search_logs(message: types.Message, db: AsyncSession, state: FSMContext):
    if not await get_admin_status(message.from_user.id, db): return
    await message.answer(Texts.ENTER_USER_ID)
    await state.set_state(AdminStates.searching_logs)

@router.message(AdminStates.searching_logs)
async def process_search_logs(message: types.Message, db: AsyncSession, state: FSMContext):
    if not await get_admin_status(message.from_user.id, db): return
    
    import html
    input_data = message.text.strip()
    target_user = None
    
    try:
        if input_data.isdigit():
            target_user = await db.scalar(select(User).where(User.tg_id == int(input_data)))
        else:
            username = input_data.replace("@", "").strip()
            target_user = await db.scalar(select(User).where(User.username == username))
            
        if not target_user:
            await message.answer(f"❌ {Texts.USER_NOT_FOUND}", parse_mode="HTML")
            await state.clear()
            await admin_panel(message, db)
            return

        # Find logs as sender or receiver
        res_logs = await db.execute(
            select(MessageLog).where(
                or_(MessageLog.sender_id == target_user.id, MessageLog.receiver_id == target_user.id)
            ).order_by(MessageLog.created_at.desc()).limit(50)
        )
        logs = res_logs.scalars().all()
        
        if not logs:
            await message.answer("⚠️ هیچ پیامی یافت نشد.", parse_mode="HTML")
        else:
            log_header = Texts.USER_LOGS_HEADER.format(user_id=target_user.tg_id)
            log_text = f"<b>🔍 {html.escape(log_header)}</b>\n\n"
            for log in logs:
                direction = "📤 ارسال" if log.sender_id == target_user.id else "📥 دریافت"
                content = html.escape(str(log.content)[:50]) if log.content else "---"
                log_text += f"{direction} (<code>{log.created_at.strftime('%H:%M')}</code>): {content}...\n"
            
            await message.answer(log_text, parse_mode="HTML")
            
    except Exception as e:
        await message.answer(f"❌ خطای غیرمنتظره: {html.escape(str(e))}", parse_mode="HTML")
    finally:
        await state.clear()
        await admin_panel(message, db)

@router.message(F.text == Texts.EXPORT_USERS)
async def export_users_list(message: types.Message, db: AsyncSession):
    if not await get_admin_status(message.from_user.id, db): return
    
    res = await db.execute(select(User))
    users = res.scalars().all()
    
    output = io.StringIO()
    output.write("ID | Username | Full Name | Nickname | Gender\n")
    output.write("-" * 60 + "\n")
    
    for u in users:
        username = f"@{u.username}" if u.username else "N/A"
        nickname = u.nickname or "N/A"
        output.write(f"{u.tg_id} | {username} | {u.full_name} | {nickname} | {u.gender.value}\n")
    
    file_content = output.getvalue().encode("utf-8")
    file = BufferedInputFile(file_content, filename="users_list.txt")
    
    await message.answer_document(file, caption="لیست تمامی کاربران ربات 👥")

@router.message(F.text == "افزودن ادمین 👤")
@router.message(F.text == Texts.ADD_ADMIN)
async def start_add_admin(message: types.Message, db: AsyncSession, state: FSMContext):
    if not await get_admin_status(message.from_user.id, db): return
    await message.answer(Texts.ENTER_ADMIN_USERNAME, parse_mode="HTML")
    await state.set_state(AdminStates.adding_admin)

@router.message(AdminStates.adding_admin)
async def process_adding_admin(message: types.Message, db: AsyncSession, state: FSMContext):
    if not await get_admin_status(message.from_user.id, db): return
    
    import html
    input_data = message.text.strip()
    target_user = None
    
    try:
        if input_data.isdigit():
            res = await db.execute(select(User).where(User.tg_id == int(input_data)))
            target_user = res.scalar_one_or_none()
        else:
            username = input_data.replace("@", "")
            res = await db.execute(select(User).where(User.username == username))
            target_user = res.scalar_one_or_none()
        
        if not target_user:
            await message.answer(
                f"❌ <b>کاربر یافت نشد.</b>\n\n"
                f"راهنمایی: کاربر باید حداقل یک بار دکمه /start را در ربات زده باشد تا ثبت‌نام شود.",
                parse_mode="HTML"
            )
        else:
            target_user.is_admin = True
            await db.commit()
            name = html.escape(target_user.nickname or target_user.full_name or "کاربر")
            await message.answer(f"✅ <b>{name}</b> با موفقیت به لیست مدیران اضافه شد.", parse_mode="HTML")
            
    except Exception as e:
        await message.answer(f"❌ خطایی رخ داد: {html.escape(str(e))}", parse_mode="HTML")
    finally:
        await state.clear()
        await admin_panel(message, db)

@router.message(F.text == Texts.STATS)
async def view_stats(message: types.Message, db: AsyncSession):
    if not await get_admin_status(message.from_user.id, db): return
    
    total_users = await db.scalar(select(func.count(User.id)))
    active_matches = await db.scalar(select(func.count(MatchSession.id)).where(MatchSession.is_active == True))
    total_logs = await db.scalar(select(func.count(MessageLog.id)))
    
    stats_text = (
        f"📊 <b>آمار ربات:</b>\n\n"
        f"👥 <b>کل کاربران:</b> <code>{total_users}</code>\n"
        f"💬 <b>چت‌های فعال:</b> <code>{active_matches}</code>\n"
        f"✉️ <b>کل پیام‌های رد و بدل شده:</b> <code>{total_logs}</code>"
    )
    await message.answer(stats_text, parse_mode="HTML")

@router.message(F.text == Texts.BROADCAST)
async def start_broadcast(message: types.Message, state: FSMContext, db: AsyncSession):
    if not await get_admin_status(message.from_user.id, db): return
    
    await message.answer(Texts.ENTER_BROADCAST_MSG, parse_mode="HTML")
    await state.set_state(AdminStates.broadcasting)

@router.message(AdminStates.broadcasting)
async def process_broadcast(message: types.Message, db: AsyncSession, bot: Bot, state: FSMContext):
    if not await get_admin_status(message.from_user.id, db): return
    
    res = await db.execute(select(User.tg_id))
    user_ids = res.scalars().all()
    
    sent = 0
    failed = 0
    msg = await message.answer(f"⏳ <b>درحال ارسال به {len(user_ids)} کاربر...</b>", parse_mode="HTML")
    
    try:
        for uid in user_ids:
            try:
                await bot.copy_message(chat_id=uid, from_chat_id=message.chat.id, message_id=message.message_id)
                sent += 1
            except Exception:
                failed += 1
            if (sent + failed) % 20 == 0:
                await bot.edit_message_text(
                    chat_id=message.chat.id,
                    message_id=msg.message_id,
                    text=f"⏳ <b>درحال ارسال...</b>\n✅ موفق: {sent}\n❌ ناموفق: {failed}",
                    parse_mode="HTML"
                )
            await asyncio.sleep(0.05)
            
        await message.answer(f"📢 <b>پایان ارسال همگانی:</b>\n✅ موفق: {sent}\n❌ ناموفق: {failed}", parse_mode="HTML")
    finally:
        await state.clear()

@router.message(F.text == "بازگشت 🔙")
async def back_to_main(message: types.Message, db: AsyncSession):
    is_admin = await get_admin_status(message.from_user.id, db)
    await message.answer(Texts.MAIN_MENU, reply_markup=main_menu_kb(is_admin=is_admin), parse_mode="HTML")
