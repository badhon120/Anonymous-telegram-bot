from aiogram import Router, types, F
from aiogram.filters import Command
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_
from database.models import User, Gender
from utils.texts import Texts
from keyboards.reply import gender_kb, main_menu_kb
import uuid
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from utils.helpers import get_admin_status

router = Router()

class ProfileStates(StatesGroup):
    editing_bio = State()
    editing_nickname = State()
    editing_age = State()

class GenderChangeState(StatesGroup):
    choosing_gender = State()

@router.message(F.text == Texts.PROFILE)
async def view_profile(message: types.Message, db_user: User):
    import html
    gender_text = Texts.GENDER_MALE if db_user.gender == Gender.MALE else Texts.GENDER_FEMALE if db_user.gender == Gender.FEMALE else "نامشخص"
    bio = db_user.bio or "تنظیم نشده"
    display_name = db_user.nickname or db_user.full_name or "بدون نام"
    age = db_user.age or "نامشخص"
    
    profile_text = (
        f"<b>👤 پروفایل شما:</b>\n\n"
        f"🏷 <b>نام نمایشی:</b> {html.escape(display_name)}\n"
        f"🎂 <b>سن:</b> {age}\n"
        f"🚻 <b>جنسیت:</b> {gender_text}\n"
        f"📝 <b>بیوگرافی:</b> {html.escape(bio)}\n"
        f"🔑 <b>توکن لینک:</b> <code>{db_user.link_token}</code>\n\n"
        f"برای تغییر لینک ناشناس /reset_link را بزنید."
    )
    
    kb = types.ReplyKeyboardMarkup(
        keyboard=[
            [types.KeyboardButton(text=Texts.EDIT_PROFILE)],
            [types.KeyboardButton(text=Texts.REFERRAL_MENU)],
            [types.KeyboardButton(text="بازگشت 🔙")]
        ],
        resize_keyboard=True
    )
    await message.answer(profile_text, parse_mode="HTML", reply_markup=kb)

@router.message(F.text == Texts.EDIT_PROFILE)
async def edit_profile_menu(message: types.Message):
    kb = types.ReplyKeyboardMarkup(
        keyboard=[
            [types.KeyboardButton(text=Texts.EDIT_NICKNAME), types.KeyboardButton(text=Texts.EDIT_AGE)],
            [types.KeyboardButton(text=Texts.CHANGE_GENDER)],
            [types.KeyboardButton(text=Texts.EDIT_BIO)],
            [types.KeyboardButton(text=Texts.BLOCK_LIST)],
            [types.KeyboardButton(text="بازگشت 🔙")]
        ],
        resize_keyboard=True
    )
    await message.answer("🛠 چه موردی را می‌خواهید ویرایش کنید؟", reply_markup=kb)

@router.message(F.text == Texts.EDIT_AGE)
async def start_edit_age(message: types.Message, state: FSMContext):
    await message.answer(Texts.ENTER_AGE)
    await state.set_state(ProfileStates.editing_age)

@router.message(ProfileStates.editing_age)
async def process_edit_age(message: types.Message, db: AsyncSession, state: FSMContext, db_user: User):
    if not message.text.isdigit():
        await message.answer("❌ لطفاً فقط عدد وارد کنید.")
        return
    
    age = int(message.text)
    if age < 10 or age > 99:
        await message.answer("❌ سن باید بین ۱۰ تا ۹۹ باشد.")
        return
    
    db_user.age = age
    await db.commit()
    
    await state.clear()
    await message.answer(Texts.AGE_UPDATED)
    await view_profile(message, db_user)

@router.message(F.text == Texts.EDIT_NICKNAME)
async def start_edit_nickname(message: types.Message, state: FSMContext):
    await message.answer(Texts.ENTER_NICKNAME)
    await state.set_state(ProfileStates.editing_nickname)

@router.message(ProfileStates.editing_nickname)
async def process_edit_nickname(message: types.Message, db: AsyncSession, state: FSMContext, db_user: User):
    # Validation: check length
    if len(message.text) > 32:
        await message.answer("❌ نام مستعار بیش از حد طولانی است (حداکثر ۳۲ کاراکتر).")
        return
    
    # Validation: only allow alphanumeric and spaces
    if not all(c.isalnum() or c.isspace() for c in message.text):
        await message.answer("❌ نام مستعار فقط می‌تواند شامل حروف، اعداد و فاصله باشد.")
        return
    
    db_user.nickname = message.text.strip()
    await db.commit()
    
    await state.clear()
    await message.answer(Texts.NICKNAME_UPDATED)
    await view_profile(message, db_user)

class GenderChangeState(StatesGroup):
    choosing_gender = State()

@router.message(F.text == Texts.CHANGE_GENDER)
@router.message(Command("gender"))
async def change_gender_cmd(message: types.Message, state: FSMContext):
    await message.answer(Texts.CHOOSE_GENDER, reply_markup=gender_kb())
    await state.set_state(GenderChangeState.choosing_gender)

@router.message(GenderChangeState.choosing_gender)
async def process_gender_change(message: types.Message, db: AsyncSession, state: FSMContext, db_user: User):
    # Only accept gender buttons
    if message.text == Texts.GENDER_MALE:
        new_gender = Gender.MALE
    elif message.text == Texts.GENDER_FEMALE:
        new_gender = Gender.FEMALE
    else:
        await message.answer("❌ لطفاً یکی از گزینه‌های پسر یا دختر را از کیبورد انتخاب کنید.")
        return
    
    db_user.gender = new_gender
    await db.commit()
    
    await state.clear()
    gender_text = Texts.GENDER_MALE if new_gender == Gender.MALE else Texts.GENDER_FEMALE
    await message.answer(f"✅ جنسیت شما به {gender_text} تغییر یافت.")
    await view_profile(message, db_user)

@router.message(F.text == Texts.EDIT_BIO)
async def start_edit_bio(message: types.Message, state: FSMContext):
    await message.answer(Texts.ENTER_BIO)
    await state.set_state(ProfileStates.editing_bio)

@router.message(ProfileStates.editing_bio)
async def process_edit_bio(message: types.Message, db: AsyncSession, state: FSMContext, db_user: User):
    if len(message.text) > 100:
        await message.answer("❌ بیوگرافی بیش از حد طولانی است (حداکثر ۱۰۰ کاراکتر).")
        return
    
    db_user.bio = message.text
    await db.commit()
    
    await state.clear()
    await message.answer(Texts.BIO_UPDATED)
    await view_profile(message, db_user)

@router.message(Command("reset_link"))
async def reset_link(message: types.Message, db: AsyncSession, db_user: User):
    import uuid
    db_user.link_token = str(uuid.uuid4())[:8]
    await db.commit()
    
    await message.answer("✅ لینک ناشناس شما با موفقیت بازنشانی شد!")

@router.message(F.text == Texts.BLOCK_LIST)
async def view_block_list(message: types.Message, db: AsyncSession, db_user: User):
    from database.models import Block
    from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
    import html
    
    res = await db.execute(
        select(User)
        .join(Block, Block.blocked_id == User.id)
        .where(Block.blocker_id == db_user.id)
    )
    blocked_users = res.scalars().all()
    
    if not blocked_users:
        await message.answer(Texts.NO_BLOCKS)
        return
        
    for u in blocked_users:
        name = html.escape(u.nickname or u.display_id or f"کاربر {u.id}")
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="آنبلاک 🔓", callback_data=f"unblock_{u.id}")]
        ])
        await message.answer(f"🚫 <b>{name}</b>", reply_markup=kb, parse_mode="HTML")

@router.callback_query(F.data.startswith("unblock_"))
async def unblock_user_callback(callback: types.CallbackQuery, db: AsyncSession, db_user: User):
    from database.models import Block
    blocked_id = int(callback.data.split("_")[1])
    
    # Remove block
    res = await db.execute(
        select(Block).where(and_(Block.blocker_id == db_user.id, Block.blocked_id == blocked_id))
    )
    block_entry = res.scalar_one_or_none()
    
    if block_entry:
        await db.delete(block_entry)
        await db.commit()
        await callback.message.edit_text(callback.message.text + "\n✅ آنبلاک شد.", reply_markup=None)
        await callback.answer("کاربر آنبلاک شد.")
    else:
        await callback.answer("این کاربر در لیست سیاه نیست.", show_alert=True)
            
@router.message(F.text == "بازگشت 🔙")
async def back_to_main_from_profile(message: types.Message, db: AsyncSession, state: FSMContext):
    await state.clear()
    is_admin = await get_admin_status(message.from_user.id, db)
    await message.answer(Texts.MAIN_MENU, reply_markup=main_menu_kb(is_admin=is_admin), parse_mode="HTML")

@router.message(F.text == Texts.HELP)
async def help_cmd(message: types.Message):
    help_text = (
        "<b>📚 راهنمای ربات:</b>\n\n"
        "🔗 <b>لینک ناشناس من:</b> دریافت لینکی که می‌توانید در بیو اینستاگرام یا کانال خود بگذارید.\n\n"
        "🎲 <b>چت ناشناس:</b> وصل شدن به یک فرد ناشناس به صورت تصادفی.\n\n"
        "🚫 <b>لیست مسدودها:</b> مدیریت افرادی که بلاک کرده‌اید.\n\n"
        "👤 <b>پروفایل من:</b> مشاهده و ویرایش اطلاعات کاربری."
    )
    await message.answer(help_text, parse_mode="HTML")
