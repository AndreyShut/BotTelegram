from aiogram import Router, F, types
from aiogram.types import Message, FSInputFile
from aiogram.filters import CommandStart, Command
from aiogram.fsm.state import State, StatesGroup, default_state
from aiogram.fsm.context import FSMContext
import logging
import app.keyboards as kb
from app.db_manager import db
from dotenv import load_dotenv
import os
from typing import Optional, Tuple, List

load_dotenv()

router = Router()
logger = logging.getLogger(__name__)
MAX_LOGIN_ATTEMPTS = 3

class AuthStates(StatesGroup):
    waiting_for_login = State()
    waiting_for_password = State()
    authorized = State()
    admin_mode = State()
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
    wait_edit_new_name = State()

class DebtFSM(StatesGroup):
    choose_action = State()
    wait_student = State()
    wait_add_disc = State()
    wait_add_type = State()
    wait_add_date = State()
    wait_del = State()

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
                "UPDATE students SET telegram_id = NULL WHERE telegram_id = ?",
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

# ==================== КОМАНДЫ АУТЕНТИФИКАЦИИ ====================
@router.message(CommandStart())
async def start(message: Message, state: FSMContext):
    student = await get_student_by_telegram(message.from_user.id)
    if student:
        if await is_admin(message.from_user.id):
            await message.answer("🔐 Вы авторизованы как администратор", reply_markup=kb.admin_kb)
            await state.set_state(AuthStates.admin_mode)
        else:
            await message.answer("Вы уже привязаны к профилю", reply_markup=kb.main)
            await state.set_state(AuthStates.authorized)
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
    if student and await db.verify_password(str(student[2]), password):
        if not student[4]:  # is_active
            await message.answer("Ваш аккаунт деактивирован. Обратитесь к администратору.")
            await state.clear()
            return
            
        if await get_student_by_telegram(message.from_user.id):
            await message.answer('Вы уже привязаны к профилю. Для отвязки используйте /unbind')
            await state.clear()
            return
            
        if await update_telegram_for_student(student[0], message.from_user.id):
            await message.answer('✅ Вы успешно авторизованы!', reply_markup=kb.main)
            await state.set_state(AuthStates.authorized)
            await state.update_data(is_admin=False)
        else:
            await message.answer('Ошибка привязки. Попробуйте позже.')
            await state.clear()
    else:
        await message.answer('Неверный логин или пароль. Попробуйте снова.\nЛогин:')
        await state.set_state(AuthStates.waiting_for_login)

@router.message(Command("unbind"))
async def unbind(message: Message, state: FSMContext):
    if await remove_telegram_binding(message.from_user.id):
        await message.answer("✅ Ваш Telegram был отвязан. Для входа используйте /start")
        await state.clear()
    else:
        await message.answer("❌ Ваш профиль не найден либо был уже отвязан.")

@router.message(Command("logout"))
async def logout(message: Message, state: FSMContext):
    await state.clear()
    await message.answer("✅ Вы успешно вышли. Для входа используйте /start", reply_markup=types.ReplyKeyboardRemove())

# ==================== ОБЩИЕ КОМАНДЫ ====================
@router.message(F.text == "🔙 Назад в меню")
async def back_to_main_menu(message: Message, state: FSMContext):
    data = await state.get_data()
    if data.get("is_admin"):
        await message.answer("Административное меню:", reply_markup=kb.admin_kb)
        await state.set_state(AuthStates.admin_mode)
    else:
        await message.answer("Главное меню:", reply_markup=kb.main)
        await state.set_state(AuthStates.authorized)

@router.message(F.text == "🔙 Назад в админку")
async def back_to_admin_menu(message: Message, state: FSMContext):
    await message.answer("Административное меню:", reply_markup=kb.admin_kb)
    await state.set_state(AuthStates.admin_mode)

@router.message(F.text == "🔙 В главное меню")
async def back_to_root_menu(message: Message, state: FSMContext):
    data = await state.get_data()
    if data.get("is_admin"):
        await message.answer("Административное меню:", reply_markup=kb.admin_kb)
        await state.set_state(AuthStates.admin_mode)
    else:
        await message.answer("Главное меню:", reply_markup=kb.main)
        await state.set_state(AuthStates.authorized)

# ==================== КОМАНДЫ ПОЛЬЗОВАТЕЛЯ ====================
from aiogram.types import FSInputFile

@router.message(F.text == "📅 Расписание")
async def show_schedule(message: Message):
    await message.answer("Выберите тип расписания:", reply_markup=kb.schedule_menu)

@router.message(F.text == "👥 Расписание групп")
async def show_group_schedule(message: Message):
    file_path = "Расписание_групп.xlsx"
    if os.path.exists(file_path):
        await message.answer_document(FSInputFile(file_path), caption="👥 Актуальное расписание групп")
    else:
        await message.answer("Файл расписания групп не найден, попробуйте позже.")

@router.message(F.text == "👨‍🏫 Расписание преподавателей")
async def show_teacher_schedule(message: Message):
    file_path = "Расписание_преподавателей.xls"
    if os.path.exists(file_path):
        await message.answer_document(FSInputFile(file_path), caption="👨‍🏫 Актуальное расписание преподавателей")
    else:
        await message.answer("Файл расписания преподавателей не найден, попробуйте позже.")

@router.message(F.text == "⏳ График приёма задолженностей")
async def show_debts_schedule(message: Message):
    file_path = "График_задолженностей.xlsx"
    if os.path.exists(file_path):
        await message.answer_document(FSInputFile(file_path), caption="⏳ График приёма задолженностей")
    else:
        await message.answer("Файл графика задолженностей не найден, попробуйте позже.")

@router.message(F.text == "📝 Задолженности")
async def show_debts(message: Message):
    student = await get_student_by_telegram(message.from_user.id)
    if not student:
        await message.answer("Сначала авторизуйтесь через /start", reply_markup=kb.main)
        return

    try:
        async with db.get_connection() as conn:
            async with conn.execute('''
                SELECT subj.name, dt.name, sd.last_date
                FROM student_debts sd
                JOIN disciplines d ON sd.discipline_id = d.id
                JOIN subjects subj ON d.subject_id = subj.id
                JOIN debt_types dt ON sd.debt_type_id = dt.id
                WHERE sd.student_id = ?
                ORDER BY sd.last_date
            ''', (student[0],)) as cursor:
                debts = await cursor.fetchall()

        if not debts:
            await message.answer("У вас нет академических задолженностей! 🎉")
            return

        response = "📝 Ваши задолженности:\n\n"
        for subj_name, debt_type, last_date in debts:
            response += (
                f"📚 {subj_name}\n"
                f"🔴 {debt_type}\n"
                f"⏳ Крайний срок: {last_date}\n"
                "----------\n"
            )
        await message.answer(response)
    except Exception as e:
        logger.error(f"Error fetching debts: {e}")
        await message.answer("❌ Ошибка получения информации о задолженностях.")

@router.message(F.text == "📊 Тесты")
async def show_tests(message: Message):
    student = await get_student_by_telegram(message.from_user.id)
    if not student:
        await message.answer("Сначала авторизуйтесь через /start", reply_markup=kb.main)
        return

    try:
        async with db.get_connection() as conn:
            async with conn.execute('''
                SELECT t.date, subj.name, tch.full_name, t.test_link
                FROM tests t
                JOIN disciplines d ON t.discipline_id = d.id
                JOIN subjects subj ON d.subject_id = subj.id
                JOIN teachers tch ON d.teacher_id = tch.id
                WHERE t.group_id = (SELECT id_group FROM students WHERE id_student = ?)
                ORDER BY t.date ASC
                LIMIT 10
            ''', (student[0],)) as cursor:
                tests = await cursor.fetchall()

        if not tests:
            await message.answer("У вашей группы нет ближайших тестов.")
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
        await message.answer(response, parse_mode="HTML")
    except Exception as e:
        logger.error(f"Error fetching tests: {e}")
        await message.answer("❌ Ошибка получения тестов.")

@router.message(F.text == "📰 Новости")
async def show_news(message: Message):
    try:
        student = await get_student_by_telegram(message.from_user.id)
        if not student:
            await message.answer("Сначала авторизуйтесь с помощью /start")
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
                await message.answer("📭 Новостей пока нет.")
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
        await message.answer("❌ Произошла ошибка при получении новостей.")

# ==================== АДМИНСКИЕ КОМАНДЫ ====================

# ==================== УПРАВЛЕНИЕ Тестами ====================

@router.message(AuthStates.admin_mode, F.text == "📊 Управление тестами")
async def manage_tests(message: Message, state: FSMContext):
    await message.answer(
        "Что сделать с тестами?\n"
        "/add_test – добавить тест\n"
        "/list_tests – список тестов\n"
        "/delete_test – удалить по ID", 
        reply_markup=kb.admin_kb
    )

@router.message(Command("add_test"))
async def test_add_start(message: Message, state: FSMContext):
    # Список групп
    async with db.get_connection() as conn:
        async with conn.execute("SELECT id, name_group FROM groups ORDER BY name_group") as cursor:
            groups = await cursor.fetchall()
    if not groups:
        await message.answer("Группы не заведены.")
        return
    await state.update_data(groups=groups)
    group_list = '\n'.join([f"{g[0]}: {g[1]}" for g in groups])
    await message.answer(f"Выберите ID группы теста:\n{group_list}")
    await state.set_state(add_test.waiting_group)

@router.message(add_test.waiting_group)
async def test_add_group(message: Message, state: FSMContext):
    try:
        group_id = int(message.text.strip())
    except ValueError:
        await message.answer("Введите числовой ID группы")
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
        await message.answer("Нет предметов у группы!")
        await state.set_state(AuthStates.admin_mode)
        return
    subject_list = '\n'.join([f"{sid}: {sname}" for sid, sname in subjects])
    await message.answer(f"Выберите ID предмета:\n{subject_list}")
    await state.set_state(add_test.waiting_subject)

@router.message(add_test.waiting_subject)
async def test_add_subject(message: Message, state: FSMContext):
    try: subject_id = int(message.text.strip())
    except ValueError:
        await message.answer("Введите числовой ID предмета")
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
        await message.answer("Нет преподавателей у этого предмета/группы!")
        await state.set_state(AuthStates.admin_mode)
        return
    teachers_str = '\n'.join([f"{tid}: {tname}" for tid, tname in teachers])
    await message.answer(f"Выберите ID преподавателя:\n{teachers_str}")
    await state.set_state(add_test.waiting_teacher)

@router.message(add_test.waiting_teacher)
async def test_add_teacher(message: Message, state: FSMContext):
    try: teacher_id = int(message.text.strip())
    except ValueError:
        await message.answer("Введите числовой ID преподавателя")
        return
    await state.update_data(teacher_id=teacher_id)
    await message.answer("Вставьте ссылку на тест:")
    await state.set_state(add_test.waiting_link)

@router.message(add_test.waiting_link)
async def test_add_link(message: Message, state: FSMContext):
    link = message.text.strip()
    await state.update_data(test_link=link)
    await message.answer("Введите дату теста (ГГГГ-ММ-ДД):")
    await state.set_state(add_test.waiting_date)

@router.message(add_test.waiting_date)
async def test_add_date(message: Message, state: FSMContext):
    date = message.text.strip()
    data = await state.get_data()
    # Тут надо получить discipline_id
    async with db.get_connection() as conn:
        async with conn.execute('''
            SELECT id FROM disciplines 
            WHERE subject_id = ? AND teacher_id = ? AND group_id = ?
        ''', (data["subject_id"], data["teacher_id"], data["group_id"])) as cursor:
            discipline = await cursor.fetchone()
    if not discipline:
        await message.answer("Не найдено дисциплины с такой комбинацией.")
        await state.set_state(AuthStates.admin_mode)
        return
    try:
        async with db.get_connection() as conn:
            await conn.execute('''
                INSERT INTO tests (group_id, discipline_id, test_link, date)
                VALUES (?, ?, ?, ?)
            ''', (data["group_id"], discipline[0], data["test_link"], date))
            await conn.commit()
        await message.answer("✅ Тест добавлен!", reply_markup=kb.admin_kb)
    except Exception as e:
        logger.error(f"Ошибка добавления теста: {e}")
        await message.answer("❌ Не удалось добавить тест.")
    await state.set_state(AuthStates.admin_mode)

# ==================== УПРАВЛЕНИЕ НОВОСТЯМИ ====================
@router.message(AuthStates.admin_mode, F.text == "📰 Управление новостями")
async def manage_news(message: Message):
    await message.answer("📰 Управление новостями:", reply_markup=kb.news_admin_kb)

@router.message(AuthStates.admin_mode, F.text == "📝 Добавить новость")
async def add_news_start(message: Message, state: FSMContext):
    await message.answer("Введите заголовок новости (или /cancel для отмены):")
    await state.set_state(AuthStates.add_news_title)

@router.message(AuthStates.add_news_title)
async def add_news_title(message: Message, state: FSMContext):
    await state.update_data(title=message.text)
    await message.answer("Введите описание новости (или /cancel для отмены):")
    await state.set_state(AuthStates.add_news_description)

@router.message(AuthStates.add_news_description)
async def add_news_description(message: Message, state: FSMContext):
    await state.update_data(description=message.text)
    await message.answer("Введите дату новости в формате ГГГГ-ММ-ДД (или /cancel для отмены):")
    await state.set_state(AuthStates.add_news_date)

@router.message(AuthStates.add_news_date)
async def add_news_date(message: Message, state: FSMContext):
    await state.update_data(date=message.text)
    await message.answer("Введите место проведения (если есть) или /skip для пропуска (/cancel для отмены):")
    await state.set_state(AuthStates.add_news_place)

@router.message(AuthStates.add_news_place, Command("skip"))
async def skip_news_place(message: Message, state: FSMContext):
    await state.update_data(place=None)
    await message.answer("Новость для всех групп? (да/нет) (/cancel для отмены)")
    await state.set_state(AuthStates.add_news_groups)

@router.message(AuthStates.add_news_place)
async def add_news_place(message: Message, state: FSMContext):
    await state.update_data(place=message.text)
    await message.answer("Новость для всех групп? (да/нет) (/cancel для отмены)")
    await state.set_state(AuthStates.add_news_groups)

@router.message(AuthStates.add_news_groups)
async def add_news_groups(message: Message, state: FSMContext):
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
                await message.answer(f"Введите ID групп через запятую:\n{gr}")
                await state.set_state("waiting_for_group_ids")
                await conn.commit()  # Зафиксируем создание новости
                return
            await conn.commit()
            await message.answer(f"✅ Новость успешно добавлена! ID: {news_id}", reply_markup=kb.admin_kb)
            await state.set_state(AuthStates.admin_mode)
    except Exception as e:
        logger.error(f"Error adding news: {e}")
        await message.answer("❌ Ошибка при добавлении новости", reply_markup=kb.admin_kb)
        await state.set_state(AuthStates.admin_mode)

# Добиваем состояние для id групп
@router.message(State("waiting_for_group_ids"))
async def add_news_group_ids(message: Message, state: FSMContext):
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
        await message.answer("✅ Новость добавлена и привязана к группам!", reply_markup=kb.admin_kb)
    except Exception as e:
        logger.error(f"Error attaching news to groups: {e}")
        await message.answer("❌ Ошибка при связывании новости и групп.", reply_markup=kb.admin_kb)
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
            await message.answer("📭 Новостей пока нет.")
            return
            
        response = "📰 Последние новости:\n\n"
        for news in news_list:
            news_id, title, date, is_published = news
            status = "✅ Опубликована" if is_published else "⏳ Не опубликована"
            response += f"📌 <b>{title}</b>\n📅 {date}\n{status}\nID: {news_id}\n\n"
        
        await message.answer(response, parse_mode="HTML")
    
    except Exception as e:
        logger.error(f"Error fetching news list: {e}")
        await message.answer("❌ Ошибка при получении списка новостей.")

@router.message(AuthStates.admin_mode, F.text == "📢 Опубликовать новость")
async def publish_news_start(message: Message, state: FSMContext):
    await message.answer("Введите ID новости для публикации (/cancel для отмены):")
    await state.set_state(AuthStates.publish_news)

@router.message(AuthStates.publish_news)
async def publish_news_execute(message: Message, state: FSMContext):
    try:
        news_id = int(message.text)
        async with db.get_connection() as conn:
            await conn.execute(
                "UPDATE news SET is_published = 1 WHERE id = ?",
                (news_id,))
            await conn.commit()
            await message.answer(f"✅ Новость с ID {news_id} опубликована!", reply_markup=kb.admin_kb)
            await state.set_state(AuthStates.admin_mode)
    except ValueError:
        await message.answer("❌ Введите корректный ID новости (число)")
    except Exception as e:
        logger.error(f"Error publishing news: {e}")
        await message.answer("❌ Ошибка при публикации новости", reply_markup=kb.admin_kb)
        await state.set_state(AuthStates.admin_mode)

@router.message(AuthStates.admin_mode, F.text == "❌ Удалить новость")
async def delete_news_start(message: Message, state: FSMContext):
    await message.answer("Введите ID новости для удаления (/cancel для отмены):")
    await state.set_state(AuthStates.delete_news)

@router.message(AuthStates.delete_news)
async def delete_news_execute(message: Message, state: FSMContext):
    try:
        news_id = int(message.text)
        async with db.get_connection() as conn:
            await conn.execute("DELETE FROM news_groups WHERE news_id = ?", (news_id,))
            await conn.execute("DELETE FROM news WHERE id = ?", (news_id,))
            await conn.commit()
            await message.answer(f"✅ Новость с ID {news_id} удалена!", reply_markup=kb.admin_kb)
            await state.set_state(AuthStates.admin_mode)
    except ValueError:
        await message.answer("❌ Введите корректный ID новости (число)")
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
        
        response += "\nВведите ID пользователя для отвязки или /all для отвязки всех (/cancel для отмены):"
        await message.answer(response)
        await state.set_state(AuthStates.unbind_user_select)
    
    except Exception as e:
        logger.error(f"Error fetching users list: {e}")
        await message.answer("❌ Ошибка при получении списка пользователей.")

@router.message(AuthStates.unbind_user_select, Command("all"))
async def unbind_all_confirm(message: Message, state: FSMContext):
    await message.answer("⚠️ Вы уверены, что хотите отвязать ВСЕХ пользователей? (да/нет) (/cancel для отмены)")
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
            
        await message.answer("✅ Все пользователи успешно отвязаны!", reply_markup=kb.admin_kb)
        await state.set_state(AuthStates.admin_mode)
    except Exception as e:
        logger.error(f"Error unbinding all users: {e}")
        await message.answer("❌ Ошибка при отвязке пользователей", reply_markup=kb.admin_kb)
        await state.set_state(AuthStates.admin_mode)

@router.message(AuthStates.unbind_user_select)
async def unbind_single_user(message: Message, state: FSMContext):
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
                await message.answer("❌ Пользователь с таким ID не найден.")
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
            
        await message.answer(f"✅ Пользователь с ID {user_id} успешно отвязан!", reply_markup=kb.admin_kb)
        await state.set_state(AuthStates.admin_mode)
    except ValueError:
        await message.answer("❌ Введите корректный ID пользователя (число) или /all (/cancel для отмены)")
    except Exception as e:
        logger.error(f"Error unbinding user: {e}")
        await message.answer("❌ Ошибка при отвязке пользователя", reply_markup=kb.admin_kb)
        await state.set_state(AuthStates.admin_mode)

@router.message(AuthStates.admin_mode, F.text == "👤 Добавить студента")
async def add_student_start(message: Message, state: FSMContext):
    await message.answer("Введите логин нового студента (/cancel для отмены):")
    await state.set_state(add_states.waiting_login)

@router.message(add_states.waiting_login)
async def add_student_login(message: Message, state: FSMContext):
    login = message.text.strip()
    # Проверка уникальности логина
    async with db.get_connection() as conn:
        async with conn.execute("SELECT 1 FROM students WHERE login = ?", (login,)) as cur:
            exists = await cur.fetchone()
    if exists:
        await message.answer("Студент с таким логином уже есть. Введите другой логин:")
        return
    await state.update_data(login=login)
    await message.answer("Укажите пароль для студента:")
    await state.set_state(add_states.waiting_password)

@router.message(add_states.waiting_password)
async def add_student_password(message: Message, state: FSMContext):
    password = message.text.strip()
    await state.update_data(password=password)
    # Покажем список групп
    async with db.get_connection() as conn:
        async with conn.execute("SELECT id, name_group FROM groups ORDER BY name_group") as cursor:
            groups = await cursor.fetchall()
    group_list = "\n".join([f"{gid}: {gname}" for gid, gname in groups])
    await message.answer(f"Выберите ID группы для студента:\n{group_list}")
    await state.set_state(add_states.waiting_group)

@router.message(add_states.waiting_group)
async def add_student_group(message: Message, state: FSMContext):
    try:
        group_id = int(message.text.strip())
        async with db.get_connection() as conn:
            async with conn.execute("SELECT name_group FROM groups WHERE id = ?", (group_id,)) as cur:
                group = await cur.fetchone()
        if not group:
            await message.answer("Группа не найдена. Введите корректный ID:")
            return
    except ValueError:
        await message.answer("Введите числовой ID группы.")
        return

    await state.update_data(group_id=group_id)
    await message.answer("Введите дополнительное описание/ФИО или /skip для пропуска:")
    await state.set_state(add_states.waiting_description)

@router.message(add_states.waiting_description, Command("skip"))
async def add_student_skip_desc(message: Message, state: FSMContext):
    await state.update_data(description=None)
    await finish_student_add(message, state)

@router.message(add_states.waiting_description)
async def add_student_desc(message: Message, state: FSMContext):
    await state.update_data(description=message.text)
    await finish_student_add(message, state)

async def finish_student_add(message: Message, state: FSMContext):
    data = await state.get_data()
    # Вставляем в БД
    try:
        password = await db.hash_password(data["password"])
        async with db.get_connection() as conn:
            await conn.execute('''
                INSERT INTO students (login, password, id_group, description) 
                VALUES (?, ?, ?, ?)
            ''', (data["login"], password, data["group_id"], data.get("description")))
            await conn.commit()
        await message.answer(f"✅ Студент {data['login']} добавлен.", reply_markup=kb.admin_kb)
    except Exception as e:
        logger.error(f"Ошибка добавления студента: {e}")
        await message.answer("❌ Не удалось добавить студента (см. лог).")
    await state.set_state(AuthStates.admin_mode)

@router.message(AuthStates.admin_mode, F.text == "📋 Список студентов")
async def list_students(message: Message):
    try:
        async with db.get_connection() as conn:
            async with conn.execute('''
                SELECT s.id_student, s.login, s.telegram_id, g.name_group, s.is_active 
                FROM students s
                JOIN groups g ON s.id_group = g.id
                ORDER BY g.name_group, s.login
            ''') as cursor:
                students = await cursor.fetchall()
        
        if not students:
            await message.answer("🤷 Нет студентов в базе.")
            return
            
        response = "👥 Список студентов:\n\n"
        for student in students:
            student_id, login, tg_id, group, is_active = student
            status = "✅ Активен" if is_active else "❌ Неактивен"
            tg_status = f"TG: {tg_id}" if tg_id else "TG: не привязан"
            response += f"👤 {login} (Группа: {group})\nID: {student_id} | {tg_status} | {status}\n\n"
        
        await message.answer(response)
    
    except Exception as e:
        logger.error(f"Error fetching students list: {e}")
        await message.answer("❌ Ошибка при получении списка студентов.")

@router.message(AuthStates.admin_mode, F.text == "✏️ Редактировать студента")
async def edit_student_start(message: Message, state: FSMContext):
    # список студентов
    async with db.get_connection() as conn:
        async with conn.execute("""
            SELECT s.id_student, s.login, g.name_group, s.is_active
            FROM students s
            JOIN groups g ON s.id_group = g.id
            ORDER BY s.id_student
        """) as cur:
            students = await cur.fetchall()
    msg = "Выберите ID студента для редактирования:\n"
    msg += "\n".join([f"{s[0]}: {s[1]} ({s[2]}) [{('Активен' if s[3] else 'Неактивен')}]" for s in students])
    await message.answer(msg)
    await state.set_state(edit_st.waiting_id)

@router.message(edit_st.waiting_id)
async def edit_student_select(message: Message, state: FSMContext):
    try:
        student_id = int(message.text.strip())
    except ValueError:
        await message.answer("Введите корректный ID студента!")
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
        await message.answer("Студент не найден.")
        await state.set_state(AuthStates.admin_mode)
        return

    # Сохраняем инфу в FSM
    await state.update_data(
        id_student=student[0], login=student[1], password=student[2], group_name=student[3],
        is_active=student[4], description=student[5] or "", id_group=student[6]
    )
    msg = (
        f"Выбран студент:\n"
        f"<b>Логин:</b> {student[1]}\n"
        f"<b>Группа:</b> {student[3]}\n"
        f"<b>Описание:</b> {student[5] or 'Нет'}\n"
        f"<b>Статус:</b> {'Активен' if student[4] else 'Неактивен'}\n\n"
        f"Что изменить?"
    )
    await message.answer(msg, reply_markup=kb.edit_student_kb, parse_mode="HTML")
    await state.set_state(edit_st.main_menu)

@router.message(edit_st.main_menu)
async def edit_student_options(message: Message, state: FSMContext):
    text = message.text.lower()
    edit_map = {
        "логин": edit_st.editing_login,
        "пароль": edit_st.editing_password,
        "группа": edit_st.editing_group,
        "статус": edit_st.editing_status,
        "описание": edit_st.editing_description,
        "сохранить": edit_st.confirm
    }
    # Выйти в меню
    if "отмена" in text or "назад" in text:
        await message.answer("Редактирование отменено.", reply_markup=kb.admin_kb)
        await state.set_state(AuthStates.admin_mode)
        return
    for k, v in edit_map.items():
        if k in text:
            await state.set_state(v)
            if v == edit_st.editing_login:
                await message.answer("Введите новый логин:")
            elif v == edit_st.editing_password:
                await message.answer("Введите новый пароль:")
            elif v == edit_st.editing_group:
                async with db.get_connection() as conn:
                    async with conn.execute("SELECT id,name_group FROM groups") as cur:
                        groups = await cur.fetchall()
                gr = '\n'.join(f"{gid}:{gname}" for gid, gname in groups)
                await message.answer(f"Выберите ID группы:\n{gr}")
            elif v == edit_st.editing_status:
                await message.answer("Введите новый статус (1 для активен, 0 для неактивен):")
            elif v == edit_st.editing_description:
                await message.answer("Введите новое описание:")
            elif v == edit_st.confirm:
                await edit_student_save(message, state)
            return
    await message.answer("Выберите действие через кнопки.", reply_markup=kb.edit_student_kb)

@router.message(edit_st.editing_login)
async def edit_student_login(message: Message, state: FSMContext):
    await state.update_data(login=message.text.strip())
    await message.answer("Логин изменен. Дальше?", reply_markup=kb.edit_student_kb)
    await state.set_state(edit_st.main_menu)

@router.message(edit_st.editing_password)
async def edit_student_password(message: Message, state: FSMContext):
    password = await db.hash_password(message.text.strip())
    await state.update_data(password=password)
    await message.answer("Пароль изменен. Дальше?", reply_markup=kb.edit_student_kb)
    await state.set_state(edit_st.main_menu)

@router.message(edit_st.editing_group)
async def edit_student_group(message: Message, state: FSMContext):
    try:
        group_id = int(message.text.strip())
        # Проверить корректность
        async with db.get_connection() as conn:
            async with conn.execute("SELECT name_group FROM groups WHERE id = ?", (group_id,)) as cur:
                group = await cur.fetchone()
        if not group:
            await message.answer("Группа не найдена. Введите ID ещё раз.")
            return
    except ValueError:
        await message.answer("ID группы только число!")
        return
    await state.update_data(id_group=group_id, group_name=group[0])
    await message.answer("Группа изменена. Дальше?", reply_markup=kb.edit_student_kb)
    await state.set_state(edit_st.main_menu)

@router.message(edit_st.editing_status)
async def edit_student_status(message: Message, state: FSMContext):
    text = message.text.strip()
    if text not in ["0", "1"]:
        await message.answer("Введите 0 (неактивен) или 1 (активен).")
        return
    is_active = int(text)
    await state.update_data(is_active=is_active)
    await message.answer("Статус изменен. Дальше?", reply_markup=kb.edit_student_kb)
    await state.set_state(edit_st.main_menu)

@router.message(edit_st.editing_description)
async def edit_student_description(message: Message, state: FSMContext):
    await state.update_data(description=message.text.strip())
    await message.answer("Описание изменено. Дальше?", reply_markup=kb.edit_student_kb)
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
        await message.answer("✅ Данные студента изменены.", reply_markup=kb.admin_kb)
    except Exception as e:
        logger.error(f"Ошибка при сохранении студента: {e}")
        await message.answer("❌ Ошибка обновления!")
    await state.set_state(AuthStates.admin_mode)

@router.message(AuthStates.admin_mode, F.text == "❌ Удалить студента")
async def delete_student_start(message: Message, state: FSMContext):
    await message.answer("Введите ID студента для удаления (/cancel для отмены):")
    await state.set_state(AuthStates.delete_student)

@router.message(AuthStates.delete_student)
async def delete_student_process(message: Message, state: FSMContext):
    try:
        student_id = int(message.text)
        async with db.get_connection() as conn:
            await conn.execute("DELETE FROM students WHERE id_student = ?", (student_id,))
            await conn.commit()
            await message.answer(f"✅ Студент с ID {student_id} удален!", reply_markup=kb.admin_kb)
            await state.set_state(AuthStates.admin_mode)
    except ValueError:
        await message.answer("❌ Введите корректный ID студента (число)")
    except Exception as e:
        logger.error(f"Error deleting student: {e}")
        await message.answer("❌ Ошибка при удалении студента", reply_markup=kb.admin_kb)
        await state.set_state(AuthStates.admin_mode)
# ==================== Управление предметами ====================

@router.message(AuthStates.admin_mode, F.text == "📚 Управление предметами")
async def manage_subjects(message: Message, state: FSMContext):
    await message.answer(
        "Что сделать с предметами?",
        reply_markup=kb.subjects_admin_kb
    )
    await state.set_state(SubjectFSM.choose_action)

@router.message(SubjectFSM.choose_action)
async def subject_action(message: Message, state: FSMContext):
    txt = message.text.lower()
    if "добавить" in txt:
        await message.answer("Введите название предмета:")
        await state.set_state(SubjectFSM.wait_name)
    elif "список" in txt:
        async with db.get_connection() as conn:
            async with conn.execute("SELECT id, name FROM subjects ORDER BY name") as cur:
                subs = await cur.fetchall()
        await message.answer(
            "📚 Предметы:\n" +
            "\n".join([f"{x[0]}: {x[1]}" for x in subs]),
            reply_markup=kb.subjects_admin_kb
        )
    elif "удалить" in txt:
        async with db.get_connection() as conn:
            async with conn.execute("SELECT id, name FROM subjects ORDER BY name") as cur:
                subs = await cur.fetchall()
        await message.answer("Введите ID предмета для удаления:\n" +
            "\n".join([f"{x[0]}: {x[1]}" for x in subs])
        )
        await state.set_state(SubjectFSM.wait_id)
    elif "редактировать" in txt:
        async with db.get_connection() as conn:
            async with conn.execute("SELECT id, name FROM subjects ORDER BY name") as cur:
                subs = await cur.fetchall()
        await message.answer("Введите ID предмета для редактирования:\n" +
            "\n".join([f"{x[0]}: {x[1]}" for x in subs])
        )
        await state.set_state(SubjectFSM.wait_id)
    elif "назад" in txt:
        await message.answer("Админ-меню", reply_markup=kb.admin_kb)
        await state.set_state(AuthStates.admin_mode)
    else:
        await message.answer("Выберите действие через кнопки.", reply_markup=kb.subjects_admin_kb)

@router.message(SubjectFSM.wait_name)
async def subject_add(message: Message, state: FSMContext):
    name = message.text.strip()
    try:
        async with db.get_connection() as conn:
            await conn.execute("INSERT INTO subjects (name) VALUES (?)", (name,))
            await conn.commit()
        await message.answer(f"✅ Предмет \"{name}\" добавлен", reply_markup=kb.subjects_admin_kb)
    except Exception as e:
        logger.error(f"Ошибка добавления предмета: {e}")
        await message.answer("❌ Ошибка добавления.")
    await state.set_state(SubjectFSM.choose_action)

@router.message(SubjectFSM.wait_id)
async def subject_edit_delete(message: Message, state: FSMContext):
    try:
        subj_id = int(message.text.strip())
    except ValueError:
        await message.answer("ID должно быть числом.")
        return
    txt = (await state.get_state())
    if txt.endswith("wait_id"):
        # запоминаем id
        await state.update_data(subj_id=subj_id)
        await message.answer("Введите новое название предмета или /del для удаления:")
        await state.set_state(SubjectFSM.wait_edit_new_name)

@router.message(SubjectFSM.wait_edit_new_name, Command("del"))
async def subject_del(message: Message, state: FSMContext):
    subj_id = (await state.get_data()).get("subj_id")
    try:
        async with db.get_connection() as conn:
            await conn.execute("DELETE FROM subjects WHERE id = ?", (subj_id,))
            await conn.commit()
        await message.answer("🗑️ Предмет удален.", reply_markup=kb.subjects_admin_kb)
    except Exception as e:
        logger.error(f"Ошибка удаления предмета: {e}")
        await message.answer("❌ Ошибка удаления.")
    await state.set_state(SubjectFSM.choose_action)

@router.message(SubjectFSM.wait_edit_new_name)
async def subject_edit_name(message: Message, state: FSMContext):
    new_name = message.text.strip()
    subj_id = (await state.get_data()).get("subj_id")
    try:
        async with db.get_connection() as conn:
            await conn.execute("UPDATE subjects SET name = ? WHERE id = ?", (new_name, subj_id))
            await conn.commit()
        await message.answer("✅ Название предмета изменено.", reply_markup=kb.subjects_admin_kb)
    except Exception as e:
        logger.error(f"Ошибка изменения предмета: {e}")
        await message.answer("❌ Не удалось изменить.")
    await state.set_state(SubjectFSM.choose_action)

# ==================== Управление преподавателями ====================

@router.message(AuthStates.admin_mode, F.text == "👨‍🏫 Управление преподавателями")
async def manage_teachers(message: Message, state: FSMContext):
    await message.answer(
        "Что сделать с преподавателями?",
        reply_markup=kb.teachers_admin_kb
    )
    await state.set_state(TeacherFSM.choose_action)

@router.message(TeacherFSM.choose_action)
async def teacher_action(message: Message, state: FSMContext):
    txt = message.text.lower()
    if "добавить" in txt:
        await message.answer("Введите ФИО преподавателя:")
        await state.set_state(TeacherFSM.wait_name)
    elif "список" in txt:
        async with db.get_connection() as conn:
            async with conn.execute("SELECT id, full_name FROM teachers ORDER BY full_name") as cur:
                ts = await cur.fetchall()
        await message.answer(
            "👨‍🏫 Преподаватели:\n" +
            "\n".join([f"{x[0]}: {x[1]}" for x in ts]),
            reply_markup=kb.teachers_admin_kb
        )
    elif "удалить" in txt or "редактировать" in txt:
        async with db.get_connection() as conn:
            async with conn.execute("SELECT id, full_name FROM teachers ORDER BY full_name") as cur:
                ts = await cur.fetchall()
        await message.answer("Введите ID преподавателя:\n" +
            "\n".join([f"{x[0]}: {x[1]}" for x in ts])
        )
        await state.set_state(TeacherFSM.wait_id)
    elif "назад" in txt:
        await message.answer("Админ-меню", reply_markup=kb.admin_kb)
        await state.set_state(AuthStates.admin_mode)
    else:
        await message.answer("Выберите действие через кнопки.", reply_markup=kb.teachers_admin_kb)

@router.message(TeacherFSM.wait_name)
async def teacher_add(message: Message, state: FSMContext):
    name = message.text.strip()
    try:
        async with db.get_connection() as conn:
            await conn.execute("INSERT INTO teachers (full_name) VALUES (?)", (name,))
            await conn.commit()
        await message.answer(f"✅ Преподаватель \"{name}\" добавлен", reply_markup=kb.teachers_admin_kb)
    except Exception as e:
        logger.error(f"Ошибка добавления: {e}")
        await message.answer("❌ Ошибка добавления.")
    await state.set_state(TeacherFSM.choose_action)

@router.message(TeacherFSM.wait_id)
async def teacher_edit_delete(message: Message, state: FSMContext):
    try:
        teacher_id = int(message.text.strip())
    except ValueError:
        await message.answer("ID должно быть числом.")
        return
    await state.update_data(teacher_id=teacher_id)
    await message.answer("Введите новое ФИО преподавателя или /del для удаления:")

@router.message(TeacherFSM.wait_id, Command("del"))
async def teacher_del(message: Message, state: FSMContext):
    teacher_id = (await state.get_data()).get("teacher_id")
    try:
        async with db.get_connection() as conn:
            await conn.execute("DELETE FROM teachers WHERE id = ?", (teacher_id,))
            await conn.commit()
        await message.answer("🗑️ Преподаватель удален.", reply_markup=kb.teachers_admin_kb)
    except Exception as e:
        logger.error(f"Ошибка удаления преподавателя: {e}")
        await message.answer("❌ Ошибка удаления.")
    await state.set_state(TeacherFSM.choose_action)

@router.message(TeacherFSM.wait_id)
async def teacher_edit_name(message: Message, state: FSMContext):
    new_name = message.text.strip()
    teacher_id = (await state.get_data()).get("teacher_id")
    try:
        async with db.get_connection() as conn:
            await conn.execute("UPDATE teachers SET full_name = ? WHERE id = ?", (new_name, teacher_id))
            await conn.commit()
        await message.answer("✅ Имя преподавателя изменено.", reply_markup=kb.teachers_admin_kb)
    except Exception as e:
        logger.error(f"Ошибка изменения преподавателя: {e}")
        await message.answer("❌ Не удалось изменить.")
    await state.set_state(TeacherFSM.choose_action)

# ==================== Управление долгами ====================


@router.message(AuthStates.admin_mode, F.text == "⏳ Управление долгами")
async def manage_debts(message: Message, state: FSMContext):
    await message.answer(
        "Что сделать с долгами?",
        reply_markup=kb.debts_admin_kb
    )
    await state.set_state(DebtFSM.choose_action)

@router.message(DebtFSM.choose_action)
async def debt_action(message: Message, state: FSMContext):
    txt = message.text.lower()
    if "список" in txt:
        async with db.get_connection() as conn:
            async with conn.execute("""
                SELECT s.id_student, s.login, subj.name, dt.name, sd.last_date
                FROM student_debts sd
                JOIN students s ON sd.student_id = s.id_student
                JOIN disciplines d ON sd.discipline_id = d.id
                JOIN subjects subj ON d.subject_id = subj.id
                JOIN debt_types dt ON sd.debt_type_id = dt.id
                ORDER BY s.id_student
            """) as cur:
                debts = await cur.fetchall()
        msg = "Задолженности студентов\n"
        for st in debts:
            msg += f"{st[0]}: {st[1]} по {st[2]} ({st[3]}) - до {st[4]}\n"
        await message.answer(msg)
    elif "добавить" in txt:
        # Выбор студента
        async with db.get_connection() as conn:
            async with conn.execute("SELECT id_student, login FROM students ORDER BY login") as cur:
                studs = await cur.fetchall()
        await message.answer("Выберите ID студента:\n" + "\n".join([f"{s[0]}: {s[1]}" for s in studs]))
        await state.set_state(DebtFSM.wait_student)
    elif "удалить" in txt:
        async with db.get_connection() as conn:
            async with conn.execute("""
                SELECT s.id_student, s.login, subj.name, dt.name, sd.last_date
                FROM student_debts sd
                JOIN students s ON sd.student_id = s.id_student
                JOIN disciplines d ON sd.discipline_id = d.id
                JOIN subjects subj ON d.subject_id = subj.id
                JOIN debt_types dt ON sd.debt_type_id = dt.id
                ORDER BY s.id_student
            """) as cur:
                debts = await cur.fetchall()
        await message.answer("Введите ID студента/предмета/типа долга через запятую (id_student, discipline_id, debt_type_id) для удаления:\n" +
            "\n".join([f"{x[0]}|{x[2]}|{x[3]}" for x in debts])
        )
        await state.set_state(DebtFSM.wait_del)
    elif "назад" in txt:
        await message.answer("Админ-меню", reply_markup=kb.admin_kb)
        await state.set_state(AuthStates.admin_mode)
    else:
        await message.answer("Выберите действие через кнопки.", reply_markup=kb.debts_admin_kb)

@router.message(DebtFSM.wait_student)
async def debt_choose_student(message: Message, state: FSMContext):
    try:
        student_id = int(message.text.strip())
    except ValueError:
        await message.answer("Только ID числа")
        return
    await state.update_data(student_id=student_id)
    # Список дисциплин студента
    async with db.get_connection() as conn:
        async with conn.execute("""
            SELECT d.id, s.name, t.full_name
            FROM disciplines d
            JOIN subjects s ON d.subject_id = s.id
            JOIN teachers t ON d.teacher_id = t.id
            JOIN students st ON st.id_group = d.group_id
            WHERE st.id_student = ?
        """, (student_id,)) as cur:
            discs = await cur.fetchall()
    if not discs:
        await message.answer("Нет предметов.")
        await state.set_state(DebtFSM.choose_action)
        return
    await message.answer("ID дисциплины:\n" +
        "\n".join([f"{d[0]}: {d[1]} ({d[2]})" for d in discs])
    )
    await state.set_state(DebtFSM.wait_add_disc)

@router.message(DebtFSM.wait_add_disc)
async def debt_choose_disc(message: Message, state: FSMContext):
    try:
        discipline_id = int(message.text.strip())
    except ValueError:
        await message.answer("Только ID числа")
        return
    await state.update_data(discipline_id=discipline_id)
    # виды долгов
    async with db.get_connection() as conn:
        async with conn.execute("SELECT id, name FROM debt_types") as cur:
            types = await cur.fetchall()
    await message.answer("ID типа долга:\n" + "\n".join([f"{t[0]}: {t[1]}" for t in types]))
    await state.set_state(DebtFSM.wait_add_type)

@router.message(DebtFSM.wait_add_type)
async def debt_choose_type(message: Message, state: FSMContext):
    try:
        debt_type_id = int(message.text.strip())
    except ValueError:
        await message.answer("ID только число")
        return
    await state.update_data(debt_type_id=debt_type_id)
    await message.answer("Крайний срок (ГГГГ-ММ-ДД):")
    await state.set_state(DebtFSM.wait_add_date)

@router.message(DebtFSM.wait_add_date)
async def debt_choose_date(message: Message, state: FSMContext):
    date = message.text.strip()
    data = await state.get_data()
    try:
        async with db.get_connection() as conn:
            await conn.execute("""
                INSERT INTO student_debts (student_id,discipline_id,debt_type_id,last_date) VALUES (?,?,?,?)
            """, (data["student_id"], data["discipline_id"], data["debt_type_id"], date))
            await conn.commit()
        await message.answer("✅ Долг добавлен.", reply_markup=kb.debts_admin_kb)
    except Exception as e:
        logger.error(f"Ошибка добавления долга: {e}")
        await message.answer("❌ Ошибка добавления.")
    await state.set_state(DebtFSM.choose_action)

@router.message(DebtFSM.wait_del)
async def debt_delete(message: Message, state: FSMContext):
    txt = message.text.strip().split(",")
    if len(txt) < 3:
        await message.answer("Введите три числа через запятую.")
        return
    student_id, discipline_id, debt_type_id = txt[:3]
    try:
        async with db.get_connection() as conn:
            await conn.execute("""
                DELETE FROM student_debts WHERE student_id=? AND discipline_id=? AND debt_type_id=?
            """, (student_id,discipline_id,debt_type_id))
            await conn.commit()
        await message.answer("🗑️ Долг удален.", reply_markup=kb.debts_admin_kb)
    except Exception as e:
        logger.error(f"Ошибка удаления долга: {e}")
        await message.answer("❌ Ошибка при удалении.")
    await state.set_state(DebtFSM.choose_action)

# ==================== ОБРАБОТЧИКИ ОТМЕНЫ ====================
@router.message(Command("cancel"))
async def cancel_command(message: Message, state: FSMContext):
    current_state = await state.get_state()
    if current_state is None:
        await message.answer("Нет активной команды для отмены.")
        return
    data = await state.get_data()
    if data.get("is_admin"):
        await message.answer("❌ Действие отменено.", reply_markup=kb.admin_kb)
        await state.set_state(AuthStates.admin_mode)
    else:
        await message.answer("❌ Действие отменено.", reply_markup=kb.main)
        await state.set_state(AuthStates.authorized)

# Добавляем возможность отмены во все состояния
for state in AuthStates.__states__:
    router.message(state, Command("cancel"))(cancel_command)

# ==================== СПРАВКА ====================
@router.message(Command("help"))
async def help_command(message: Message, state: FSMContext):
    current_state = await state.get_state()
    if current_state == AuthStates.admin_mode:
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
            "❌ /cancel - отменить текущее действие"
        )
    else:
        help_text = (
            "ℹ️ <b>Доступные команды</b>:\n\n"
            "📅 Расписание - просмотр расписания\n"
            "📰 Новости - просмотр актуальных новостей\n"
            "📝 Задолженности - просмотр академических долгов\n"
            "📊 Тесты - просмотр предстоящих тестов\n\n"
            "🔗 /unbind - отвязать текущего пользователя\n"
            "🚪 /logout - выйти из системы\n"
            "❌ /cancel - отменить текущее действие"
        )
    await message.answer(help_text, parse_mode="HTML")