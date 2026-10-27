from aiogram import Router, types, F, Bot
from aiogram.filters import Command
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete, and_, or_
from database.models import User, Gender, MatchQueue, MatchSession, MessageLog
from utils.texts import Texts
from keyboards.inline import gender_pref_kb
from keyboards.reply import main_menu_kb
from aiogram.fsm.context import FSMContext
from datetime import datetime
from utils.helpers import get_admin_status

router = Router()

@router.message(F.text == Texts.RANDOM_CHAT)
async def start_matchmaking(message: types.Message, db: AsyncSession):
    # Check if already in session
    res_user = await db.execute(select(User).where(User.tg_id == message.from_user.id))
    user = res_user.scalar_one()
    
    res_session = await db.execute(
        select(MatchSession).where(
            and_(
                or_(MatchSession.user1_id == user.id, MatchSession.user2_id == user.id),
                MatchSession.is_active == True
            )
        )
    )
    if res_session.scalar_one_or_none():
        await message.answer("شما درحال حاضر در یک چت هستید!", parse_mode="HTML")
        return
        
    await message.answer("تمایل دارید با چه کسی چت کنید؟", reply_markup=gender_pref_kb(), parse_mode="HTML")

@router.callback_query(F.data.startswith("match_"))
async def start_matching(callback: types.CallbackQuery, db: AsyncSession, state: FSMContext, db_user: User):
    import html
    pref = callback.data.split("_")[1]
    pref_gender = Gender.MALE if pref == "male" else Gender.FEMALE if pref == "female" else Gender.UNKNOWN
    
    # Check if already in queue
    res_q = await db.execute(select(MatchQueue).where(MatchQueue.user_id == db_user.id))
    if res_q.scalar_one_or_none():
        await callback.message.answer("⚠️ شما در حال حاضر در صف انتظار هستید.", parse_mode="HTML")
        await callback.answer()
        return

    # Try to find a match
    query = select(MatchQueue).where(MatchQueue.user_id != db_user.id)
    if pref_gender != Gender.UNKNOWN:
        query = query.join(User).where(User.gender == pref_gender)
    
    # Priority for those looking for our gender or any
    res_match = await db.execute(query.order_by(MatchQueue.created_at.asc()))
    match_entry = res_match.scalar_one_or_none()

    if match_entry:
        match_user_id = match_entry.user_id
        # Remove from queue
        await db.delete(match_entry)
        
        # Create session
        session = MatchSession(user1_id=db_user.id, user2_id=match_user_id)
        db.add(session)
        await db.commit()
        
        # Notify both
        res_partner = await db.execute(select(User).where(User.id == match_user_id))
        partner = res_partner.scalar_one()
        
        partner_name = html.escape(partner.nickname or partner.full_name or "ناشناس")
        my_name = html.escape(db_user.nickname or db_user.full_name or "ناشناس")

        # Custom keyboard for chat
        chat_kb = types.ReplyKeyboardMarkup(
            keyboard=[
                [types.KeyboardButton(text=Texts.STOP_CHAT), types.KeyboardButton(text=Texts.BLOCK_USER)],
                [types.KeyboardButton(text=Texts.SEND_PROFILE)]
            ],
            resize_keyboard=True
        )

        msg = "<b>🎉 متصل شدید!</b>\nاکنون می‌توانید با هم صحبت کنید."
        await callback.message.answer(f"{msg}\n👤 طرف مقابل: <b>{partner_name}</b>", parse_mode="HTML", reply_markup=chat_kb)
        await callback.bot.send_message(partner.tg_id, f"{msg}\n👤 طرف مقابل: <b>{my_name}</b>", parse_mode="HTML", reply_markup=chat_kb)
    else:
        # Add to queue
        new_q = MatchQueue(user_id=db_user.id, preferred_gender=pref_gender)
        db.add(new_q)
        await db.commit()
        await callback.message.answer("🔎 <b>درحال جستجوی فرد مناسب...</b>\nلطفاً صبور باشید.", parse_mode="HTML")
    
    await callback.answer()

@router.message(F.text == Texts.SEND_PROFILE)
async def send_profile_in_chat(message: types.Message, db: AsyncSession, db_user: User, bot: Bot):
    # Find active session
    res_session = await db.execute(
        select(MatchSession).where(
            and_(
                or_(MatchSession.user1_id == db_user.id, MatchSession.user2_id == db_user.id),
                MatchSession.is_active == True
            )
        )
    )
    session = res_session.scalars().first()
    
    if not session:
        await message.answer("⚠️ شما در چت فعالی نیستید.", parse_mode="HTML")
        return

    # Determine partner
    partner_id = session.user2_id if session.user1_id == db_user.id else session.user1_id
    res_partner = await db.execute(select(User).where(User.id == partner_id))
    partner = res_partner.scalar_one()
    
    # Format Profile
    import html
    gender_text = "پسر 👦" if db_user.gender == Gender.MALE else "دختر 👧" if db_user.gender == Gender.FEMALE else "نامشخص"
    bio = db_user.bio or "ندارد"
    age = db_user.age or "نامشخص"
    name = html.escape(db_user.nickname or db_user.full_name or "ناشناس")
    
    profile_text = (
        f"<b>👤 پروفایل کاربر مقابل:</b>\n\n"
        f"🏷 <b>نام:</b> {name}\n"
        f"🎂 <b>سن:</b> {age}\n"
        f"🚻 <b>جنسیت:</b> {gender_text}\n"
        f"📝 <b>بیوگرافی:</b> {html.escape(bio)}"
    )
    
    await bot.send_message(partner.tg_id, profile_text, parse_mode="HTML")
    await message.answer("✅ پروفایل شما برای طرف مقابل ارسال شد.", parse_mode="HTML")

@router.message(F.text == Texts.BLOCK_USER)
async def block_user_btn(message: types.Message, db: AsyncSession, db_user: User, bot: Bot):
    # Find active session
    res_session = await db.execute(
        select(MatchSession).where(
            and_(
                or_(MatchSession.user1_id == db_user.id, MatchSession.user2_id == db_user.id),
                MatchSession.is_active == True
            )
        )
    )
    session = res_session.scalars().first()
    
    if not session:
        await message.answer("⚠️ شما در چت فعالی نیستید.", parse_mode="HTML")
        return

    # Determine partner
    partner_id = session.user2_id if session.user1_id == db_user.id else session.user1_id
    res_partner = await db.execute(select(User).where(User.id == partner_id))
    partner = res_partner.scalar_one()

    # Create Block
    from database.models import Block
    block = Block(blocker_id=db_user.id, blocked_id=partner.id)
    db.add(block)
    
    # End Session
    session.is_active = False
    session.ended_at = datetime.utcnow()
    await db.commit()
    
    await message.answer(Texts.USER_BLOCKED, reply_markup=main_menu_kb(is_admin=db_user.is_admin), parse_mode="HTML")
    await bot.send_message(partner.tg_id, Texts.YOU_ARE_BLOCKED, reply_markup=main_menu_kb(is_admin=partner.is_admin), parse_mode="HTML")

@router.message(Command("stop"))
@router.message(F.text == Texts.STOP_CHAT)
async def stop_chat(message: types.Message, db: AsyncSession, db_user: User, bot: Bot):
    # Find active session
    res_session = await db.execute(
        select(MatchSession).where(
            and_(
                or_(MatchSession.user1_id == db_user.id, MatchSession.user2_id == db_user.id),
                MatchSession.is_active == True
            )
        )
    )
    session = res_session.scalars().first()
    
    if session:
        session.is_active = False
        session.ended_at = datetime.utcnow()
        await db.commit()
        
        partner_id = session.user2_id if session.user1_id == db_user.id else session.user1_id
        res_partner = await db.execute(select(User).where(User.id == partner_id))
        partner = res_partner.scalar_one()
        
        is_admin = await get_admin_status(db_user.tg_id, db)
        await message.answer("🏁 چت به درخواست شما پایان یافت.", reply_markup=main_menu_kb(is_admin=is_admin), parse_mode="HTML")
        
        partner_is_admin = await get_admin_status(partner.tg_id, db)
        await bot.send_message(partner.tg_id, "🏁 طرف مقابل چت را ترک کرد.", reply_markup=main_menu_kb(is_admin=partner_is_admin), parse_mode="HTML")
    else:
        # Also check if in queue
        res_q = await db.execute(select(MatchQueue).where(MatchQueue.user_id == db_user.id))
        entry = res_q.scalars().first()
        if entry:
            await db.delete(entry)
            await db.commit()
            is_admin = await get_admin_status(db_user.tg_id, db)
            await message.answer("❌ از صف انتظار خارج شدید.", reply_markup=main_menu_kb(is_admin=is_admin), parse_mode="HTML")
        else:
            # Force remove keyboard if user thinks they are in chat but aren't
            is_admin = await get_admin_status(db_user.tg_id, db)
            await message.answer("⚠️ شما در چت فعالی نیستید.", reply_markup=main_menu_kb(is_admin=is_admin), parse_mode="HTML")

@router.message()
async def process_chat_message(message: types.Message, db: AsyncSession, db_user: User, bot: Bot):
    # This handler captures ALL text/media not handled above.
    # It serves as the Relay for active matches.
    
    # Check Active Session
    res_session = await db.execute(
        select(MatchSession).where(
            and_(
                or_(MatchSession.user1_id == db_user.id, MatchSession.user2_id == db_user.id),
                MatchSession.is_active == True
            )
        )
    )
    session = res_session.scalars().first()
    
    if session:
        # Relay message
        partner_id = session.user2_id if session.user1_id == db_user.id else session.user1_id
        res_partner = await db.execute(select(User).where(User.id == partner_id))
        partner = res_partner.scalar_one()
        
        try:
            await bot.copy_message(
                chat_id=partner.tg_id,
                from_chat_id=message.chat.id,
                message_id=message.message_id
            )
        except Exception:
            # Maybe partner blocked bot?
            pass
    else:
        # User sent text but not in chat/command.
        # Just ignore or maybe guide them?
        # If they just strictly text, maybe show main menu?
        pass
