from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

def gender_pref_kb():
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="پسر 👦", callback_data="match_pref_male"),
                InlineKeyboardButton(text="دختر 👧", callback_data="match_pref_female")
            ],
            [
                InlineKeyboardButton(text="فرقی ندارد 👫", callback_data="match_pref_any")
            ]
        ]
    )
