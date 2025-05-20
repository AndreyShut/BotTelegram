import os
import asyncio
import logging
from aiogram import Bot, Dispatcher
from aiogram.exceptions import TelegramNetworkError
from app.handlers import router
from dotenv import load_dotenv
from app.notification import notify_users,track_changes
from app.state import BotState
from app.db_manager import db

load_dotenv()
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)



async def shutdown(bot: Bot):
    """Корректное завершение работы бота"""
    try:
        await BotState.shutdown()
        await db.close()
        if bot:
            await bot.session.close()
        logger.info("Бот успешно завершил работу")
    except Exception as e:
        logger.error(f"Ошибка при завершении работы: {e}")

async def main():
    max_restarts = 3
    restart_delay = 30
    for attempt in range(max_restarts):
        bot = Bot(token=os.getenv("BOT_TOKEN"))
        dp = Dispatcher()
        try:
            await db.connect()
            BotState.bot_instance = bot
            dp.include_router(router)
        
            for webhook_attempt in range(3):
                try:
                    await bot.delete_webhook(drop_pending_updates=True)
                    break
                except TelegramNetworkError as e:
                    if attempt == 2:
                        logger.error(f"Не удалось удалить webhook после {3} попыток: {e}")
                        raise
                    logger.warning(f"Ошибка при удалении webhook (попытка {attempt + 1}): {e}")
                    await asyncio.sleep(5)

            notification_task = asyncio.create_task(notify_users(bot))
            change_tracking_task = asyncio.create_task(track_changes('student_bot.db', bot))

        # Запускаем polling с обработкой ошибок сети
            async def run_tasks():
                        while True:
                            try:
                                await dp.start_polling(bot)
                            except Exception as e:
                                logger.error(f"Polling error: {e}")
                                await asyncio.sleep(10)

            await asyncio.gather(
            run_tasks(),
            notification_task,
            change_tracking_task,
            return_exceptions=True
            )
            
        except Exception as e:
            logger.critical(f"Critical error: {e}")
        finally:
            await shutdown(bot)
            

if __name__ == "__main__":
    logger.info("Бот запускается")
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Бот остановлен по запросу пользователя")
    except Exception as e:
        logger.error(f"Критическая ошибка при запуске бота: {e}")
    finally:
        logger.info("Работа бота завершена")