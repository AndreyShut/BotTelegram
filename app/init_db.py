from database import create_database
from content_database import populate_database

if __name__ == "__main__":
    create_database()  # Создаёт таблицы
    populate_database()  # Заполняет тестовыми данными