-- ============================================
-- СХЕМА БАЗЫ ДАННЫХ NUTRICOACH
-- ============================================

-- Подписки
CREATE TABLE IF NOT EXISTS subscriptions (
    user_id BIGINT PRIMARY KEY,
    username TEXT,
    expires_at TIMESTAMP WITH TIME ZONE,
    free_until TIMESTAMP WITH TIME ZONE,
    used_free_lab BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_subscriptions_expires ON subscriptions(expires_at);
CREATE INDEX IF NOT EXISTS idx_subscriptions_free ON subscriptions(free_until);

-- Кредиты на анализы
CREATE TABLE IF NOT EXISTS credits (
    user_id BIGINT PRIMARY KEY,
    labs_credits INTEGER DEFAULT 0,
    FOREIGN KEY (user_id) REFERENCES subscriptions(user_id) ON DELETE CASCADE
);

-- Реферальная система
CREATE TABLE IF NOT EXISTS referrals (
    user_id BIGINT PRIMARY KEY,
    ref_code TEXT UNIQUE NOT NULL,
    invited_count INTEGER DEFAULT 0,
    FOREIGN KEY (user_id) REFERENCES subscriptions(user_id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_referrals_code ON referrals(ref_code);

-- Активации рефералов
CREATE TABLE IF NOT EXISTS referral_activations (
    inviter_id BIGINT NOT NULL,
    invited_id BIGINT NOT NULL,
    activated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (inviter_id, invited_id),
    FOREIGN KEY (inviter_id) REFERENCES subscriptions(user_id) ON DELETE CASCADE,
    FOREIGN KEY (invited_id) REFERENCES subscriptions(user_id) ON DELETE CASCADE
);

-- Промокоды
CREATE TABLE IF NOT EXISTS promocodes (
    code TEXT PRIMARY KEY,
    days INTEGER DEFAULT 0,
    labs_credits INTEGER DEFAULT 0,
    max_uses INTEGER,
    used_count INTEGER DEFAULT 0,
    expires_at TIMESTAMP WITH TIME ZONE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Платежи
CREATE TABLE IF NOT EXISTS payments (
    id SERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL,
    payload TEXT,
    currency TEXT,
    amount INTEGER,
    tg_charge_id TEXT,
    provider_charge_id TEXT UNIQUE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES subscriptions(user_id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_payments_user ON payments(user_id);
CREATE INDEX IF NOT EXISTS idx_payments_provider ON payments(provider_charge_id);

-- Приёмы пищи
CREATE TABLE IF NOT EXISTS meals (
    id SERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL,
    ts TIMESTAMP WITH TIME ZONE NOT NULL,
    text TEXT,
    calories INTEGER,
    proteins REAL,
    fats REAL,
    carbs REAL,
    FOREIGN KEY (user_id) REFERENCES subscriptions(user_id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_meals_user_ts ON meals(user_id, ts DESC);

-- Продукты (база данных питания)
CREATE TABLE IF NOT EXISTS products (
    name TEXT PRIMARY KEY,
    kcal_per_100 REAL NOT NULL,
    proteins_per_100 REAL NOT NULL,
    fats_per_100 REAL NOT NULL,
    carbs_per_100 REAL NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_products_name ON products(LOWER(name));

-- Отслеживание веса
CREATE TABLE IF NOT EXISTS weight_tracking (
    id SERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL,
    weight REAL NOT NULL,
    ts TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES subscriptions(user_id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_weight_user_ts ON weight_tracking(user_id, ts DESC);

-- Достижения
CREATE TABLE IF NOT EXISTS achievements (
    user_id BIGINT NOT NULL,
    badge TEXT NOT NULL,
    ts TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (user_id, badge),
    FOREIGN KEY (user_id) REFERENCES subscriptions(user_id) ON DELETE CASCADE
);

-- Челленджи
CREATE TABLE IF NOT EXISTS challenges (
    user_id BIGINT NOT NULL,
    challenge_type TEXT NOT NULL,
    start_date TIMESTAMP WITH TIME ZONE NOT NULL,
    progress INTEGER DEFAULT 0,
    completed INTEGER DEFAULT 0,
    PRIMARY KEY (user_id, challenge_type),
    FOREIGN KEY (user_id) REFERENCES subscriptions(user_id) ON DELETE CASCADE
);

-- Логи челленджей
CREATE TABLE IF NOT EXISTS challenge_logs (
    user_id BIGINT NOT NULL,
    challenge_type TEXT NOT NULL,
    log_date DATE NOT NULL,
    completed INTEGER DEFAULT 1,
    PRIMARY KEY (user_id, challenge_type, log_date),
    FOREIGN KEY (user_id, challenge_type) REFERENCES challenges(user_id, challenge_type) ON DELETE CASCADE
);

-- Инициализация базовых продуктов
INSERT INTO products (name, kcal_per_100, proteins_per_100, fats_per_100, carbs_per_100) VALUES
    ('яблоко', 52, 0.3, 0.2, 14),
    ('банан', 96, 1.3, 0.3, 23),
    ('рис', 360, 7.0, 0.7, 79),
    ('гречка', 343, 13.3, 3.4, 72.6),
    ('овсянка', 370, 13, 7, 62),
    ('куриная грудка', 165, 31, 3.6, 0),
    ('яйцо', 143, 12.6, 10.6, 0.7),
    ('творог 5%', 121, 17, 5, 1.8),
    ('молоко 2.5%', 52, 3.2, 2.5, 4.8),
    ('оливковое масло', 884, 0, 100, 0),
    ('огурец', 15, 0.7, 0.1, 3.6),
    ('помидор', 18, 0.9, 0.2, 3.9),
    ('сыр моцарелла', 280, 18, 21, 3)
ON CONFLICT (name) DO NOTHING;