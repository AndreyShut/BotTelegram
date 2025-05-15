import sqlite3


def create_database():
    connection = sqlite3.connect('student_bot.db')
    cursor = connection.cursor()

    # Группы студентов
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS groups (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name_group TEXT NOT NULL UNIQUE
        )
    ''')

    # Студенты
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS students (
            id_student INTEGER PRIMARY KEY AUTOINCREMENT,
            id_group INTEGER NOT NULL,
            login TEXT NOT NULL,
            password TEXT NOT NULL,
            description TEXT,
            telegram_id INTEGER UNIQUE,
            FOREIGN KEY (id_group) REFERENCES groups(id)
        )
    ''')

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS news (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            description TEXT,
            date TEXT NOT NULL,
            place TEXT
        )
    ''')


    connection.commit()
    connection.close()
create_database()

