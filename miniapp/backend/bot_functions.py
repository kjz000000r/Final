# -*- coding: utf-8 -*-
"""
Переиспользуемые функции из бота для backend.
ИСПРАВЛЕННАЯ ВЕРСИЯ - совместима с openai 1.12.0
"""

import os
import re
import json
import asyncio
import logging
from typing import Optional, Dict, List, Tuple
from datetime import datetime, timezone

# ⭐ ДОБАВЬТЕ ЭТИ СТРОКИ В САМОЕ НАЧАЛО
from dotenv import load_dotenv
load_dotenv()  # Загружаем переменные окружения

logger = logging.getLogger("bot_functions")

# ===== Конфигурация =====
OPENROUTER_KEY = os.getenv("OPENROUTER_API_KEY", "").strip()
APP_TITLE = os.getenv("APP_TITLE", "NutriCoach Bot")
APP_REFERER = os.getenv("APP_REFERER", "https://example.com")

# Выводим для отладки (уберите после проверки)
if OPENROUTER_KEY:
    logger.info(f"✅ API Key loaded: {OPENROUTER_KEY[:10]}...")
else:
    logger.warning("⚠️ OPENROUTER_API_KEY not found in .env")

PRIMARY_MODEL = "deepseek/deepseek-chat"
# ... остальной код
FALLBACK_MODELS = [
    "openai/gpt-4o-mini",
    "anthropic/claude-3-haiku",
]

# В начале файла bot_functions.py, замените секцию инициализации AI:

## ===== Инициализация AI =====
# ===== Инициализация AI =====
ai = None
AI_AVAILABLE = False

try:
    from openai import OpenAI
    if OPENROUTER_KEY:
        # Простая инициализация - только api_key и base_url
        ai = OpenAI(
            api_key=OPENROUTER_KEY,
            base_url="https://openrouter.ai/api/v1"
        )
        AI_AVAILABLE = True
        logger.info("✅ AI client initialized")
    else:
        logger.warning("⚠️ OPENROUTER_API_KEY not set")
except ImportError as e:
    logger.error(f"❌ OpenAI library not installed: {e}")
except Exception as e:
    logger.error(f"❌ AI init error: {e}")
    import traceback
    logger.error(traceback.format_exc())


async def ai_chat(system: str, user_text: str, temperature: float = 0.5) -> str:
    """Запрос к AI-модели"""
    if not AI_AVAILABLE:
        return "AI не настроен. Установите OPENROUTER_API_KEY в .env"

    def _call(model: str):
        return ai.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user_text}
            ],
            temperature=temperature
            # Убрали extra_headers - они добавляются через base_url
        )

    for model in [PRIMARY_MODEL] + FALLBACK_MODELS:
        try:
            resp = await asyncio.to_thread(_call, model)
            if hasattr(resp, "choices") and resp.choices:
                content = resp.choices[0].message.content
                if content:
                    return content.strip()
        except Exception as e:
            logger.warning(f"Model {model} failed: {e}")
            continue

    return "Все AI модели недоступны"


def parse_meal_json(text: str) -> Tuple[int, float, float, float, str]:
    """Парсинг ответа AI о еде"""
    try:
        # Ищем JSON
        match = re.search(r'\{[^}]+\}', text, re.DOTALL)
        if match:
            data = json.loads(match.group(0))
            return (
                int(data.get("calories", 200)),
                float(data.get("proteins", 10)),
                float(data.get("fats", 10)),
                float(data.get("carbs", 20)),
                str(data.get("summary", "приём пищи"))
            )
    except:
        pass
    
    # Fallback
    return 200, 10.0, 10.0, 20.0, "приём пищи"


# ===== Функции для работы с БД =====

def try_estimate_meal_from_db(meal_text: str) -> Optional[Tuple[int, float, float, float, str]]:
    """Оценка еды из базы продуктов"""
    from database import execute_query
    import html
    
    items = []
    for line in meal_text.split('\n'):
        match = re.search(r'([а-яё\s]+)\s+(\d+)', line, re.I)
        if match:
            items.append((match.group(1).strip(), float(match.group(2))))
    
    if not items:
        return None
    
    total = {"kcal": 0, "p": 0, "f": 0, "c": 0}
    lines = []
    found = False
    
    for name, grams in items:
        result = execute_query(
            "SELECT * FROM products WHERE LOWER(name) = %s",
            (name.lower(),)
        )
        
        if result:
            prod = result[0]
            found = True
            k = grams / 100
            total["kcal"] += prod["kcal_per_100"] * k
            total["p"] += prod["proteins_per_100"] * k
            total["f"] += prod["fats_per_100"] * k
            total["c"] += prod["carbs_per_100"] * k
            lines.append(f"• {html.escape(prod['name'])} — {int(grams)} г")
    
    if not found:
        return None
    
    return (
        int(total["kcal"]),
        round(total["p"], 1),
        round(total["f"], 1),
        round(total["c"], 1),
        "<br>".join(lines)
    )


def has_access(user_id: int, username: Optional[str] = None) -> bool:
    """Проверка доступа"""
    from database import execute_query
    
    admin = os.getenv("ADMIN_USERNAME", "").lower()
    if username and username.lower() == admin and admin:
        return True
    
    result = execute_query(
        "SELECT expires_at, free_until FROM subscriptions WHERE user_id = %s",
        (user_id,)
    )
    
    if not result:
        return False
    
    row = result[0]
    now = datetime.now(timezone.utc)
    
    if row.get("expires_at") and row["expires_at"] > now:
        return True
    if row.get("free_until") and row["free_until"] > now:
        return True
    
    return False


def get_labs_credits(user_id: int) -> int:
    """Получить кредиты на анализы"""
    from database import execute_query
    
    result = execute_query(
        "SELECT labs_credits FROM credits WHERE user_id = %s",
        (user_id,)
    )
    return result[0]["labs_credits"] if result else 0


def consume_labs_credit(user_id: int) -> bool:
    """Списать кредит"""
    from database import execute_update
    
    try:
        if get_labs_credits(user_id) <= 0:
            return False
        execute_update(
            "UPDATE credits SET labs_credits = labs_credits - 1 WHERE user_id = %s",
            (user_id,)
        )
        return True
    except:
        return False


def init_challenge(user_id: int, challenge_type: str) -> bool:
    """Инициализировать челлендж"""
    from database import execute_update
    
    try:
        execute_update(
            """
            INSERT INTO challenges (user_id, challenge_type, start_date, progress, completed)
            VALUES (%s, %s, %s, 0, 0)
            ON CONFLICT (user_id, challenge_type) DO NOTHING
            """,
            (user_id, challenge_type, datetime.now(timezone.utc))
        )
        return True
    except:
        return False


def update_challenge_progress(user_id: int, challenge_type: str) -> bool:
    """Обновить прогресс челленджа"""
    from database import execute_query, execute_update
    
    try:
        today = datetime.now(timezone.utc).date().isoformat()
        
        # Проверка
        existing = execute_query(
            "SELECT 1 FROM challenge_logs WHERE user_id=%s AND challenge_type=%s AND log_date=%s",
            (user_id, challenge_type, today)
        )
        
        if existing:
            return False
        
        # Добавляем лог
        execute_update(
            "INSERT INTO challenge_logs (user_id, challenge_type, log_date, completed) VALUES (%s, %s, %s, 1)",
            (user_id, challenge_type, today)
        )
        
        # Обновляем прогресс
        execute_update(
            "UPDATE challenges SET progress = progress + 1 WHERE user_id=%s AND challenge_type=%s",
            (user_id, challenge_type)
        )
        
        # Проверяем завершение
        challenge = execute_query(
            "SELECT progress FROM challenges WHERE user_id=%s AND challenge_type=%s",
            (user_id, challenge_type)
        )
        
        if challenge and challenge[0]["progress"] >= 7:
            execute_update(
                "UPDATE challenges SET completed = 1 WHERE user_id=%s AND challenge_type=%s",
                (user_id, challenge_type)
            )
            
            achievement_name = f"Челлендж: {get_challenge_name(challenge_type)}"
            execute_update(
                """
                INSERT INTO achievements (user_id, badge, ts)
                VALUES (%s, %s, %s)
                ON CONFLICT (user_id, badge) DO NOTHING
                """,
                (user_id, achievement_name, datetime.now(timezone.utc))
            )
        
        return True
    except Exception as e:
        logger.error(f"Error updating challenge: {e}")
        return False


def get_challenge_name(challenge_type: str) -> str:
    """Название челленджа"""
    names = {
        "water_challenge": "Пить 2л воды ежедневно",
        "steps_challenge": "8k шагов ежедневно",
        "diet_challenge": "Здоровое питание 7 дней",
        "workout_challenge": "Тренировки 3х в неделю",
        "tracking_challenge": "Отслеживать калории",
        "nosugar_challenge": "Без сахара 7 дней"
    }
    return names.get(challenge_type, "Неизвестный челлендж")