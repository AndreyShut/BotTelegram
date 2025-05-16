import aiosqlite
import asyncio
from aiogram import Bot
import logging
from app.state import BotState

logger = logging.getLogger(__name__)

async def notify_users(bot: Bot):
    sent_news = set()
    db_connection = None
    
    try:
        db_connection = await aiosqlite.connect('student_bot.db')
        while True:
            try:
                # Получаем только новые новости
                async with db_connection.execute('''
                    SELECT id, title, description FROM news 
                    WHERE id NOT IN (
                        SELECT news_id FROM sent_notifications
                    ) ORDER BY date DESC
                ''') as cursor:
                    news_list = await cursor.fetchall()

                if news_list:
                    # Получаем только активных пользователей
                    async with db_connection.execute('''
                        SELECT telegram_id FROM students 
                        WHERE telegram_id IS NOT NULL
                        AND is_active = 1
                    ''') as cursor:
                        active_users = await cursor.fetchall()

                    for news_id, title, description in news_list:
                        if news_id in sent_news:
                            continue
                            
                        success_sends = 0
                        for (telegram_id,) in active_users:
                            try:
                                await bot.send_message(
                                    chat_id=telegram_id,
                                    text=f'📢{title}\n\n{description}'
                                )
                                success_sends += 1
                                await asyncio.sleep(0.5)  # Задержка между сообщениями
                                
                                # Записываем факт успешной отправки
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
                
                await asyncio.sleep(60)  # Проверка новых новостей каждую минуту
                
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