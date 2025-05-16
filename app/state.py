import asyncio
from typing import Optional
from aiogram import Bot

class BotState:
    notification_task: Optional[asyncio.Task] = None
    bot_instance: Optional['Bot'] = None  # Для хранения экземпляра бота, если нужно

    @classmethod
    async def shutdown(cls):
        """Корректное завершение всех задач"""
        if cls.notification_task and not cls.notification_task.done():
            cls.notification_task.cancel()
            try:
                await cls.notification_task
            except asyncio.CancelledError:
                pass
        cls.notification_task = None
        cls.bot_instance = None