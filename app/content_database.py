import sqlite3
from security import PasswordManager
from datetime import datetime, timedelta
import json


def populate_database():
    conn = sqlite3.connect('student_bot.db')
    cur = conn.cursor()
    pw_manager = PasswordManager()

    # Группы
    groups = [
        (1, '21ВВС1'), (2, '21ВА1'), (3, '22ВВС1'), 
        (4, '22ВА1'), (5, '23ВВВ4'), (6, '23ВА1'), 
        (7, '24ВВВ4'), (8, '24ВА1')
    ]
    for group in groups:
        cur.execute("INSERT OR IGNORE INTO groups (id, name_group) VALUES (?, ?)", group)

    # Студенты
    with open("students.json", "r", encoding='utf-8') as f:
        students_data = json.load(f)

    for group_id, students in students_data.items():
        for student in students:
            id_student = student["id"]
            login = student["login"]
            password = student["password"]
            description = student["name"]
            cur.execute(
                "INSERT OR IGNORE INTO students (id_student, id_group, login, password, description) VALUES (?, ?, ?, ?, ?)",
                (id_student, group_id, login, pw_manager.encrypt(password), description)
            )


 # Добавляем преподавателей
    teachers = ['Бурукина И.П.', 'Бершадский А.М.', 'Бождай А.С.', 
                'Финогеев А.Г.', 'Подмарькова Е.М.', 'Тимонин А.Ю.', 
                'Селиверстова И.A.', 'Глотова Т.В.', 'Валько А.Ф.', 
                'Евсеева Ю.И.', 'Гудков А.А.', 'Гудков П.А.', 
                'Финогеев А.А.', 'Эпп В.В.','Мурысина Н.Н.',
                'Яшин С.В.','Болотникова О.В.','Калиниченко Е.И.',
                'Митрохина Н.Ю', 'Юрова О.В.', 'Гарбуз Г.В.', 
                'Слепцов Н.В.','Генералова А.А.','Голотенков Н.О.',
                'Токарев А.Н.','Сеидов Ш.Г.','Кучигина С.К.',
                'Тимошина С.А.','Данкова Н.С.','Самуйлова С.В.',
                'Мусорина О.А.','Романова Е.Г','Акифьев И.В.',
                'Дубинин В.Н.','Логинова О.А.','Митишев А.В.',
                'Авдонина Л.А.', 'Синев М.П.', 'Исхаков Н.В.',
                'Бычков А.С.', 'Семенов А.О.', 'Леонова Т.Ю.',
                'Мишина К.Д.', 'Бикташев Р.А.', 'Ермохина Е.Н.',
                'Никишин К.И.', 'Кузьмин А.В.', 'Масленников А.А.','Кузнецова О.Ю.'
                ]
    for teacher in teachers:
        cur.execute("INSERT OR IGNORE INTO teachers (full_name) VALUES (?)", (teacher,))

  # Заполнение типов задолженностей
    debt_types = ['Экзамен', 'Зачет', 'Зачет с оценкой', 'Курсовая работа']
    for debt_type in debt_types:
        cur.execute('INSERT INTO debt_types (name) VALUES (?)', (debt_type,))

    # Заполнение предметов
    subjects = [ 'Кураторский час','Физика','Математика','Арифметические и логические основы ВТ',
                'Информационные технологии в проф. деятельности','История России','Элективные дисциплины по физической культуре и спорту',
                'Программирование','Правоведение','Вычислительные и ИС','Русский язык и деловые коммуникации','Ин.яз',
                'Математический анализ','Информатика','Алгебра и теория чисел','Геометрия и топология','Инсталляция и эксплуатация ВСиС',
                'Декларативные языки прогр.','О - ОП','ОиСП','ДВ Основы первой доврачебной помощи','ДВ Основы военной подготовки',
                'Интерфейсы программирования приложений','Компьютерная графика и 3D моделирование','Электротехника, электроника и схемотехника',
                'Теория автоматов','Дисциплина по выбору','МО ИС','Математическое обеспечение информационных систем',
                'ДВ Лингвистическое и программное обеспечения','Вычислительные методы в системах администрирования','Компьютерная графика',
                'Структуры и алгоритмы компьютерной обработки данных','Администрирование инфокоммуникационных систем','Автоматизация конструкторского проектирования ЭА',
                'Компьютерное моделирование в системах АП','ЭВМ и периферийные устройства','Технологии разработки программного обеспечения',
                'Экономико-правовые основы рынка программного обеспечения','Качество и тестирование программного обеспечения', 
                'Мультимедийные технологии', 'Интеллектуализация информационных систем','Проектирование ИС c использованием ШП',
                'Операционные системы и оболочки', 'Информационные технологии','Модели и методы анализа ПР','Геометрическое моделирование в системах АП',
                'Системы реального времени','Архитектура компьютерных систем','Администрирование информационных систем',
                ]
    for subject in subjects:
        cur.execute('INSERT INTO subjects (name) VALUES (?)', (subject,))

    # Заполнение новостей
    news_data = [
        ('Отмена занятий', 'В связи с отключением электричества занятия отменены с 11:40 16.05.2025', 
         (datetime.now() + timedelta(days=1)).strftime('%Y-%m-%d'), '7к', 0, 1),
        ('Собрание старост', 'Собрание старост в 15:00', 
         datetime.now().strftime('%Y-%m-%d'), '7а-203', 0, 1),
         ('Собрание группы', 'Собрание группы по поводу практики ', 
         datetime.now().strftime('%Y-%m-%d'), '7а-203', 1, 1),
    ]
    for news in news_data:
        cur.execute('''
            INSERT INTO news (title, description, date, place, for_all_groups, is_published)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', news)

    # Связи новостей и групп (для новостей не для всех)
    news_groups = [(3, 1)]  # Собрание старост только для 21ВВС1 и 21ВА1
    for ng in news_groups:
        cur.execute('INSERT INTO news_groups (news_id, group_id) VALUES (?, ?)', ng)
    
        # Заполнение тестов
    tests_data = [
        (1, 48, 1, 'https://test.com', (datetime.now() + timedelta(days=5)).strftime('%Y-%m-%d')),
        (2, 48, 1, 'https://test.com', (datetime.now() + timedelta(days=7)).strftime('%Y-%m-%d')),
        (3, 2, 1, 'https://test.com', (datetime.now() + timedelta(days=10)).strftime('%Y-%m-%d'))
    ]
    for test in tests_data:
        cur.execute('''
            INSERT INTO tests (group_id, subject_id, teacher_id, test_link, date)
            VALUES (?, ?, ?, ?, ?)
        ''', test)

        # Задолженности студентов
    student_debts_data = [
        (1, 2, 1, (datetime.now() + timedelta(days=14)).strftime('%Y-%m-%d')),  
        (1, 3, 2, (datetime.now() + timedelta(days=21)).strftime('%Y-%m-%d')),  
        (3, 1, 4, (datetime.now() + timedelta(days=7)).strftime('%Y-%m-%d')),   
        (4, 2, 3, (datetime.now() + timedelta(days=10)).strftime('%Y-%m-%d'))   
    ]
    for debt in student_debts_data:
        cur.execute('''
            INSERT INTO student_debts (student_id, subject_id, debt_type_id, last_date)
            VALUES (?, ?, ?, ?)
        ''', debt)


    conn.commit()
    conn.close()

if __name__ == "__main__":
    populate_database()  # Теперь скрипт нужно запускать вручную