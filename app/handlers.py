from aiogram import Router, F
from aiogram.types import Message
from aiogram.filters import CommandStart, Command
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.context import FSMContext
import logging
import asyncio
import app.keyboards as kb
from app.state import BotState
from app.db_manager import db


router = Router()
logger = logging.getLogger(__name__)
MAX_LOGIN_ATTEMPTS = 3

class AuthStates(StatesGroup):
    waiting_for_login = State()
    waiting_for_password = State()
    authorized = State()

async def get_student_by_login(login: str):
    """Поиск студента по логину"""
    try:
        async with db.get_connection() as conn:
            async with conn.execute(
                "SELECT id_student, login, password, telegram_id FROM students WHERE login = ?",
                (login,)
            ) as cur:
                return await cur.fetchone()
    except Exception as e:
        logger.error(f"Error in get_student_by_login: {e}")
        return None

async def update_telegram_for_student(id_student: int, telegram_id: int) -> bool:
    """Привязывает Telegram ID к студенту"""
    try:
        async with db.get_connection() as conn:
            # Явно начинаем транзакцию
            await conn.execute("BEGIN")
            try:
                # 1. Сначала отвязываем от других пользователей
                await conn.execute(
                    "UPDATE students SET telegram_id = NULL WHERE telegram_id = ?",
                    (telegram_id,)
                )
                
                # 2. Привязываем к текущему студенту
                await conn.execute(
                    "UPDATE students SET telegram_id = ? WHERE id_student = ?",
                    (telegram_id, id_student)
                )
                
                await conn.commit()
                return True
            except Exception as e:
                await conn.rollback()
                logger.error(f"Transaction failed: {e}")
                return False
    except Exception as e:
        logger.error(f"Database error: {e}")
        return False

async def get_student_by_telegram(telegram_id):
    try:
        async with db.get_connection() as conn:
            async with conn.execute(
                "SELECT id_student, login FROM students WHERE telegram_id = ?", 
                (telegram_id,)
            ) as cur:
                return await cur.fetchone()
    except Exception as e:
        logger.error(f"Database error in get_student_by_telegram: {e}")
        return None

async def remove_telegram_binding(telegram_id: int) -> bool:
    """Отвязывает Telegram ID от студента"""
    try:
        async with db.get_connection() as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    "UPDATE students SET telegram_id = NULL WHERE telegram_id = ?",
                    (telegram_id,)
                )
                await conn.commit()
                return cur.rowcount > 0
    except Exception as e:
        logger.error(f"Error in remove_telegram_binding: {e}")
        return False

@router.message(CommandStart())
async def start(message: Message, state: FSMContext):
    student = await get_student_by_telegram(message.from_user.id)
    if student:
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
        # Устанавливаем новое состояние
        await state.set_state(AuthStates.authorized)
        await state.update_data(is_admin=True)
        await message.answer("Добро пожаловать, администратор!", reply_markup=kb.main)
        return

    student = await get_student_by_login(login)
    if student and str(student[2]) == password:
        if await get_student_by_telegram(message.from_user.id):
            await message.answer('Вы уже привязаны к профилю. Для отвязки используйте /unbind')
            await state.clear()
            return
        try:
            async with db.get_connection() as conn:
                await conn.execute("BEGIN")
                # Отвязываем от других пользователей
                await conn.execute(
                    "UPDATE students SET telegram_id = NULL WHERE telegram_id = ?",
                    (message.from_user.id,))
                # Привязываем к текущему
                await conn.execute(
                    "UPDATE students SET telegram_id = ? WHERE id_student = ?",
                    (message.from_user.id, student[0]))
                await conn.commit()
                
            await message.answer('Вы успешно авторизованы!', reply_markup=kb.main)
            await state.set_state(AuthStates.authorized)
            await state.update_data(is_admin=False)
        except Exception as e:
            logger.error(f"Ошибка привязки: {e}")
            await message.answer('Ошибка привязки. Попробуйте позже.')
            await state.clear()

    else:
        await message.answer('Неверный логин или пароль. Попробуйте снова.\nЛогин:')
        await state.set_state(AuthStates.waiting_for_login)
        await state.clear()
    return

@router.message(Command("unbind"))
async def unbind(message: Message, state: FSMContext):
    if await remove_telegram_binding(message.from_user.id):
        await message.answer("Ваш Telegram был отвязан. Для повторной регистрации используйте /start")
        await state.clear()
    else:
        await message.answer("Ваш профиль не найден либо был уже отвязан.")

@router.message(Command("logout"))
async def logout(message: Message, state: FSMContext):
    try:
        # Очищаем состояние
        await state.clear()
        
        await message.answer("Вы успешно вышли. Для входа используйте /start")
    except Exception as e:
        logger.error(f"Ошибка выхода: {e}")

@router.message(AuthStates.authorized, F.text)
async def main_menu(message: Message, state: FSMContext):
    data = await state.get_data()
    if data.get("is_admin"):
        await message.answer("Меню администратора.\n(Здесь добавьте свои команды админа.)", reply_markup=kb.main)
    else:
        await message.answer("Вы в главном меню.", reply_markup=kb.main)

@router.message(F.text == "Новости")
async def show_news(message: Message):
    async with db.get_connection() as db:
        try:
            async with db.execute("SELECT title, description, date, place FROM news ORDER BY date DESC") as cur:
                all_news = await cur.fetchall()
            
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
        except Exception as e:
            logger.error(f"Error fetching news: {e}")
            await message.answer("Произошла ошибка при получении новостей.")