from aiogram.types import ReplyKeyboardMarkup, KeyboardButton

main = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="📅 Расписание")],
        [KeyboardButton(text="📰 Новости")],
        [KeyboardButton(text="📝 Задолженности"), KeyboardButton(text="📊 Тесты")]
    ],
    resize_keyboard=True,
    input_field_placeholder='Выберите пункт меню ниже 👇'
)

# Клавиатура для меню расписания
schedule_menu = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="👥 Расписание групп")],
        [KeyboardButton(text="👨‍🏫 Расписание преподавателей")],
        [KeyboardButton(text="⏳ График приёма задолженностей")],
        [KeyboardButton(text="🔙 Назад в меню")]
    ],
    resize_keyboard=True,
    input_field_placeholder='Выберите тип расписания 👇'
)