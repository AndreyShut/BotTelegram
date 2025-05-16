import sqlite3
from security import PasswordManager


def populate_database():
    conn = sqlite3.connect('student_bot.db')
    cur = conn.cursor()
    pw_manager = PasswordManager()

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
    cur.execute("INSERT OR IGNORE INTO students (id_student, id_group, login, password, description) VALUES (?, ?, ?, ?, ?)", (2,1,'a123451',pw_manager.encrypt('124101'), "Гребенев А.С."))
    cur.execute("INSERT OR IGNORE INTO students (id_student, id_group, login, password, description) VALUES (?, ?, ?, ?, ?)", (3,1,'a123452',pw_manager.encrypt('124111'), "Калыева С.К."))
    cur.execute("INSERT OR IGNORE INTO students (id_student, id_group, login, password, description) VALUES (?, ?, ?, ?, ?)", (4,2,'a123453',pw_manager.encrypt('124121'), "Колокольцева У.А."))
    cur.execute("INSERT OR IGNORE INTO students (id_student, id_group, login, password, description) VALUES (?, ?, ?, ?, ?)", (5,1,'a123454',pw_manager.encrypt('124131'), "Купцов Т.А."))
    cur.execute("INSERT OR IGNORE INTO students (id_student, id_group, login, password, description) VALUES (?, ?, ?, ?, ?)", (6,1,'a123455',pw_manager.encrypt('124141'), "Куряев Ю.Р."))
    cur.execute("INSERT OR IGNORE INTO students (id_student, id_group, login, password, description) VALUES (?, ?, ?, ?, ?)", (7,1,'a123456',pw_manager.encrypt('124151'), "Нагорная Д.А."))
    cur.execute("INSERT OR IGNORE INTO students (id_student, id_group, login, password, description) VALUES (?, ?, ?, ?, ?)", (8,1,'a123457',pw_manager.encrypt('124161'), "Никитин М.А."))
    cur.execute("INSERT OR IGNORE INTO students (id_student, id_group, login, password, description) VALUES (?, ?, ?, ?, ?)", (9,1,'a123458',pw_manager.encrypt('124171'), "Никишин Д.Д."))
    cur.execute("INSERT OR IGNORE INTO students (id_student, id_group, login, password, description) VALUES (?, ?, ?, ?, ?)", (10,1,'a123459',pw_manager.encrypt('124821'), "Ошкин И.В."))
    cur.execute("INSERT OR IGNORE INTO students (id_student, id_group, login, password, description) VALUES (?, ?, ?, ?, ?)", (11,1,'a123461',pw_manager.encrypt('1241921'), "Роганов Д.В."))
    cur.execute("INSERT OR IGNORE INTO students (id_student, id_group, login, password, description) VALUES (?, ?, ?, ?, ?)", (12,1,'a123462',pw_manager.encrypt('124112'), "Савкин В.В."))
    cur.execute("INSERT OR IGNORE INTO students (id_student, id_group, login, password, description) VALUES (?, ?, ?, ?, ?)", (13,1,'a123463',pw_manager.encrypt('124113'), "Сурков Е.В."))
    cur.execute("INSERT OR IGNORE INTO students (id_student, id_group, login, password, description) VALUES (?, ?, ?, ?, ?)", (14,1,'a123464',pw_manager.encrypt('124114'), "Шутихин А.Э."))



    conn.commit()
    conn.close()

if __name__ == "__main__":
    populate_database()  # Теперь скрипт нужно запускать вручную