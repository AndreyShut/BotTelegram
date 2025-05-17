from aiogram import Router, F, types
from aiogram.types import Message
from aiogram.filters import CommandStart, Command
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.context import FSMContext
import logging
import app.keyboards as kb
from app.db_manager import db
from dotenv import load_dotenv
import os

load_dotenv()

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
    """Отвязывает Telegram ID от студента с обработкой зависимых записей"""
    try:
        async with db.get_connection() as conn:
            await conn.execute("BEGIN")
            
            # 1. Удаляем зависимые записи из sent_notifications
            await conn.execute(
                "DELETE FROM sent_notifications WHERE user_id = ?",
                (telegram_id,)
            )
            
            # 2. Отвязываем Telegram ID
            await conn.execute(
                "UPDATE students SET telegram_id = NULL WHERE telegram_id = ?",
                (telegram_id,)
            )
            
            await conn.commit()
            return True
            
    except Exception as e:
        logger.error(f"Error in remove_telegram_binding: {e}")
        if conn:
            await conn.rollback()
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
    if login == os.getenv("ADMIN_LOGIN") and password == os.getenv("ADMIN_PASSWORD"):
        # Устанавливаем новое состояние
        await state.set_state(AuthStates.authorized)
        await state.update_data(is_admin=True)
        await message.answer("Добро пожаловать, администратор!", reply_markup=kb.main)
        return

    student = await get_student_by_login(login)
    if student and await db.verify_password(str(student[2]), password):
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


@router.message(F.text == "📰 Новости")
async def show_news(message: Message):
    try:
        # Получаем студента
        student = await get_student_by_telegram(message.from_user.id)
        if not student:
            await message.answer("Сначала авторизуйтесь с помощью /start")
            return

        async with db.get_connection() as conn:
            # Получаем новости для студента (все или только для его группы)
            async with conn.execute('''
                SELECT n.id, n.title, n.description, n.date, n.place 
                FROM news n
                LEFT JOIN news_groups ng ON n.id = ng.news_id
                WHERE n.is_published = 1
                AND (n.for_all_groups = 1 OR ng.group_id = (
                    SELECT id_group FROM students WHERE id_student = ?
                ))
                ORDER BY n.date DESC
                LIMIT 10
            ''', (student[0],)) as cursor:
                news_items = await cursor.fetchall()

            if not news_items:
                await message.answer("Новостей пока нет.")
                return

            response = "📰 Последние новости:\n\n"
            for news in news_items:
                news_id, title, description, date, place = news
                response += (
                    f"📌 <b>{title}</b>\n"
                    f"📅 {date}\n"
                )
                if place:
                    response += f"📍 {place}\n"
                response += f"\n{description}\n\n"
                response += "――――――――――――――――――――\n\n"

            await message.answer(response, parse_mode="HTML")

    except Exception as e:
        logger.error(f"Error fetching news: {e}")
        await message.answer("Произошла ошибка при получении новостей.")


@router.message(F.text == "📊 Тесты")
async def show_tests(message: Message):
    try:
        # Получаем студента
        student = await get_student_by_telegram(message.from_user.id)
        if not student:
            await message.answer("Сначала авторизуйтесь с помощью /start")
            return

        async with db.get_connection() as conn:
            # Получаем тесты для группы студента
            async with conn.execute('''
                SELECT t.date, s.name, t.test_link, te.full_name 
                FROM tests t
                JOIN subjects s ON t.subject_id = s.id
                JOIN teachers te ON t.teacher_id = te.id
                WHERE t.group_id = (
                    SELECT id_group FROM students WHERE id_student = ?
                )
                ORDER BY t.date
            ''', (student[0],)) as cursor:
                tests = await cursor.fetchall()

            if not tests:
                await message.answer("У вас нет назначенных тестов.")
                return

            response = "📝 Ваши тесты:\n\n"
            for test in tests:
                date, subject, link, teacher = test
                response += (
                    f"📌 <b>{subject}</b>\n"
                    f"👨‍🏫 Преподаватель: {teacher}\n"
                    f"📅 Дата: {date}\n"
                    f"🔗 Ссылка: {link}\n\n"
                )

            await message.answer(response, parse_mode="HTML")

    except Exception as e:
        logger.error(f"Error fetching tests: {e}")
        await message.answer("Произошла ошибка при получении списка тестов.")


@router.message(F.text == "📝 Задолженности")
async def show_debts(message: Message):
    try:
        # Получаем студента
        student = await get_student_by_telegram(message.from_user.id)
        if not student:
            await message.answer("Сначала авторизуйтесь с помощью /start")
            return

        async with db.get_connection() as conn:
            # Получаем долги студента
            async with conn.execute('''
                SELECT s.name, dt.name, sd.last_date 
                FROM student_debts sd
                JOIN subjects s ON sd.subject_id = s.id
                JOIN debt_types dt ON sd.debt_type_id = dt.id
                WHERE sd.student_id = ?
                ORDER BY sd.last_date
            ''', (student[0],)) as cursor:
                debts = await cursor.fetchall()

            if not debts:
                await message.answer("У вас нет академических долгов.")
                return

            response = "📝 Ваши долги:\n\n"
            for debt in debts:
                subject, debt_type, last_date = debt
                response += (
                    f"📌 <b>{subject}</b>\n"
                    f"🔴 Тип долга: {debt_type}\n"
                    f"📅 Крайний срок: {last_date}\n\n"
                )

            await message.answer(response, parse_mode="HTML")

    except Exception as e:
        logger.error(f"Error fetching debts: {e}")
        await message.answer("Произошла ошибка при получении списка долгов.")




@router.message(F.text == "📅 Расписание")
async def schedule_handler(message: Message):
    await message.answer("Выберите тип расписания:", reply_markup=kb.schedule_menu)

@router.message(F.text == "👥 Расписание групп")
async def send_group_schedule(message: Message):
    file_path = "Расписание_групп.xlsx"
    if os.path.exists(file_path):
        with open(file_path, 'rb') as file:
            await message.answer_document(types.BufferedInputFile(file.read(), filename=file_path), 
                                        reply_markup=kb.schedule_menu)
    else:
        await message.answer("Файл с расписанием групп не найден.", reply_markup=kb.schedule_menu)

@router.message(F.text == "👨‍🏫 Расписание преподавателей")
async def send_teacher_schedule(message: Message):
    file_path = "Расписание_преподавателей.xls"
    if os.path.exists(file_path):
        with open(file_path, 'rb') as file:
            await message.answer_document(types.BufferedInputFile(file.read(), filename=file_path),
                                        reply_markup=kb.schedule_menu)
    else:
        await message.answer("Файл с расписанием преподавателей не найден.", reply_markup=kb.schedule_menu)

@router.message(F.text == "⏳ График приёма задолженностей")
async def send_debt_schedule(message: Message):
    file_path = "График_задолженностей.xlsx"
    if os.path.exists(file_path):
        with open(file_path, 'rb') as file:
            await message.answer_document(types.BufferedInputFile(file.read(), filename=file_path),
                                        reply_markup=kb.schedule_menu)
    else:
        await message.answer("Файл с графиком задолженностей не найден.", reply_markup=kb.schedule_menu)

@router.message(F.text == "🔙 Назад в меню")
async def back_to_main_menu(message: Message):
    await message.answer("Главное меню:", reply_markup=kb.main)