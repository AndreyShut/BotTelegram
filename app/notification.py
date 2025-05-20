import aiosqlite
import asyncio
from aiogram import Bot
import logging
from datetime import datetime, timedelta, timezone
import os
import hashlib
import time
from typing import Optional, List, Dict, Any, Tuple, Set

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('notifications.log')
    ]
)
logger = logging.getLogger(__name__)

def get_db_timestamp(dt: datetime = None) -> str:
    """Возвращает timestamp в UTC для SQLite"""
    dt = dt or datetime.now(timezone.utc)
    return dt.strftime('%Y-%m-%d %H:%M:%S')

async def convert_db_time(timestamp: str) -> datetime:
    """Конвертирует время из SQLite в локальное время"""
    try:
        dt = datetime.strptime(timestamp, '%Y-%m-%d %H:%M:%S')
        return dt.replace(tzinfo=timezone.utc).astimezone()
    except ValueError:
        return datetime.now(timezone.utc).astimezone()
    
class ChangeTracker:
    def __init__(self):
        self.last_check_time = datetime.now()
        self.sent_notifications: Set[Tuple] = set()
        self.last_cleanup = datetime.now()
        self.lock = asyncio.Lock()
        logger.info(f"ChangeTracker initialized, last_check_time: {get_db_timestamp(self.last_check_time)}")

    async def cleanup_old(self):
        """Очистка старых уведомлений для предотвращения утечки памяти"""
        async with self.lock:
            if datetime.now() - self.last_cleanup > timedelta(hours=1):
                cutoff_time = datetime.now() - timedelta(days=1)
                old_notifications = {
                    n for n in self.sent_notifications 
                    if len(n) > 2 and isinstance(n[2], datetime) and n[2] < cutoff_time
                }
                self.sent_notifications -= old_notifications
                self.last_cleanup = datetime.now()
                logger.info(f"Cleaned up {len(old_notifications)} old notifications")

async def track_changes(db_path: str, bot: Bot):
    """Основная функция отслеживания изменений"""
    tracker = ChangeTracker()
    semaphore = asyncio.Semaphore(100)
    
    while True:
        try:
            await tracker.cleanup_old()
            current_check_time = datetime.now()
            last_check_str = get_db_timestamp(tracker.last_check_time)
            
            logger.debug(f"Checking changes since: {last_check_str}")
            
            async with aiosqlite.connect(db_path) as conn:
                await conn.execute("PRAGMA journal_mode=WAL")
                await conn.execute("PRAGMA synchronous=NORMAL")
                await conn.execute("PRAGMA foreign_keys=ON")
                await conn.commit()
                
                
                logger.info("Starting change tracking cycle")
                start_time = time.time()
                
                await check_test_changes(conn, bot, tracker, semaphore, current_check_time, last_check_str)
                await check_debt_changes(conn, bot, tracker, semaphore, current_check_time, last_check_str)
                
                tracker.last_check_time = current_check_time
                logger.info(f"Change tracking completed in {time.time() - start_time:.2f}s")
                
            await asyncio.sleep(5)
            
        except Exception as e:
            logger.error(f"Error in tracker main loop: {str(e)}", exc_info=True)
            await asyncio.sleep(10)


async def check_test_changes(
    db_connection: aiosqlite.Connection, 
    bot: Bot, 
    tracker: ChangeTracker,
    semaphore: asyncio.Semaphore,
    current_check_time: datetime,
    last_check_str: str
):
    start_time = time.time()
    """Проверка изменений в тестах"""
    last_check_utc = tracker.last_check_time.astimezone(timezone.utc)
    last_check_str = last_check_utc.strftime('%Y-%m-%d %H:%M:%S')
    
    # Добавляем 1-секундный буфер
    buffer_time = (last_check_utc - timedelta(seconds=1)).strftime('%Y-%m-%d %H:%M:%S')
    logger.debug(f"Last check time (UTC): {buffer_time}")

    try:
        logger.debug("Checking for test changes...")
        
        query = '''
            SELECT t.id, t.test_link, t.date, g.name_group, subj.name, tch.full_name, 
                CASE 
                    WHEN t.deleted_at IS NOT NULL AND datetime(t.deleted_at) > datetime(?, 'utc') THEN 'deleted'
                    WHEN datetime(t.updated_at) > datetime(?, 'utc') THEN 'updated'
                    WHEN datetime(t.created_at) > datetime(?, 'utc') AND datetime(t.created_at) = datetime(t.updated_at) THEN 'created'
                END as change_type,
                MAX(COALESCE(t.created_at, t.updated_at, t.deleted_at)) as change_time
            FROM tests t
            JOIN groups g ON t.group_id = g.id
            JOIN disciplines d ON t.discipline_id = d.id
            JOIN subjects subj ON d.subject_id = subj.id
            JOIN teachers tch ON d.teacher_id = tch.id
            WHERE (datetime(t.deleted_at) > datetime(?, 'utc'))
            OR (datetime(t.updated_at) > datetime(?, 'utc'))
            OR (datetime(t.created_at) > datetime(?, 'utc'))
            GROUP BY t.id, change_type
        '''
        async with db_connection.execute(query, [buffer_time]*6) as cursor:
                changes = await cursor.fetchall()

        if not changes:
            logger.debug("No test changes found")
            return
        
        logger.info(f"Found {len(changes)} test changes to process")
        logger.debug(f"Changes: {changes}")
        
        # Группируем по группе для batch-обработки
        changes_by_group: Dict[str, List] = {}
        for row in changes:
            group_name = row[3]
            changes_by_group.setdefault(group_name, []).append(row)
        
        # Получаем всех студентов для групп с изменениями
        group_placeholders = ','.join(['?'] * len(changes_by_group))
        async with db_connection.execute(f'''
            SELECT s.telegram_id, g.name_group 
            FROM students s
            JOIN groups g ON s.id_group = g.id
            WHERE g.name_group IN ({group_placeholders})
            AND s.telegram_id IS NOT NULL
            AND s.is_active = 1
        ''', list(changes_by_group.keys())) as cursor:
            students = await cursor.fetchall()
        
        # Создаем mapping группа -> список telegram_id
        group_to_students: Dict[str, List[int]] = {}
        for telegram_id, group_name in students:
            group_to_students.setdefault(group_name, []).append(telegram_id)
        
        # Отправляем уведомления
        tasks = []
        for group_name, group_changes in changes_by_group.items():
            if group_name not in group_to_students:
                logger.debug(f"No active students in group {group_name} to notify")
                continue
                
            for change in group_changes:
                test_id, test_link, test_date, _, subject_name, teacher_name, change_type, change_time = change
                
                try:
                    change_datetime = datetime.strptime(change_time, '%Y-%m-%d %H:%M:%S.%f')
                except ValueError:
                    change_datetime = datetime.strptime(change_time, '%Y-%m-%d %H:%M:%S')
                notification_key = (test_id, change_type, change_datetime)
                
                async with tracker.lock:
                    if notification_key in tracker.sent_notifications:
                        continue
                    tracker.sent_notifications.add(notification_key)
                
                # Формируем сообщение
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
                
                # Добавляем задачи на отправку
                for telegram_id in group_to_students[group_name]:
                    tasks.append(
                        send_notification_with_retry(
                            bot=bot,
                            chat_id=telegram_id,
                            text=message,
                            semaphore=semaphore,
                            notification_key=notification_key,
                            tracker=tracker,
                            db_connection=db_connection
                        )
                    )
        
        # Выполняем все задачи параллельно
        if tasks:
            results = await asyncio.gather(*tasks, return_exceptions=True)
            successful = sum(1 for r in results if not isinstance(r, Exception))
            errors = sum(1 for r in results if isinstance(r, Exception))
            
            logger.info(f"Sent {successful} test notifications, {errors} errors in {time.time() - start_time:.2f}s")
        
    except Exception as e:
        logger.error(f"Error in check_test_changes: {str(e)}", exc_info=True)
        raise

async def check_debt_changes(
    db_connection: aiosqlite.Connection, 
    bot: Bot, 
    tracker: ChangeTracker,
    semaphore: asyncio.Semaphore,
    current_check_time: datetime,
    last_check_str: str
):
    """Проверка изменений в долгах"""
    start_time = time.time()
    last_check_utc = tracker.last_check_time.astimezone(timezone.utc)
    last_check_str = last_check_utc.strftime('%Y-%m-%d %H:%M:%S')
    
    # Добавляем 1-секундный буфер
    buffer_time = (last_check_utc - timedelta(seconds=1)).strftime('%Y-%m-%d %H:%M:%S')
    logger.debug(f"Last check time (UTC): {buffer_time}")
   
    try:
        logger.debug("Checking for debt changes...")
        
        query = '''
            SELECT sd.student_id, sd.discipline_id, sd.debt_type_id, 
                   subj.name, dt.name, sd.last_date,
                   CASE 
                        WHEN sd.deleted_at IS NOT NULL AND datetime(sd.deleted_at) > datetime(?, 'utc') THEN 'deleted'
                        WHEN datetime(sd.updated_at) > datetime(?, 'utc') THEN 'updated'
                        WHEN datetime(sd.created_at) > datetime(?, 'utc') AND datetime(sd.created_at) = datetime(sd.updated_at) THEN 'created'
                   END as change_type,
                   MAX(COALESCE(sd.created_at, sd.updated_at, sd.deleted_at)) as change_time
            FROM student_debts sd
            JOIN disciplines d ON sd.discipline_id = d.id
            JOIN subjects subj ON d.subject_id = subj.id
            JOIN debt_types dt ON sd.debt_type_id = dt.id
            WHERE (datetime(sd.deleted_at) > datetime(?, 'utc'))
               OR (datetime(sd.updated_at) > datetime(?, 'utc'))
               OR (datetime(sd.created_at) > datetime(?, 'utc'))
            GROUP BY sd.student_id, sd.discipline_id, sd.debt_type_id, change_type
        '''
        async with db_connection.execute(query, [buffer_time]*6) as cursor:
            changes = await cursor.fetchall()

        if not changes:
            logger.debug("No debt changes found")
            return
        
        logger.info(f"Found {len(changes)} debt changes to process")
        
        # Validate all rows have expected columns
        valid_changes = []
        for row in changes:
            if len(row) < 8:
                logger.warning(f"Skipping invalid debt change row: {row}")
                continue
            valid_changes.append(row)
        
        if not valid_changes:
            logger.debug("No valid debt changes found after validation")
            return
            
        logger.debug(f"Valid changes: {valid_changes}")
        
        # Получаем telegram_id для студентов с изменениями
        student_ids = list({row[0] for row in valid_changes})
        student_placeholders = ','.join(['?'] * len(student_ids))
        
        async with db_connection.execute(f'''
            SELECT id_student, telegram_id FROM students 
            WHERE id_student IN ({student_placeholders})
            AND telegram_id IS NOT NULL
            AND is_active = 1
        ''', student_ids) as cursor:
            student_telegram_map = {row[0]: row[1] for row in await cursor.fetchall()}
        
        # Отправляем уведомления
        tasks = []
        for row in valid_changes:
            student_id, discipline_id, debt_type_id, subject_name, debt_type, last_date, change_type, change_time = row
            
            if student_id not in student_telegram_map:
                logger.debug(f"No active telegram ID for student {student_id}")
                continue
                
            telegram_id = student_telegram_map[student_id]
            
            try:
                change_datetime = datetime.strptime(change_time, '%Y-%m-%d %H:%M:%S.%f')
            except ValueError:
                try:
                    change_datetime = datetime.strptime(change_time, '%Y-%m-%d %H:%M:%S')
                except ValueError as e:
                    logger.error(f"Invalid change_time format: {change_time}, error: {str(e)}")
                    continue
                    
            notification_key = (student_id, discipline_id, debt_type_id, change_type, change_datetime)
            
            async with tracker.lock:
                if notification_key in tracker.sent_notifications:
                    continue
                tracker.sent_notifications.add(notification_key)
            
            if change_type == 'created':
                message = (f"📢 <b>Добавлен новый долг!</b>\n\n"
                          f"📚 Предмет: {subject_name}\n"
                          f"🔴 Тип долга: {debt_type}\n"
                          f"⏳ Сдать до: {last_date}\n")
            elif change_type == 'updated':
                message = (f"🔄 <b>Изменен долг!</b>\n\n"
                          f"📚 Предмет: {subject_name}\n"
                          f"🔴 Тип долга: {debt_type}\n"
                          f"⏳ Новый срок: {last_date}\n")
            elif change_type == 'deleted':
                message = (f"❌ <b>Долг снят!</b>\n\n"
                          f"📚 Предмет: {subject_name}\n"
                          f"🔴 Тип долга: {debt_type}\n")
            else:
                logger.warning(f"Unknown change type: {change_type}")
                continue
            
            tasks.append(
                send_notification_with_retry(
                    bot=bot,
                    chat_id=telegram_id,
                    text=message,
                    semaphore=semaphore,
                    notification_key=notification_key,
                    tracker=tracker,
                    db_connection=db_connection
                )
            )
        
        # Выполняем все задачи параллельно
        if tasks:
            results = await asyncio.gather(*tasks, return_exceptions=True)
            successful = sum(1 for r in results if not isinstance(r, Exception))
            errors = sum(1 for r in results if isinstance(r, Exception))
            
            logger.info(f"Sent {successful} debt notifications, {errors} errors in {time.time() - start_time:.2f}s")
        
    except Exception as e:
        logger.error(f"Error in check_debt_changes: {str(e)}", exc_info=True)
        raise

async def send_notification_with_retry(
    bot: Bot,
    chat_id: int,
    text: str,
    semaphore: asyncio.Semaphore,
    notification_key: Tuple,
    tracker: ChangeTracker,
    db_connection: aiosqlite.Connection,
    max_retries: int = 3
):
    """Отправка уведомления с повторными попытками"""
    async with semaphore:
        last_error = None
        for attempt in range(max_retries):
            try:
                await bot.send_message(
                    chat_id=chat_id,
                    text=text,
                    parse_mode='HTML'
                )
                return True
            except Exception as e:
                last_error = e
                if "bot was blocked" in str(e).lower():
                    # Помечаем пользователя как неактивного
                    await mark_user_inactive(db_connection, chat_id)
                    logger.warning(f"User {chat_id} blocked the bot, marked as inactive")
                    break
                await asyncio.sleep(1 * (attempt + 1))
        
        if last_error:
            logger.error(f"Failed to send notification to {chat_id} after {max_retries} attempts: {str(last_error)}")
            # Удаляем уведомление из sent_notifications если не удалось отправить
            async with tracker.lock:
                tracker.sent_notifications.discard(notification_key)
        
        return False

async def mark_user_inactive(db_connection: aiosqlite.Connection, telegram_id: int):
    """Помечает пользователя как неактивного"""
    try:
        await db_connection.execute(
            "UPDATE students SET is_active = 0 WHERE telegram_id = ?",
            (telegram_id,)
        )
        await db_connection.commit()
        logger.info(f"Marked user {telegram_id} as inactive")
    except Exception as e:
        logger.error(f"Error marking user {telegram_id} as inactive: {str(e)}")

class FileWatcher:
    def __init__(self):
        self.file_hashes = {}
        self.file_stats = {}
        self.file_notification_sent = False
        self.lock = asyncio.Lock()
        
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
            logger.error(f"Error reading file {file_path}: {str(e)}")
            return None
            
    async def check_file_changes(self, file_path: str) -> bool:
        """Проверяет изменения в файле (по метаданным и хешу)"""
        async with self.lock:
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
                    self.file_notification_sent = False
                    return True
                    
        return False

async def notify_users(bot: Bot):
    """Функция рассылки уведомлений о новостях, тестах и долгах"""
    db_connection = None
    BATCH_SIZE = 100
    DELAY_BETWEEN_BATCHES = 0.1
    DELAY_BETWEEN_MESSAGES = 0.01
    
    schedule_files = [
        "Расписание_групп.xlsx",
        "Расписание_преподавателей.xls",
        "График_задолженностей.xlsx"
    ]
    
    try:
        db_connection = await aiosqlite.connect('student_bot.db')
        file_watcher = FileWatcher()
        
        while True:
            try:
                start_time = time.time()
                logger.info("Starting notification cycle")
                
                # 1. Проверка новых новостей
                await process_news_notifications(db_connection, bot, BATCH_SIZE, DELAY_BETWEEN_BATCHES)
                
                # 2. Проверка тестов (за 1 день до)
                await process_test_reminders(db_connection, bot, BATCH_SIZE, DELAY_BETWEEN_BATCHES)
                
                # 3. Проверка долгов (за 3 дня до крайнего срока)
                await process_debt_reminders(db_connection, bot, BATCH_SIZE, DELAY_BETWEEN_BATCHES)
                
                # 4. Проверка изменений в файлах расписания
                await process_schedule_changes(db_connection, bot, file_watcher, schedule_files, BATCH_SIZE, DELAY_BETWEEN_BATCHES)
                
                logger.info(f"Notification cycle completed in {time.time() - start_time:.2f}s")
                await asyncio.sleep(10)
                
            except Exception as e:
                logger.error(f"Error in notification cycle: {str(e)}", exc_info=True)
                await asyncio.sleep(10)
                
    except asyncio.CancelledError:
        logger.info("Notification service stopped")
    finally:
        if db_connection:
            await db_connection.close()
        logger.info("Database connection closed")

# Дополнительные вспомогательные функции для notify_users
async def process_news_notifications(db_connection, bot, batch_size, delay):
    """Обработка уведомлений о новостях"""
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

    if not news_list:
        return

    for news_id, title, description, for_all_groups, date, place in news_list:
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

        success_sends = 0
        for i in range(0, len(recipients), batch_size):
            batch = recipients[i:i+batch_size]
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
                        else:
                            logger.error(f"Error sending news to {telegram_id}: {str(result)}")
                    else:
                        await db_connection.execute(
                            '''INSERT INTO sent_notifications 
                            (notification_type, entity_id, user_id)
                            VALUES ('news', ?, ?)''',
                            (news_id, telegram_id)
                        )
                        success_sends += 1
                
                await db_connection.commit()
                await asyncio.sleep(delay)
                
            except Exception as e:
                logger.error(f"Error sending news batch: {str(e)}")

        if success_sends > 0:
            logger.info(f"News {news_id} sent to {success_sends} users")

async def process_test_reminders(db_connection, bot, batch_size, delay):
    """Обработка напоминаний о тестах"""
    today = datetime.now().date()
    tomorrow = today + timedelta(days=3)
    
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
    
    if not upcoming_tests:
        return

    for test_id, test_link, test_date, group_name, subject_name, teacher_name in upcoming_tests:
        async with db_connection.execute('''
            SELECT telegram_id FROM students 
            WHERE id_group = (SELECT id FROM groups WHERE name_group = ?)
            AND telegram_id IS NOT NULL
            AND is_active = 1
        ''', (group_name,)) as cursor:
            students = await cursor.fetchall()
        
        message_text = (f'⚠️ <b>Напоминание о тесте!</b>\n\n'
                     f'📚 Предмет: {subject_name}\n'
                     f'👨‍🏫 Преподаватель: {teacher_name}\n'
                     f'👥 Группа: {group_name}\n'
                     f'📅 Дата: {test_date}\n'
                     f'🔗 Ссылка: <a href="{test_link}">Перейти к тесту</a>')
        
        success_sends = 0
        for i in range(0, len(students), batch_size):
            batch = students[i:i+batch_size]
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
                        else:
                            logger.error(f"Error sending test reminder to {telegram_id}: {str(result)}")
                    else:
                        await db_connection.execute(
                            '''INSERT INTO sent_notifications 
                            (notification_type, entity_id, user_id)
                            VALUES ('test', ?, ?)''',
                            (test_id, telegram_id)
                        )
                        success_sends += 1
                
                await db_connection.commit()
                await asyncio.sleep(delay)
            except Exception as e:
                logger.error(f"Error sending test reminders batch: {str(e)}")
        
        if success_sends > 0:
            logger.info(f"Test reminder {test_id} sent to {success_sends} users")

async def process_debt_reminders(db_connection, bot, batch_size, delay):
    """Обработка напоминаний о долгах"""
    today = datetime.now().date()
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
    
    if not upcoming_debts:
        return

    debts_by_user = {}
    for telegram_id, subject_name, debt_type, last_date in upcoming_debts:
        debts_by_user.setdefault(telegram_id, []).append((subject_name, debt_type, last_date))
    
    success_sends = 0
    user_ids = list(debts_by_user.keys())
    for i in range(0, len(user_ids), batch_size):
        batch = user_ids[i:i+batch_size]
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
                    else:
                        logger.error(f"Error sending debt reminder to {telegram_id}: {str(result)}")
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
            await asyncio.sleep(delay)
        except Exception as e:
            logger.error(f"Error sending debt reminders batch: {str(e)}")
    
    if success_sends > 0:
        logger.info(f"Debt reminders sent to {success_sends} users")

async def process_schedule_changes(db_connection, bot, file_watcher, schedule_files, batch_size, delay):
    """Обработка изменений в расписании"""
    for file_path in schedule_files:
        if await file_watcher.check_file_changes(file_path) and not file_watcher.file_notification_sent:
            logger.info(f"Detected changes in file {file_path}")
            
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
            
            success_sends = 0
            for i in range(0, len(users), batch_size):
                batch = users[i:i+batch_size]
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
                            else:
                                logger.error(f"Error sending schedule update to {telegram_id}: {str(result)}")
                        else:
                            success_sends += 1
                    
                    await asyncio.sleep(delay)
                except Exception as e:
                    logger.error(f"Error sending schedule updates batch: {str(e)}")
            
            if success_sends > 0:
                file_watcher.file_notification_sent = True
                logger.info(f"Schedule update for {file_path} sent to {success_sends} users")