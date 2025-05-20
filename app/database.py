import sqlite3
import logging
from typing import Optional, List, Dict, Any

logger = logging.getLogger(__name__)

class StudentBotDB:
    def __init__(self, db_name: str = 'student_bot.db'):
        self.db_name = db_name
        self.create_database()

    def _execute(self, query: str, params: tuple = (), commit: bool = False) -> sqlite3.Cursor:
        """Внутренний метод для выполнения SQL-запросов"""
        connection = sqlite3.connect(self.db_name)
        cursor = connection.cursor()
        try:
            cursor.execute(query, params)
            if commit:
                connection.commit()
            return cursor
        except Exception as e:
            connection.rollback()
            raise e
        finally:
            if not commit:
                connection.close()

    def create_database(self):

        """Создание всех таблиц базы данных и индексов"""
        # Создание таблиц
        table_queries = [
            '''CREATE TABLE IF NOT EXISTS groups (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name_group TEXT NOT NULL UNIQUE
            )''',
            '''CREATE TABLE IF NOT EXISTS debt_types (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL UNIQUE
            )''',
            '''CREATE TABLE IF NOT EXISTS teachers (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                full_name TEXT NOT NULL
            )''',
            '''CREATE TABLE IF NOT EXISTS subjects (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL UNIQUE
            )''',
            '''CREATE TABLE IF NOT EXISTS students (
                id_student INTEGER PRIMARY KEY AUTOINCREMENT,
                id_group INTEGER NOT NULL,
                login TEXT NOT NULL,
                password TEXT NOT NULL,
                description TEXT,
                telegram_id INTEGER UNIQUE,
                is_active INTEGER DEFAULT 1,
                FOREIGN KEY (id_group) REFERENCES groups(id)
            )''',
            '''CREATE TABLE IF NOT EXISTS news (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                description TEXT,
                date TEXT NOT NULL,
                place TEXT,
                for_all_groups INTEGER DEFAULT 1,
                is_published INTEGER DEFAULT 0
            )''',
            '''CREATE TABLE IF NOT EXISTS disciplines (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                subject_id INTEGER NOT NULL,
                teacher_id INTEGER NOT NULL,
                group_id INTEGER,
                FOREIGN KEY (subject_id) REFERENCES subjects(id),
                FOREIGN KEY (teacher_id) REFERENCES teachers(id),
                FOREIGN KEY (group_id) REFERENCES groups(id),
                UNIQUE(subject_id, teacher_id, group_id)
            )''',
            '''CREATE TABLE IF NOT EXISTS news_groups (
                news_id INTEGER NOT NULL,
                group_id INTEGER NOT NULL,
                PRIMARY KEY (news_id, group_id),
                FOREIGN KEY (news_id) REFERENCES news(id) ON DELETE CASCADE,
                FOREIGN KEY (group_id) REFERENCES groups(id) ON DELETE CASCADE
            )''',
            '''CREATE TABLE IF NOT EXISTS sent_notifications (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                notification_type TEXT NOT NULL,  -- 'news', 'test', 'debt'
                entity_id INTEGER,               -- ID новости/теста
                entity_date TEXT,                -- Для долгов (last_date)
                user_id INTEGER NOT NULL,
                sent_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES students(telegram_id) ON DELETE CASCADE
            )''',
            '''CREATE TABLE IF NOT EXISTS tests (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                group_id INTEGER NOT NULL,
                discipline_id INTEGER NOT NULL,
                test_link TEXT NOT NULL,
                date TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                deleted_at TIMESTAMP,
                FOREIGN KEY (group_id) REFERENCES groups(id),
                FOREIGN KEY (discipline_id) REFERENCES disciplines(id)
            )''',
            '''CREATE TABLE IF NOT EXISTS student_debts (
                student_id INTEGER NOT NULL,
                discipline_id INTEGER NOT NULL,
                debt_type_id INTEGER NOT NULL,
                last_date TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                deleted_at TIMESTAMP,
                PRIMARY KEY (student_id, discipline_id, debt_type_id),
                FOREIGN KEY (student_id) REFERENCES students(id_student),
                FOREIGN KEY (discipline_id) REFERENCES disciplines(id),
                FOREIGN KEY (debt_type_id) REFERENCES debt_types(id)
            )'''
        ]
        
        # Создание индексов
        index_queries = [
            # Индексы для таблицы students
            'CREATE INDEX IF NOT EXISTS idx_students_telegram ON students(telegram_id)',
            'CREATE INDEX IF NOT EXISTS idx_students_active ON students(is_active)',
            'CREATE INDEX IF NOT EXISTS idx_students_group ON students(id_group)',
            'CREATE INDEX IF NOT EXISTS idx_students_telegram_active ON students(telegram_id, is_active)',

            # Индексы для таблицы tests
            'CREATE INDEX IF NOT EXISTS idx_tests_date ON tests(date)',
            'CREATE INDEX IF NOT EXISTS idx_tests_group ON tests(group_id)',
            'CREATE INDEX IF NOT EXISTS idx_tests_discipline ON tests(discipline_id)',
            'CREATE INDEX IF NOT EXISTS idx_tests_timestamps ON tests(created_at, updated_at, deleted_at)',
            'CREATE INDEX IF NOT EXISTS idx_tests_updated ON tests(updated_at)',

            # Индексы для таблицы student_debts
            'CREATE INDEX IF NOT EXISTS idx_debts_date ON student_debts(last_date)',
            'CREATE INDEX IF NOT EXISTS idx_debts_student ON student_debts(student_id)',
            'CREATE INDEX IF NOT EXISTS idx_debts_discipline ON student_debts(discipline_id)',
            'CREATE INDEX IF NOT EXISTS idx_debts_timestamps ON student_debts(created_at, updated_at, deleted_at)',
            'CREATE INDEX IF NOT EXISTS idx_debts_updated ON student_debts(updated_at)',

            # Индексы для таблицы sent_notifications
            'CREATE INDEX IF NOT EXISTS idx_sent_notifications_user ON sent_notifications(user_id)',
            'CREATE INDEX IF NOT EXISTS idx_sent_notifications_type ON sent_notifications(notification_type, entity_id)',
            'CREATE INDEX IF NOT EXISTS idx_sent_notifications_date ON sent_notifications(entity_date)',
            
            # Индексы для таблицы disciplines
            'CREATE INDEX IF NOT EXISTS idx_disciplines_subject ON disciplines(subject_id)',
            'CREATE INDEX IF NOT EXISTS idx_disciplines_teacher ON disciplines(teacher_id)',
            'CREATE INDEX IF NOT EXISTS idx_disciplines_group ON disciplines(group_id)'
        ]


        trigger_queries = [
            '''CREATE TRIGGER IF NOT EXISTS update_test_timestamp
            AFTER UPDATE ON tests
            FOR EACH ROW
            WHEN (OLD.group_id != NEW.group_id OR 
                OLD.discipline_id != NEW.discipline_id OR
                OLD.test_link != NEW.test_link OR
                OLD.date != NEW.date OR
                (OLD.deleted_at IS NULL AND NEW.deleted_at IS NOT NULL) OR
                (OLD.deleted_at IS NOT NULL AND NEW.deleted_at IS NULL))
            BEGIN
                UPDATE tests SET updated_at = datetime('now') WHERE id = NEW.id;
            END;''',
            
            '''CREATE TRIGGER IF NOT EXISTS update_debt_timestamp
            AFTER UPDATE ON student_debts
            FOR EACH ROW
            WHEN (OLD.last_date != NEW.last_date OR
                (OLD.deleted_at IS NULL AND NEW.deleted_at IS NOT NULL) OR
                (OLD.deleted_at IS NOT NULL AND NEW.deleted_at IS NULL))
            BEGIN
                UPDATE student_debts SET updated_at = datetime('now') 
                WHERE student_id = NEW.student_id 
                AND discipline_id = NEW.discipline_id 
                AND debt_type_id = NEW.debt_type_id;
            END;'''
        ]

        # Создаем таблицы
        for query in table_queries:
            self._execute(query, commit=True)
            
        # Создаем индексы
        for query in index_queries:
            try:
                self._execute(query, commit=True)
            except Exception as e:
                logger.error(f"Ошибка при создании индекса: {e}")
        
        # Создаем триггеры
        for query in trigger_queries:
            try:
                self._execute(query, commit=True)
                logger.info("Database triggers created successfully")
            except Exception as e:
                logger.error(f"Ошибка при создании триггера: {e}")

if __name__ == "__main__":
    db = StudentBotDB()