# test_db.py
from bot.db_pg import db
from dotenv import load_dotenv

load_dotenv()

print("Тестирование подключения к Neon DB...")

try:
    # Тест 1: Простой SELECT
    result = db.execute("SELECT 1 AS test")
    row = result.fetchone()
    print(f"✅ Тест 1: {row}")
    
    # Тест 2: Проверка таблиц
    result = db.execute("""
        SELECT table_name 
        FROM information_schema.tables 
        WHERE table_schema = 'public'
    """)
    tables = result.fetchall()
    print(f"✅ Тест 2: Найдено таблиц: {len(tables)}")
    for table in tables:
        print(f"   - {table['table_name']}")
    
    # Тест 3: Проверка продуктов
    result = db.execute("SELECT COUNT(*) as cnt FROM products")
    count = result.fetchone()
    print(f"✅ Тест 3: Продуктов в базе: {count['cnt']}")
    
    print("\n🎉 ВСЁ РАБОТАЕТ! База данных готова.")
    
except Exception as e:
    print(f"❌ Ошибка: {e}")
    import traceback
    traceback.print_exc()