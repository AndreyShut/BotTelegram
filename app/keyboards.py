from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton

main = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text='Расписание')],
        [KeyboardButton(text='Новости')],
        [KeyboardButton(text='Задолженности'), KeyboardButton(text='Тесты')]
    ],
    resize_keyboard=True,
    input_field_placeholder='Выберите пункт меню...'
)


