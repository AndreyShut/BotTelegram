import sqlite3

def create_database():
    connection = sqlite3.connect('student_bot.db')
    cursor = connection.cursor()

    # Группы студентов
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS groups (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE
        )
    ''')

    # Пользователи
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            login TEXT NOT NULL,
            password TEXT NOT NULL,
            group_id INTEGER,
            FOREIGN KEY (group_id) REFERENCES groups(id)
        )
    ''')

    # Новости
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS news (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            description TEXT,
            date TEXT NOT NULL,
            place TEXT
        )
    ''')

    # События
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            description TEXT,
            date TEXT NOT NULL,
            place TEXT,
            group_id INTEGER,
            FOREIGN KEY (group_id) REFERENCES groups(id)
        )
    ''')

    # Расписание (для группы)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS schedule (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            group_id INTEGER,
            date TEXT NOT NULL,
            start_time TEXT,
            end_time TEXT,
            subject TEXT NOT NULL,
            lecturer TEXT,
            classroom TEXT,
            FOREIGN KEY (group_id) REFERENCES groups(id)
        )
    ''')

    # Задолженности (для пользователя)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS debts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            subject TEXT NOT NULL,
            amount REAL NOT NULL,
            FOREIGN KEY (user_id) REFERENCES users(user_id)
        )
    ''')

    # Тесты (на группу)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS tests (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            group_id INTEGER,
            test_description TEXT,
            date TEXT,
            file_link TEXT,
            FOREIGN KEY (group_id) REFERENCES groups(id)
        )
    ''')

    connection.commit()
    connection.close()

create_database()