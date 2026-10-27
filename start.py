from aiogram import Router, types, F
from aiogram.filters import CommandStart, Command
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, or_
from database.models import User, Gender
from utils.texts import Texts
from utils.helpers import get_admin_status
from keyboards.reply import main_menu_kb, gender_kb
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from handlers.relay import RelayStates

router = Router()

class Registration(StatesGroup):
    choosing_gender = State()

@router.message(CommandStart())
async def cmd_start(message: types.Message, db: AsyncSession, state: FSMContext, db_user: User):
    import html
    # Handle deep-linking (t.me/bot?start=token)
    args = message.text.split()
    if len(args) > 1:
        token = args[1]
        # Check if token belongs to someone
        res_target = await db.execute(select(User).where(User.link_token == token))
        target = res_target.scalar_one_or_none()
        
        if target:
            if target.tg_id == message.from_user.id:
                await message.answer("⚠️ شما نمی‌توانید به خودتان پیام ناشناس بدهید! 😅", parse_mode="HTML")
            else:
                # [NEW] Referral Tracking
                # Track if user was never referred before
                if not db_user.referred_by_id and target.id != db_user.id:
                    db_user.referred_by_id = target.id
                    # Also reset referral_confirmed just in case they were registered but NOT confirmed
                    db_user.referral_confirmed = False
                    await db.commit()
                    import logging
                    logging.info(f"Referral tracked: {db_user.tg_id} referred by {target.tg_id}")
                
                target_name = html.escape(target.nickname or target.full_name or "یک نفر")
                await state.update_data(target_id=target.id)
                
                # Add cancel button
                from keyboards.reply import ReplyKeyboardMarkup, KeyboardButton
                cancel_kb = ReplyKeyboardMarkup(
                    keyboard=[
                        [KeyboardButton(text="انصراف ❌")]
                    ],
                    resize_keyboard=True,
                    one_time_keyboard=True
                )
                
                await message.answer(
                    f"✍️ درحال ارسال پیام ناشناس به <b>{target_name}</b>...\n"
                    f"هر چه می‌خواهید بنویسید (متن، عکس، صدا و...):",
                    parse_mode="HTML",
                    reply_markup=cancel_kb
                )
                await state.set_state(RelayStates.relay_flow)
                return

    # If they are returning without a link
    if db_user.gender == Gender.UNKNOWN:
        await message.answer(f"👋 {Texts.START_WELCOME}", parse_mode="HTML")
        await message.answer(Texts.CHOOSE_GENDER, reply_markup=gender_kb(), parse_mode="HTML")
        await state.set_state(Registration.choosing_gender)
    else:
        # IMPORTANT: Check if user is in active chat session
        from database.models import MatchSession
        res_session = await db.execute(
            select(MatchSession).where(
                and_(
                    or_(MatchSession.user1_id == db_user.id, MatchSession.user2_id == db_user.id),
                    MatchSession.is_active == True
                )
            )
        )
        active_session = res_session.scalars().first()
        
        if active_session:
            # User is in active chat - preserve chat keyboard
            chat_kb = types.ReplyKeyboardMarkup(
                keyboard=[
                    [types.KeyboardButton(text=Texts.STOP_CHAT), types.KeyboardButton(text=Texts.BLOCK_USER)],
                    [types.KeyboardButton(text=Texts.SEND_PROFILE)]
                ],
                resize_keyboard=True
            )
            await message.answer("💬 شما در حال چت هستید. از دکمه‌های زیر استفاده کنید.", reply_markup=chat_kb, parse_mode="HTML")
        else:
            # Normal flow - show main menu
            is_admin = await get_admin_status(message.from_user.id, db)
            await message.answer(f"🏠 {Texts.MAIN_MENU}", reply_markup=main_menu_kb(is_admin=is_admin), parse_mode="HTML")

@router.message(Registration.choosing_gender)
async def process_gender(message: types.Message, db: AsyncSession, state: FSMContext, db_user: User):
    if message.text == Texts.GENDER_MALE:
        gender = Gender.MALE
    elif message.text == Texts.GENDER_FEMALE:
        gender = Gender.FEMALE
    else:
        await message.answer("❌ لطفاً یکی از گزینه‌ها را از کیبورد انتخاب کنید.", parse_mode="HTML")
        return
    
    db_user.gender = gender
    await db.commit()
    
    await state.clear()
    is_admin = await get_admin_status(message.from_user.id, db)
    await message.answer("✅ جنسیت شما ثبت شد!", reply_markup=main_menu_kb(is_admin=is_admin), parse_mode="HTML")
