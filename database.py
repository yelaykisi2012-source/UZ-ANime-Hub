import aiosqlite
import time
from config import DB_PATH

async def init_db():
    async with aiosqlite.connect(DB_PATH) as db:
        # Foydalanuvchilar
        await db.execute('''
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                username TEXT,
                full_name TEXT,
                premium_until INTEGER DEFAULT 0,
                created_at INTEGER
            )
        ''')
        # Anime seriyalari
        await db.execute('''
            CREATE TABLE IF NOT EXISTS series (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                code TEXT UNIQUE,
                title TEXT,
                country TEXT,
                language TEXT,
                year TEXT,
                genre TEXT,
                total_episodes INTEGER,
                created_at INTEGER
            )
        ''')
        # Anime qismlari
        await db.execute('''
            CREATE TABLE IF NOT EXISTS episodes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                series_code TEXT,
                episode_number INTEGER,
                file_id TEXT NOT NULL,
                is_premium INTEGER DEFAULT 0,
                views INTEGER DEFAULT 0,
                created_at INTEGER,
                FOREIGN KEY(series_code) REFERENCES series(code) ON DELETE CASCADE
            )
        ''')
        # To‘lovlar
        await db.execute('''
            CREATE TABLE IF NOT EXISTS payments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                amount INTEGER,
                status TEXT DEFAULT 'pending',
                created_at INTEGER,
                confirmed_at INTEGER
            )
        ''')
        # Sozlamalar
        await db.execute('''
            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT
            )
        ''')
        await db.commit()

# ----------------- Foydalanuvchilar -----------------
async def add_user(user_id, username=None, full_name=None):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute('''
            INSERT OR IGNORE INTO users (user_id, username, full_name, created_at)
            VALUES (?, ?, ?, ?)
        ''', (user_id, username, full_name, int(time.time())))
        await db.commit()

async def get_user(user_id):
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute('SELECT * FROM users WHERE user_id = ?', (user_id,)) as cursor:
            return await cursor.fetchone()

async def set_premium(user_id, days):
    user = await get_user(user_id)
    now = int(time.time())
    if user and user[3] > now:
        new_until = user[3] + days * 86400
    else:
        new_until = now + days * 86400
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute('UPDATE users SET premium_until = ? WHERE user_id = ?', (new_until, user_id))
        await db.commit()
    return new_until

async def check_premium(user_id):
    user = await get_user(user_id)
    return user and user[3] > int(time.time())

async def premium_remaining(user_id):
    user = await get_user(user_id)
    if not user or user[3] <= int(time.time()):
        return "Muddati tugagan yoki mavjud emas"
    remaining = user[3] - int(time.time())
    days = remaining // 86400
    hours = (remaining % 86400) // 3600
    minutes = (remaining % 3600) // 60
    return f"{days} kun, {hours} soat, {minutes} daqiqa"

async def get_all_users():
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute('SELECT user_id FROM users') as cursor:
            rows = await cursor.fetchall()
            return [row[0] for row in rows]

# ----------------- Seriyalar -----------------
async def add_series(code, title, country, language, year, genre, total_episodes):
    async with aiosqlite.connect(DB_PATH) as db:
        try:
            await db.execute('''
                INSERT INTO series (code, title, country, language, year, genre, total_episodes, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ''', (code, title, country, language, year, genre, total_episodes, int(time.time())))
            await db.commit()
            return True
        except aiosqlite.IntegrityError:
            return False

async def get_series(code):
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute('SELECT * FROM series WHERE code = ?', (code,)) as cursor:
            return await cursor.fetchone()

async def delete_series(code):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute('DELETE FROM series WHERE code = ?', (code,))
        await db.commit()

async def list_series():
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute('SELECT code, title, total_episodes FROM series ORDER BY created_at DESC') as cursor:
            return await cursor.fetchall()

# ----------------- Qismlar -----------------
async def add_episode(series_code, episode_number, file_id, is_premium=0):
    async with aiosqlite.connect(DB_PATH) as db:
        try:
            await db.execute('''
                INSERT INTO episodes (series_code, episode_number, file_id, is_premium, created_at)
                VALUES (?, ?, ?, ?, ?)
            ''', (series_code, episode_number, file_id, is_premium, int(time.time())))
            await db.commit()
            return True
        except aiosqlite.IntegrityError:
            return False

async def get_episodes(series_code):
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute('''
            SELECT episode_number, file_id, is_premium, views FROM episodes
            WHERE series_code = ?
            ORDER BY episode_number
        ''', (series_code,)) as cursor:
            return await cursor.fetchall()

async def get_episode(series_code, episode_number):
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute('''
            SELECT * FROM episodes WHERE series_code = ? AND episode_number = ?
        ''', (series_code, episode_number)) as cursor:
            return await cursor.fetchone()

async def increment_episode_views(series_code, episode_number):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute('''
            UPDATE episodes SET views = views + 1
            WHERE series_code = ? AND episode_number = ?
        ''', (series_code, episode_number))
        await db.commit()

async def delete_episodes(series_code):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute('DELETE FROM episodes WHERE series_code = ?', (series_code,))
        await db.commit()

# ----------------- To‘lovlar -----------------
async def add_payment(user_id, amount):
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute('''
            INSERT INTO payments (user_id, amount, created_at)
            VALUES (?, ?, ?)
        ''', (user_id, amount, int(time.time())))
        await db.commit()
        return cursor.lastrowid

async def confirm_payment(payment_id):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute('''
            UPDATE payments SET status = 'confirmed', confirmed_at = ?
            WHERE id = ?
        ''', (int(time.time()), payment_id))
        await db.commit()

# ----------------- Sozlamalar -----------------
async def get_setting(key, default=None):
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute('SELECT value FROM settings WHERE key = ?', (key,)) as cursor:
            row = await cursor.fetchone()
            return row[0] if row else default

async def set_setting(key, value):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute('''
            INSERT INTO settings (key, value) VALUES (?, ?)
            ON CONFLICT(key) DO UPDATE SET value = excluded.value
        ''', (key, value))
        await db.commit()