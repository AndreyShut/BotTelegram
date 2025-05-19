import aiosqlite
import asyncio
from aiogram import Bot
import logging
from datetime import datetime, timedelta
import os
import hashlib
import time
from typing import Optional, List, Dict, Any

logger = logging.getLogger(__name__)

class FileWatcher:
    def __init__(self):
        self.file_hashes = {}
        self.file_stats = {}  # Для хранения метаданных
        
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
                return True
                
        return False

async def notify_users(bot: Bot):
    sent_news = set()
    db_connection = None
    file_watcher = FileWatcher()
    
    # Конфигурационные параметры
    BATCH_SIZE = 30  # Размер батча для отправки
    DELAY_BETWEEN_BATCHES = 1  # Задержка между батчами в секундах
    DELAY_BETWEEN_MESSAGES = 0.1  # Задержка между сообщениями внутри батча
    
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
                    AND n.id NOT IN (SELECT news_id FROM sent_notifications)
                    ORDER BY n.date DESC
                ''') as cursor:
                    news_list = await cursor.fetchall()

                if news_list:
                    for news_id, title, description, for_all_groups, date, place in news_list:
                        if news_id in sent_news:
                            continue
                            
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
                                        if "chat not found" in str(result):
                                            await db_connection.execute(
                                                'UPDATE students SET is_active = 0 WHERE telegram_id = ?',
                                                (telegram_id,)
                                            )
                                            logger.warning(f"Пользователь {telegram_id} недоступен, помечен как неактивный")
                                        else:
                                            logger.error(f"Ошибка отправки {telegram_id}: {result}")
                                    else:
                                        await db_connection.execute(
                                            'INSERT INTO sent_notifications (news_id, user_id) VALUES (?, ?)',
                                            (news_id, telegram_id)
                                        )
                                        success_sends += 1
                                
                                await db_connection.commit()
                                await asyncio.sleep(DELAY_BETWEEN_BATCHES)
                                
                            except Exception as e:
                                logger.error(f"Ошибка при отправке батча: {e}")
                        
                        if success_sends > 0:
                            sent_news.add(news_id)
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
                                await asyncio.gather(*tasks, return_exceptions=True)
                                await asyncio.sleep(DELAY_BETWEEN_BATCHES)
                            except Exception as e:
                                logger.error(f"Ошибка при отправке батча напоминаний о тестах: {e}")
                
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
                            await asyncio.gather(*tasks, return_exceptions=True)
                            await asyncio.sleep(DELAY_BETWEEN_BATCHES)
                        except Exception as e:
                            logger.error(f"Ошибка при отправке батча напоминаний о долгах: {e}")
                
                # 4. Проверка изменений в файлах расписания с batch-обработкой
                for file_path in schedule_files:
                    if await file_watcher.check_file_changes(file_path):
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
                                await asyncio.gather(*tasks, return_exceptions=True)
                                await asyncio.sleep(DELAY_BETWEEN_BATCHES)
                            except Exception as e:
                                logger.error(f"Ошибка при отправке батча уведомлений о расписании: {e}")
                
                await asyncio.sleep(60)
                
            except Exception as e:
                logger.error(f"Ошибка в цикле рассылки: {e}")
                await asyncio.sleep(60)
                
    except asyncio.CancelledError:
        logger.info("Рассылка уведомлений остановлена")
    finally:
        if db_connection:
            await db_connection.close()
        logger.info("Соединение с БД закрыто")