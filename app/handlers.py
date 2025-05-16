from aiogram import Router, F
from aiogram.types import Message
from aiogram.filters import CommandStart, Command
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.context import FSMContext
import logging
import aiosqlite
import asyncio
import atexit
import app.keyboards as kb
from app.state import BotState

db_connection = None

router = Router()
logger = logging.getLogger(__name__)
DB_PATH = "student_bot.db"


class AuthStates(StatesGroup):
    waiting_for_login = State()
    waiting_for_password = State()
    authorized = State()

async def init_db():
    global db_connection
    try:
        if db_connection is None or (not db_connection._running and not db_connection._connection):
            db_connection = await aiosqlite.connect(DB_PATH)
            await db_connection.execute("PRAGMA journal_mode=WAL")
            await db_connection.execute("PRAGMA synchronous=NORMAL")
            await db_connection.execute("PRAGMA busy_timeout=30000")
            await db_connection.execute("PRAGMA cache_size=-10000")
            await db_connection.execute("PRAGMA foreign_keys=ON")
            logger.info("Database connection initialized with WAL mode")
        return db_connection
    except Exception as e:
        logger.error(f"Error initializing database: {e}")
        # Попробуем переподключиться через 5 секунд
        await asyncio.sleep(5)
        return await init_db()

async def close_db():
    global db_connection
    if db_connection is not None:
        await db_connection.close()
        db_connection = None
        logger.info("Database connection closed")
atexit.register(lambda: asyncio.get_event_loop().run_until_complete(close_db()))


async def get_student_by_login(login):
    db = await init_db()
    try:
        async with db.execute(
            "SELECT id_student, login, password, telegram_id FROM students WHERE login = ?", 
            (login,)
        ) as cur:
            return await cur.fetchone()
    except aiosqlite.Error as e:
        logger.error(f"Database error in get_student_by_login: {e}")
        return None

async def update_telegram_for_student(id_student, telegram_id):
    db = await init_db()
    try:
        async with db:
            # Сначала отвяжем Telegram у других пользователей
            await db.execute(
                "UPDATE students SET telegram_id = NULL WHERE telegram_id = ?", 
                (telegram_id,)
            )
            await db.execute(
                "UPDATE students SET telegram_id = ? WHERE id_student = ?", 
                (telegram_id, id_student)
            )
            await db.commit()
            
            # Проверяем обновление
            async with db.execute(
                "SELECT telegram_id FROM students WHERE id_student = ?", 
                (id_student,)
            ) as cur:
                updated = await cur.fetchone()
            return updated is not None and updated[0] == telegram_id
    except aiosqlite.Error as e:
        logger.error(f"Database error in update_telegram_for_student: {e}")
        return False

async def get_student_by_telegram(telegram_id):
    db = await init_db()
    try:
        async with db.execute(
            "SELECT id_student, login FROM students WHERE telegram_id = ?", 
            (telegram_id,)
        ) as cur:
            return await cur.fetchone()
    except aiosqlite.Error as e:
        logger.error(f"Database error in get_student_by_telegram: {e}")
        return None

async def remove_telegram_binding(telegram_id):
    db = await init_db()
    try:
        async with db:
            cur = await db.execute(
                "UPDATE students SET telegram_id = NULL WHERE telegram_id = ?", 
                (telegram_id,)
            )
            await db.commit()
            return cur.rowcount > 0
    except aiosqlite.Error as e:
        logger.error(f"Database error in remove_telegram_binding: {e}")
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
        await state.clear()
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
        updated = await update_telegram_for_student(student[0], message.from_user.id)
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
    async with aiosqlite.connect(DB_PATH) as db:
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