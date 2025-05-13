import sqlite3

def populate_database():
    connection = sqlite3.connect('student_bot.db')
    cursor = connection.cursor()

    try:
        cursor.execute("INSERT OR IGNORE INTO users (user_id, login, password) VALUES (?, ?, ?)", (1, 'student1', 'password1'))
        cursor.execute("INSERT OR IGNORE INTO users (user_id, login, password) VALUES (?, ?, ?)", (2, 'student2', 'password2'))

        cursor.execute('INSERT INTO schedule (user_id, date, subject) VALUES (?, ?, ?)', (1, '2024-04-01', 'Математика'))
        cursor.execute('INSERT INTO schedule (user_id, date, subject) VALUES (?, ?, ?)', (1, '2024-04-01', 'Физика'))
        cursor.execute('INSERT INTO schedule (user_id, date, subject) VALUES (?, ?, ?)', (2, '2024-04-02', 'Химия'))

        cursor.execute('INSERT INTO debts (user_id, subject, amount) VALUES (?, ?, ?)', (1, 'Алгебра', 1500.0))
        cursor.execute('INSERT INTO debts (user_id, subject, amount) VALUES (?, ?, ?)', (2, 'Геометрия', 500.0))

        cursor.execute('INSERT INTO news (title, description, date) VALUES (?, ?, ?)',
                       ('Новая олимпиада', 'Открыта регистрация на олимпиаду.', '2024-04-01'))

        cursor.execute('INSERT INTO tests (user_id, test_description, date) VALUES (?, ?, ?)',
                       (1, 'Тест по математике', '2024-04-02'))

        connection.commit()
    except Exception as e:
        print(f'Error: {e}')
    finally:
        connection.close()

populate_database()