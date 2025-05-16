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
            place TEXT
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
 

    connection.commit()
    connection.close()
    
if __name__ == "__main__":
    create_database()  # Теперь скрипт нужно запускать вручную


