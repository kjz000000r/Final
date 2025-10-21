# init_db.py
import psycopg
from dotenv import load_dotenv
import os

load_dotenv()

DSN = os.getenv("POSTGRES_DSN")

print("Подключение к Neon DB...")

try:
    with psycopg.connect(DSN) as conn:
        with conn.cursor() as cur:
            # Читаем SQL файл
            with open("schema_pg.sql", "r", encoding="utf-8") as f:
                sql = f.read()
            
            # Выполняем
            cur.execute(sql)
            conn.commit()
            
            print("✅ Схема БД успешно создана!")
            
            # Проверка
            cur.execute("SELECT COUNT(*) FROM products")
            count = cur.fetchone()[0]
            print(f"✅ Продуктов в базе: {count}")
            
except Exception as e:
    print(f"❌ Ошибка: {e}")