# security.py (синхронная версия)
from cryptography.fernet import Fernet
import base64
import os
from dotenv import load_dotenv

load_dotenv()

class PasswordManager:
    _instance = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            key = os.getenv("ENCRYPTION_KEY")
            if not key:
                key = Fernet.generate_key().decode()
                print(f"ВАЖНО: Добавьте в .env ENCRYPTION_KEY={key}")
            cls._instance.cipher = Fernet(key.encode())
        return cls._instance
    
    def encrypt(self, data: str) -> str:
        return self.cipher.encrypt(data.encode()).decode()
    
    def decrypt(self, encrypted_data: str) -> str:
        return self.cipher.decrypt(encrypted_data.encode()).decode()