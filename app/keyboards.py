# keyboard.py
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton

# Главное меню
main = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="📅 Расписание")],
        [KeyboardButton(text="📝 Задолженности"), KeyboardButton(text="📊 Тесты")],
        [KeyboardButton(text="📰 Новости")],
    ], resize_keyboard=True
)

# Меню админки
admin_kb = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="📰 Управление новостями")],
        [KeyboardButton(text="📚 Управление предметами"), KeyboardButton(text="👨‍🏫 Управление преподавателями")],
        [KeyboardButton(text="📊 Управление тестами"), KeyboardButton(text="⏳ Управление долгами")],
        [KeyboardButton(text="👥 Управление пользователями")]
    ], resize_keyboard=True
)

# Админ новости
news_admin_kb = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="📋 Список новостей")], 
        [KeyboardButton(text="📝 Добавить новость"), KeyboardButton(text="📢 Опубликовать новость")],
        [KeyboardButton(text="❌ Удалить новость"), KeyboardButton(text="🔙 Назад в админку")]
    ], resize_keyboard=True
)

# Админ студенты
students_admin_kb = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="📋 Список студентов")],
        [KeyboardButton(text="👤 Добавить студента"), KeyboardButton(text="✏️ Редактировать студента")],
        [KeyboardButton(text="🔗 Отвязать пользователя"), KeyboardButton(text="❌ Удалить студента")],
        [KeyboardButton(text="🔙 Назад в админку")]
    ], resize_keyboard=True
)

# Админ тесты
tests_admin_kb = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="📋 Список тестов"), KeyboardButton(text="📝 Добавить тест")],
        [KeyboardButton(text="❌ Удалить"), KeyboardButton(text="🔙 Назад в админку")]
    ], resize_keyboard=True
)

# Админ предметы
subjects_admin_kb = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="📋 Список предметов")], 
        [KeyboardButton(text="📝 Добавить предмет"), KeyboardButton(text="✏️ Редактировать предмет")],
        [KeyboardButton(text="❌ Удалить предмет"), KeyboardButton(text="🔙 Назад в админку")]

    ], resize_keyboard=True
)

# Админ преподаватели
teachers_admin_kb = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="📋 Список преподавателя")],
        [KeyboardButton(text="📝 Добавить преподавателя"), KeyboardButton(text="✏️ Редактировать преподавателя")],
        [KeyboardButton(text="❌ Удалить преподавателя"), KeyboardButton(text="🔙 Назад в админку")]
    ], resize_keyboard=True
)

# Админ долги
debts_admin_kb = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="📋 Список долгов")], 
        [KeyboardButton(text="📝 Добавить долг"),KeyboardButton(text="✏️ Редактировать долг") ],
        [KeyboardButton(text="❌ Удалить долг"), KeyboardButton(text="🔙 Назад в админку")]
    ], resize_keyboard=True
)

# Редактирование студента
edit_student_kb = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="👤 Логин"), KeyboardButton(text="🔗 Пароль")],
        [KeyboardButton(text="👥 Группа"), KeyboardButton(text="⏳ Статус")],
        [KeyboardButton(text="ℹ️ Описание")],
        [KeyboardButton(text="✅ Сохранить"), KeyboardButton(text="❌ Отмена")]
    ], resize_keyboard=True
)

# Меню расписания
schedule_menu = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="👥 Расписание групп")],
        [KeyboardButton(text="👨‍🏫 Расписание преподавателей")],
        [KeyboardButton(text="⏳ График приёма задолженностей")],
        [KeyboardButton(text="🔙 В главное меню")]
    ], resize_keyboard=True
    
)

cancel_kb = ReplyKeyboardMarkup(
    keyboard=[[KeyboardButton(text="❌ Отмена")]],
    resize_keyboard=True
)