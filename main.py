import os
import asyncio
import logging
from aiogram import Bot, Dispatcher
from aiogram.exceptions import TelegramNetworkError
from app.handlers import router
from dotenv import load_dotenv
from app.notification import notify_users
from aiogram.client.default import DefaultBotProperties
from app.state import BotState

load_dotenv()
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)



async def close_bot_session(bot: Bot):
    """Корректное закрытие сессии бота"""
    if bot is not None:
        try:
            session = getattr(bot, 'session', None)
            if session and not session.closed:
                await session.close()
                logger.info("Сессия бота успешно закрыта")
        except Exception as e:
            logger.error(f"Ошибка при закрытии сессии бота: {e}")

async def main():
    bot = None
    notification_task = None
    dp = None

    try:
        bot = Bot(token=os.getenv("BOT_TOKEN"))
        BotState.bot_instance = bot
        dp = Dispatcher()
        dp.include_router(router)
        
        # Удаляем webhook с повторными попытками
        max_retries = 3
        for attempt in range(max_retries):
            try:
                await bot.delete_webhook(drop_pending_updates=True)
                break
            except TelegramNetworkError as e:
                if attempt == max_retries - 1:
                    logger.error(f"Не удалось удалить webhook после {max_retries} попыток: {e}")
                    raise
                logger.warning(f"Ошибка при удалении webhook (попытка {attempt + 1}): {e}")
                await asyncio.sleep(5)

        if BotState.notification_task is None:
            BotState.notification_task = asyncio.create_task(notify_users(bot))

        # Запускаем polling с обработкой ошибок сети
        while True:
            try:
                await dp.start_polling(bot, handle_signals=True)
                break  # Если polling завершился без ошибок
            except TelegramNetworkError as e:
                logger.error(f"Ошибка сети в polling: {e}")
                await asyncio.sleep(10)  # Пауза перед повторной попыткой
                continue
            except Exception as e:
                logger.error(f"Неожиданная ошибка в polling: {e}")
                raise

    except asyncio.CancelledError:
        logger.info("Получен сигнал отмены")
    except Exception as e:
        logger.error(f"Критическая ошибка в main: {e}")
    finally:
        # Отменяем задачу рассылки
        await asyncio.sleep(1)
        await BotState.shutdown()

        # Закрываем диспетчер
        if dp is not None:
            try:
                await dp.storage.close()
            except Exception as e:
                logger.error(f"Ошибка при закрытии хранилища диспетчера: {e}")

        if bot:
        # Закрываем сессию бота
            await close_bot_session(bot)

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