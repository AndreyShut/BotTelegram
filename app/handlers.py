from aiogram import Router
from aiogram.types import Message, CallbackQuery
from aiogram.filters import CommandStart, Command
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.context import FSMContext
import logging

import app.keyboards as kb

router = Router()
logger = logging.getLogger(__name__)

class Register(StatesGroup):
    login = State()
    password = State()

@router.message(CommandStart())
async def cmd_start(message: Message):
    logger.info(f"User {message.from_user.id} started the bot")
    await message.answer('Добро пожаловать!', reply_markup=kb.main)

@router.message(Command('help'))
async def cmd_help(message: Message):
    await message.answer(
        "Доступные команды:\n"
        "/start - Начать работу\n"
        "/help - Справка\n"
        "/register - Регистрация"
    )

@router.message(Command('register'))
async def register(message: Message, state: FSMContext):
    await state.set_state(Register.login)
    await message.answer('Введите ваш логин:')

@router.message(Register.login)
async def register_login(message: Message, state: FSMContext):
    login = message.text.strip()
    if len(login) < 4:
        await message.answer("Логин слишком короткий!")
        return
    await state.update_data(login=login)
    await state.set_state(Register.password)
    await message.answer("Введите ваш пароль:")

@router.message(Register.password)
async def register_password(message: Message, state: FSMContext):
    password = message.text.strip()
    if len(password) < 6:
        await message.answer("Пароль слишком короткий!")
        return
    data = await state.get_data()
    import aiosqlite
    # Сохраняем пользователя в БД
    async with aiosqlite.connect('student_bot.db') as db:
        await db.execute(
            'INSERT OR IGNORE INTO users (user_id, login, password) VALUES (?, ?, ?)',
            (message.from_user.id, data["login"], password)
        )
        await db.commit()
    await message.answer(
        f'Регистрация успешна!\n'
        f'Логин: {data["login"]}\n'
        f'Пароль: {"*" * len(password)}'
    )
    await state.clear()

@router.message(lambda m: m.text == "Расписание")
async def select_schedule(message: Message):
    await message.answer('Выберите расписание', reply_markup=kb.select)

@router.callback_query(lambda call: call.data in ("today", "tomorrow", "week"))
async def schedule_handler(call: CallbackQuery):
    await call.message.answer(f'Расписание на {call.data}...')

@router.message(lambda m: m.text == "Задолженности")
async def debts(message: Message):
    # Здесь нужно реализовать получение задолженностей
    await message.answer("Показать задолженности? Пока не реализовано.")

@router.message(lambda m: m.text == "Новости")
async def news(message: Message):
    # Здесь нужно реализовать показ новостей из базы
    await message.answer("Показать новости? Пока не реализовано.")