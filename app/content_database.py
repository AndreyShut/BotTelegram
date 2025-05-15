import sqlite3

def populate_database():
    conn = sqlite3.connect('student_bot.db')
    cur = conn.cursor()

    # Пример групп
    cur.execute("INSERT OR IGNORE INTO groups (id, name_group) VALUES (?, ?)", (1, '21ВВС1'))
    cur.execute("INSERT OR IGNORE INTO groups (id, name_group) VALUES (?, ?)", (2, '21ВА1'))
    cur.execute("INSERT OR IGNORE INTO groups (id, name_group) VALUES (?, ?)", (3, '22ВВС1'))
    cur.execute("INSERT OR IGNORE INTO groups (id, name_group) VALUES (?, ?)", (4, '22ВА1'))
    cur.execute("INSERT OR IGNORE INTO groups (id, name_group) VALUES (?, ?)", (5, '23ВВ4'))
    cur.execute("INSERT OR IGNORE INTO groups (id, name_group) VALUES (?, ?)", (6, '23ВА1'))
    cur.execute("INSERT OR IGNORE INTO groups (id, name_group) VALUES (?, ?)", (7, '24ВВВ4'))
    cur.execute("INSERT OR IGNORE INTO groups (id, name_group) VALUES (?, ?)", (8, '24ВА1'))

    # Пример пользователей
    cur.execute("INSERT OR IGNORE INTO students (id_student, id_group, login, password, description) VALUES (?, ?, ?, ?, ?)", (2,1,'a123451','124121', "Гребенев А.С."))
    cur.execute("INSERT OR IGNORE INTO students (id_student, id_group, login, password, description) VALUES (?, ?, ?, ?, ?)", (3,1,'a123452','124122', "Калыева С.К."))
    cur.execute("INSERT OR IGNORE INTO students (id_student, id_group, login, password, description) VALUES (?, ?, ?, ?, ?)", (4,2,'a123453','124123', "Колокольцева У.А."))
    cur.execute("INSERT OR IGNORE INTO students (id_student, id_group, login, password, description) VALUES (?, ?, ?, ?, ?)", (5,1,'a123454','124124', "Купцов Т.А."))
    cur.execute("INSERT OR IGNORE INTO students (id_student, id_group, login, password, description) VALUES (?, ?, ?, ?, ?)", (6,1,'a123455','124125', "Куряев Ю.Р."))
    cur.execute("INSERT OR IGNORE INTO students (id_student, id_group, login, password, description) VALUES (?, ?, ?, ?, ?)", (7,1,'a123456','124126', "Нагорная Д.А."))
    cur.execute("INSERT OR IGNORE INTO students (id_student, id_group, login, password, description) VALUES (?, ?, ?, ?, ?)", (8,1,'a123457','124127', "Никитин М.А."))
    cur.execute("INSERT OR IGNORE INTO students (id_student, id_group, login, password, description) VALUES (?, ?, ?, ?, ?)", (9,1,'a123458','124128', "Никишин Д.Д."))
    cur.execute("INSERT OR IGNORE INTO students (id_student, id_group, login, password, description) VALUES (?, ?, ?, ?, ?)", (10,1,'a123459','124129', "Ошкин И.В."))
    cur.execute("INSERT OR IGNORE INTO students (id_student, id_group, login, password, description) VALUES (?, ?, ?, ?, ?)", (11,1,'a123461','124110', "Роганов Д.В."))
    cur.execute("INSERT OR IGNORE INTO students (id_student, id_group, login, password, description) VALUES (?, ?, ?, ?, ?)", (12,1,'a123462','124111', "Савкин В.В."))
    cur.execute("INSERT OR IGNORE INTO students (id_student, id_group, login, password, description) VALUES (?, ?, ?, ?, ?)", (13,1,'a123463','124112', "Сурков Е.В."))
    cur.execute("INSERT OR IGNORE INTO students (id_student, id_group, login, password, description) VALUES (?, ?, ?, ?, ?)", (14,1,'a123464','124113', "Шутихин А.Э."))


    conn.commit()
    conn.close()

populate_database()