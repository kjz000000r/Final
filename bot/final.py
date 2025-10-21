# -*- coding: utf-8 -*-
"""
NutriCoach - Минимальный Telegram бот для запуска Mini App
Весь функционал находится в Mini App!
"""
import os
import logging
import secrets
from datetime import datetime, timezone, timedelta
from dotenv import load_dotenv
from telegram import Update, MenuButtonWebApp, WebAppInfo
from telegram.ext import (
    Application, CommandHandler, ContextTypes,
    PreCheckoutQueryHandler, MessageHandler, filters
)

# Загрузка переменных окружения
load_dotenv()

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("nutricoach-bot")

# Конфигурация
BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
MINI_APP_URL = os.getenv("MINI_APP_URL", "https://your-domain.com")
PAYMENT_TOKEN = os.getenv("PAYMENT_PROVIDER_TOKEN", "")
TRIAL_HOURS = int(os.getenv("TRIAL_HOURS", "24"))
WELCOME_IMAGE = os.getenv("WELCOME_IMAGE_URL", "")
ADMIN_USERNAME = (os.getenv("ADMIN_USERNAME", "") or "").lower()

if not BOT_TOKEN:
    raise RuntimeError("TELEGRAM_BOT_TOKEN is required in .env")

# Подключение к базе данных
from db_pg import db

# ============================================
# ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ
# ============================================

def save_user(user_id: int, username: str = None):
    """Сохранить/обновить пользователя в БД"""
    try:
        uname = (username or "").lower().lstrip("@")
        db.execute(
            "INSERT INTO subscriptions (user_id, username) VALUES (%s, %s) "
            "ON CONFLICT (user_id) DO UPDATE SET username = EXCLUDED.username",
            (user_id, uname)
        )
        db.execute(
            "INSERT INTO credits (user_id, labs_credits) VALUES (%s, 0) "
            "ON CONFLICT (user_id) DO NOTHING",
            (user_id,)
        )
        db.execute(
            "INSERT INTO referrals (user_id, ref_code, invited_count) VALUES (%s, %s, 0) "
            "ON CONFLICT (user_id) DO NOTHING",
            (user_id, secrets.token_urlsafe(6))
        )
        db.commit()
    except Exception as e:
        logger.exception(f"Error saving user {user_id}: {e}")
        db.rollback()


def activate_trial(user_id: int, hours: int) -> datetime:
    """Активировать пробный период"""
    try:
        db.execute(
            "INSERT INTO subscriptions (user_id) VALUES (%s) "
            "ON CONFLICT (user_id) DO NOTHING",
            (user_id,)
        )
        until = datetime.now(timezone.utc) + timedelta(hours=hours)
        db.execute(
            "UPDATE subscriptions SET free_until = %s WHERE user_id = %s",
            (until, user_id)
        )
        db.commit()
        return until
    except Exception as e:
        logger.exception(f"Error activating trial for {user_id}: {e}")
        db.rollback()
        raise


def get_ref_code(user_id: int) -> str:
    """Получить реферальный код пользователя"""
    row = db.execute(
        "SELECT ref_code FROM referrals WHERE user_id = %s",
        (user_id,)
    ).fetchone()
    if row and row["ref_code"]:
        return row["ref_code"]
    
    code = secrets.token_urlsafe(6)
    try:
        db.execute(
            "INSERT INTO referrals (user_id, ref_code, invited_count) VALUES (%s, %s, 0) "
            "ON CONFLICT (user_id) DO UPDATE SET ref_code = EXCLUDED.ref_code",
            (user_id, code)
        )
        db.commit()
    except Exception as e:
        logger.exception(f"Error generating ref code for {user_id}: {e}")
        db.rollback()
    return code


def activate_sub(user_id: int, days: int) -> datetime:
    """Активировать подписку"""
    try:
        db.execute(
            "INSERT INTO subscriptions (user_id) VALUES (%s) "
            "ON CONFLICT (user_id) DO NOTHING",
            (user_id,)
        )
        row = db.execute(
            "SELECT expires_at FROM subscriptions WHERE user_id = %s",
            (user_id,)
        ).fetchone()
        
        now = datetime.now(timezone.utc)
        base = now
        
        if row and row["expires_at"]:
            try:
                existing = row["expires_at"]
                if isinstance(existing, str):
                    existing = datetime.fromisoformat(existing)
                if hasattr(existing, 'tzinfo') and existing.tzinfo is None:
                    existing = existing.replace(tzinfo=timezone.utc)
                if existing > now:
                    base = existing
            except Exception as e:
                logger.warning(f"Error parsing existing date: {e}")
                base = now
        
        new_exp = base + timedelta(days=days)
        db.execute(
            "UPDATE subscriptions SET expires_at = %s WHERE user_id = %s",
            (new_exp, user_id)
        )
        db.commit()
        return new_exp
    except Exception as e:
        logger.exception(f"Error activating subscription for {user_id}: {e}")
        db.rollback()
        raise


# ============================================
# ОБРАБОТЧИКИ КОМАНД
# ============================================

async def start_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Команда /start - единственная команда бота!
    1. Регистрирует пользователя
    2. Активирует триал
    3. Показывает приветствие с кнопкой Mini App
    """
    user = update.effective_user
    save_user(user.id, user.username)
    
    # Обработка реферальной ссылки
    if context.args:
        code = (context.args[0] or "").strip()
        if code:
            row = db.execute(
                "SELECT user_id FROM referrals WHERE ref_code = %s",
                (code,)
            ).fetchone()
            inviter_id = row["user_id"] if row else None
            
            if inviter_id and inviter_id != user.id:
                # Проверяем что реферал еще не активирован
                act = db.execute(
                    "SELECT 1 FROM referral_activations WHERE invited_id = %s",
                    (user.id,)
                ).fetchone()
                
                if not act:
                    try:
                        db.execute(
                            "INSERT INTO referral_activations (inviter_id, invited_id) "
                            "VALUES (%s, %s) ON CONFLICT DO NOTHING",
                            (inviter_id, user.id)
                        )
                        db.execute(
                            "UPDATE referrals SET invited_count = COALESCE(invited_count, 0) + 1 "
                            "WHERE user_id = %s",
                            (inviter_id,)
                        )
                        activate_sub(inviter_id, 7)  # 7 дней бонус
                        db.commit()
                        
                        try:
                            await context.bot.send_message(
                                inviter_id,
                                "🎉 Вам начислено +7 дней за приглашённого друга!"
                            )
                        except Exception:
                            pass
                    except Exception as e:
                        logger.exception(f"Error processing referral: {e}")
                        db.rollback()
    
    # Активация триала (только для новых пользователей)
    is_admin = (user.username or "").lower() == ADMIN_USERNAME and ADMIN_USERNAME
    if not is_admin:
        row = db.execute(
            "SELECT free_until FROM subscriptions WHERE user_id = %s",
            (user.id,)
        ).fetchone()
        
        if row is None or not row.get("free_until"):
            until = activate_trial(user.id, TRIAL_HOURS)
            try:
                await update.message.reply_text(
                    f"🎁 Пробный доступ активирован на {TRIAL_HOURS} часов!\n"
                    f"До: {until.strftime('%d.%m.%Y %H:%M UTC')}"
                )
            except Exception:
                pass
    
    # Установка кнопки Mini App
    async def setup_menu_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Устанавливает кнопку Mini App в меню"""
        web_app_url = os.getenv("MINI_APP_URL", "https://your-domain.com")
    
        menu_button = MenuButtonWebApp(
            text="🥗 Открыть приложение",
            web_app=WebAppInfo(url=web_app_url)
        )
    
        await context.bot.set_chat_menu_button(
            chat_id=update.effective_chat.id,
            menu_button=menu_button
        )
    
        await update.message.reply_text(
            "✅ Кнопка Mini App установлена!\n\n"
            "Теперь нажмите на кнопку меню (☰) рядом с полем ввода сообщения, "
            "чтобы открыть приложение.",
            reply_markup=reply_kb()
        )
    try:
        menu_button = MenuButtonWebApp(
            text="🥗 Открыть приложение",
            web_app=WebAppInfo(url=MINI_APP_URL)
        )
        await context.bot.set_chat_menu_button(
            chat_id=update.effective_chat.id,
            menu_button=menu_button
        )
    except Exception as e:
        logger.error(f"Error setting menu button: {e}")
    
    # Генерация реферальной ссылки
    ref_code = get_ref_code(user.id)
    bot_me = await context.bot.get_me()
    ref_link = f"t.me/{bot_me.username}?start={ref_code}"
    
    # Приветственное сообщение
    caption = (
        f"👋 Привет, {user.first_name}!\n\n"
        "🥗 <b>NutriCoach</b> - твой персональный помощник по питанию!\n\n"
        "<b>Что я умею:</b>\n"
        "• 📊 Вести дневник питания с подсчётом калорий\n"
        "• 🥗 Создавать персональные планы питания\n"
        "• 🧪 Анализировать лабораторные данные\n"
        "• 🍳 Генерировать рецепты из того, что есть дома\n"
        "• ⚡ Мотивировать через челленджи и достижения\n"
        "• 📈 Отслеживать прогресс и вес\n\n"
        f"🎁 <b>Пригласи друга:</b> {ref_link}\n"
        "Получи +7 дней подписки за каждого приглашённого!\n\n"
        "⚠️ <i>Бот не ставит диагнозы и не заменяет консультацию врача.</i>"
    )
    
    # Кнопка для открытия Mini App (если меню не сработало)
    from telegram import InlineKeyboardButton, InlineKeyboardMarkup
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton(
            "🥗 Открыть приложение",
            web_app=WebAppInfo(url=MINI_APP_URL)
        )]
    ])
    
    try:
        if WELCOME_IMAGE:
            await update.message.reply_photo(
                photo=WELCOME_IMAGE,
                caption=caption,
                parse_mode="HTML",
                reply_markup=keyboard
            )
        else:
            await update.message.reply_text(
                caption,
                parse_mode="HTML",
                reply_markup=keyboard
            )
    except Exception as e:
        logger.error(f"Error sending welcome message: {e}")
        await update.message.reply_text(
            caption,
            parse_mode="HTML",
            reply_markup=keyboard
        )


# ============================================
# ОБРАБОТКА ПЛАТЕЖЕЙ (ОПЦИОНАЛЬНО)
# ============================================

async def precheckout(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Pre-checkout handler для платежей"""
    query = update.pre_checkout_query
    await query.answer(ok=True)


async def successful_payment(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка успешного платежа"""
    user_id = update.effective_user.id
    msg = update.message
    sp = msg.successful_payment
    
    payload = (sp.invoice_payload or "").strip()
    currency = (sp.currency or "").upper()
    amount = int(sp.total_amount or 0)
    provider_charge_id = sp.provider_payment_charge_id
    
    logger.info(f"Payment: user={user_id}, payload={payload}, amount={amount}")
    
    # Проверка дубликата
    if provider_charge_id:
        dup = db.execute(
            "SELECT 1 FROM payments WHERE provider_charge_id = %s",
            (provider_charge_id,)
        ).fetchone()
        if dup:
            await msg.reply_text("Этот платёж уже учтён 👍")
            return
    
    try:
        # Парсинг payload (формат: "pay:sub:30" или "pay:labs")
        if payload.startswith("pay:sub:"):
            days = int(payload.split(":")[2])
            exp = activate_sub(user_id, days)
            
            db.execute(
                "INSERT INTO payments (user_id, payload, currency, amount, provider_charge_id) "
                "VALUES (%s, %s, %s, %s, %s) ON CONFLICT DO NOTHING",
                (user_id, payload, currency, amount, provider_charge_id)
            )
            db.commit()
            
            await msg.reply_text(
                f"✅ Подписка на {days} дней активирована до {exp.strftime('%d.%m.%Y')}!\n"
                "Спасибо за покупку! 🎉"
            )
            
        elif payload.startswith("pay:labs"):
            qty = 1
            db.execute(
                "INSERT INTO credits (user_id, labs_credits) VALUES (%s, 0) "
                "ON CONFLICT (user_id) DO NOTHING",
                (user_id,)
            )
            db.execute(
                "UPDATE credits SET labs_credits = labs_credits + %s WHERE user_id = %s",
                (qty, user_id)
            )
            db.execute(
                "INSERT INTO payments (user_id, payload, currency, amount, provider_charge_id) "
                "VALUES (%s, %s, %s, %s, %s) ON CONFLICT DO NOTHING",
                (user_id, payload, currency, amount, provider_charge_id)
            )
            db.commit()
            
            await msg.reply_text(f"✅ Оплачено! Доступно {qty} анализ(а/ов). 🧪")
        else:
            await msg.reply_text("✅ Платёж успешен!")
            
    except Exception as e:
        logger.exception(f"Payment processing error: {e}")
        db.rollback()
        await msg.reply_text(
            "❌ Ошибка при обработке платежа. Обратитесь в поддержку."
        )


# ============================================
# ОБРАБОТКА ПРОМОКОДОВ
# ============================================

async def promo_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда /promo КОД - применить промокод"""
    if not context.args:
        await update.message.reply_text(
            "Применить промокод:\n/promo КОД\n\n"
            "Промокоды можно получить в боте или у администратора."
        )
        return
    
    code = (context.args[0] or "").strip()
    user_id = update.effective_user.id
    
    row = db.execute(
        "SELECT days, labs_credits, max_uses, used_count, expires_at "
        "FROM promocodes WHERE code = %s",
        (code,)
    ).fetchone()
    
    if not row:
        await update.message.reply_text("❌ Промокод не найден.")
        return
    
    days = int(row["days"] or 0)
    credits = int(row["labs_credits"] or 0)
    max_uses = row["max_uses"]
    used_count = row["used_count"]
    expires_at = row["expires_at"]
    
    # Проверка срока действия
    now = datetime.now(timezone.utc)
    if expires_at:
        try:
            exp_dt = expires_at if isinstance(expires_at, datetime) else datetime.fromisoformat(expires_at)
            if exp_dt.tzinfo is None:
                exp_dt = exp_dt.replace(tzinfo=timezone.utc)
            if exp_dt < now:
                await update.message.reply_text("❌ Срок действия промокода истёк.")
                return
        except Exception as e:
            logger.warning(f"Error parsing promo expiry: {e}")
    
    # Проверка лимита использований
    if max_uses is not None and used_count is not None and used_count >= max_uses:
        await update.message.reply_text("❌ Этот промокод исчерпан.")
        return
    
    if days <= 0 and credits <= 0:
        await update.message.reply_text("❌ Этот промокод ничего не даёт.")
        return
    
    try:
        parts = []
        if days > 0:
            activate_sub(user_id, days)
            parts.append(f"+{days} дней подписки")
        if credits > 0:
            db.execute(
                "INSERT INTO credits (user_id, labs_credits) VALUES (%s, 0) "
                "ON CONFLICT (user_id) DO NOTHING",
                (user_id,)
            )
            db.execute(
                "UPDATE credits SET labs_credits = labs_credits + %s WHERE user_id = %s",
                (credits, user_id)
            )
            parts.append(f"+{credits} анализ(а/ов)")
        
        db.execute(
            "UPDATE promocodes SET used_count = COALESCE(used_count, 0) + 1 WHERE code = %s",
            (code,)
        )
        db.commit()
        
        await update.message.reply_text(
            f"✅ Промокод применён: {', '.join(parts)}!"
        )
    except Exception as e:
        logger.exception(f"Promo apply error: {e}")
        db.rollback()
        await update.message.reply_text("❌ Ошибка применения промокода.")


# ============================================
# ADMIN: Создание промокодов
# ============================================

async def addpromo_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Команда для администратора
    /addpromo КОД ДНИ [АНАЛИЗЫ] [MAX_USES] [YYYY-MM-DD]
    """
    user = update.effective_user
    if (user.username or "").lower() != ADMIN_USERNAME:
        await update.message.reply_text("⛔ Нет доступа.")
        return
    
    args = context.args
    if len(args) < 2:
        await update.message.reply_text(
            "Использование:\n"
            "/addpromo КОД ДНИ [АНАЛИЗЫ] [MAX_USES] [YYYY-MM-DD]\n\n"
            "Примеры:\n"
            "• /addpromo TEST30 30\n"
            "• /addpromo FREE2 0 2\n"
            "• /addpromo MEGA 30 5 100 2025-12-31"
        )
        return
    
    code = args[0].strip()
    days = int(args[1])
    
    labs_credits = 0
    max_uses = None
    expires_at = None
    
    if len(args) >= 3:
        labs_credits = int(args[2])
    if len(args) >= 4:
        max_uses = int(args[3])
    if len(args) >= 5:
        expires_at = args[4]
    
    try:
        db.execute(
            """
            INSERT INTO promocodes (code, days, labs_credits, max_uses, used_count, expires_at)
            VALUES (%s, %s, %s, %s, 0, %s)
            ON CONFLICT (code) DO UPDATE SET
                days = EXCLUDED.days,
                labs_credits = EXCLUDED.labs_credits,
                max_uses = EXCLUDED.max_uses,
                expires_at = EXCLUDED.expires_at
            """,
            (code, days, labs_credits, max_uses, expires_at)
        )
        db.commit()
        
        await update.message.reply_text(
            f"✅ Промокод {code} создан:\n"
            f"• {days} дней подписки\n"
            f"• {labs_credits} анализ(ов)\n"
            f"• max_uses: {max_uses}\n"
            f"• expires: {expires_at or 'никогда'}"
        )
    except Exception as e:
        logger.exception(f"Error creating promo: {e}")
        db.rollback()
        await update.message.reply_text("❌ Ошибка создания промокода.")


# ============================================
# CATCH-ALL HANDLER
# ============================================

async def handle_any_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Обработчик любых других сообщений
    Направляет пользователя в Mini App
    """
    keyboard = [[InlineKeyboardButton(
        "🥗 Открыть приложение",
        web_app=WebAppInfo(url=MINI_APP_URL)
    )]]
    from telegram import InlineKeyboardMarkup
    
    await update.message.reply_text(
        "👋 Привет! Для работы со мной открой приложение.\n\n"
        "Нажми на кнопку ниже или используй меню (☰) рядом с полем ввода.",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


# ============================================
# MAIN
# ============================================

def main():
    """Запуск бота"""
    app = Application.builder().token(BOT_TOKEN).build()
    
    # Команды
    app.add_handler(CommandHandler("start", start_cmd))
    app.add_handler(CommandHandler("promo", promo_cmd))
    app.add_handler(CommandHandler("addpromo", addpromo_cmd))
    
    # Платежи (если настроены)
    if PAYMENT_TOKEN:
        app.add_handler(PreCheckoutQueryHandler(precheckout))
        app.add_handler(MessageHandler(filters.SUCCESSFUL_PAYMENT, successful_payment))
    
    # Catch-all для всех остальных сообщений
    app.add_handler(MessageHandler(
        filters.TEXT | filters.PHOTO | filters.Document.ALL,
        handle_any_message
    ))
    
    logger.info("🚀 NutriCoach Mini App Bot started!")
    logger.info(f"📱 Mini App URL: {MINI_APP_URL}")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()