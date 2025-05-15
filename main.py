import os
import asyncio
import logging

from aiogram import Bot,Dispatcher
from app.handlers import router
from dotenv import load_dotenv
from app.notification import notify_users


load_dotenv()
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def main():
    bot = Bot(token=os.getenv("BOT_TOKEN"))
    dp = Dispatcher()
    dp.include_router(router)
    await bot.delete_webhook(drop_pending_updates=True)
    notification_task = asyncio.create_task(notify_users(bot))
    try:
        await dp.start_polling(bot)
    except Exception as e:
        logging.error(f"Ошибка: {e}")
    finally:
        notification_task.cancel()
        await bot.session.close()

if __name__ == "__main__":
    logger.info("Бот включен")
    try:
        asyncio.run(main())
    except KeyboardInterrupt:   
        logger.info("Бот выключен")
    except Exception as e:
        logger.error(f"Ошибка: {e}")