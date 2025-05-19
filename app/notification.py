import aiosqlite
import asyncio
from aiogram import Bot
import logging
from datetime import datetime, timedelta
import os
import hashlib
import time
from typing import Optional, List, Dict, Any, Tuple

logger = logging.getLogger(__name__)

class ChangeTracker:
    def __init__(self):
        self.last_check_time = datetime.now()
        self.sent_notifications = set()

async def track_changes(db_connection: aiosqlite.Connection, bot: Bot):
    tracker = ChangeTracker()
    
    while True:
        try:
            # Проверяем изменения в тестах
            await check_test_changes(db_connection, bot, tracker)
            
            # Проверяем изменения в долгах
            await check_debt_changes(db_connection, bot, tracker)
            
            # Обновляем время последней проверки
            tracker.last_check_time = datetime.now()
            
            await asyncio.sleep(10)  # Проверяем каждую минуту
            
        except Exception as e:
            logger.error(f"Ошибка в трекере изменений: {e}")
            await asyncio.sleep(10)

async def check_test_changes(db_connection: aiosqlite.Connection, bot: Bot, tracker: ChangeTracker):
    # Получаем все изменения тестов после последней проверки
    async with db_connection.execute('''
        SELECT t.id, t.test_link, t.date, g.name_group, subj.name, tch.full_name, 
               CASE 
                   WHEN t.created_at > ? THEN 'created'
                   WHEN t.updated_at > ? THEN 'updated'
                   WHEN t.deleted_at > ? THEN 'deleted'
               END as change_type
        FROM tests t
        JOIN groups g ON t.group_id = g.id
        JOIN disciplines d ON t.discipline_id = d.id
        JOIN subjects subj ON d.subject_id = subj.id
        JOIN teachers tch ON d.teacher_id = tch.id
        WHERE t.created_at > ? OR t.updated_at > ? OR t.deleted_at > ?
    ''', (tracker.last_check_time,) * 6) as cursor:
        changes = await cursor.fetchall()
    
    for test_id, test_link, test_date, group_name, subject_name, teacher_name, change_type in changes:
        if (test_id, change_type) in tracker.sent_notifications:
            continue
            
        # Получаем студентов группы
        async with db_connection.execute('''
            SELECT telegram_id FROM students 
            WHERE id_group = (SELECT id FROM groups WHERE name_group = ?)
            AND telegram_id IS NOT NULL
            AND is_active = 1
        ''', (group_name,)) as cursor:
            students = await cursor.fetchall()
        
        # Формируем сообщение в зависимости от типа изменения
        if change_type == 'created':
            message = (f"📌 <b>Добавлен новый тест!</b>\n\n"
                      f"📚 Предмет: {subject_name}\n"
                      f"👨‍🏫 Преподаватель: {teacher_name}\n"
                      f"👥 Группа: {group_name}\n"
                      f"📅 Дата: {test_date}\n"
                      f"🔗 Ссылка: <a href='{test_link}'>Перейти к тесту</a>")
        elif change_type == 'updated':
            message = (f"🔄 <b>Изменен тест!</b>\n\n"
                      f"📚 Предмет: {subject_name}\n"
                      f"👨‍🏫 Преподаватель: {teacher_name}\n"
                      f"👥 Группа: {group_name}\n"
                      f"📅 Новая дата: {test_date}\n"
                      f"🔗 Ссылка: <a href='{test_link}'>Перейти к тесту</a>")
        elif change_type == 'deleted':
            message = (f"❌ <b>Тест отменен!</b>\n\n"
                      f"📚 Предмет: {subject_name}\n"
                      f"👨‍🏫 Преподаватель: {teacher_name}\n"
                      f"👥 Группа: {group_name}\n"
                      f"📅 Дата: {test_date}")
        
        # Отправляем уведомления
        for (telegram_id,) in students:
            try:
                await bot.send_message(
                    chat_id=telegram_id,
                    text=message,
                    parse_mode='HTML'
                )
                tracker.sent_notifications.add((test_id, change_type))
            except Exception as e:
                logger.error(f"Ошибка отправки уведомления о тесте: {e}")

async def check_debt_changes(db_connection: aiosqlite.Connection, bot: Bot, tracker: ChangeTracker):
    # Получаем все изменения долгов после последней проверки
    async with db_connection.execute('''
        SELECT sd.student_id, sd.discipline_id, sd.debt_type_id, 
               subj.name, dt.name, sd.last_date,
               CASE 
                   WHEN sd.created_at > ? THEN 'created'
                   WHEN sd.updated_at > ? THEN 'updated'
                   WHEN sd.deleted_at > ? THEN 'deleted'
               END as change_type
        FROM student_debts sd
        JOIN disciplines d ON sd.discipline_id = d.id
        JOIN subjects subj ON d.subject_id = subj.id
        JOIN debt_types dt ON sd.debt_type_id = dt.id
        WHERE sd.created_at > ? OR sd.updated_at > ? OR sd.deleted_at > ?
    ''', (tracker.last_check_time,) * 6) as cursor:
        changes = await cursor.fetchall()
    
    # Группируем по студентам
    debts_by_student: Dict[int, List[Tuple]] = {}
    for change in changes:
        student_id = change[0]
        if student_id not in debts_by_student:
            debts_by_student[student_id] = []
        debts_by_student[student_id].append(change)
    
    # Отправляем уведомления
    for student_id, debts in debts_by_student.items():
        # Получаем telegram_id студента
        async with db_connection.execute('''
            SELECT telegram_id FROM students 
            WHERE id_student = ? AND is_active = 1 AND telegram_id IS NOT NULL
        ''', (student_id,)) as cursor:
            student = await cursor.fetchone()
        
        if not student:
            continue
            
        telegram_id = student[0]
        
        # Формируем сообщение
        message = "📢 <b>Изменения в ваших долгах:</b>\n\n"
        for debt in debts:
            _, _, _, subject_name, debt_type, last_date, change_type = debt
            
            if change_type == 'created':
                message += (f"➕ Добавлен долг:\n"
                          f"📚 {subject_name}\n"
                          f"🔴 {debt_type}\n"
                          f"⏳ Сдать до: {last_date}\n\n")
            elif change_type == 'updated':
                message += (f"🔄 Изменен долг:\n"
                          f"📚 {subject_name}\n"
                          f"🔴 {debt_type}\n"
                          f"⏳ Новый срок: {last_date}\n\n")
            elif change_type == 'deleted':
                message += (f"❌ Снят долг:\n"
                          f"📚 {subject_name}\n"
                          f"🔴 {debt_type}\n\n")
        
        try:
            await bot.send_message(
                chat_id=telegram_id,
                text=message,
                parse_mode='HTML'
            )
            # Помечаем как отправленные
            for debt in debts:
                tracker.sent_notifications.add((student_id, debt[1], debt[2], debt[6]))
        except Exception as e:
            logger.error(f"Ошибка отправки уведомления о долге: {e}")

class FileWatcher:
    def __init__(self):
        self.file_hashes = {}
        self.file_stats = {}  # Для хранения метаданных
        self.file_notification_sent = False
        
    async def get_file_info(self, file_path: str) -> Optional[dict]:
        """Получает информацию о файле (хеш и метаданные)"""
        if not os.path.exists(file_path):
            return None
            
        try:
            stat = os.stat(file_path)
            with open(file_path, 'rb') as f:
                content = f.read()
                return {
                    'hash': hashlib.sha256(content).hexdigest(),
                    'size': stat.st_size,
                    'mtime': stat.st_mtime
                }
        except Exception as e:
            logger.error(f"Ошибка чтения файла {file_path}: {e}")
            return None
            
    async def check_file_changes(self, file_path: str) -> bool:
        """Проверяет изменения в файле (по метаданным и хешу)"""
        current_info = await self.get_file_info(file_path)
        if not current_info:
            return False
            
        if file_path not in self.file_stats:
            self.file_stats[file_path] = current_info
            self.file_hashes[file_path] = current_info['hash']
            return False
            
        # Сначала проверяем по метаданным (быстрее)
        if (self.file_stats[file_path]['size'] != current_info['size'] or 
            self.file_stats[file_path]['mtime'] != current_info['mtime']):
            # Если метаданные изменились, проверяем хеш
            if self.file_hashes[file_path] != current_info['hash']:
                self.file_stats[file_path] = current_info
                self.file_hashes[file_path] = current_info['hash']
                self.file_notification_sent = False  # Сброс флага при изменении файла
                return True
                
        return False
    




async def mark_user_inactive(db_connection: aiosqlite.Connection, telegram_id: int):
    """Помечает пользователя как неактивного"""
    try:
        await db_connection.execute(
            "UPDATE students SET is_active = 0 WHERE telegram_id = ?",
            (telegram_id,)
        )
        await db_connection.commit()
        logger.info(f"Пользователь {telegram_id} помечен как неактивный")
    except Exception as e:
        logger.error(f"Ошибка при пометке пользователя {telegram_id} как неактивного: {e}")

async def notify_users(bot: Bot):
    db_connection = None
    file_watcher = FileWatcher()
    
   # Уменьшите задержки
    BATCH_SIZE = 50  # Увеличьте размер батча
    DELAY_BETWEEN_BATCHES = 0.3  # Уменьшите задержку между батчами
    DELAY_BETWEEN_MESSAGES = 0.05  # Уменьшите задержку внутри батча
    
    schedule_files = [
        "Расписание_групп.xlsx",
        "Расписание_преподавателей.xls",
        "График_задолженностей.xlsx"
    ]
    
    try:
        db_connection = await aiosqlite.connect('student_bot.db')
        while True:
            try:
                
                # 1. Проверка новых новостей с batch-обработкой
                async with db_connection.execute('''
                    SELECT n.id, n.title, n.description, n.for_all_groups, n.date, n.place 
                    FROM news n
                    WHERE n.is_published = 1 
                    AND NOT EXISTS (
                        SELECT 1 FROM sent_notifications sn 
                        WHERE sn.notification_type = 'news' 
                        AND sn.entity_id = n.id
                    )
                    ORDER BY n.date DESC
                ''') as cursor:
                    news_list = await cursor.fetchall()

                if news_list:
                    for news_id, title, description, for_all_groups, date, place in news_list:                         
                        success_sends = 0
                        
                        if for_all_groups:
                            query = '''
                                SELECT s.telegram_id 
                                FROM students s
                                WHERE s.telegram_id IS NOT NULL
                                AND s.is_active = 1
                            '''
                            params = ()
                        else:
                            query = '''
                                SELECT s.telegram_id 
                                FROM students s
                                JOIN news_groups ng ON s.id_group = ng.group_id
                                WHERE s.telegram_id IS NOT NULL
                                AND s.is_active = 1
                                AND ng.news_id = ?
                            '''
                            params = (news_id,)
                        
                        async with db_connection.execute(query, params) as cursor:
                            recipients = await cursor.fetchall()
                        
                        message_text = f'📢 <b>{title}</b>\n\n'
                        if description:
                            message_text += f'{description}\n\n'
                        if place:
                            message_text += f'📍 Место: {place}\n'
                        message_text += f'📅 Дата: {date}'
                        
                        # Batch-обработка получателей
                        for i in range(0, len(recipients), BATCH_SIZE):
                            batch = recipients[i:i+BATCH_SIZE]
                            tasks = []
                            
                            for (telegram_id,) in batch:
                                try:
                                    tasks.append(
                                        bot.send_message(
                                            chat_id=telegram_id,
                                            text=message_text,
                                            parse_mode='HTML'
                                        )
                                    )
                                except Exception as e:
                                    logger.error(f"Ошибка подготовки сообщения для {telegram_id}: {e}")
                            
                            # Отправка батча
                            try:
                                results = await asyncio.gather(*tasks, return_exceptions=True)
                                for j, result in enumerate(results):
                                    telegram_id = batch[j][0]
                                    if isinstance(result, Exception):
                                        if "chat not found" in str(result) or "bot was blocked" in str(result).lower():
                                            await mark_user_inactive(db_connection, telegram_id)
                                            logger.warning(f"Пользователь {telegram_id} недоступен, помечен как неактивный")
                                        else:
                                            logger.error(f"Ошибка отправки {telegram_id}: {result}")
                                    else:
                                        await db_connection.execute(
                                            '''INSERT INTO sent_notifications 
                                            (notification_type, entity_id, user_id)
                                            VALUES ('news', ?, ?)''',
                                            (news_id, telegram_id)
                                        )
                                        success_sends += 1
                                
                                await db_connection.commit()
                                
                                await asyncio.sleep(DELAY_BETWEEN_BATCHES)
                                
                            except Exception as e:
                                logger.error(f"Ошибка при отправке батча: {e}")
                        
                        if success_sends > 0:
                            logger.info(f"Новость {news_id} отправлена {success_sends} пользователям")
                
                # 2. Проверка тестов (за 1 день до) с batch-обработкой
                today = datetime.now().date()
                tomorrow = today + timedelta(days=1)
                
                async with db_connection.execute('''
                    SELECT t.id, t.test_link, t.date, g.name_group, subj.name, tch.full_name
                    FROM tests t
                    JOIN groups g ON t.group_id = g.id
                    JOIN disciplines d ON t.discipline_id = d.id
                    JOIN subjects subj ON d.subject_id = subj.id
                    JOIN teachers tch ON d.teacher_id = tch.id
                    WHERE date(t.date) = date(?)
                    AND NOT EXISTS (
                        SELECT 1 FROM sent_notifications sn 
                        WHERE sn.notification_type = 'test' 
                        AND sn.entity_id = t.id
                    )
                ''', (tomorrow.strftime("%Y-%m-%d"),)) as cursor:
                    upcoming_tests = await cursor.fetchall()
                
                if upcoming_tests:
                    for test_id, test_link, test_date, group_name, subject_name, teacher_name in upcoming_tests:
                        async with db_connection.execute('''
                            SELECT telegram_id FROM students 
                            WHERE id_group = (SELECT id FROM groups WHERE name_group = ?)
                            AND telegram_id IS NOT NULL
                            AND is_active = 1
                        ''', (group_name,)) as cursor:
                            students = await cursor.fetchall()
                        
                        # Подготовка сообщения
                        message_text = (f'⚠️ <b>Напоминание о тесте!</b>\n\n'
                                     f'📚 Предмет: {subject_name}\n'
                                     f'👨‍🏫 Преподаватель: {teacher_name}\n'
                                     f'👥 Группа: {group_name}\n'
                                     f'📅 Дата: {test_date}\n'
                                     f'🔗 Ссылка: <a href="{test_link}">Перейти к тесту</a>')
                        
                        # Batch-обработка
                        success_sends = 0
                        for i in range(0, len(students), BATCH_SIZE):
                            batch = students[i:i+BATCH_SIZE]
                            tasks = []
                            
                            for (telegram_id,) in batch:
                                tasks.append(
                                    bot.send_message(
                                        chat_id=telegram_id,
                                        text=message_text,
                                        parse_mode='HTML'
                                    )
                                )
                            
                            try:
                                results = await asyncio.gather(*tasks, return_exceptions=True)
                                for j, result in enumerate(results):
                                    telegram_id = batch[j][0]
                                    if isinstance(result, Exception):
                                        if "chat not found" in str(result) or "bot was blocked" in str(result).lower():
                                            await mark_user_inactive(db_connection, telegram_id)
                                            logger.warning(f"Пользователь {telegram_id} недоступен, помечен как неактивный")
                                        else:
                                            logger.error(f"Ошибка отправки {telegram_id}: {result}")
                                    else:
                                        await db_connection.execute(
                                            '''INSERT INTO sent_notifications 
                                            (notification_type, entity_id, user_id)
                                            VALUES ('test', ?, ?)''',
                                            (test_id, telegram_id)
                                        )
                                        success_sends += 1
                                
                                await db_connection.commit()
                                await asyncio.sleep(DELAY_BETWEEN_BATCHES)
                            except Exception as e:
                                logger.error(f"Ошибка при отправке батча напоминаний о тестах: {e}")
                        
                        if success_sends > 0:
                            logger.info(f"Напоминание о тесте {test_id} отправлено {success_sends} пользователям")
                
                # 3. Проверка долгов (за 3 дня до крайнего срока) с batch-обработкой
                debt_notification_date = today + timedelta(days=3)
                
                async with db_connection.execute('''
                    SELECT s.telegram_id, subj.name, dt.name, sd.last_date
                    FROM student_debts sd
                    JOIN students s ON sd.student_id = s.id_student
                    JOIN disciplines d ON sd.discipline_id = d.id
                    JOIN subjects subj ON d.subject_id = subj.id
                    JOIN debt_types dt ON sd.debt_type_id = dt.id
                    WHERE date(sd.last_date) = date(?)
                    AND s.telegram_id IS NOT NULL
                    AND s.is_active = 1
                    AND NOT EXISTS (
                        SELECT 1 FROM sent_notifications sn 
                        WHERE sn.notification_type = 'debt' 
                        AND sn.entity_date = sd.last_date
                        AND sn.user_id = s.telegram_id
                    )
                ''', (debt_notification_date.strftime("%Y-%m-%d"),)) as cursor:
                    upcoming_debts = await cursor.fetchall()
                
                if upcoming_debts:
                    # Группировка по telegram_id для отправки одного сообщения с несколькими долгами
                    debts_by_user = {}
                    for telegram_id, subject_name, debt_type, last_date in upcoming_debts:
                        if telegram_id not in debts_by_user:
                            debts_by_user[telegram_id] = []
                        debts_by_user[telegram_id].append((subject_name, debt_type, last_date))
                    
                    # Подготовка и отправка сообщений батчами
                    success_sends = 0
                    user_ids = list(debts_by_user.keys())
                    for i in range(0, len(user_ids), BATCH_SIZE):
                        batch = user_ids[i:i+BATCH_SIZE]
                        tasks = []
                        
                        for telegram_id in batch:
                            debts = debts_by_user[telegram_id]
                            message_text = '‼️ <b>Внимание! Подходит срок сдачи долгов!</b>\n\n'
                            for subject, debt, date in debts:
                                message_text += (f'📚 Предмет: {subject}\n'
                                              f'🔴 Тип долга: {debt}\n'
                                              f'⏳ Крайний срок: {date}\n\n')
                            message_text += 'Не забудьте сдать долги вовремя!'
                            
                            tasks.append(
                                bot.send_message(
                                    chat_id=telegram_id,
                                    text=message_text,
                                    parse_mode='HTML'
                                )
                            )
                        
                        try:
                            results = await asyncio.gather(*tasks, return_exceptions=True)
                            for j, result in enumerate(results):
                                telegram_id = batch[j]
                                if isinstance(result, Exception):
                                    if "chat not found" in str(result) or "bot was blocked" in str(result).lower():
                                        await mark_user_inactive(db_connection, telegram_id)
                                        logger.warning(f"Пользователь {telegram_id} недоступен, помечен как неактивный")
                                    else:
                                        logger.error(f"Ошибка отправки {telegram_id}: {result}")
                                else:
                                    for _, _, last_date in debts_by_user[telegram_id]:
                                        await db_connection.execute(
                                            '''INSERT INTO sent_notifications 
                                            (notification_type, entity_date, user_id)
                                            VALUES ('debt', ?, ?)''',
                                            (last_date, telegram_id)
                                        )
                                    success_sends += 1
                            
                            await db_connection.commit()
                            await asyncio.sleep(DELAY_BETWEEN_BATCHES)
                        except Exception as e:
                            logger.error(f"Ошибка при отправке батча напоминаний о долгах: {e}")
                    
                    if success_sends > 0:
                        logger.info(f"Напоминания о долгах отправлены {success_sends} пользователям")
                
                # 4. Проверка изменений в файлах расписания с batch-обработкой
                for file_path in schedule_files:
                    if await file_watcher.check_file_changes(file_path) and not file_watcher.file_notification_sent:
                        logger.info(f"Обнаружено изменение в файле {file_path}")
                        
                        if "групп" in file_path:
                            schedule_type = "групп"
                            emoji = "👥"
                        elif "преподавателей" in file_path:
                            schedule_type = "преподавателей"
                            emoji = "👨‍🏫"
                        else:
                            schedule_type = "задолженностей"
                            emoji = "⏳"
                        
                        async with db_connection.execute('''
                            SELECT telegram_id FROM students 
                            WHERE telegram_id IS NOT NULL
                            AND is_active = 1
                        ''') as cursor:
                            users = await cursor.fetchall()
                        
                        message_text = (f'{emoji} <b>Обновлено расписание {schedule_type}!</b>\n\n'
                                     f'Проверьте актуальное расписание в соответствующем разделе.')
                        
                        # Batch-обработка
                        success_sends = 0
                        for i in range(0, len(users), BATCH_SIZE):
                            batch = users[i:i+BATCH_SIZE]
                            tasks = []
                            
                            for (telegram_id,) in batch:
                                tasks.append(
                                    bot.send_message(
                                        chat_id=telegram_id,
                                        text=message_text,
                                        parse_mode='HTML'
                                    )
                                )
                            
                            try:
                                results = await asyncio.gather(*tasks, return_exceptions=True)
                                for j, result in enumerate(results):
                                    telegram_id = batch[j][0]
                                    if isinstance(result, Exception):
                                        if "chat not found" in str(result) or "bot was blocked" in str(result).lower():
                                            await mark_user_inactive(db_connection, telegram_id)
                                            logger.warning(f"Пользователь {telegram_id} недоступен, помечен как неактивный")
                                        else:
                                            logger.error(f"Ошибка отправки {telegram_id}: {result}")
                                    else:
                                        success_sends += 1
                                
                                await db_connection.commit()
                                await asyncio.sleep(DELAY_BETWEEN_BATCHES)
                            except Exception as e:
                                logger.error(f"Ошибка при отправке батча уведомлений о расписании: {e}")
                        
                        if success_sends > 0:
                            file_watcher.file_notification_sent = True
                            logger.info(f"Уведомление об изменении {file_path} отправлено {success_sends} пользователям")
                
                await asyncio.sleep(10)
                
            except Exception as e:
                logger.error(f"Ошибка в цикле рассылки: {e}")
                await asyncio.sleep(10)
                
    except asyncio.CancelledError:
        logger.info("Рассылка уведомлений остановлена")
    finally:
        if db_connection:
            await db_connection.close()
        logger.info("Соединение с БД закрыто")