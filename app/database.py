import sqlite3

def create_database():
    connection = sqlite3.connect('student_bot.db')
    cursor = connection.cursor()

    # Создаем таблицы в правильном порядке, чтобы внешние ключи могли ссылаться на существующие таблицы
    
    # 1. Сначала создаем таблицы, которые не зависят от других
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS groups (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name_group TEXT NOT NULL UNIQUE
        )
    ''')

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS debt_types (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE
        )
    ''')

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS teachers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            full_name TEXT NOT NULL
        )
    ''')

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS subjects (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE
        )
    ''')

    # 2. Затем таблицы, которые зависят от уже созданных
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS students (
            id_student INTEGER PRIMARY KEY AUTOINCREMENT,
            id_group INTEGER NOT NULL,
            login TEXT NOT NULL,
            password TEXT NOT NULL,
            description TEXT,
            telegram_id INTEGER UNIQUE,
            is_active INTEGER DEFAULT 1,
            FOREIGN KEY (id_group) REFERENCES groups(id)
        )
    ''')

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS news (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            description TEXT,
            date TEXT NOT NULL,
            place TEXT,
            for_all_groups INTEGER DEFAULT 1,  -- 1 - для всех, 0 - для конкретных групп
            is_published INTEGER DEFAULT 0      -- 0 - черновик, 1 - опубликовано
        )
    ''')

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS news_groups (
            news_id INTEGER NOT NULL,
            group_id INTEGER NOT NULL,
            PRIMARY KEY (news_id, group_id),
            FOREIGN KEY (news_id) REFERENCES news(id) ON DELETE CASCADE,
            FOREIGN KEY (group_id) REFERENCES groups(id) ON DELETE CASCADE
        )
    ''')

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS sent_notifications (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            news_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            sent_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (news_id) REFERENCES news(id) ON DELETE CASCADE,
            FOREIGN KEY (user_id) REFERENCES students(telegram_id) ON DELETE CASCADE
        )
    ''')

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS tests (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            group_id INTEGER NOT NULL,
            subject_id INTEGER NOT NULL,
            teacher_id INTEGER NOT NULL,
            test_link TEXT NOT NULL,
            date TEXT NOT NULL,
            FOREIGN KEY (group_id) REFERENCES groups(id),
            FOREIGN KEY (subject_id) REFERENCES subjects(id),
            FOREIGN KEY (teacher_id) REFERENCES teachers(id)
        )
    ''')

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS student_debts (
            student_id INTEGER NOT NULL,
            subject_id INTEGER NOT NULL,
            debt_type_id INTEGER NOT NULL,
            last_date TEXT NOT NULL,       -- "YYYY-MM-DD"
            PRIMARY KEY (student_id, subject_id, debt_type_id),
            FOREIGN KEY (student_id) REFERENCES students(id_student),
            FOREIGN KEY (subject_id) REFERENCES subjects(id),
            FOREIGN KEY (debt_type_id) REFERENCES debt_types(id)
        )
    ''')

    
    connection.commit()
    connection.close()

if __name__ == "__main__":
    create_database()