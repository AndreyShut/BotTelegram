import asyncio
import sqlite3
from db_manager import pm
from datetime import datetime, timedelta
import json
import logging
from pathlib import Path
from typing import Dict, List

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)
handler = logging.StreamHandler()
handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
logger.addHandler(handler)

def validate_student_data(student: Dict) -> bool:
    """Проверяет корректность данных студента"""
    required_fields = {"id", "login", "password", "name"}
    if not all(field in student for field in required_fields):
        logger.warning(f"Отсутствуют обязательные поля у студента: {student}")
        return False
    return True

def load_students_from_json(json_path: str) -> Dict:
    """Загружает данные студентов из JSON файла"""
    try:
        if not Path(json_path).exists():
            raise FileNotFoundError(f"Файл {json_path} не найден")
        
        with open(json_path, "r", encoding='utf-8') as f:
            students_data = json.load(f)
        
        if not isinstance(students_data, dict):
            raise ValueError("Некорректный формат JSON файла")
        
        return students_data
    except json.JSONDecodeError as e:
        logger.error(f"Ошибка парсинга JSON: {e}")
        raise
    except Exception as e:
        logger.error(f"Ошибка загрузки файла: {e}")
        raise

async def check_triggers_exist():
    conn = sqlite3.connect('student_bot.db')
    cursor = conn.cursor()
    cursor.execute("SELECT name FROM sqlite_master WHERE type='trigger'")
    triggers = [row[0] for row in cursor.fetchall()]
    cursor.close()
    conn.close()
    required_triggers = ['update_test_timestamp', 'update_debt_timestamp']
    missing = [t for t in required_triggers if t not in triggers]
    if missing:
        logger.error(f"Missing triggers: {missing}")
        raise RuntimeError(f"Required triggers not found: {missing}")


async def populate_database():
    try:
        await check_triggers_exist()
        conn = sqlite3.connect('student_bot.db')
        cur = conn.cursor()
        
        # Группы
        groups = [
            (1, '21ВВС1'), (2, '21ВА1'), (3, '22ВВС1'), 
            (4, '22ВА1'), (5, '23ВВВ4'), (6, '23ВА1'), 
            (7, '24ВВВ4'), (8, '24ВА1')
        ]
        for group in groups:
            cur.execute("INSERT OR IGNORE INTO groups (id, name_group) VALUES (?, ?)", group)

        # Студенты
        try:
            students_data = load_students_from_json("students.json")
            total_students = 0
            
            for group_id, students in students_data.items():
                if not isinstance(students, list):
                    logger.warning(f"Некорректный формат данных для группы {group_id}")
                    continue
                
                for student in students:
                    if not validate_student_data(student):
                        continue
                    
                    try:
                        # Хеширование пароля
                        hashed_password = await pm.hash_password(student["password"])
                        cur.execute(
                            """INSERT OR IGNORE INTO students 
                            (id_student, id_group, login, password, description) 
                            VALUES (?, ?, ?, ?, ?)""",
                            (
                                student["id"],
                                group_id,
                                student["login"],
                                hashed_password,  # Используем уже хешированный пароль
                                student["name"]
                            )
                        )
                        total_students += 1
                    except Exception as e:
                        logger.error(f"Ошибка добавления студента {student.get('login')}: {e}")
            
            logger.info(f"Добавлено {total_students} студентов")
        except Exception as e:
            logger.error("Ошибка при заполнении студентов")
            raise


        # Добавляем преподавателей
        teachers = ['Бурукина И.П.', 'Бершадский А.М.', 'Бождай А.С.', 
                    'Финогеев А.Г.', 'Подмарькова Е.М.', 'Тимонин А.Ю.', 
                    'Селиверстова И.А.', 'Глотова Т.В.', 'Валько А.Ф.', 
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
                    'Никишин К.И.', 'Кузьмин А.В.', 'Масленников А.А.',
                    'Кузнецова О.Ю.','Елистратова О.В'
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
                    'Декларативные языки прогр.','ООП','ОиСП','ДВ Основы первой доврачебной помощи','ДВ Основы военной подготовки',
                    'Интерфейсы программирования приложений','Компьютерная графика и 3D моделирование','Электротехника, электроника и схемотехника',
                    'Теория автоматов','Дисциплина по выбору','Военная подготовка','Математическое обеспечение информационных систем',
                    'ДВ Лингвистическое и программное обеспечение','Вычислительные методы в системах администрирования','Компьютерная графика',
                    'Структуры и алгоритмы компьютерной обработки данных','Администрирование инфокоммуникационных систем','Автоматизация конструкторского проектирования ЭА',
                    'Компьютерное моделирование в системах АП','ЭВМ и периферийные устройства','Технологии разработки программного обеспечения',
                    'Экономико-правовые основы рынка программного обеспечения','Качество и тестирование программного обеспечения', 
                    'Мультимедийные технологии', 'Интеллектуализация информационных систем','Проектирование ИС c использованием ШП',
                    'Операционные системы и оболочки', 'Информационные технологии','Модели и методы анализа ПР','Геометрическое моделирование в системах АП',
                    'Системы реального времени','Архитектура компьютерных систем','Администрирование информационных систем',
                    ]
        for subject in subjects:
            cur.execute('INSERT INTO subjects (name) VALUES (?)', (subject,))



        # Заполнение таблицы disciplines (дисциплины)
        disciplines_data = [
            (48, 1,2),  # Системы реального времени Бурукина И.П. 21ВА1
            (36, 1,3),  # Компьютерное моделирование в системах АП Бурукина И.П. 22ВВС1
            (35, 2,3),  # Автоматизация конструкторского проектирования ЭА Бершадский А.М. 22ВВС1
            (32, 3,6),  # Компьютерная графика Бождай А.С. 23ВА1
            (45, 3,2),  # Информационные технологии Бождай А.С. 21ВА1
            (45, 3,1),  # Информационные технологии Бождай А.С. 21ВВС1
            (34, 4,3),  # Администрирование инфокоммуникационных систем Финогеев А.Г. 22ВВС1
            (50, 4,2),  # Администрирование информационных систем Финогеев А.Г. 21ВА1
            (30, 4,6),  # ДВ Лингвистическое и программное обеспечение Финогеев А.Г. 23ВА1
            (41, 4,4),  # Мультимедийные технологии Финогеев А.Г. 22ВА1
            (49, 4,2),  # Архитектура компьютерных систем Финогеев А.Г. 21ВА1
            (24, 4,5),  # Компьютерная графика и 3D моделирование Финогеев А.Г. 23ВВ4
            (19, 5,4),  # ООП Подмарькова Е.М. 22ВА1
            (36, 6,3),  # Компьютерное моделирование в системах АП Тимонин А.Ю. 22ВВС1
            (14, 6,8),  # Информатика Тимонин А.Ю. 24ВА1
            (45, 6,2),  # Информационные технологии Тимонин А.Ю. 21ВА1
            (10, 6,7),  # Вычислительные и ИС Тимонин А.Ю. 24ВВВ4
            (39, 7,3),  # Экономико-правовые основы рынка программного обеспечения Селиверстова И.A. 22ВВС1
            (33, 8,6),  # Структуры и алгоритмы компьютерной обработки данных Глотова Т.В. 23ВА1
            (14, 8,8),  # Информатика Глотова Т.В. 24ВА1
            (43, 8,4),  # Проектирование ИС c использованием ШП Глотова Т.В. 22ВА1
            (46, 9,1),  # Модели и методы анализа ПР Валько А.Ф. 21ВВС1
            (29, 9,6),  # Математическое обеспечение информационных систем  Валько А.Ф. 23ВА1
            (38, 9,3),  # Технологии разработки программного обеспечения Валько А.Ф. 22ВВС1
            (10, 9,7),  # Вычислительные и ИС Валько А.Ф. 24ВВВ4
            (44, 10,4), # Операционные системы и оболочки Евсеева Ю.И. 22ВА1
            (19, 10,5), # ООП Евсеева Ю.И. 23ВВВ4
            (33, 10,6), # Структуры и алгоритмы компьютерной обработки данных Евсеева Ю.И. 23ВА1
            (43, 10,4), # Проектирование ИС c использованием ШП Евсеева Ю.И. 22ВА1
            (8, 10,8),  # Программирование Евсеева Ю.И. 24ВА1
            (19, 11,4), # ООП Гудков А.А. 22ВА1
            (19, 11,5), # ООП Гудков А.А. 23ВВ4
            (47, 11,1), # Геометрическое моделирование в системах АП Гудков А.А. 21ВВС1
            (8, 11,8),  # Программирование АП Гудков А.А. 24ВА1
            (31, 11,6), # Вычислительные методы в системах администрирования АП Гудков А.А. 23ВА1
            (44, 11,4), # Операционные системы и оболочки Гудков А.А. 22ВА1
            (35, 12,3), # Автоматизация конструкторского проектирования ЭА Гудков П.А.22ВВС1
            (31, 12,6), # Вычислительные методы в системах администрирования АП Гудков П.А. 23ВА1
            (49, 12,2), # Архитектура компьютерных систем Гудков П.А. 21ВА1
            (40, 12,4), # Качество и тестирование программного обеспечения Гудков П.А. 22ВА1
            (39, 12,3), # Экономико-правовые основы рынка программного обеспечения Гудков П.А. 22ВВС1
            (48, 12,2), # Системы реального времени Гудков П.А. 21ВА1
            (30, 13,6), # ДВ Лингвистическое и программное обеспечение Финогеев А.А. 23ВА1
            (24, 13,5), # Компьютерная графика и 3D моделирование Финогеев А.А. 23ВВ4
            (50, 13,2), # Администрирование информационных систем Финогеев А.А. 21ВА1
            (41, 13,4), # Мультимедийные технологии Финогеев А.А. 22ВА1
            (32, 13,6), # Компьютерная графика Финогеев А.А. 23ВА1
            (34, 13,3), # Администрирование инфокоммуникационных систем Финогеев А.А. 22ВВС1
            (29, 14,6), # Математическое обеспечение информационных систем Эпп В.В. 23ВА1
            (40, 14,1), # Качество и тестирование программного обеспечения Эпп В.В. 21ВВС1 
            (40, 14,4), # Качество и тестирование программного обеспечения Эпп В.В. 22ВА1
            (38, 14,3), # Технологии разработки программного обеспечения Эпп В.В. 22ВВС1
            (2, 15,7),  # Физика Мурысина Н.Н. 24ВВВ4
            (2, 16,7),  # Физика Яшин С.В. 24ВВВ4
            (3, 17,7),  # Математика Болотникова О.В. 24ВВВ4
            (4, 18,7),  # Арифметические и логические основы ВТ Калиниченко Е.И. 24ВВВ4
            (5, 19,7),  # Информационные технологии в проф. деятельности Митрохина Н.Ю 24ВВВ4
            (5, 20,7),  # Информационные технологии в проф. деятельности Юрова О.В. 24ВВВ4
            (5, 19,8),  # Информационные технологии в проф. деятельности Митрохина Н.Ю 24ВА1
            (5, 20,8),  # Информационные технологии в проф. деятельности Юрова О.В. 24ВА1
            (6, 21,7),  # История России Гарбуз Г.В. 24ВВВ4
            (6, 21,8),  # История России Гарбуз Г.В. 24ВА1
            (4, 22,7),  # Арифметические и логические основы ВТ Слепцов Н.В. 24ВВВ4
            (37, 22,3), # ЭВМ и периферийные устройства Слепцов Н.В. 22ВВС1
            (8, 23,7),  # Программирование Генералова А.А. 24ВВВ4
            (8, 24,7),  # Программирование Голотенков Н.О. 24ВВВ4
            (8, 25,7),  # Программирование Токарев А.Н. 24ВВВ4
            (9, 26,7),  # Правоведение Сеидов Ш.Г. 24ВВВ4
            (11, 27,7), # Русский язык и деловые коммуникации Кучигина С.К. 24ВВВ4
            (11, 27,8), # Русский язык и деловые коммуникации Кучигина С.К. 24ВА1
            (12, 28,7), # Ин.яз Тимошина С.А. 24ВВВ4
            (12, 29,7), # Ин.яз Данкова Н.С. 24ВВВ4
            (12, 29,8), # Ин.яз Данкова Н.С. 24ВА1
            (13, 30,8), # Математический анализ Самуйлова С.В. 24ВА1
            (12, 31,8), # Ин.яз Мусорина О.А. 24ВА1
            (15, 32,8), # Алгебра и теория чисел Романова Е.Г 24ВА1
            (16, 32,8), # Геометрия и топология Романова Е.Г 24ВА1
            (17, 33,5), # Инсталляция и эксплуатация ВСиС Акифьев И.В. 23ВВВ4
            (18, 33,5), # Декларативные языки прогр. Акифьев И.В. 23ВВВ4
            (18, 34,5), # Декларативные языки прогр. Дубинин В.Н. 23ВВВ4
            (20, 35,6), # ОиСП Логинова О.А. 23ВА1
            (20, 35,5), # ОиСП Логинова О.А. 23ВВВ4
            (21, 36,6), # ДВ Основы первой доврачебной помощи Митишев А.В. 23ВА1
            (22, 37,6), # ДВ Основы военной подготовки Авдонина Л.А. 23ВА1
            (21, 36,5), # ДВ Основы первой доврачебной помощи Митишев А.В. 23ВВ4
            (22, 37,5), # ДВ Основы военной подготовки Авдонина Л.А. 23ВВ4
            (23, 38,5), # Интерфейсы программирования приложений Синев М.П. 23ВВ4
            (23, 39,5), # Интерфейсы программирования приложений Исхаков Н.В. 23ВВ4
            (25, 40,5), # Электротехника, электроника и схемотехника Бычков А.С. 23ВВ4
            (25, 41,5), # Электротехника, электроника и схемотехника Семенов А.О. 23ВВ4
            (26, 41,5), # Теория автоматов Семенов А.О. 23ВВ4
            (17, 42,5), # Инсталляция и эксплуатация ВСиС Леонова Т.Ю. 23ВВВ4
            (22, 43,6), # ДВ Основы военной подготовки Мишина К.Д. 23ВА1
            (22, 43,5), # ДВ Основы военной подготовки Мишина К.Д. 23ВВ4
            (26, 44,5), # Теория автоматов Бикташев Р.А. 23ВВ4
            (21, 45,6), # ДВ Основы первой доврачебной помощи Ермохина Е.Н. 23ВА1
            (21, 45,5), # ДВ Основы первой доврачебной помощи Ермохина Е.Н. 23ВВ4
            (37, 46,3), # ЭВМ и периферийные устройства Никишин К.И. 22ВВС1
            (42, 47,4), # Интеллектуализация информационных систем Кузьмин А.В. 22ВА1
            (42, 48,4), # Интеллектуализация информационных систем Масленников А.А. 22ВА1
            (42, 49,4), # Интеллектуализация информационных систем Кузнецова О.Ю. 22ВА1
            (9, 50,8)   # Правоведение Елистратова О.В 24ВА1
        ]
        for discipline in disciplines_data:
            cur.execute('''
                INSERT OR IGNORE INTO disciplines (subject_id, teacher_id,group_id)
                VALUES (?, ?, ?)
            ''', discipline)

        conn.commit()
        conn.close()
        logger.info("БД заполнена")
    except Exception as e:
        logger.error("Ошибка при заполнении БД")
        raise

if __name__ == "__main__":
    asyncio.run(populate_database())  # Теперь скрипт нужно запускать вручную