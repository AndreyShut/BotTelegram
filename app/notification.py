import aiosqlite
import asyncio
from aiogram import Bot
import logging
from datetime import datetime, timedelta
import os
import hashlib
import time
from typing import Optional, List, Dict, Any, Tuple,Set

logger = logging.getLogger(__name__)


class ChangeTracker:
    def __init__(self):
        self.last_check_time = datetime.now()
        self.sent_notifications: Set[Tuple] = set()
        self.last_cleanup = datetime.now()
    
    async def cleanup_old(self):
        """Очистка старых уведомлений для предотвращения утечки памяти"""
        if datetime.now() - self.last_cleanup > timedelta(hours=1):
            # Удаляем уведомления старше 24 часов
            cutoff_time = datetime.now() - timedelta(days=1)
            old_notifications = {
                n for n in self.sent_notifications 
                if len(n) > 2 and isinstance(n[2], datetime) and n[2] < cutoff_time
            }
            self.sent_notifications -= old_notifications
            self.last_cleanup = datetime.now()
            logger.debug(f"Cleaned up {len(old_notifications)} old notifications")

async def track_changes(db_path: str, bot: Bot):
    """Основная функция отслеживания изменений"""
    tracker = ChangeTracker()
    semaphore = asyncio.Semaphore(100)
    conn = None
    
    while True:
        try:
            await tracker.cleanup_old()
            async with aiosqlite.connect(db_path) as conn:
                start_time = time.time()
                # Check both tests and debts
                test_task = check_test_changes(conn, bot, tracker, semaphore)
                debt_task = check_debt_changes(conn, bot, tracker, semaphore)
                await asyncio.gather(test_task, debt_task)
                tracker.last_check_time = datetime.now()

                logger.debug(f"Change tracking completed in {time.time() - start_time:.2f}s")
                await asyncio.sleep(5)
            
        except Exception as e:
            logger.error(f"Error in tracker main loop: {e}")
            await asyncio.sleep(10)
        finally:
            if conn:
                await conn.close()

async def check_test_changes(
    db_connection: aiosqlite.Connection, 
    bot: Bot, 
    tracker: ChangeTracker,
    semaphore: asyncio.Semaphore
):
    """Проверка изменений в тестах"""
    start_time = time.time()
    last_check_str = tracker.last_check_time.strftime('%Y-%m-%d %H:%M:%S.%f')
    
    try:
        # Получаем изменения тестов
        async with db_connection.execute('''
            SELECT t.id, t.test_link, t.date, g.name_group, subj.name, tch.full_name, 
                    CASE 
                        WHEN t.deleted_at > ? THEN 'deleted'
                        WHEN t.updated_at > ? AND t.updated_at != t.created_at THEN 'updated'
                        WHEN t.created_at > ? THEN 'created'
                    END as change_type,
                    MAX(COALESCE(t.created_at, t.updated_at, t.deleted_at)) as change_time
            FROM tests t
            JOIN groups g ON t.group_id = g.id
            JOIN disciplines d ON t.discipline_id = d.id
            JOIN subjects subj ON d.subject_id = subj.id
            JOIN teachers tch ON d.teacher_id = tch.id
            WHERE t.deleted_at > ? OR (t.updated_at > ? AND t.updated_at != t.created_at) OR t.created_at > ?
            GROUP BY t.id, change_type
        ''', (last_check_str,) * 6) as cursor:
                changes = await cursor.fetchall()
        

        logger.debug(f"Test changes detected: {changes}")
        if not changes:
            logger.debug("No test changes found")
            return
        
        # Группируем по группе для batch-обработки
        changes_by_group: Dict[str, List] = {}
        for row in changes:
            group_name = row[3]
            if group_name not in changes_by_group:
                changes_by_group[group_name] = []
            changes_by_group[group_name].append(row)
        
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
            if group_name not in group_to_students:
                group_to_students[group_name] = []
            group_to_students[group_name].append(telegram_id)
        
        # Отправляем уведомления
        tasks = []
        for group_name, group_changes in changes_by_group.items():
            if group_name not in group_to_students:
                continue
                
            for change in group_changes:
                test_id, test_link, test_date, _, subject_name, teacher_name, change_type, change_time = change
                
                notification_key = (test_id, change_type, datetime.strptime(change_time, '%Y-%m-%d %H:%M:%S.%f'))
                if notification_key in tracker.sent_notifications:
                    continue
                
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
                            tracker=tracker
                        )
                    )
        
        # Выполняем все задачи параллельно
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Обрабатываем результаты
        successful = 0
        for result in results:
            if isinstance(result, Exception):
                logger.error(f"Error sending test notification: {result}")
            else:
                successful += 1
        
        logger.info(f"Sent {successful} test notifications in {time.time() - start_time:.2f}s")
        
    except Exception as e:
        logger.error(f"Error in check_test_changes: {e}")
        raise

async def check_debt_changes(
    db_connection: aiosqlite.Connection, 
    bot: Bot, 
    tracker: ChangeTracker,
    semaphore: asyncio.Semaphore
):
    """Проверка изменений в долгах"""
    start_time = time.time()
    last_check_str = tracker.last_check_time.strftime('%Y-%m-%d %H:%M:%S.%f')
    
    try:
        # Получаем изменения долгов
        async with db_connection.execute('''
            SELECT sd.student_id, sd.discipline_id, sd.debt_type_id, 
                   subj.name, dt.name, sd.last_date,
                   CASE 
                       WHEN sd.deleted_at > ? THEN 'deleted'
                       WHEN sd.updated_at > ? AND sd.updated_at != sd.created_at THEN 'updated'
                       WHEN sd.created_at > ? THEN 'created'
                   END as change_type,
                   MAX(COALESCE(sd.created_at, sd.updated_at, sd.deleted_at)) as change_time
            FROM student_debts sd
            JOIN disciplines d ON sd.discipline_id = d.id
            JOIN subjects subj ON d.subject_id = subj.id
            JOIN debt_types dt ON sd.debt_type_id = dt.id
            WHERE sd.deleted_at > ? OR sd.updated_at > ? OR sd.created_at > ?
            GROUP BY sd.student_id, sd.discipline_id, sd.debt_type_id, change_type
        ''', (last_check_str,) * 6) as cursor:
            changes = await cursor.fetchall()
        
        logger.debug(f"Debt changes detected: {changes}")
        if not changes:
            logger.debug("No debt changes found")
            return
        
        # Группируем по студентам
        debts_by_student: Dict[int, List] = {}
        for row in changes:
            student_id = row[0]
            if student_id not in debts_by_student:
                debts_by_student[student_id] = []
            debts_by_student[student_id].append(row)
        
        # Получаем telegram_id для студентов с изменениями
        student_placeholders = ','.join(['?'] * len(debts_by_student))
        async with db_connection.execute(f'''
            SELECT id_student, telegram_id FROM students 
            WHERE id_student IN ({student_placeholders})
            AND telegram_id IS NOT NULL
            AND is_active = 1
        ''', list(debts_by_student.keys())) as cursor:
            students = await cursor.fetchall()
        
        # Отправляем уведомления
        tasks = []
        for student_id, telegram_id in students:
            if student_id not in debts_by_student:
                continue
                
            debts = debts_by_student[student_id]
            messages = []
            
            for debt in debts:
                _, _, _, subject_name, debt_type, last_date, change_type, change_time = debt
                
                notification_key = (student_id, debt[1], debt[2], change_type, 
                                  datetime.strptime(change_time, '%Y-%m-%d %H:%M:%S.%f'))
                if notification_key in tracker.sent_notifications:
                    continue
                
                if change_type == 'created':
                    messages.append(
                        f"➕ Добавлен долг:\n"
                        f"📚 {subject_name}\n"
                        f"🔴 {debt_type}\n"
                        f"⏳ Сдать до: {last_date}\n"
                    )
                elif change_type == 'updated':
                    messages.append(
                        f"🔄 Изменен долг:\n"
                        f"📚 {subject_name}\n"
                        f"🔴 {debt_type}\n"
                        f"⏳ Новый срок: {last_date}\n"
                    )
                elif change_type == 'deleted':
                    messages.append(
                        f"❌ Снят долг:\n"
                        f"📚 {subject_name}\n"
                        f"🔴 {debt_type}\n"
                    )
            
            if not messages:
                continue
                
            full_message = "📢 <b>Изменения в ваших долгах:</b>\n\n" + "\n".join(messages)
            
            tasks.append(
                send_notification_with_retry(
                    bot=bot,
                    chat_id=telegram_id,
                    text=full_message,
                    semaphore=semaphore,
                    notification_key=notification_key,
                    tracker=tracker
                )
            )
        
        # Выполняем все задачи параллельно
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Обрабатываем результаты
        successful = 0
        for result in results:
            if isinstance(result, Exception):
                logger.error(f"Error sending debt notification: {result}")
            else:
                successful += 1
        
        logger.info(f"Sent {successful} debt notifications in {time.time() - start_time:.2f}s")
        
    except Exception as e:
        logger.error(f"Error in check_debt_changes: {e}")
        raise

async def send_notification_with_retry(
    bot: Bot,
    chat_id: int,
    text: str,
    semaphore: asyncio.Semaphore,
    notification_key: Tuple,
    tracker: ChangeTracker,
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
                tracker.sent_notifications.add(notification_key)
                return True
            except Exception as e:
                last_error = e
                if "bot was blocked" in str(e).lower():
                    break  # Не пытаемся повторно, если бот заблокирован
                await asyncio.sleep(1 * (attempt + 1))
        
        logger.error(f"Failed to send notification after {max_retries} attempts: {last_error}")
        return False

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
    
   # Уменьшите задержки
    BATCH_SIZE = 100  # Увеличьте размер батча
    DELAY_BETWEEN_BATCHES = 0.1  # Уменьшите задержку между батчами
    DELAY_BETWEEN_MESSAGES = 0.01  # Уменьшите задержку внутри батча
    
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