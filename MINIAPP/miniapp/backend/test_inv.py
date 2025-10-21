# test_env.py
from dotenv import load_dotenv
import os

load_dotenv()

print("Проверка переменных окружения:")
print("-" * 50)

api_key = os.getenv("OPENROUTER_API_KEY", "")
if api_key:
    print(f"✅ OPENROUTER_API_KEY: {api_key[:20]}...")
else:
    print("❌ OPENROUTER_API_KEY не найден!")

bot_token = os.getenv("TELEGRAM_BOT_TOKEN", "")
if bot_token:
    print(f"✅ TELEGRAM_BOT_TOKEN: {bot_token[:20]}...")
else:
    print("❌ TELEGRAM_BOT_TOKEN не найден!")

db_url = os.getenv("DATABASE_URL", "")
if db_url:
    print(f"✅ DATABASE_URL: {db_url[:30]}...")
else:
    print("❌ DATABASE_URL не найден!")

print("-" * 50)
print(f"Текущая папка: {os.getcwd()}")
print(f"Файл .env существует: {os.path.exists('.env')}")

if os.path.exists('.env'):
    print("\nСодержимое .env (первые 5 строк):")
    with open('.env', 'r', encoding='utf-8') as f:
        for i, line in enumerate(f):
            if i < 5:
                # Маскируем значения
                if '=' in line and not line.startswith('#'):
                    key = line.split('=')[0]
                    print(f"  {key}=***")
                else:
                    print(f"  {line.strip()}")