import sqlite3

def populate_database():
    conn = sqlite3.connect('student_bot.db')
    cur = conn.cursor()

    # Пример групп
    cur.execute("INSERT OR IGNORE INTO groups (id, name) VALUES (?, ?)", (1, '21ВВС1'))
    cur.execute("INSERT OR IGNORE INTO groups (id, name) VALUES (?, ?)", (2, '21ВА1'))
    cur.execute("INSERT OR IGNORE INTO groups (id, name) VALUES (?, ?)", (2, '22ВВС1'))
    cur.execute("INSERT OR IGNORE INTO groups (id, name) VALUES (?, ?)", (2, '22ВА1'))
    cur.execute("INSERT OR IGNORE INTO groups (id, name) VALUES (?, ?)", (2, '23ВВ4'))
    cur.execute("INSERT OR IGNORE INTO groups (id, name) VALUES (?, ?)", (2, '23ВА1'))
    cur.execute("INSERT OR IGNORE INTO groups (id, name) VALUES (?, ?)", (2, '24ВВВ4'))
    cur.execute("INSERT OR IGNORE INTO groups (id, name) VALUES (?, ?)", (2, '24ВА1'))

    # Пример пользователей
    cur.execute("INSERT OR IGNORE INTO users (user_id, login, password, group_id) VALUES (?, ?, ?, ?)", (123456, "Andrey", "passwd1", 1))
    cur.execute("INSERT OR IGNORE INTO users (user_id, login, password, group_id) VALUES (?, ?, ?, ?)", (123457, "Vadim", "passwd2", 1))

    # Пример расписания
    cur.execute("INSERT INTO schedule (group_id, date, start_time, end_time, subject, lecturer, classroom) VALUES (?, ?, ?, ?, ?, ?, ?)", (1, "2025-05-12", "08:00", "9:30", "Информационные технологии", "Бождай А.С.", "7a-203"))
    cur.execute("INSERT INTO schedule (group_id, date, start_time, end_time, subject, lecturer, classroom) VALUES (?, ?, ?, ?, ?, ?, ?)", (1, "2025-05-18", "09:50", "11:20", "Качество и тестирование ПО", "Эпп В.В.", "7a-203"))

    # Пример новости
    cur.execute("INSERT INTO news (title, description, date, place) VALUES (?, ?, ?, ?)",
                ("Новости образования", "Абилимпикс в ПГУ", "2025-04-21", "7а-203"))

    # Пример событий
    cur.execute("INSERT INTO events (title, description, date, place, group_id) VALUES (?, ?, ?, ?, ?)",
                ("Ярмарка вакансий", "Встреча с работодателями", "2025-04-03", "8 Корпус", None))
    cur.execute("INSERT INTO events (title, description, date, place, group_id) VALUES (?, ?, ?, ?, ?)",
                ("Собрание группы", "Практика", "2025-05-21", "7а-203", 1))

    # Пример задолженности
    cur.execute("INSERT INTO debts (user_id, subject, amount) VALUES (?, ?, ?)", (123456, "Технология больших данные", 1))
    cur.execute("INSERT INTO debts (user_id, subject, amount) VALUES (?, ?, ?)", (123457, "Математика", 1))

    # Пример тестов
    cur.execute("INSERT INTO tests (group_id, test_description, date, file_link) VALUES (?, ?, ?, ?)",
                (1, "Тест Геометрическому моделированию в АП", "2025-04-07", "ссылка на тест"))
    cur.execute("INSERT INTO tests (group_id, test_description, date, file_link) VALUES (?, ?, ?, ?)",
                (2, "Тест Качество и тестирование ПО", "2024-04-08", "ссылка"))

    conn.commit()
    conn.close()

populate_database()