import aiosqlite
import asyncio
from aiogram import Bot

async def notify_users(bot: Bot):
    sent_news = set()

    while True:
        try:
            async with aiosqlite.connect('student_bot.db') as db:
                # Получаем последние новости, которые еще не рассылали
                async with db.execute('SELECT id, title, description FROM news ORDER BY date DESC') as cursor:
                    news_list = await cursor.fetchall()

                if news_list:
                    async with db.execute('SELECT id_student FROM students') as cursor:
                        students = await cursor.fetchall()

                    for news_id, title, description in news_list:
                        if news_id in sent_news:
                            continue # Эта новость уже рассылалась
                        for (id_student,) in students:
                            try:
                                await bot.send_message(id_student, f'Новость: {title}\n{description}')
                            except Exception: pass
                        sent_news.add(news_id)
            await asyncio.sleep(60)
        except asyncio.CancelledError:
            print("Notify task cancelled, cleanup if needed")
            raise
        except Exception as e:
            print(f"Ошибка: {e}")
            await asyncio.sleep(60)