import sqlite3
from typing import Optional, List, Dict, Any

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
        """Создание всех таблиц базы данных"""
        queries = [
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
                is_active INTEGER DEFAULT 0,
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
                news_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                sent_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (news_id) REFERENCES news(id) ON DELETE CASCADE,
                FOREIGN KEY (user_id) REFERENCES students(telegram_id) ON DELETE CASCADE
            )''',
            '''CREATE TABLE IF NOT EXISTS tests (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                group_id INTEGER NOT NULL,
                discipline_id INTEGER NOT NULL,
                test_link TEXT NOT NULL,
                date TEXT NOT NULL,
                FOREIGN KEY (group_id) REFERENCES groups(id),
                FOREIGN KEY (discipline_id) REFERENCES disciplines(id)
            )''',
            '''CREATE TABLE IF NOT EXISTS student_debts (
                student_id INTEGER NOT NULL,
                discipline_id INTEGER NOT NULL,
                debt_type_id INTEGER NOT NULL,
                last_date TEXT NOT NULL,
                PRIMARY KEY (student_id, discipline_id, debt_type_id),
                FOREIGN KEY (student_id) REFERENCES students(id_student),
                FOREIGN KEY (discipline_id) REFERENCES disciplines(id),
                FOREIGN KEY (debt_type_id) REFERENCES debt_types(id)
            )'''
        ]
        
        for query in queries:
            self._execute(query, commit=True)
            
if __name__ == "__main__":
    StudentBotDB()
    