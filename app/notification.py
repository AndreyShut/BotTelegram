import aiosqlite
import asyncio
from aiogram import Bot
import logging
from app.state import BotState
from datetime import datetime
import os
import hashlib

logger = logging.getLogger(__name__)

class FileWatcher:
    def __init__(self):
        self.file_hashes = {}
        
    async def get_file_hash(self, file_path):
        if not os.path.exists(file_path):
            return None
            
        with open(file_path, 'rb') as f:
            file_hash = hashlib.md5(f.read()).hexdigest()
        return file_hash
        
    async def check_file_changes(self, file_path):
        current_hash = await self.get_file_hash(file_path)
        if not current_hash:
            return False
            
        if file_path not in self.file_hashes:
            self.file_hashes[file_path] = current_hash
            return False
            
        if self.file_hashes[file_path] != current_hash:
            self.file_hashes[file_path] = current_hash
            return True
            
        return False

async def notify_users(bot: Bot):
    sent_news = set()
    db_connection = None
    file_watcher = FileWatcher()
    
    # Файлы для отслеживания изменений
    schedule_files = [
        "Расписание_групп.xlsx",
        "Расписание_преподавателей.xls",
        "График_задолженностей.xlsx"
    ]
    
    try:
        db_connection = await aiosqlite.connect('student_bot.db')
        while True:
            try:
                # 1. Проверка новых новостей
                async with db_connection.execute('''
                    SELECT id, title, description, for_all_groups 
                    FROM news 
                    WHERE is_published = 1 
                    AND id NOT IN (SELECT news_id FROM sent_notifications)
                    ORDER BY date DESC
                ''') as cursor:
                    news_list = await cursor.fetchall()

                if news_list:
                    for news_id, title, description, for_all_groups in news_list:
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
                        
                        for (telegram_id,) in recipients:
                            try:
                                await bot.send_message(
                                    chat_id=telegram_id,
                                    text=f'📢 {title}\n\n{description}'
                                )
                                success_sends += 1
                                await asyncio.sleep(0.5)
                                
                                await db_connection.execute(
                                    'INSERT INTO sent_notifications (news_id, user_id) VALUES (?, ?)',
                                    (news_id, telegram_id)
                                )
                                
                            except Exception as e:
                                if "chat not found" in str(e):
                                    await db_connection.execute(
                                        'UPDATE students SET is_active = 0 WHERE telegram_id = ?',
                                        (telegram_id,)
                                    )
                                    logger.warning(f"Пользователь {telegram_id} недоступен, помечен как неактивный")
                                else:
                                    logger.error(f"Ошибка отправки {telegram_id}: {e}")
                        
                        await db_connection.commit()
                        if success_sends > 0:
                            sent_news.add(news_id)
                            logger.info(f"Новость {news_id} отправлена {success_sends} пользователям")
                
                # 2. Проверка тестов
                today = datetime.now().strftime("%Y-%m-%d")
                async with db_connection.execute('''
                    SELECT t.id, t.test_link, t.date, g.name_group, s.name 
                    FROM tests t
                    JOIN groups g ON t.group_id = g.id
                    JOIN subjects s ON t.subject_id = s.id
                    WHERE date(t.date, '-1 day') = date(?)
                ''', (today,)) as cursor:
                    upcoming_tests = await cursor.fetchall()
                
                if upcoming_tests:
                    for test_id, test_link, test_date, group_name, subject_name in upcoming_tests:
                        async with db_connection.execute('''
                            SELECT telegram_id FROM students 
                            WHERE id_group = (SELECT id FROM groups WHERE name_group = ?)
                            AND telegram_id IS NOT NULL
                            AND is_active = 1
                        ''', (group_name,)) as cursor:
                            students = await cursor.fetchall()
                        
                        for (telegram_id,) in students:
                            try:
                                await bot.send_message(
                                    chat_id=telegram_id,
                                    text=f'⚠️ Напоминание о тесте!\n\n'
                                         f'Предмет: {subject_name}\n'
                                         f'Группа: {group_name}\n'
                                         f'Дата: {test_date}\n'
                                         f'Ссылка: {test_link}'
                                )
                                await asyncio.sleep(0.5)
                            except Exception as e:
                                logger.error(f"Ошибка отправки напоминания о тесте {telegram_id}: {e}")
                
                # 3. Проверка изменений в файлах расписания
                for file_path in schedule_files:
                    if await file_watcher.check_file_changes(file_path):
                        logger.info(f"Обнаружено изменение в файле {file_path}")
                        
                        # Определяем тип расписания по имени файла
                        if "групп" in file_path:
                            schedule_type = "групп"
                        elif "преподавателей" in file_path:
                            schedule_type = "преподавателей"
                        else:
                            schedule_type = "задолженностей"
                        
                        # Получаем всех активных пользователей
                        async with db_connection.execute('''
                            SELECT telegram_id FROM students 
                            WHERE telegram_id IS NOT NULL
                            AND is_active = 1
                        ''') as cursor:
                            users = await cursor.fetchall()
                        
                        # Отправляем уведомление
                        for (telegram_id,) in users:
                            try:
                                await bot.send_message(
                                    chat_id=telegram_id,
                                    text=f'ℹ️ Обновлено расписание {schedule_type}!'
                                )
                                await asyncio.sleep(0.5)
                            except Exception as e:
                                logger.error(f"Ошибка отправки уведомления об изменении расписания {telegram_id}: {e}")
                
                await asyncio.sleep(60)
                
            except Exception as e:
                logger.error(f"Ошибка в цикле рассылки: {e}")
                await asyncio.sleep(60)
                
    except asyncio.CancelledError:
        logger.info("Рассылка уведомлений остановлена")
    finally:
        if BotState.notification_task:
            BotState.notification_task = None
        if db_connection:
            await db_connection.close()
        logger.info("Соединение с БД закрыто")