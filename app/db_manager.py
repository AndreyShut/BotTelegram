import aiosqlite
import asyncio
import logging
from contextlib import asynccontextmanager

logger = logging.getLogger(__name__)

class Database:
    _instance = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._conn = None
        return cls._instance
    
    async def connect(self):
        """Устанавливает соединение с БД с повторами"""
        if self._conn is None:
            for attempt in range(3):
                try:
                    self._conn = await aiosqlite.connect('student_bot.db')
                    await self._setup_connection()
                    logger.info("DB connection established")
                    return self._conn
                except Exception as e:
                    if attempt == 2:
                        raise
                    await asyncio.sleep(2)
        return self._conn
    
    async def _setup_connection(self):
        """Настройка параметров соединения"""
        await self._conn.execute("PRAGMA journal_mode=WAL")
        await self._conn.execute("PRAGMA synchronous=NORMAL")
        await self._conn.execute("PRAGMA busy_timeout=30000")
        await self._conn.execute("PRAGMA foreign_keys=ON")
    
    @asynccontextmanager
    async def get_connection(self):
        """Контекст для работы с БД"""
        conn = await self.connect()
        try:
            yield conn
        except Exception as e:
            logger.error(f"DB error: {e}")
            await conn.rollback()
            raise
        finally:
            # Соединение не закрываем - оно живет весь срок работы бота
            pass
    
    async def close(self):
        """Закрытие соединения"""
        if self._conn is not None:
            try:
                await self._conn.close()
                self._conn = None
                logger.info("DB connection closed")
            except Exception as e:
                logger.error(f"Error closing DB: {e}")

# Глобальный экземпляр
db = Database()