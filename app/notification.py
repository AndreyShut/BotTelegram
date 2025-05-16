import aiosqlite
import asyncio
from aiogram import Bot
import logging
from app.state import BotState
from datetime import datetime

logger = logging.getLogger(__name__)

async def notify_users(bot: Bot):
    sent_news = set()
    db_connection = None
    
    try:
        db_connection = await aiosqlite.connect('student_bot.db')
        while True:
            try:
                # Получаем только опубликованные новости, которые еще не отправлялись
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
                        
                        # Формируем запрос в зависимости от типа новости (для всех или для конкретных групп)
                        if for_all_groups:
                            # Для всех активных пользователей
                            query = '''
                                SELECT s.telegram_id 
                                FROM students s
                                WHERE s.telegram_id IS NOT NULL
                                AND s.is_active = 1
                            '''
                            params = ()
                        else:
                            # Только для пользователей из определенных групп
                            query = '''
                                SELECT s.telegram_id 
                                FROM students s
                                JOIN news_groups ng ON s.id_group = ng.group_id
                                WHERE s.telegram_id IS NOT NULL
                                AND s.is_active = 1
                                AND ng.news_id = ?
                            '''
                            params = (news_id,)
                        
                        # Получаем список пользователей для рассылки
                        async with db_connection.execute(query, params) as cursor:
                            recipients = await cursor.fetchall()
                        
                        # Отправляем новость каждому пользователю
                        for (telegram_id,) in recipients:
                            try:
                                await bot.send_message(
                                    chat_id=telegram_id,
                                    text=f'📢 {title}\n\n{description}'
                                )
                                success_sends += 1
                                await asyncio.sleep(0.5)  # Задержка между сообщениями
                                
                                # Записываем факт отправки
                                await db_connection.execute(
                                    'INSERT INTO sent_notifications (news_id, user_id) VALUES (?, ?)',
                                    (news_id, telegram_id)
                                )
                                
                            except Exception as e:
                                if "chat not found" in str(e):
                                    # Помечаем пользователя как неактивного
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
                
                # Проверяем тесты с ближайшим дедлайном (за 1 день до)
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
                        # Получаем студентов группы
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
                
                await asyncio.sleep(60)  # Проверка каждую минуту
                
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