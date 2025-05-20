import aiosqlite
import asyncio
import logging
from contextlib import asynccontextmanager
import bcrypt
from typing import Optional, AsyncGenerator

logger = logging.getLogger(__name__)

class PasswordManager:
    @staticmethod
    async def hash_password(password: str) -> str:
        """Хеширует пароль с использованием bcrypt"""
        if not password:
            raise ValueError("Password cannot be empty")
        
        # Генерируем соль и хешируем пароль
        salt = bcrypt.gensalt()  
        hashed = bcrypt.hashpw(password.encode('utf-8'), salt)
        if isinstance(hashed, bytes):
            return hashed.decode('utf-8')
        return hashed

    @staticmethod
    async def verify_password(hashed_password: str, plain_password: str) -> bool:
        """Проверяет соответствие пароля хешу"""
        try:
            if not hashed_password or not plain_password:
                return False
            # Проверяем пароль
            return bcrypt.checkpw(
                plain_password.encode('utf-8'),
                hashed_password.encode('utf-8')
            )
        except Exception as e:
            logger.error(f"Password verification error: {e}")
            return False

class Database:
    _instance: Optional['Database'] = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._conn = None
            cls._instance._connection_attempts = 0
        return cls._instance
    
    @asynccontextmanager
    async def transaction(self) -> AsyncGenerator[aiosqlite.Connection, None]:
        """Provides a connection with an active transaction"""
        conn = await self.connect()
        try:
            await conn.execute("BEGIN")
            yield conn
            await conn.commit()
        except Exception as e:
            await conn.rollback()
            logger.error(f"Transaction failed: {e}")
            raise
        
    
    async def connect(self) -> aiosqlite.Connection:
        """Устанавливает соединение с БД с автоматическими повторами"""
        max_attempts = 3
        backoff_delay = 2  # секунды
        
        if self._conn is None:
            for attempt in range(1, max_attempts + 1):
                try:
                    self._conn = await aiosqlite.connect('student_bot.db')
                    await self._setup_connection(self._conn)
                    logger.info("Database connection established")
                    return self._conn
                except Exception as e:
                    if attempt == max_attempts:
                        logger.error("Failed to establish DB connection after %d attempts", max_attempts)
                        raise
                    logger.warning("DB connection attempt %d failed, retrying...", attempt)
                    await asyncio.sleep(backoff_delay * attempt)
        return self._conn
    
    async def _setup_connection(self, conn: aiosqlite.Connection) -> None:
        """Настраивает параметры соединения с БД"""
        await conn.execute("PRAGMA journal_mode=WAL")
        await conn.execute("PRAGMA synchronous=NORMAL")
        await conn.execute("PRAGMA busy_timeout=30000")
        await conn.execute("PRAGMA foreign_keys=ON")
        await conn.commit()
        logger.debug("Database connection configured")
    
    @asynccontextmanager
    async def get_connection(self) -> AsyncGenerator[aiosqlite.Connection, None]:
        """Предоставляет соединение с БД в контексте"""
        conn = await self.connect()
        try:
            yield conn
        except aiosqlite.Error as e:
            logger.error(f"Database error: {e}")
            await conn.rollback()
            raise
        except Exception as e:
            logger.error(f"Unexpected error: {e}")
            await conn.rollback()
            raise
    
    async def close(self) -> None:
        """Корректно закрывает соединение с БД"""
        if self._conn is not None:
            try:
                await self._conn.close()
                self._conn = None
                logger.info("Database connection closed")
            except Exception as e:
                logger.error(f"Error closing database connection: {e}")
                raise
    
    async def execute(self, query: str, *args, **kwargs) -> None:
        """Выполняет SQL-запрос без возврата результата"""
        async with self.get_connection() as conn:
            await conn.execute(query, *args, **kwargs)
            await conn.commit()
    
    async def fetch_one(self, query: str, *args, **kwargs) -> Optional[dict]:
        """Выполняет запрос и возвращает одну строку"""
        async with self.get_connection() as conn:
            cursor = await conn.execute(query, *args, **kwargs)
            row = await cursor.fetchone()
            return dict(row) if row else None
    
    async def fetch_all(self, query: str, *args, **kwargs) -> list[dict]:
        """Выполняет запрос и возвращает все строки"""
        async with self.get_connection() as conn:
            cursor = await conn.execute(query, *args, **kwargs)
            rows = await cursor.fetchall()
            return [dict(row) for row in rows] if rows else []

# Глобальный экземпляр для использования
db = Database()
pm = PasswordManager()