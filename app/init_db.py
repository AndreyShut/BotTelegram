import asyncio
from database import  StudentBotDB
from content_database import populate_database

if __name__ == "__main__":
    StudentBotDB()
    asyncio.run(populate_database())