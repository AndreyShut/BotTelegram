import sqlite3

def create_database():
    connection = sqlite3.connect('student_bot.db')
    cursor = connection.cursor()
    
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS users (
        user_id INTEGER PRIMARY KEY,
        login TEXT NOT NULL,
        password TEXT NOT NULL
    )
    ''')

    cursor.execute('''
    CREATE TABLE IF NOT EXISTS schedule (
        id INTEGER PRIMARY KEY,
        user_id INTEGER,
        date TEXT,
        subject TEXT,
        FOREIGN KEY (user_id) REFERENCES users (user_id)
    )
    ''')

    cursor.execute('''
    CREATE TABLE IF NOT EXISTS debts (
        id INTEGER PRIMARY KEY,
        user_id INTEGER,
        subject TEXT,
        amount FLOAT,
        FOREIGN KEY (user_id) REFERENCES users (user_id)
    )
    ''')

    cursor.execute('''
    CREATE TABLE IF NOT EXISTS news (
        id INTEGER PRIMARY KEY,
        title TEXT,
        description TEXT,
        date TEXT
    )
    ''')

    cursor.execute('''
    CREATE TABLE IF NOT EXISTS tests (
        id INTEGER PRIMARY KEY,
        user_id INTEGER,
        test_description TEXT,
        date TEXT,
        FOREIGN KEY (user_id) REFERENCES users (user_id)
    )
    ''')

    connection.commit()
    connection.close()

create_database()