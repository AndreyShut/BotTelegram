from aiogram import Router, F, types
from aiogram.types import Message, FSInputFile
from aiogram.filters import CommandStart, Command, StateFilter
from aiogram.fsm.state import State, StatesGroup, default_state, any_state
from aiogram.fsm.context import FSMContext
from aiogram.exceptions import TelegramBadRequest
import logging
import app.keyboards as kb
from app.db_manager import db,pm
from dotenv import load_dotenv
import os
from typing import Optional, Tuple, List
from datetime import datetime

load_dotenv()

router = Router()
logger = logging.getLogger(__name__)
MAX_LOGIN_ATTEMPTS = 3

class AuthStates(StatesGroup):
    waiting_for_login = State()
    waiting_for_password = State()
    authorized = State()
    admin_mode = State()
    user_mode = State()
    add_news_title = State()
    add_news_description = State()
    add_news_date = State()
    add_news_place = State()
    add_news_groups = State()
    delete_news = State()
    publish_news = State()
    unbind_user_select = State()
    unbind_all_confirm = State()
    add_student = State()
    edit_student = State()
    delete_student = State()

class StudentRegisterState(StatesGroup):
    waiting_login = State()
    waiting_password = State()
    waiting_group = State()
    waiting_description = State()
add_states = StudentRegisterState

class AddTestStates(StatesGroup):
    waiting_group = State()
    waiting_subject = State()
    waiting_teacher = State()
    waiting_link = State()
    waiting_date = State()
    waiting_test_delete = State()      
    confirm_test_delete = State() 
add_test = AddTestStates

class EditStudentFSM(StatesGroup):
    waiting_id = State()
    main_menu = State()
    waiting_field = State()
    editing_login = State()
    editing_password = State()
    editing_group = State()
    editing_status = State()
    editing_description = State()
    confirm = State()
edit_st = EditStudentFSM

class SubjectFSM(StatesGroup):
    choose_action = State()
    wait_name = State()
    wait_id = State()
    wait_edit_new_name = State()
    

class TeacherFSM(StatesGroup):
    choose_action = State()
    wait_name = State()
    wait_id = State()
    wait_new_name = State()

class DebtFSM(StatesGroup):
    choose_action = State()
    wait_student = State()
    wait_add_disc = State()
    wait_add_type = State()
    wait_add_date = State()
    wait_del = State()
    wait_edit_id = State()
    wait_edit_field = State()
    wait_edit_value = State()

class NewsGroupsFSM(StatesGroup):
    waiting_for_group_ids = State()

# ==================== ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ====================
async def get_student_by_login(login: str) -> Optional[Tuple]:
    """Поиск студента по логину"""
    try:
        async with db.get_connection() as conn:
            async with conn.execute(
                "SELECT id_student, login, password, telegram_id, is_active FROM students WHERE login = ?",
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
            await conn.execute("BEGIN")
            try:
                await conn.execute(
                    "UPDATE students SET telegram_id = NULL WHERE telegram_id = ?",
                    (telegram_id,))
                await conn.execute(
                    "UPDATE students SET telegram_id = ?, is_active = 1 WHERE id_student = ?",
                    (telegram_id, id_student))
                await conn.commit()
                return True
            except Exception as e:
                await conn.rollback()
                logger.error(f"Transaction failed: {e}")
                return False
    except Exception as e:
        logger.error(f"Database error: {e}")
        return False

async def get_student_by_telegram(telegram_id: int) -> Optional[Tuple]:
    try:
        async with db.get_connection() as conn:
            async with conn.execute(
                "SELECT id_student, login, is_active FROM students WHERE telegram_id = ?", 
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
            await conn.execute("BEGIN")
            await conn.execute(
                "DELETE FROM sent_notifications WHERE user_id = ?",
                (telegram_id,))
            await conn.execute(
                "UPDATE students SET telegram_id = NULL, is_active = 0 WHERE telegram_id = ?",
                (telegram_id,))
            await conn.commit()
            return True
    except Exception as e:
        logger.error(f"Error in remove_telegram_binding: {e}")
        if conn:
            await conn.rollback()
        return False

async def is_admin(telegram_id: int) -> bool:
    """Проверяет, является ли пользователь администратором"""
    try:
        async with db.get_connection() as conn:
            async with conn.execute(
                "SELECT telegram_id FROM students WHERE login = ? AND telegram_id = ?",
                (os.getenv("ADMIN_LOGIN"), telegram_id)
            ) as cur:
                return await cur.fetchone() is not None
    except Exception as e:
        logger.error(f"Error checking admin status: {e}")
        return False
    

async def safe_send_message(message: Message, text: str, **kwargs):
    """
    Безопасная отправка сообщения с автоматическим разбиением на части,
    если текст слишком длинный
    """
    MAX_LENGTH = 4096  # Максимальная длина сообщения в Telegram
    
    try:
        if len(text) <= MAX_LENGTH:
            await message.answer(text, **kwargs)
        else:
            # Разбиваем текст на части
            parts = []
            while text:
                if len(text) > MAX_LENGTH:
                    part = text[:MAX_LENGTH]
                    # Пытаемся разбить по последнему переносу строки
                    last_newline = part.rfind('\n')
                    if last_newline > 0:
                        part = part[:last_newline]
                    parts.append(part)
                    text = text[len(part):].lstrip('\n')
                else:
                    parts.append(text)
                    text = ''
            
            # Отправляем части по очереди
            for part in parts:
                await message.answer(part, **kwargs)
    except TelegramBadRequest as e:
        logger.error(f"Ошибка отправки сообщения: {e}")
        await message.answer("❌ Не удалось отправить сообщение")



async def cleanup_deleted_records():
    try:
        async with db.get_connection() as conn:
            # Удаляем записи из всех таблиц с soft delete
            tables = [
                "tests", "student_debts", 
            ]
            
            for table in tables:
                    await conn.execute(f"DELETE FROM {table} WHERE deleted_at NOT NULL")
            await conn.commit()
        return True
    except Exception as e:
        logger.error(f"Error cleaning up deleted records: {e}")
        return False


# ==================== ОБРАБОТЧИКИ ОТМЕНЫ ====================
async def cancel_command(message: Message, state: FSMContext):
    current_state = await state.get_state()
    data = await state.get_data()
    if current_state is None:
        await message.answer("❌ Нет активной команды для отмены")
        return
    if data.get("is_admin"):
        await message.answer("❌ Действие отменено", reply_markup=kb.admin_kb)
        await state.set_state(AuthStates.admin_mode)
    else:
        await message.answer("❌ Действие отменено", reply_markup=kb.main)
        await state.set_state(AuthStates.authorized)

def add_cancel_to_states(cls):
    for st in cls.__states__:
        router.message(st, Command("cancel"))(cancel_command)
        router.message(st, lambda m: m.text and m.text.lower() in ("отмена", "/отмена"))(cancel_command)
    return cls
add_cancel_to_states(AuthStates)
add_cancel_to_states(StudentRegisterState)
add_cancel_to_states(AddTestStates)
add_cancel_to_states(EditStudentFSM)
add_cancel_to_states(SubjectFSM)
add_cancel_to_states(TeacherFSM)
add_cancel_to_states(DebtFSM)
add_cancel_to_states(NewsGroupsFSM)

# ==================== КОМАНДЫ АУТЕНТИФИКАЦИИ ====================
@router.message(CommandStart())
async def start(message: Message, state: FSMContext):
    student = await get_student_by_telegram(message.from_user.id)
    if student:
        if await is_admin(message.from_user.id):
            await message.answer("🔐 Вы авторизованы как администратор", reply_markup=kb.admin_kb)
            await state.set_state(AuthStates.admin_mode)
        else:
            await message.answer("🔗 Вы уже привязаны к профилю", reply_markup=kb.main)
            await state.set_state(AuthStates.authorized)
        return
    await message.answer("🚪Добро пожаловать! Введите ваш логин:")
    await state.set_state(AuthStates.waiting_for_login)

@router.message(AuthStates.waiting_for_login)
async def process_login(message: Message, state: FSMContext):
    login = message.text.strip()
    await state.update_data(login=login)
    await message.answer('🔐 Введите ваш пароль:')
    await state.set_state(AuthStates.waiting_for_password)

@router.message(AuthStates.waiting_for_password)
async def process_password(message: Message, state: FSMContext):
    password = message.text.strip()
    data = await state.get_data()
    login = data.get("login")

    # Проверка администратора
    if login == os.getenv("ADMIN_LOGIN") and password == os.getenv("ADMIN_PASSWORD"):
        await state.update_data(is_admin=True)
        
        # Привязываем Telegram ID к администратору
        async with db.get_connection() as conn:
            await conn.execute("BEGIN")
            await conn.execute(
                "UPDATE students SET telegram_id = NULL WHERE telegram_id = ?",
                (message.from_user.id,))
            await conn.execute(
                "UPDATE students SET telegram_id = ? WHERE login = ?",
                (message.from_user.id, login))
            await conn.commit()
        
        await message.answer("🔐 Добро пожаловать, администратор!", reply_markup=kb.admin_kb)
        await state.set_state(AuthStates.admin_mode)
        return

    student = await get_student_by_login(login)
    if student and await pm.verify_password(student[2], password):
        if not student[4]:  # is_active
            await message.answer("❌ Ваш аккаунт деактивирован. Обратитесь к администратору")
            await state.clear()
            return
            
        if await get_student_by_telegram(message.from_user.id):
            await message.answer('🔗 Вы уже привязаны к профилю. Для отвязки используйте /unbind')
            await state.clear()
            return
            
        if await update_telegram_for_student(student[0], message.from_user.id):
            await message.answer('✅ Вы успешно авторизованы!', reply_markup=kb.main)
            await state.set_state(AuthStates.authorized)
            await state.update_data(is_admin=False)
        else:
            await message.answer('❌ Ошибка привязки. Попробуйте позже')
            await state.clear()
    else:
        await message.answer('❌ Неверный логин или пароль. Попробуйте снова.\n\nЛогин:')
        await state.set_state(AuthStates.waiting_for_login)

@router.message(Command("unbind"))
async def unbind(message: Message, state: FSMContext):
    if await remove_telegram_binding(message.from_user.id):
        await message.answer("❌ Ваш Telegram был отвязан. Для входа используйте /start")
        await state.clear()
    else:
        await message.answer("❌ Ваш профиль не найден либо был уже отвязан")

@router.message(Command("logout"))
async def logout(message: Message, state: FSMContext):
    try:
        async with db.get_connection() as conn:
            await conn.execute(
                "UPDATE students SET is_active = 0 WHERE telegram_id = ?",
                (message.from_user.id,))
            await conn.commit()
    except Exception as e:
        logger.error(f"Error marking user inactive: {e}")
    
    await state.clear()
    await message.answer("✅ Вы успешно вышли. Для входа используйте /start", 
                       reply_markup=types.ReplyKeyboardRemove())

# ==================== ОБЩИЕ КОМАНДЫ ====================
@router.message(F.text == "🔙 Назад в меню")
async def back_to_main_menu(message: Message, state: FSMContext):
    data = await state.get_data()
    if data.get("is_admin"):
        await message.answer("🔐 Административное меню:", reply_markup=kb.admin_kb)
        await state.set_state(AuthStates.admin_mode)
    else:
        await message.answer("ℹ️ Главное меню:", reply_markup=kb.main)
        await state.set_state(AuthStates.authorized)

@router.message(F.text == "🔙 Назад в административное меню")
async def back_to_admin_menu(message: Message, state: FSMContext):
    await message.answer("🔐 Административное меню:", reply_markup=kb.admin_kb)
    await state.set_state(AuthStates.admin_mode)

@router.message(F.text == "🔙 Назад в админку")
async def back_to_root_menu(message: Message, state: FSMContext):
    data = await state.get_data()
    if data.get("is_admin"):
        await message.answer("🔐 Административное меню:", reply_markup=kb.admin_kb)
        await state.set_state(AuthStates.admin_mode)
    else:
        await message.answer("ℹ️ Главное меню:", reply_markup=kb.main)
        await state.set_state(AuthStates.authorized)

# ==================== КОМАНДЫ ПОЛЬЗОВАТЕЛЯ ====================
@router.message(F.text == "📅 Расписание")
async def show_schedule(message: Message):
    await message.answer("📋 Выберите тип расписания:", reply_markup=kb.schedule_menu)

@router.message(F.text == "👥 Расписание групп")
async def show_group_schedule(message: Message):
    file_path = "Расписание_групп.xlsx"
    if os.path.exists(file_path):
        await message.answer_document(FSInputFile(file_path), caption="👥 Актуальное расписание групп")
    else:
        await message.answer("❌ Файл расписания групп не найден, попробуйте позже")

@router.message(F.text == "👨‍🏫 Расписание преподавателей")
async def show_teacher_schedule(message: Message):
    file_path = "Расписание_преподавателей.xls"
    if os.path.exists(file_path):
        await message.answer_document(FSInputFile(file_path), caption="👨‍🏫 Актуальное расписание преподавателей")
    else:
        await message.answer("❌ Файл расписания преподавателей не найден, попробуйте позже")

@router.message(F.text == "⏳ График приёма задолженностей")
async def show_debts_schedule(message: Message):
    file_path = "График_задолженностей.xlsx"
    if os.path.exists(file_path):
        await message.answer_document(FSInputFile(file_path), caption="⏳ График приёма задолженностей")
    else:
        await message.answer("❌ Файл графика задолженностей не найден, попробуйте позже")

@router.message(F.text == "📝 Задолженности")
async def show_debts(message: Message):
    student = await get_student_by_telegram(message.from_user.id)
    if not student:
        await message.answer("❌ Сначала авторизуйтесь через /start", reply_markup=kb.main)
        return

    try:
        async with db.get_connection() as conn:
            async with conn.execute('''
                SELECT subj.name, dt.name, sd.last_date
                FROM student_debts sd
                JOIN disciplines d ON sd.discipline_id = d.id
                JOIN subjects subj ON d.subject_id = subj.id
                JOIN debt_types dt ON sd.debt_type_id = dt.id
                WHERE sd.student_id = ? AND sd.deleted_at IS NULL
                ORDER BY sd.last_date
            ''', (student[0],)) as cursor:
                debts = await cursor.fetchall()

        if not debts:
            await message.answer("🎉 У вас нет академических задолженностей")
            return

        response = "📝 Ваши задолженности:\n\n"
        for subj_name, debt_type, last_date in debts:
            response += (
                f"📚 {subj_name}\n"
                f"🔴 {debt_type}\n"
                f"⏳ Крайний срок: {last_date}\n"
                "----------\n"
            )
        await safe_send_message(message, response, parse_mode="HTML")
        

    except Exception as e:
        logger.error(f"Error fetching debts: {e}")
        await message.answer("❌ Ошибка получения информации о задолженностях")

@router.message(F.text == "📊 Тесты")
async def show_tests(message: Message):
    student = await get_student_by_telegram(message.from_user.id)
    if not student:
        await message.answer("❌ Сначала авторизуйтесь через /start", reply_markup=kb.main)
        return

    try:
        async with db.get_connection() as conn:
            async with conn.execute('''
                SELECT t.date, subj.name, tch.full_name, t.test_link
                FROM tests t
                JOIN disciplines d ON t.discipline_id = d.id
                JOIN subjects subj ON d.subject_id = subj.id
                JOIN teachers tch ON d.teacher_id = tch.id
                WHERE t.group_id = (SELECT id_group FROM students WHERE id_student = ?) AND t.deleted_at IS NULL
                ORDER BY t.date ASC
                LIMIT 10
            ''', (student[0],)) as cursor:
                tests = await cursor.fetchall()

        if not tests:
            await message.answer("🎉 У вашей группы нет ближайших тестов")
            return

        response = "📊 Ближайшие тесты вашей группы:\n\n"
        for date, subj, teacher, test_link in tests:
            response += (
                f"📅 {date}\n"
                f"📚 {subj}\n"
                f"👨‍🏫 {teacher}\n"
                f"🔗 <a href=\"{test_link}\">Ссылка на тест</a>\n"
                "----------\n"
            )
        await safe_send_message(message, response, parse_mode="HTML")
    except Exception as e:
        logger.error(f"Error fetching tests: {e}")
        await message.answer("❌ Ошибка получения тестов.")

@router.message(F.text == "📰 Новости")
async def show_news(message: Message):
    try:
        student = await get_student_by_telegram(message.from_user.id)
        if not student:
            await message.answer("❌ Сначала авторизуйтесь с помощью /start")
            return

        async with db.get_connection() as conn:
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
                await message.answer("📭 Новостей пока нет")
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

            await safe_send_message(message, response, parse_mode="HTML")

    except Exception as e:
        logger.error(f"Error fetching news: {e}")
        await message.answer("❌ Произошла ошибка при получении новостей")

# ==================== АДМИНСКИЕ КОМАНДЫ ====================

# ==================== УПРАВЛЕНИЕ Тестами ====================

@router.message(AuthStates.admin_mode, F.text == "📊 Управление тестами")
async def manage_tests(message: Message, state: FSMContext):
    await message.answer(
        "📋 Выберите действие с тестами:",
        reply_markup=kb.tests_admin_kb
    )

@router.message(AuthStates.admin_mode, F.text == "📝 Добавить тест")
async def test_add_start(message: Message, state: FSMContext):
    # Список групп
    async with db.get_connection() as conn:
        async with conn.execute("SELECT id, name_group FROM groups ORDER BY id") as cursor:
            groups = await cursor.fetchall()
    if not groups:
        await message.answer("❌ группы не найдены")
        return
    await state.update_data(groups=groups)
    group_list = '\n'.join([f"{g[0]}: {g[1]}" for g in groups])
    await message.answer(f"👥 Выберите ID группы теста:\n{group_list}")
    await state.set_state(AddTestStates.waiting_group)

@router.message(AddTestStates.waiting_group)
async def test_add_group(message: Message, state: FSMContext):
    try:
        group_id = int(message.text.strip())
    except ValueError:
        await message.answer("📝 Введите числовой ID группы")
        return
    await state.update_data(group_id=group_id)
    # Перебираем предметы по дисциплинам этой группы
    async with db.get_connection() as conn:
        async with conn.execute('''
            SELECT s.id, s.name
            FROM disciplines d
            JOIN subjects s ON d.subject_id = s.id
            WHERE d.group_id = ?
            GROUP BY s.id
            ORDER BY s.name
        ''', (group_id,)) as cursor:
            subjects = await cursor.fetchall()
    if not subjects:
        await message.answer("❌ Нет предметов у группы!")
        await state.set_state(AuthStates.admin_mode)
        return
    subject_list = '\n'.join([f"{sid}: {sname}" for sid, sname in subjects])
    await message.answer("📋 Выберите ID предмета:")
    await safe_send_message(message, subject_list)
    await state.set_state(AddTestStates.waiting_subject)

@router.message(AddTestStates.waiting_subject)
async def test_add_subject(message: Message, state: FSMContext):
    try: subject_id = int(message.text.strip())
    except ValueError:
        await message.answer("📝 Введите числовой ID предмета")
        return

    await state.update_data(subject_id=subject_id)
    group_id = (await state.get_data())["group_id"]
    # Перебираем преподавателей у этого предмета и группы
    async with db.get_connection() as conn:
        async with conn.execute('''
            SELECT t.id, t.full_name
            FROM disciplines d
            JOIN teachers t ON d.teacher_id = t.id
            WHERE d.group_id = ? AND d.subject_id = ?
            GROUP BY t.id
            ORDER BY t.full_name
        ''', (group_id, subject_id)) as cursor:
            teachers = await cursor.fetchall()
    if not teachers:
        await message.answer("❌ Нет преподавателей у этого предмета/группы!")
        await state.set_state(AuthStates.admin_mode)
        return
    teachers_str = '\n'.join([f"{tid}: {tname}" for tid, tname in teachers])
    await message.answer("👤 Выберите ID преподавателя:\n")
    await safe_send_message(message, teachers_str)
    await state.set_state(AddTestStates.waiting_teacher)

@router.message(AddTestStates.waiting_teacher)
async def test_add_teacher(message: Message, state: FSMContext):
    try: teacher_id = int(message.text.strip())
    except ValueError:
        await message.answer("📝 Введите числовой ID преподавателя")
        return
    await state.update_data(teacher_id=teacher_id)
    await message.answer("ℹ️ Вставьте ссылку на тест:")
    await state.set_state(AddTestStates.waiting_link)

@router.message(AddTestStates.waiting_link)
async def test_add_link(message: Message, state: FSMContext):
    link = message.text.strip()
    await state.update_data(test_link=link)
    await message.answer("⏳ Введите дату теста (ГГГГ-ММ-ДД):")
    await state.set_state(AddTestStates.waiting_date)

@router.message(AddTestStates.waiting_date)
async def test_add_date(message: Message, state: FSMContext):
    date = message.text.strip()
    try:
        # Проверяем корректность даты
        datetime.strptime(date, "%Y-%m-%d")
    except ValueError:
        await message.answer("❌ Неверный формат даты. Используйте ГГГГ-ММ-ДД")
        return
    data = await state.get_data()
    # Тут надо получить discipline_id
    async with db.get_connection() as conn:
        async with conn.execute('''
            SELECT id FROM disciplines 
            WHERE subject_id = ? AND teacher_id = ? AND group_id = ?
        ''', (data["subject_id"], data["teacher_id"], data["group_id"])) as cursor:
            discipline = await cursor.fetchone()
    if not discipline:
        await message.answer("❌ Не найдено дисциплины с такой комбинацией")
        await state.set_state(AuthStates.admin_mode)
        return
    try:
        async with db.get_connection() as conn:
            await conn.execute('''
                INSERT INTO tests (group_id, discipline_id, test_link, date,created_at,updated_at)
                VALUES (?, ?, ?, ?,CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            ''', (data["group_id"], discipline[0], data["test_link"], date))
            await conn.commit()
            await message.answer("✅ Тест добавлен!\n"
                         f"👥 Группа: {data['group_id']}\n"
                         f"📚 Дисциплина: {data['subject_id']}\n"
                         f"👨‍🏫 Преподаватель: {data['teacher_id']}\n"
                         f"🔗 Ссылка: {data['test_link']}\n"
                         f"⏳ Дата: {date}",
                         reply_markup=kb.admin_kb)
    except Exception as e:
        logger.error(f"Ошибка добавления теста: {e}")
        await message.answer("❌ Не удалось добавить тест.")
    await state.set_state(AuthStates.admin_mode)

@router.message(AuthStates.admin_mode, F.text == "📋 Список тестов")
async def list_tests(message: Message):
    try:
        async with db.get_connection() as conn:
            async with conn.execute('''
                SELECT t.id, g.name_group, s.name, tch.full_name, t.date, t.test_link
                FROM tests t
                JOIN groups g ON t.group_id = g.id
                JOIN disciplines d ON t.discipline_id = d.id
                JOIN subjects s ON d.subject_id = s.id
                JOIN teachers tch ON d.teacher_id = tch.id
                WHERE t.deleted_at IS NULL
                ORDER BY t.date DESC
                LIMIT 20
            ''') as cursor:
                tests = await cursor.fetchall()
        
        if not tests:
            await message.answer("🎉 Тестов пока нет")
            return
            
        response = "📊 Список тестов:\n\n"
        for test in tests:
            test_id, group, subject, teacher, date, link = test
            response += (
                f"📌 ID: {test_id}\n"
                f"👥 Группа: {group}\n"
                f"📚 Предмет: {subject}\n"
                f"👨‍🏫 Преподаватель: {teacher}\n"
                f"📅 Дата: {date}\n"
                f"🔗 Ссылка: {link}\n\n"
            )
        await safe_send_message(message, response, parse_mode="HTML")
    
    except Exception as e:
        logger.error(f"Error fetching tests list: {e}")
        await message.answer("❌ Ошибка при получении списка тестов")


@router.message(AuthStates.admin_mode, F.text == "❌ Удалить")
async def delete_test_start(message: Message, state: FSMContext):
    # Получаем список тестов для выбора
    try:
        async with db.get_connection() as conn:
            async with conn.execute('''
                SELECT t.id, g.name_group, s.name, t.date
                FROM tests t
                JOIN groups g ON t.group_id = g.id
                JOIN disciplines d ON t.discipline_id = d.id
                JOIN subjects s ON d.subject_id = s.id
                WHERE t.deleted_at IS NULL
                ORDER BY t.date DESC
                LIMIT 50
            ''') as cursor:
                tests = await cursor.fetchall()
        
        if not tests:
            await message.answer("❌ Тестов для удаления нет")
            return
            
        tests_list = "\n".join([f"{t[0]}: {t[1]} - {t[2]} ({t[3]})" for t in tests])
        await message.answer ("📚 Введите ID теста для удаления:")
        await safe_send_message(message, tests_list, parse_mode="HTML")
        await state.set_state(AddTestStates.waiting_test_delete)
    
    except Exception as e:
        logger.error(f"Ошибка при получении списка тестов: {e}")
        await message.answer("❌ Ошибка при получении списка тестов")

@router.message(AddTestStates.waiting_test_delete)
async def execute_delete_test(message: Message, state: FSMContext):
    if message.text.lower() == "/cancel":
        return
    
    try:
        test_id = int(message.text.strip())
    except ValueError:
        await message.answer("📚 Введите числовой ID теста")
        return
    
    # Получаем информацию о тесте для подтверждения
    try:
        async with db.get_connection() as conn:
            async with conn.execute('''
                SELECT t.id, g.name_group, s.name, tch.full_name, t.date, t.test_link
                FROM tests t
                JOIN groups g ON t.group_id = g.id
                JOIN disciplines d ON t.discipline_id = d.id
                JOIN subjects s ON d.subject_id = s.id
                JOIN teachers tch ON d.teacher_id = tch.id
                WHERE t.id = ? AND t.deleted_at IS NULL
            ''', (test_id,)) as cursor:
                test = await cursor.fetchone()
        
        if not test:
            await message.answer("❌ Тест с указанным ID не найден")
            await state.set_state(AuthStates.admin_mode)
            return
            
        async with db.get_connection() as conn:
            await conn.execute("""
                UPDATE tests 
                SET deleted_at = CURRENT_TIMESTAMP, 
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
            """, (test_id,))
            await conn.commit()

        await message.answer(
            f"✅ Тест успешно удалён!\n"
            f"👥 Группа: {test[1]}\n"
            f"📚 Предмет: {test[2]}\n"
            f"⏳ Дата: {test[4]}",
            reply_markup=kb.admin_kb
        )
        await state.set_state(AuthStates.admin_mode)
    
    except Exception as e:
        logger.error(f"Ошибка при получении информации о тесте: {e}")
        await message.answer("❌ Ошибка при получении информации о тесте")

# ==================== УПРАВЛЕНИЕ НОВОСТЯМИ ====================
@router.message(AuthStates.admin_mode, F.text == "📰 Управление новостями")
async def manage_news(message: Message):
    await message.answer("📰 Управление новостями:", reply_markup=kb.news_admin_kb)

@router.message(AuthStates.admin_mode, F.text == "📝 Добавить новость")
async def add_news_start(message: Message, state: FSMContext):
    await message.answer("📝 Введите заголовок новости:")
    await state.set_state(AuthStates.add_news_title)

@router.message(AuthStates.add_news_title)
async def add_news_title(message: Message, state: FSMContext):
    if message.text == "/cancel":
        await cancel_command(message, state)
        return
    await state.update_data(title=message.text)
    await message.answer("📝 Введите описание новости:")
    await state.set_state(AuthStates.add_news_description)

@router.message(AuthStates.add_news_description)
async def add_news_description(message: Message, state: FSMContext):
    if message.text == "/cancel":
        await cancel_command(message, state)
        return
    await state.update_data(description=message.text)
    await message.answer("⏳ Введите дату новости в формате ГГГГ-ММ-ДД:")
    await state.set_state(AuthStates.add_news_date)

@router.message(AuthStates.add_news_date)
async def add_news_date(message: Message, state: FSMContext):
    if message.text == "/cancel":
        await cancel_command(message, state)
        return
    date_str = message.text.strip()
    try:
        # Проверяем корректность даты
        datetime.strptime(date_str, "%Y-%m-%d")
    except ValueError:
        await message.answer("❌ Неверный формат даты. Используйте ГГГГ-ММ-ДД")
        return
    await state.update_data(date=message.text)
    await message.answer("ℹ️ Введите место проведения или /skip для пропуска:")
    await state.set_state(AuthStates.add_news_place)

@router.message(AuthStates.add_news_place, Command("skip"))
async def skip_news_place(message: Message, state: FSMContext):
    await state.update_data(place=None)
    await message.answer("👥 Новость для всех групп? (да/нет)")
    await state.set_state(AuthStates.add_news_groups)

@router.message(AuthStates.add_news_place)
async def add_news_place(message: Message, state: FSMContext):
    if message.text == "/cancel":
        await cancel_command(message, state)
        return
    await state.update_data(place=message.text)
    await message.answer("👥 Новость для всех групп? (да/нет)")
    await state.set_state(AuthStates.add_news_groups)

@router.message(AuthStates.add_news_groups)
async def add_news_groups(message: Message, state: FSMContext):
    if message.text == "/cancel":
        await cancel_command(message, state)
        return
        
    data = await state.get_data()
    for_all = message.text.lower() == "да"
    try:
        async with db.get_connection() as conn:
            cursor = await conn.execute(
                '''INSERT INTO news (title, description, date, place, for_all_groups) 
                   VALUES (?, ?, ?, ?, ?)''',
                (data['title'], data['description'], data['date'], data.get('place'), int(for_all)))
            news_id = cursor.lastrowid

            if not for_all:
                # Запросим id групп
                await state.update_data(news_id=news_id)
                async with conn.execute("SELECT id, name_group FROM groups") as c:
                    groups = await c.fetchall()
                gr = '\n'.join(f"{g[0]}: {g[1]}" for g in groups)
                await message.answer(f"📝 Введите ID групп через запятую:\n{gr}")
                await state.set_state(NewsGroupsFSM.waiting_for_group_ids)
                await conn.commit()  # Зафиксируем создание новости
                return
            await conn.commit()
            await message.answer(f"✅ Новость успешно добавлена! ID: {news_id}", reply_markup=kb.admin_kb)
            await state.set_state(AuthStates.admin_mode)
    except Exception as e:
        logger.error(f"Error adding news: {e}")
        await message.answer("❌ Ошибка при добавлении новости", reply_markup=kb.admin_kb)
        await state.set_state(AuthStates.admin_mode)

@router.message(NewsGroupsFSM.waiting_for_group_ids)
async def add_news_group_ids(message: Message, state: FSMContext):
    if message.text == "/cancel":
        await cancel_command(message, state)
        return
        
    data = await state.get_data()
    news_id = data["news_id"]
    group_ids = [int(x) for x in message.text.replace(" ", "").split(",") if x.isdigit()]

        
    try:
        async with db.get_connection() as conn:
            await conn.executemany(
                "INSERT INTO news_groups (news_id, group_id) VALUES (?, ?)",
                [(news_id, gid) for gid in group_ids]
            )
            await conn.commit()
        await message.answer("✅ Новость добавлена и привязана к группам", reply_markup=kb.admin_kb)
    except Exception as e:
        logger.error(f"Error attaching news to groups: {e}")
        await message.answer("❌ Ошибка при связывании новости и групп", reply_markup=kb.admin_kb)
    await state.set_state(AuthStates.admin_mode)

@router.message(AuthStates.admin_mode, F.text == "📋 Список новостей")
async def list_news(message: Message):
    try:
        async with db.get_connection() as conn:
            async with conn.execute('''
                SELECT id, title, date, is_published FROM news ORDER BY date DESC LIMIT 20
            ''') as cursor:
                news_list = await cursor.fetchall()
        
        if not news_list:
            await message.answer("📭 Новостей пока нет")
            return
            
        response = "📰 Последние новости:\n\n"
        for news in news_list:
            news_id, title, date, is_published = news
            status = "✅ Опубликована" if is_published else "⏳ Не опубликована"
            response += f"📌 <b>{title}</b>\n📅 {date}\n{status}\nID: {news_id}\n\n"
        
        await safe_send_message(message, response, parse_mode="HTML")
    
    except Exception as e:
        logger.error(f"Error fetching news list: {e}")
        await message.answer("❌ Ошибка при получении списка новостей.")

@router.message(AuthStates.admin_mode, F.text == "📢 Опубликовать новость")
async def publish_news_start(message: Message, state: FSMContext):
    await message.answer("📝 Введите ID новости для публикации:")
    await state.set_state(AuthStates.publish_news)

@router.message(AuthStates.publish_news)
async def publish_news_execute(message: Message, state: FSMContext):
    if message.text == "/cancel":
        await cancel_command(message, state)
        return
        
    try:
        news_id = int(message.text)
        async with db.get_connection() as conn:
            await conn.execute(
                "UPDATE news SET is_published = 1 WHERE id = ?",
                (news_id,))
            await conn.commit()
            await message.answer(f"✅ Новость с ID {news_id} опубликована", reply_markup=kb.admin_kb)
            await state.set_state(AuthStates.admin_mode)
    except ValueError:
        await message.answer("❌ Введите корректный ID новости: ")
    except Exception as e:
        logger.error(f"Error publishing news: {e}")
        await message.answer("❌ Ошибка при публикации новости", reply_markup=kb.admin_kb)
        await state.set_state(AuthStates.admin_mode)

@router.message(AuthStates.admin_mode, F.text == "❌ Удалить новость")
async def delete_news_start(message: Message, state: FSMContext):
    await message.answer("📝 Введите ID новости для удаления:")
    await state.set_state(AuthStates.delete_news)

@router.message(AuthStates.delete_news)
async def delete_news_execute(message: Message, state: FSMContext):
    if message.text == "/cancel":
        await cancel_command(message, state)
        return
        
    try:
        news_id = int(message.text)
        async with db.get_connection() as conn:
            await conn.execute("DELETE FROM news_groups WHERE news_id = ?", (news_id,))
            await conn.execute("DELETE FROM news WHERE id = ?", (news_id,))
            await conn.commit()
            await message.answer(f"✅ Новость с ID {news_id} удалена", reply_markup=kb.admin_kb)
            await state.set_state(AuthStates.admin_mode)
    except ValueError:
        await message.answer("❌ Введите корректный ID новости:")
    except Exception as e:
        logger.error(f"Error deleting news: {e}")
        await message.answer("❌ Ошибка при удалении новости", reply_markup=kb.admin_kb)
        await state.set_state(AuthStates.admin_mode)

# ==================== УПРАВЛЕНИЕ ПОЛЬЗОВАТЕЛЯМИ ====================
@router.message(AuthStates.admin_mode, F.text == "👥 Управление пользователями")
async def manage_users(message: Message, state: FSMContext):
    await message.answer("👥 Управление пользователями:", reply_markup=kb.students_admin_kb)

@router.message(AuthStates.admin_mode, F.text == "🔗 Отвязать пользователя")
async def unbind_user_start(message: Message, state: FSMContext):
    try:
        async with db.get_connection() as conn:
            async with conn.execute('''
                SELECT s.id_student, s.login, s.telegram_id, g.name_group 
                FROM students s
                JOIN groups g ON s.id_group = g.id
                WHERE s.telegram_id IS NOT NULL
                ORDER BY g.name_group, s.login
            ''') as cursor:
                users = await cursor.fetchall()
        
        if not users:
            await message.answer("🤷 Нет привязанных пользователей.")
            return
            
        response = "👥 Список привязанных пользователей:\n\n"
        for user in users:
            user_id, login, tg_id, group = user
            response += f"👤 {login} (Группа: {group})\nID: {user_id} | TG: {tg_id}\n\n"
        
        response += "\n🔗 Введите ID пользователя для отвязки или /all для отвязки всех:"
        await safe_send_message(message, response)
        await state.set_state(AuthStates.unbind_user_select)
    
    except Exception as e:
        logger.error(f"Error fetching users list: {e}")
        await message.answer("❌ Ошибка при получении списка пользователей.")

@router.message(AuthStates.unbind_user_select, Command("all"))
async def unbind_all_confirm(message: Message, state: FSMContext):
    await message.answer("⚠️ Вы уверены, что хотите отвязать ВСЕХ пользователей? (да/нет)")
    await state.set_state(AuthStates.unbind_all_confirm)

@router.message(AuthStates.unbind_all_confirm, F.text.lower() == "да")
async def unbind_all_execute(message: Message, state: FSMContext):
    try:
        async with db.get_connection() as conn:
            await conn.execute("BEGIN")
            # Отвязываем всех пользователей
            await conn.execute("UPDATE students SET telegram_id = NULL")
            # Очищаем историю отправленных уведомлений
            await conn.execute("DELETE FROM sent_notifications")
            await conn.commit()
            
        await message.answer("✅ Все пользователи успешно отвязаны", reply_markup=kb.admin_kb)
        await state.set_state(AuthStates.admin_mode)
    except Exception as e:
        logger.error(f"Error unbinding all users: {e}")
        await message.answer("❌ Ошибка при отвязке пользователей", reply_markup=kb.admin_kb)
        await state.set_state(AuthStates.admin_mode)

@router.message(AuthStates.unbind_user_select)
async def unbind_single_user(message: Message, state: FSMContext):
    if message.text == "/cancel":
        await cancel_command(message, state)
        return
        
    try:
        user_id = int(message.text)
        async with db.get_connection() as conn:
            await conn.execute("BEGIN")
            # Получаем telegram_id пользователя
            async with conn.execute(
                "SELECT telegram_id FROM students WHERE id_student = ?",
                (user_id,)
            ) as cursor:
                tg_id = await cursor.fetchone()
                
            if not tg_id:
                await message.answer("❌ Пользователь с таким ID не найден")
                return
                
            # Отвязываем пользователя
            await conn.execute(
                "UPDATE students SET telegram_id = NULL WHERE id_student = ?",
                (user_id,))
            # Удаляем его уведомления
            await conn.execute(
                "DELETE FROM sent_notifications WHERE user_id = ?",
                (tg_id[0],))
            await conn.commit()
            
        await message.answer(f"✅ Пользователь с ID {user_id} успешно отвязан", reply_markup=kb.admin_kb)
        await state.set_state(AuthStates.admin_mode)
    except ValueError:
        await message.answer("❌ Введите корректный ID пользователя или /all")
    except Exception as e:
        logger.error(f"Error unbinding user: {e}")
        await message.answer("❌ Ошибка при отвязке пользователя", reply_markup=kb.admin_kb)
        await state.set_state(AuthStates.admin_mode)

@router.message(AuthStates.admin_mode, F.text == "👤 Добавить студента")
async def add_student_start(message: Message, state: FSMContext):
    await message.answer("👤 Введите логин нового студента:")
    await state.set_state(add_states.waiting_login)

@router.message(add_states.waiting_login)
async def add_student_login(message: Message, state: FSMContext):
    if message.text == "/cancel":
        await cancel_command(message, state)
        return
        
    login = message.text.strip()
    # Проверка уникальности логина
    async with db.get_connection() as conn:
        async with conn.execute("SELECT 1 FROM students WHERE login = ?", (login,)) as cur:
            exists = await cur.fetchone()
    if exists:
        await message.answer("❌ Студент с таким логином уже есть. Введите другой логин:")
        return
    await state.update_data(login=login)
    await message.answer("🔐 Укажите пароль для студента:")
    await state.set_state(add_states.waiting_password)

@router.message(add_states.waiting_password)
async def add_student_password(message: Message, state: FSMContext):
    if message.text == "/cancel":
        await cancel_command(message, state)
        return
        
    password = message.text.strip()
    await state.update_data(password=password)
    # Покажем список групп
    async with db.get_connection() as conn:
        async with conn.execute("SELECT id, name_group FROM groups ORDER BY name_group") as cursor:
            groups = await cursor.fetchall()
    group_list = "\n".join([f"{gid}: {gname}" for gid, gname in groups])
    await message.answer(f"👥 Выберите ID группы для студента:\n{group_list}")
    await state.set_state(add_states.waiting_group)

@router.message(add_states.waiting_group)
async def add_student_group(message: Message, state: FSMContext):
    if message.text == "/cancel":
        await cancel_command(message, state)
        return
        
    try:
        group_id = int(message.text.strip())
        async with db.get_connection() as conn:
            async with conn.execute("SELECT name_group FROM groups WHERE id = ?", (group_id,)) as cur:
                group = await cur.fetchone()
        if not group:
            await message.answer("❌ Группа не найдена. Введите корректный ID:")
            return
    except ValueError:
        await message.answer("❌ Введите корректный ID группы")
        return

    await state.update_data(group_id=group_id)
    await message.answer("ℹ️ Введите дополнительное ФИО или /skip для пропуска:")
    await state.set_state(add_states.waiting_description)

@router.message(add_states.waiting_description, Command("skip"))
async def add_student_skip_desc(message: Message, state: FSMContext):
    await state.update_data(description=None)
    await finish_student_add(message, state)

@router.message(add_states.waiting_description)
async def add_student_desc(message: Message, state: FSMContext):
    if message.text == "/cancel":
        await cancel_command(message, state)
        return
        
    await state.update_data(description=message.text)
    await finish_student_add(message, state)

async def finish_student_add(message: Message, state: FSMContext):
    data = await state.get_data()
    # Вставляем в БД
    try:
        hashed_password = await pm.hash_password(data["password"])
        async with db.get_connection() as conn:
            await conn.execute('''
                INSERT INTO students (login, password, id_group, description) 
                VALUES (?, ?, ?, ?)
            ''', (data["login"], hashed_password, data["group_id"], data.get("description",None)))
            await conn.commit()
        await message.answer(f"✅ Студент {data['login']} добавлен", reply_markup=kb.admin_kb)
    except Exception as e:
        logger.error(f"Ошибка добавления студента: {e}")
        await message.answer("❌ Не удалось добавить студента")
    await state.set_state(AuthStates.admin_mode)

@router.message(AuthStates.admin_mode, F.text == "📋 Список студентов")
async def list_students(message: Message, state: FSMContext):
    try:
        async with db.get_connection() as conn:
            async with conn.execute('''
                SELECT s.id_student, s.login, g.name_group, s.is_active, s.telegram_id 
                FROM students s
                JOIN groups g ON s.id_group = g.id
                ORDER BY s.id_student
            ''') as cursor:
                students = await cursor.fetchall()
        
        if not students:
            await message.answer("🤷 Нет студентов в базе")
            return
        
        chunk_size = 70
        for i in range(0, len(students), chunk_size):
            chunk = students[i:i + chunk_size]
            msg = ["👥 Список студентов:"] if i == 0 else []
            
            for student in chunk:
                status = "✅ Активен" if student[3] else "❌ Неактивен"
                tg_status = "✅ Привязан" if student[4] else "❌ Не привязан"
                msg.append(f"{student[0]}: {student[1]} ({student[2]}) [{status}] [{tg_status}]")
            
            await message.answer("\n".join(msg))
    
    except Exception as e:
        logger.error(f"Error fetching students list: {e}")
        await message.answer("❌ Ошибка при получении списка студентов")

    await state.set_state(AuthStates.admin_mode)

@router.message(AuthStates.admin_mode, F.text == "✏️ Редактировать студента")
async def edit_student_start(message: Message, state: FSMContext):
    # список студентов
    try:
        async with db.get_connection() as conn:
            async with conn.execute("""
                SELECT s.id_student, s.login, g.name_group
                FROM students s
                JOIN groups g ON s.id_group = g.id
                ORDER BY s.id_student
            """) as cur:
                students = await cur.fetchall()
        
        if not students:
                await message.answer("🤷 Нет студентов в базе")
                return
        
        chunk_size = 70
        for i in range(0, len(students), chunk_size):
            chunk = students[i:i + chunk_size]
            msg = ["👥 Список студентов:"] if i == 0 else []
            
            for student in chunk:
                msg.append(f"{student[0]}: {student[1]} ({student[2]})")
            await message.answer("\n".join(msg))

    except Exception as e:
        logger.error(f"Error fetching students list: {e}")
        await message.answer("❌ Ошибка при получении списка студентов")

    await state.set_state(edit_st.waiting_id)

@router.message(edit_st.waiting_id)
async def edit_student_select(message: Message, state: FSMContext):
    if message.text == "/cancel":
        await cancel_command(message, state)
        return
        
    try:
        student_id = int(message.text.strip())
    except ValueError:
        await message.answer("❌ Введите корректный ID студента")
        return

    async with db.get_connection() as conn:
        async with conn.execute("""
            SELECT s.id_student, s.login, s.password, g.name_group, s.is_active, s.description, s.id_group
            FROM students s
            JOIN groups g ON s.id_group = g.id
            WHERE s.id_student = ?
        """, (student_id,)) as cur:
            student = await cur.fetchone()
    if not student:
        await message.answer("❌ Студент не найден")
        await state.set_state(AuthStates.admin_mode)
        return

    # Сохраняем инфу в FSM
    await state.update_data(
        id_student=student[0], login=student[1], password=student[2], group_name=student[3],
        is_active=student[4], description=student[5] or "", id_group=student[6]
    )
    msg = (
        f"Выбран студент:\n"
        f"👤Логин: {student[1]}\n"
        f"👥Группа: {student[3]}\n"
        f"ℹ️Описание: {student[5] or 'Нет'}\n"
        f"⏳Статус: {'✅ Активен' if student[4] else '❌ Неактивен'}\n\n"
        f"Что изменить?"
    )
    await message.answer(msg, reply_markup=kb.edit_student_kb, parse_mode="HTML")
    await state.set_state(edit_st.main_menu)

# ==================== РЕДАКТИРОВАНИЕ СТУДЕНТА ====================
@router.message(edit_st.main_menu, F.text == "👤 Логин")
async def edit_student_login_btn(message: Message, state: FSMContext):
    await message.answer("📝 Введите новый логин:")
    await state.set_state(edit_st.editing_login)

@router.message(edit_st.main_menu, F.text == "🔗 Пароль")
async def edit_student_password_btn(message: Message, state: FSMContext):
    await message.answer("📝 Введите новый пароль:")
    await state.set_state(edit_st.editing_password)

@router.message(edit_st.main_menu, F.text == "👥 Группа")
async def edit_student_group_btn(message: Message, state: FSMContext):
    async with db.get_connection() as conn:
        async with conn.execute("SELECT id,name_group FROM groups") as cur:
            groups = await cur.fetchall()
    gr = '\n'.join(f"{gid}: {gname}" for gid, gname in groups)
    await message.answer(f"📋 Выберите ID группы:\n{gr}")
    await state.set_state(edit_st.editing_group)

@router.message(edit_st.main_menu, F.text == "⏳ Статус")
async def edit_student_status_btn(message: Message, state: FSMContext):
    await message.answer("📋 Выберите статус:")
    await state.set_state(edit_st.editing_status)

@router.message(edit_st.main_menu, F.text == "ℹ️ Описание")
async def edit_student_description_btn(message: Message, state: FSMContext):
    await message.answer("📝 Введите новое описание:")
    await state.set_state(edit_st.editing_description)

@router.message(edit_st.main_menu, F.text == "✅ Сохранить")
async def edit_student_save_btn(message: Message, state: FSMContext):
    await edit_student_save(message, state)

@router.message(edit_st.main_menu, F.text == "❌ Отмена")
async def edit_student_cancel_btn(message: Message, state: FSMContext):
    await message.answer("❌ Редактирование отменено.", reply_markup=kb.admin_kb)
    await state.set_state(AuthStates.admin_mode)


@router.message(edit_st.editing_login)
async def edit_student_login(message: Message, state: FSMContext):
    if message.text == "/cancel":
        await cancel_command(message, state)
        return
        
    await state.update_data(login=message.text.strip())
    await message.answer("✅ Логин изменен.", reply_markup=kb.edit_student_kb)
    await state.set_state(edit_st.main_menu)

@router.message(edit_st.editing_password)
async def edit_student_password(message: Message, state: FSMContext):
    if message.text == "/cancel":
        await cancel_command(message, state)
        return
        
    password = await pm.hash_password(message.text.strip())
    await state.update_data(password=password)
    await message.answer("✅ Пароль изменен.", reply_markup=kb.edit_student_kb)
    await state.set_state(edit_st.main_menu)

@router.message(edit_st.editing_group)
async def edit_student_group(message: Message, state: FSMContext):
    if message.text == "/cancel":
        await cancel_command(message, state)
        return
        
    try:
        group_id = int(message.text.strip())
        # Проверить корректность
        async with db.get_connection() as conn:
            async with conn.execute("SELECT name_group FROM groups WHERE id = ?", (group_id,)) as cur:
                group = await cur.fetchone()
        if not group:
            await message.answer("❌ Группа не найдена. Введите ID ещё раз")
            return
    except ValueError:
        await message.answer("❌ ID группы только число")
        return
    await state.update_data(id_group=group_id, group_name=group[0])
    await message.answer("✅ Группа изменена", reply_markup=kb.edit_student_kb)
    await state.set_state(edit_st.main_menu)

@router.message(edit_st.editing_status)
async def edit_student_status(message: Message, state: FSMContext):
    if message.text == "/cancel":
        await cancel_command(message, state)
        return
        
    text = message.text.strip().lower()
    if text not in ["активен", "неактивен", "1", "0"]:
        await message.answer("📝 Введите 'активен' или 'неактивен' (или 1/0)")
        return
        
    is_active = 1 if text in ["активен", "1"] else 0
    await state.update_data(is_active=is_active)
    await message.answer(f"✅ Статус изменен на {'активен' if is_active else 'неактивен'}",
                       reply_markup=kb.edit_student_kb)
    await state.set_state(edit_st.main_menu)

@router.message(edit_st.editing_description)
async def edit_student_description(message: Message, state: FSMContext):
    if message.text == "/cancel":
        await cancel_command(message, state)
        return
        
    await state.update_data(description=message.text.strip())
    await message.answer("✅ Описание изменено.", reply_markup=kb.edit_student_kb)
    await state.set_state(edit_st.main_menu)

@router.message(edit_st.confirm)
async def edit_student_save(message: Message, state: FSMContext):
    data = await state.get_data()
    try:
        async with db.get_connection() as conn:
            await conn.execute("""
                UPDATE students SET login = ?, password = ?, id_group = ?, is_active = ?, description = ?
                WHERE id_student = ?
            """, (
                data["login"], data["password"], data["id_group"], data["is_active"], data["description"], data["id_student"]
            ))
            await conn.commit()
        await message.answer("✅ Данные студента изменены", reply_markup=kb.admin_kb)
    except Exception as e:
        logger.error(f"Ошибка при сохранении студента: {e}")
        await message.answer("❌ Ошибка обновления")
    await state.set_state(AuthStates.admin_mode)



@router.message(AuthStates.admin_mode, F.text == "❌ Удалить студента")
async def delete_student_start(message: Message, state: FSMContext):
    await message.answer("📝 Введите ID студента для удаления:")
    await state.set_state(AuthStates.delete_student)

@router.message(AuthStates.delete_student)
async def delete_student_process(message: Message, state: FSMContext):
    if message.text == "/cancel":
        await cancel_command(message, state)
        return
        
    try:
        student_id = int(message.text)
        async with db.get_connection() as conn:
            await conn.execute("DELETE FROM students WHERE id_student = ?", (student_id,))
            await conn.commit()
            await message.answer(f"✅ Студент с ID {student_id} удален", reply_markup=kb.admin_kb)
            await state.set_state(AuthStates.admin_mode)
    except ValueError:
        await message.answer("❌ Введите корректный ID студента: ")
    except Exception as e:
        logger.error(f"Error deleting student: {e}")
        await message.answer("❌ Ошибка при удалении студента", reply_markup=kb.admin_kb)
        await state.set_state(AuthStates.admin_mode)

# ==================== Управление предметами ====================

@router.message(AuthStates.admin_mode, F.text == "📚 Управление предметами")
async def manage_subjects(message: Message, state: FSMContext):
    await message.answer(
        "📋 Выберите действие:",
        reply_markup=kb.subjects_admin_kb
    )
    await state.set_state(SubjectFSM.choose_action)

@router.message(SubjectFSM.choose_action)
async def subject_action(message: Message, state: FSMContext):
    if message.text == "/cancel":
        await cancel_command(message, state)
        return
        
    if message.text == "📝 Добавить предмет":
        await message.answer("📝 Введите название предмета:")
        await state.set_state(SubjectFSM.wait_name)
    elif message.text == "📋 Список предметов":
        async with db.get_connection() as conn:
            async with conn.execute("SELECT id, name FROM subjects ORDER BY name") as cur:
                subs = await cur.fetchall()
        await message.answer(
            "📚 Предметы:\n" +
            "\n".join([f"{x[0]}: {x[1]}" for x in subs]),
            reply_markup=kb.subjects_admin_kb
        )
    elif message.text == "❌ Удалить предмет":
        async with db.get_connection() as conn:
            async with conn.execute("SELECT id, name FROM subjects ORDER BY name") as cur:
                subs = await cur.fetchall()
        await message.answer("📝 Введите ID предмета для удаления:\n" +
            "\n".join([f"{x[0]}: {x[1]}" for x in subs])
        )
        await state.set_state(SubjectFSM.wait_id)
    elif message.text == "✏️ Редактировать предмет":
        async with db.get_connection() as conn:
            async with conn.execute("SELECT id, name FROM subjects ORDER BY name") as cur:
                subs = await cur.fetchall()
        await message.answer("📝 Введите ID предмета для редактирования:\n" +
            "\n".join([f"{x[0]}: {x[1]}" for x in subs])
        )
        await state.set_state(SubjectFSM.wait_id)
    elif message.text == "🔙 Назад в админку":
        await message.answer("🔐 Административное меню", reply_markup=kb.admin_kb)
        await state.set_state(AuthStates.admin_mode)
    else:
        await message.answer("📋 Выберите действие", reply_markup=kb.subjects_admin_kb)

@router.message(SubjectFSM.wait_name)
async def subject_add(message: Message, state: FSMContext):
    if message.text == "/cancel":
        await cancel_command(message, state)
        return
        
    name = message.text.strip()
    try:
        async with db.get_connection() as conn:
            await conn.execute("INSERT INTO subjects (name) VALUES (?)", (name,))
            await conn.commit()
        await message.answer(f"✅ Предмет \"{name}\" добавлен", reply_markup=kb.subjects_admin_kb)
    except Exception as e:
        logger.error(f"Ошибка добавления предмета: {e}")
        await message.answer("❌ Ошибка добавления")
    await state.set_state(SubjectFSM.choose_action)

@router.message(SubjectFSM.wait_id)
async def subject_edit_delete(message: Message, state: FSMContext):
    if message.text == "/cancel":
        await cancel_command(message, state)
        return
        
    try:
        subj_id = int(message.text.strip())
    except ValueError:
        await message.answer("❌ ID должно быть числом")
        return
        
    await state.update_data(subj_id=subj_id)
    await message.answer("📝 Введите новое название предмета или /del для удаления:")
    await state.set_state(SubjectFSM.wait_edit_new_name)

@router.message(SubjectFSM.wait_edit_new_name, Command("del"))
async def subject_del(message: Message, state: FSMContext):
    subj_id = (await state.get_data()).get("subj_id")
    try:
        async with db.get_connection() as conn:
            await conn.execute("DELETE FROM subjects WHERE id = ?", (subj_id,))
            await conn.commit()
        await message.answer("🗑️ Предмет удален", reply_markup=kb.subjects_admin_kb)
    except Exception as e:
        logger.error(f"Ошибка удаления предмета: {e}")
        await message.answer("❌ Ошибка удаления")
    await state.set_state(SubjectFSM.choose_action)

@router.message(SubjectFSM.wait_edit_new_name)
async def subject_edit_name(message: Message, state: FSMContext):
    if message.text == "/cancel":
        await cancel_command(message, state)
        return
        
    new_name = message.text.strip()
    subj_id = (await state.get_data()).get("subj_id")
    try:
        async with db.get_connection() as conn:
            await conn.execute("UPDATE subjects SET name = ? WHERE id = ?", (new_name, subj_id))
            await conn.commit()
        await message.answer("✅ Название предмета изменено", reply_markup=kb.subjects_admin_kb)
    except Exception as e:
        logger.error(f"Ошибка изменения предмета: {e}")
        await message.answer("❌ Не удалось изменить")
    await state.set_state(SubjectFSM.choose_action)

# ==================== Управление преподавателями ====================

@router.message(AuthStates.admin_mode, F.text == "👨‍🏫 Управление преподавателями")
async def manage_teachers(message: Message, state: FSMContext):
    await message.answer(
        "📋 Выберите действие",
        reply_markup=kb.teachers_admin_kb
    )
    await state.set_state(TeacherFSM.choose_action)

@router.message(TeacherFSM.choose_action, F.text == "📋 Список преподавателей")
async def teacher_list(message: Message, state: FSMContext):
    try:
        async with db.get_connection() as conn:
            async with conn.execute("SELECT id, full_name FROM teachers ORDER BY full_name") as cur:
                teachers = await cur.fetchall()
        
        if not teachers:
            await message.answer("❌ Список преподавателей пуст", reply_markup=kb.teachers_admin_kb)
            return
            
        teachers_list = "\n".join([f"{teacher[0]}: {teacher[1]}" for teacher in teachers])
        await message.answer(
            f"👨‍🏫 Список преподавателей:\n{teachers_list}",
            reply_markup=kb.teachers_admin_kb
        )
    except Exception as e:
        logger.error(f"Ошибка при получении списка преподавателей: {e}")
        await message.answer("❌ Ошибка при получении списка преподавателей", reply_markup=kb.teachers_admin_kb)

@router.message(TeacherFSM.choose_action, F.text == "📝 Добавить преподавателя")
async def teacher_add_prompt(message: Message, state: FSMContext):
    await message.answer("📝 Введите ФИО преподавателя:")
    await state.set_state(TeacherFSM.wait_name)

@router.message(TeacherFSM.wait_name)
async def teacher_add(message: Message, state: FSMContext):
    name = message.text.strip()
    try:
        async with db.get_connection() as conn:
            await conn.execute("INSERT INTO teachers (full_name) VALUES (?)", (name,))
            await conn.commit()
        await message.answer(
            f"✅ Преподаватель \"{name}\" добавлен",
            reply_markup=kb.teachers_admin_kb
        )
    except Exception as e:
        logger.error(f"Ошибка добавления: {e}")
        await message.answer("❌ Ошибка добавления", reply_markup=kb.teachers_admin_kb)
    await state.set_state(TeacherFSM.choose_action)

@router.message(TeacherFSM.choose_action, F.text.in_(["✏️ Редактировать преподавателя", "❌ Удалить преподавателя"]))
async def teacher_edit_delete_prompt(message: Message, state: FSMContext):
    action = "edit" if message.text == "✏️ Редактировать преподавателя" else "delete"
    await state.update_data(action=action)
    
    async with db.get_connection() as conn:
        async with conn.execute("SELECT id, full_name FROM teachers ORDER BY full_name") as cur:
            ts = await cur.fetchall()
    
    await message.answer(
        f"📝 Введите ID преподавателя для {'редактирования' if action == 'edit' else 'удаления'}:\n" +
        "\n".join([f"{x[0]}: {x[1]}" for x in ts])
    )
    await state.set_state(TeacherFSM.wait_id)

@router.message(TeacherFSM.wait_id)
async def teacher_process_id(message: Message, state: FSMContext):
    try:
        teacher_id = int(message.text.strip())
    except ValueError:
        await message.answer("❌ ID должно быть числом")
        return
        
    data = await state.get_data()
    action = data.get("action")
    
    if action == "edit":
        await state.update_data(teacher_id=teacher_id)
        await message.answer("📝 Введите новое ФИО преподавателя:")
        await state.set_state(TeacherFSM.wait_new_name)
    elif action == "delete":
        try:
            async with db.get_connection() as conn:
                await conn.execute("DELETE FROM teachers WHERE id = ?", (teacher_id,))
                await conn.commit()
            await message.answer("🗑️ Преподаватель удален", reply_markup=kb.teachers_admin_kb)
        except Exception as e:
            logger.error(f"Ошибка удаления преподавателя: {e}")
            await message.answer("❌ Ошибка удаления", reply_markup=kb.teachers_admin_kb)
        await state.set_state(TeacherFSM.choose_action)

@router.message(TeacherFSM.wait_new_name)
async def teacher_update_name(message: Message, state: FSMContext):
    new_name = message.text.strip()
    teacher_id = (await state.get_data()).get("teacher_id")
    try:
        async with db.get_connection() as conn:
            await conn.execute("UPDATE teachers SET full_name = ? WHERE id = ?", (new_name, teacher_id))
            await conn.commit()
        await message.answer("✅ Имя преподавателя изменено", reply_markup=kb.teachers_admin_kb)
    except Exception as e:
        logger.error(f"Ошибка изменения преподавателя: {e}")
        await message.answer("❌ Не удалось изменить", reply_markup=kb.teachers_admin_kb)
    await state.set_state(TeacherFSM.choose_action)

@router.message(TeacherFSM.choose_action, F.text == "🔙 Назад в админку")
async def teacher_back(message: Message, state: FSMContext):
    await message.answer("🔐 Административное меню", reply_markup=kb.admin_kb)
    await state.set_state(AuthStates.admin_mode)

# ==================== Управление долгами ====================

@router.message(AuthStates.admin_mode, F.text == "⏳ Управление долгами")
async def manage_debts(message: Message, state: FSMContext):
    await message.answer(
        "📋 Выберите действие",
        reply_markup=kb.debts_admin_kb
    )
    await state.set_state(DebtFSM.choose_action)

@router.message(DebtFSM.choose_action, F.text == "📋 Список долгов")
async def debt_list(message: Message, state: FSMContext):
    async with db.get_connection() as conn:
        async with conn.execute("""
            SELECT s.id_student, s.login, subj.name, dt.name, sd.last_date
            FROM student_debts sd
            JOIN students s ON sd.student_id = s.id_student
            JOIN disciplines d ON sd.discipline_id = d.id
            JOIN subjects subj ON d.subject_id = subj.id
            JOIN debt_types dt ON sd.debt_type_id = dt.id
            WHERE sd.deleted_at IS NULL
            ORDER BY s.id_student
        """) as cur:
            debts = await cur.fetchall()
    
    if not debts:
        await message.answer("❌ Нет задолженностей")
        return
    
    # Формируем сообщение частями
    msg_parts = []
    current_part = "Задолженности студентов\n"
    
    for st in debts:
        line = f"{st[0]}: {st[1]} по {st[2]} ({st[3]}) - до {st[4]}\n"
        if len(current_part) + len(line) > 4000:  # Оставляем запас
            msg_parts.append(current_part)
            current_part = line
        else:
            current_part += line
    
    if current_part:
        msg_parts.append(current_part)
    
    # Отправляем части
    for part in msg_parts:
        await safe_send_message(message, part)

@router.message(DebtFSM.choose_action, F.text == "📝 Добавить долг")
async def debt_add(message: Message, state: FSMContext):
    # Выбор студента
    async with db.get_connection() as conn:
        async with conn.execute("SELECT id_student, login FROM students ORDER BY login") as cur:
            studs = await cur.fetchall()
    
    if not studs:
        await message.answer("❌ Нет студентов в базе")
        return
    
    students_list = "\n".join([f"{s[0]}: {s[1]}" for s in studs])
    await safe_send_message(
        message, 
        "📋 Выберите ID студента:\n" + students_list,
        parse_mode=None
    )
    await state.set_state(DebtFSM.wait_student)

@router.message(DebtFSM.wait_student)
async def debt_choose_student(message: Message, state: FSMContext):
    if message.text == "/cancel":
        await cancel_command(message, state)
        return
        
    try:
        student_id = int(message.text.strip())
    except ValueError:
        await message.answer("📝 Введите числовой ID студента")
        return
        
    # Проверяем существование студента
    async with db.get_connection() as conn:
        async with conn.execute("SELECT id_student FROM students WHERE id_student = ?", (student_id,)) as cur:
            if not await cur.fetchone():
                await message.answer("❌ Студент с таким ID не найден")
                return
    
    await state.update_data(student_id=student_id)
    
    # Получаем список дисциплин
    async with db.get_connection() as conn:
        async with conn.execute("""
            SELECT d.id, s.name, t.full_name 
            FROM disciplines d
            JOIN subjects s ON d.subject_id = s.id
            JOIN teachers t ON d.teacher_id = t.id
            ORDER BY s.name
        """) as cur:
            disciplines = await cur.fetchall()
    
    if not disciplines:
        await message.answer("❌ Нет доступных дисциплин")
        return
        
    disciplines_list = "\n".join([f"{d[0]}: {d[1]} ({d[2]})" for d in disciplines])
    await safe_send_message(
        message,
        "📋 Выберите ID дисциплины:\n" + disciplines_list,
        parse_mode=None
    )
    await state.set_state(DebtFSM.wait_add_disc)

@router.message(DebtFSM.wait_add_disc)
async def debt_choose_disc(message: Message, state: FSMContext):
    if message.text == "/cancel":
        await cancel_command(message, state)
        return
        
    try:
        discipline_id = int(message.text.strip())
    except ValueError:
        await message.answer("📝 Введите числовой ID дисциплины")
        return
        
    # Проверяем существование дисциплины
    async with db.get_connection() as conn:
        async with conn.execute("SELECT id FROM disciplines WHERE id = ?", (discipline_id,)) as cur:
            if not await cur.fetchone():
                await message.answer("❌ Дисциплина с таким ID не найдена")
                return
    
    await state.update_data(discipline_id=discipline_id)
    
    # Получаем типы долгов
    async with db.get_connection() as conn:
        async with conn.execute("SELECT id, name FROM debt_types ORDER BY name") as cur:
            types = await cur.fetchall()
    
    if not types:
        await message.answer("❌ Нет доступных типов долгов")
        return
        
    types_list = "\n".join([f"{t[0]}: {t[1]}" for t in types])
    await safe_send_message(
        message,
        "📋 Выберите ID типа долга:\n" + types_list,
        parse_mode=None
    )
    await state.set_state(DebtFSM.wait_add_type)

@router.message(DebtFSM.wait_add_type)
async def debt_choose_type(message: Message, state: FSMContext):
    if message.text == "/cancel":
        await cancel_command(message, state)
        return
        
    try:
        debt_type_id = int(message.text.strip())
    except ValueError:
        await message.answer("📝 Введите числовой ID типа долга")
        return
        
    # Проверяем существование типа долга
    async with db.get_connection() as conn:
        async with conn.execute("SELECT id FROM debt_types WHERE id = ?", (debt_type_id,)) as cur:
            if not await cur.fetchone():
                await message.answer("❌ Тип долга с таким ID не найден")
                return
    
    await state.update_data(debt_type_id=debt_type_id)
    await message.answer("⏳ Введите крайний срок сдачи в формате ГГГГ-ММ-ДД:")
    await state.set_state(DebtFSM.wait_add_date)

@router.message(DebtFSM.wait_add_date)
async def debt_choose_date(message: Message, state: FSMContext):
    if message.text == "/cancel":
        await cancel_command(message, state)
        return
    
    date = message.text.strip()
    try:
        # Проверяем корректность даты
        datetime.strptime(date, "%Y-%m-%d")
    except ValueError:
        await message.answer("❌ Неверный формат даты. Используйте ГГГГ-ММ-ДД")
        return
        
    data = await state.get_data()
    await state.update_data(last_date=date)

    # Проверяем, не существует ли уже такой долг
    async with db.get_connection() as conn:
        async with conn.execute("""
            SELECT 1 FROM student_debts 
            WHERE student_id = ? AND discipline_id = ? AND debt_type_id = ? AND deleted_at IS NULL
        """, (data["student_id"], data["discipline_id"], data["debt_type_id"])) as cur:
            if await cur.fetchone():
                await message.answer("❌ Такой долг уже существует")
                return
    
    try:
        async with db.get_connection() as conn:
            await conn.execute("""
                INSERT INTO student_debts (student_id, discipline_id, debt_type_id, last_date, created_at, updated_at)
                VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            """, (data["student_id"], data["discipline_id"], data["debt_type_id"], date))
            await conn.commit()
            
        await safe_send_message(
            message,
            "✅ Долг успешно добавлен:\n"
            f"👤 Студент ID: {data['student_id']}\n"
            f"📚 Дисциплина ID: {data['discipline_id']}\n"
            f"ℹ️ Тип долга ID: {data['debt_type_id']}\n"
            f"⏳ Крайний срок: {date}",
            reply_markup=kb.debts_admin_kb
        )
    except Exception as e:
        logger.error(f"Ошибка при добавлении долга: {e}")
        await message.answer("❌ Произошла ошибка при добавлении долга")
    
    await state.set_state(DebtFSM.choose_action)

@router.message(DebtFSM.choose_action, F.text == "✏️ Редактировать долг")
async def debt_edit_start(message: Message, state: FSMContext):
    async with db.get_connection() as conn:
        async with conn.execute("""
            SELECT s.id_student, d.id, dt.id, s.login, subj.name, dt.name, sd.last_date
            FROM student_debts sd
            JOIN students s ON sd.student_id = s.id_student
            JOIN disciplines d ON sd.discipline_id = d.id
            JOIN subjects subj ON d.subject_id = subj.id
            JOIN debt_types dt ON sd.debt_type_id = dt.id
            WHERE sd.deleted_at IS NULL
            ORDER BY s.id_student
        """) as cur:
            debts = await cur.fetchall()
    
    if not debts:
        await message.answer("❌ Нет долгов для редактирования")
        return
    
    debts_list = []
    for d in debts:
        debts_list.append(f"{d[0]},{d[1]},{d[2]}: {d[3]} - {d[4]} ({d[5]}) до {d[6]} ")
    
    await safe_send_message(
        message,
        "📝 Выберите долг для редактирования (введите 3 ID через запятую - id студента, id дисциплины, id тип долга):\n" +
        "\n".join(debts_list),
        parse_mode=None
    )
    await state.set_state(DebtFSM.wait_edit_id)

@router.message(DebtFSM.wait_edit_id)
async def debt_edit_choose(message: Message, state: FSMContext):
    try:
        student_id, discipline_id, debt_type_id = map(int, message.text.strip().split(','))
    except ValueError:
        await message.answer("📝 Введите 3 ID через запятую - id студента, id дисциплины, id тип долга: ")
        return
    
    await state.update_data(
        student_id=student_id,
        discipline_id=discipline_id,
        debt_type_id=debt_type_id
    )
    
    await message.answer(
        "Что изменить?\n"
        "1.📚 Дисциплину\n"
        "2.ℹ️Тип долга\n"
        "3.⏳Крайний срок\n"
        "📝Введите номер пункта:"
    )
    await state.set_state(DebtFSM.wait_edit_field)

@router.message(DebtFSM.wait_edit_field)
async def debt_edit_field(message: Message, state: FSMContext):
    field_map = {
        "1": "discipline",
        "2": "type",
        "3": "date"
    }
    
    choice = message.text.strip()
    if choice not in field_map:
        await message.answer("📝 Введите номер от 1 до 3")
        return
    
    field = field_map[choice]
    await state.update_data(edit_field=field)
    
    data = await state.get_data()
    
    if field == "discipline":
        async with db.get_connection() as conn:
            # Получаем текущую дисциплину
            async with conn.execute("""
                SELECT d.id, s.name, t.full_name
                FROM disciplines d
                JOIN subjects s ON d.subject_id = s.id
                JOIN teachers t ON d.teacher_id = t.id
                WHERE d.id = ? 
            """, (data["discipline_id"],)) as cur:
                current = await cur.fetchone()
            
            # Получаем список всех дисциплин
            async with conn.execute("""
                SELECT d.id, s.name, t.full_name
                FROM disciplines d
                JOIN subjects s ON d.subject_id = s.id
                JOIN teachers t ON d.teacher_id = t.id
            """) as cur:
                disciplines = await cur.fetchall()
        
        disciplines_list = "\n".join([f"{d[0]}: {d[1]} ({d[2]})" for d in disciplines])
        await safe_send_message(
            message,
            f"📚 Текущая дисциплина: {current[1]} ({current[2]})\n"
            "📋 Выберите новую дисциплину (ID):\n" + disciplines_list,
            parse_mode=None
        )
        await state.set_state(DebtFSM.wait_edit_value)
    
    elif field == "type":
        async with db.get_connection() as conn:
            # Получаем текущий тип долга
            async with conn.execute("""
                SELECT dt.id, dt.name
                FROM debt_types dt
                WHERE dt.id = ?
            """, (data["debt_type_id"],)) as cur:
                current = await cur.fetchone()
            
            # Получаем все типы долгов
            async with conn.execute("SELECT id, name FROM debt_types") as cur:
                types = await cur.fetchall()
        
        types_list = "\n".join([f"{t[0]}: {t[1]}" for t in types])
        await safe_send_message(
            message,
            f"ℹ️ Текущий тип: {current[1]}\n"
            "📋 Выберите новый тип (ID):\n" + types_list,
            parse_mode=None
        )
        await state.set_state(DebtFSM.wait_edit_value)
    
    elif field == "date":
        # Получаем текущую дату
        async with db.get_connection() as conn:
            async with conn.execute("""
                SELECT last_date FROM student_debts
                WHERE student_id = ? AND discipline_id = ? AND debt_type_id = ?
            """, (data["student_id"], data["discipline_id"], data["debt_type_id"])) as cur:
                current_date = await cur.fetchone()
        
        await message.answer(
            f"⏳ Текущая дата: {current_date[0]}\n"
            "📝 Введите новую дату (ГГГГ-ММ-ДД):"
        )
        await state.set_state(DebtFSM.wait_edit_value)

@router.message(DebtFSM.wait_edit_value)
async def debt_edit_save(message: Message, state: FSMContext):
    data = await state.get_data()
    value = message.text.strip()
    
    try:
        async with db.get_connection() as conn:
            if data["edit_field"] == "discipline":
                await conn.execute("""
                    UPDATE student_debts 
                    SET discipline_id = ?, updated_at = CURRENT_TIMESTAMP
                    WHERE student_id = ? AND discipline_id = ? AND debt_type_id = ? AND deleted_at IS NULL
                """, (int(value), data["student_id"], data["discipline_id"], data["debt_type_id"]))
                    
            elif data["edit_field"] == "type":
                await conn.execute("""
                    UPDATE student_debts 
                    SET debt_type_id = ?, updated_at = CURRENT_TIMESTAMP
                    WHERE student_id = ? AND discipline_id = ? AND debt_type_id = ? AND deleted_at IS NULL
                """, (int(value), data["student_id"], data["discipline_id"], data["debt_type_id"]))
                
            elif data["edit_field"] == "date":
                try:
                    # Проверяем корректность даты
                    datetime.strptime(value, "%Y-%m-%d")
                except ValueError:
                    await message.answer("❌ Неверный формат даты. Используйте ГГГГ-ММ-ДД")
                    return
                
                await conn.execute("""
                    UPDATE student_debts 
                    SET last_date = ?, updated_at = CURRENT_TIMESTAMP
                    WHERE student_id = ? AND discipline_id = ? AND debt_type_id = ? AND deleted_at IS NULL
                """, (value, data["student_id"], data["discipline_id"], data["debt_type_id"]))

            
            await conn.commit()
        await message.answer("✅ Долг обновлен", reply_markup=kb.debts_admin_kb)
    except Exception as e:
        logger.error(f"Ошибка обновления долга: {e}")
        await message.answer("❌ Ошибка при обновлении")
    
    await state.set_state(DebtFSM.choose_action)

@router.message(DebtFSM.choose_action, F.text == "❌ Удалить долг")
async def debt_delete_start(message: Message, state: FSMContext):
    async with db.get_connection() as conn:
        async with conn.execute("""
            SELECT s.id_student, d.id, dt.id, s.login, subj.name, dt.name, sd.last_date
            FROM student_debts sd
            JOIN students s ON sd.student_id = s.id_student
            JOIN disciplines d ON sd.discipline_id = d.id
            JOIN subjects subj ON d.subject_id = subj.id
            JOIN debt_types dt ON sd.debt_type_id = dt.id
            WHERE deleted_at IS NULL
            ORDER BY s.id_student
        """) as cur:
            debts = await cur.fetchall()
    
    if not debts:
        await message.answer("❌ Нет долгов для удаления")
        return
    
    debts_list = []
    for d in debts:
        debts_list.append(f"{d[0]},{d[1]},{d[2]}: {d[3]} - {d[4]} ({d[5]}) до {d[6]}")
    
    await safe_send_message(
        message,
        "📝 Введите 3 ID через запятую - id студента, id дисциплины, id тип долга: \n" +
        "\n".join(debts_list),
        parse_mode=None
    )
    await state.set_state(DebtFSM.wait_del)

@router.message(DebtFSM.wait_del)
async def debt_delete(message: Message, state: FSMContext):
    if message.text == "/cancel":
        await cancel_command(message, state)
        return
        
    txt = message.text.strip().split(",")
    if len(txt) < 3:
        await message.answer("📝 Введите три числа через запятую: ")
        return
        
    try:
        student_id, discipline_id, debt_type_id = [int(x.strip()) for x in txt[:3]]
    except ValueError:
        await message.answer("❌ Введите числовые ID через запятую: ")
        return
        
    try:
        async with db.get_connection() as conn:
            await conn.execute("""
                UPDATE student_debts 
                SET deleted_at = CURRENT_TIMESTAMP,  
                    updated_at = CURRENT_TIMESTAMP
                WHERE student_id=? AND discipline_id=? AND debt_type_id=? AND deleted_at IS NULL
            """, (student_id, discipline_id, debt_type_id))
            await conn.commit()
        await message.answer("🗑️ Долг удален", reply_markup=kb.debts_admin_kb)
    except Exception as e:
        logger.error(f"Ошибка удаления долга: {e}")
        await message.answer("❌ Ошибка при удалении")
    await state.set_state(DebtFSM.choose_action)

# ==================== СПРАВКА ====================
@router.message(Command("help"))
async def help_command(message: Message, state: FSMContext):
    current_state = await state.get_state()
    if current_state == AuthStates.admin_mode.state:
        help_text = (
            "🛠 <b>Команды администратора</b>:\n\n"
            "👥 Управление пользователями - просмотр и редактирование пользователей\n"
            "📰 Управление новостями - добавление и публикация новостей\n"
            "📚 Управление предметами - редактирование списка предметов\n"
            "👨‍🏫 Управление преподавателями - редактирование списка преподавателей\n"
            "📊 Управление тестами - добавление и удаление тестов\n"
            "⏳ Управление долгами - просмотр и редактирование долгов студентов\n\n"
            "🔗 /unbind - отвязать текущего пользователя\n"
            "🚪 /logout - выйти из системы\n"
            "🗑️ /clear - очистить удаленные записи из БД\n"
            "❌ /cancel - отменить текущее действие"
        )
    else:
        help_text = (
            "ℹ️ <b>Доступные команды</b>:\n\n"
            "📅 Расписание - просмотр расписания\n"
            "📰 Новости - просмотр актуальных новостей\n"
            "📝 Задолженности - просмотр академических долгов\n"
            "📊 Тесты - просмотр предстоящих тестов\n\n"
            "✅ /start - войти в систему\n"
            "🔗 /unbind - отвязать текущего пользователя\n"
            "🚪 /logout - выйти из системы\n"
            "❌ /cancel - отменить текущее действие"
        )
    await message.answer(help_text, parse_mode="HTML")

@router.message(Command("clear"), AuthStates.admin_mode)
async def clear_command(message: Message):
    if await cleanup_deleted_records():
        await message.answer("🗑️ Удаленные записи очищены")
    else:
        await message.answer("❌ Произошла ошибка при очистке удаленных записей")

@router.message(StateFilter(any_state), F.text)  # Обрабатываем любое текстовое сообщение в любом состоянии
async def handle_unknown_command(message: Message, state: FSMContext):
    # Получаем текущее состояние
    current_state = await state.get_state()
    
    # Если состояние None или admin_mode/user_mode (основные состояния)
    if current_state is None or current_state in [AuthStates.admin_mode.state, AuthStates.user_mode.state]:
        await message.answer("❌ Неизвестная команда. Введите /help для справки")

@router.message(StateFilter(any_state), F.text)
async def handle_unknown_input(message: Message, state: FSMContext):
    current_state = await state.get_state()
    
    if current_state is None or current_state in [AuthStates.admin_mode.state, AuthStates.user_mode.state]:
        if message.text.startswith('/'):
            await message.answer("❌ Неизвестная команда. Введите /help для справки")
        else:
            await message.answer("❌ Неизвестная команда. Введите /help для справки")