from aiogram import Router, F
from aiogram.types import Message
from aiogram.filters import CommandStart, Command
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.context import FSMContext
import logging
import sqlite3

import app.keyboards as kb

router = Router()
logger = logging.getLogger(__name__)

DB_PATH = "student_bot.db"

class AuthStates(StatesGroup):
    waiting_for_login = State()
    waiting_for_password = State()
    authorized = State()

def get_student_by_login(login):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("SELECT id_student, login, password, telegram_id FROM students WHERE login = ?", (login,))
    result = cur.fetchone()
    conn.close()
    return result

def update_telegram_for_student(id_student, telegram_id):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    # Проверяем, что этот телеграм нигде больше не привязан
    cur.execute("UPDATE students SET telegram_id = NULL WHERE telegram_id = ?", (telegram_id,))
    cur.execute("UPDATE students SET telegram_id = ? WHERE id_student = ?", (telegram_id, id_student))
    conn.commit()
    affected = cur.rowcount
    conn.close()
    return affected > 0

def get_student_by_telegram(telegram_id):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("SELECT id_student, login FROM students WHERE telegram_id = ?", (telegram_id,))
    result = cur.fetchone()
    conn.close()
    return result

def remove_telegram_binding(telegram_id):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("UPDATE students SET telegram_id = NULL WHERE telegram_id = ?", (telegram_id,))
    conn.commit()
    affected = cur.rowcount
    conn.close()
    return affected > 0

@router.message(CommandStart())
async def start(message: Message, state: FSMContext):
    # сначала проверим, привязан ли уже Telegram к записи
    if get_student_by_telegram(message.from_user.id):
        await message.answer("Вы уже привязаны к своему профилю. Для отвязки используйте /unbind")
        return
    await message.answer("Добро пожаловать! Введите ваш логин:")
    await state.set_state(AuthStates.waiting_for_login)

@router.message(AuthStates.waiting_for_login)
async def process_login(message: Message, state: FSMContext):
    login = message.text.strip()
    await state.update_data(login=login)
    await message.answer('Введите ваш пароль:')
    await state.set_state(AuthStates.waiting_for_password)

@router.message(AuthStates.waiting_for_password)
async def process_password(message: Message, state: FSMContext):
    password = message.text.strip()
    data = await state.get_data()
    login = data.get("login")

    # обработка режима администратора
    if login == 'admin' and password == 'admin':
        await message.answer("Добро пожаловать, администратор!", reply_markup=kb.main)
        await state.set_state(AuthStates.authorized)
        await state.update_data(is_admin=True)
        return

    student = get_student_by_login(login)
    if student and str(student[2]) == password:
        # Если уже привязан к другой учётке — запретить
        if get_student_by_telegram(message.from_user.id):
            await message.answer('Вы уже привязаны к профилю. Для отвязки используйте /unbind')
            await state.clear()
            return
        updated = update_telegram_for_student(student[0], message.from_user.id)
        if updated:
            await message.answer('Вы успешно авторизованы и привязаны к своей записи.', reply_markup=kb.main)
            await state.set_state(AuthStates.authorized)
            await state.update_data(is_admin=False)
        else:
            await message.answer('Ошибка привязки. Повторите попытку.')
            await state.set_state(AuthStates.waiting_for_login)
    else:
        await message.answer('Неверный логин или пароль. Попробуйте снова.\nЛогин:')
        await state.set_state(AuthStates.waiting_for_login)

@router.message(Command("unbind"))
async def unbind(message: Message, state: FSMContext):
    # только если реально был привязан
    if remove_telegram_binding(message.from_user.id):
        await message.answer("Ваш Telegram был отвязан. Для повторной регистрации используйте /start")
        await state.clear()
    else:
        await message.answer("Ваш профиль не найден либо был уже отвязан.")

@router.message(Command("logout"))
async def logout(message: Message, state: FSMContext):
    # выход из системы без отвязки Telegram
    await state.clear()
    await message.answer("Вы вышли из сессии. Для повторного входа: /start")

# обработка остальных сообщений после авторизации
@router.message(AuthStates.authorized, F.text)
async def main_menu(message: Message, state: FSMContext):
    data = await state.get_data()
    if data.get("is_admin"):
        await message.answer("Меню администратора.\n(Здесь добавьте свои команды админа.)", reply_markup=kb.main)
    else:
        await message.answer("Вы в главном меню.", reply_markup=kb.main)


@router.message(F.text == "Новости")
async def show_news(message: Message):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("SELECT title, description, date, place FROM news ORDER BY date DESC")
    all_news = cur.fetchall()
    conn.close()
    if not all_news:
        await message.answer("Новостей пока нет.")
        return

    text = ""
    for news in all_news:
        title, description, date, place = news
        text += f"<b>{title}</b>\n{description or ''}\nДата: {date}"
        if place:
            text += f"\nМесто: {place}"
        text += "\n\n"
    await message.answer(text.strip(), parse_mode="HTML")