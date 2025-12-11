"""
Database abstraction layer that supports both SQLite (local) and PostgreSQL (Railway).

Usage:
- If DATABASE_URL is set (Railway PostgreSQL), uses PostgreSQL
- Otherwise falls back to SQLite for local development

All functions return connection objects with a cursor() method that works the same way.
"""

import os
import sqlite3
from contextlib import contextmanager

DATABASE_URL = os.getenv("DATABASE_URL")
USE_POSTGRES = DATABASE_URL is not None

if USE_POSTGRES:
    import psycopg2
    from psycopg2.extras import RealDictCursor
    print(f"[Database] Using PostgreSQL (Railway)")
else:
    print(f"[Database] Using SQLite (local)")

DB_PATH = "cryptounc_lotto.db"


class SQLiteConnection:
    """Wrapper to make SQLite work like psycopg2"""
    def __init__(self, path):
        self.conn = sqlite3.connect(path)
        self.conn.row_factory = sqlite3.Row
    
    def cursor(self):
        return self.conn.cursor()
    
    def commit(self):
        self.conn.commit()
    
    def rollback(self):
        self.conn.rollback()
    
    def close(self):
        self.conn.close()
    
    def __enter__(self):
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()


def convert_query(query: str) -> str:
    """
    Convert SQLite query syntax to PostgreSQL.
    Handles: ? placeholders, INSERT OR IGNORE, INSERT OR REPLACE
    This function is idempotent - safe to call multiple times.
    """
    # Skip if already converted (contains %s instead of ?)
    if "%s" in query and "?" not in query:
        return query
    
    result = query.replace("?", "%s")
    
    # Handle INSERT OR IGNORE -> INSERT ... ON CONFLICT DO NOTHING
    if "INSERT OR IGNORE" in result.upper():
        result = result.replace("INSERT OR IGNORE", "INSERT")
        result = result.replace("insert or ignore", "INSERT")
        if "ON CONFLICT" not in result.upper():
            result = result.rstrip().rstrip(";") + " ON CONFLICT DO NOTHING"
    
    # Handle INSERT OR REPLACE (more complex - convert to upsert)
    if "INSERT OR REPLACE" in result.upper():
        result = result.replace("INSERT OR REPLACE", "INSERT")
        result = result.replace("insert or replace", "INSERT")
        if "ON CONFLICT" not in result.upper():
            result = result.rstrip().rstrip(";") + " ON CONFLICT DO NOTHING"
    
    return result


class PostgresCursor:
    """Wrapper that auto-converts SQLite syntax to PostgreSQL"""
    def __init__(self, cursor):
        self._cursor = cursor
    
    def execute(self, query, params=None):
        converted = convert_query(query)
        if params:
            return self._cursor.execute(converted, params)
        return self._cursor.execute(converted)
    
    def fetchone(self):
        return self._cursor.fetchone()
    
    def fetchall(self):
        return self._cursor.fetchall()
    
    @property
    def lastrowid(self):
        # PostgreSQL doesn't have lastrowid; return None
        return None
    
    @property
    def rowcount(self):
        return self._cursor.rowcount
    
    @property
    def description(self):
        return self._cursor.description


class PostgresConnection:
    """Wrapper for psycopg2 connection with auto-query conversion"""
    def __init__(self, url):
        try:
            self.conn = psycopg2.connect(url)
        except Exception as e:
            print(f"[Database] PostgreSQL connection error: {e}")
            raise
    
    def cursor(self):
        return PostgresCursor(self.conn.cursor())
    
    def commit(self):
        self.conn.commit()
    
    def rollback(self):
        self.conn.rollback()
    
    def close(self):
        self.conn.close()
    
    @property
    def rowcount(self):
        return self.conn.cursor().rowcount
    
    def __enter__(self):
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()


def get_db_conn():
    """Get database connection - works with both SQLite and PostgreSQL"""
    if USE_POSTGRES:
        return PostgresConnection(DATABASE_URL)
    else:
        return SQLiteConnection(DB_PATH)


def init_all_tables():
    """Initialize all database tables with correct syntax for current DB type"""
    conn = get_db_conn()
    c = conn.cursor()
    
    if USE_POSTGRES:
        c.execute("""
            CREATE TABLE IF NOT EXISTS wallets (
                id SERIAL PRIMARY KEY,
                user_id BIGINT NOT NULL,
                wallet_address TEXT NOT NULL,
                wallet_type TEXT NOT NULL,
                wallet_name TEXT,
                private_key TEXT,
                is_active INTEGER DEFAULT 1,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(user_id, wallet_address)
            )
        """)
        
        c.execute("""
            CREATE TABLE IF NOT EXISTS user_active_wallet (
                user_id BIGINT PRIMARY KEY,
                active_wallet_address TEXT
            )
        """)
        
        c.execute("""
            CREATE TABLE IF NOT EXISTS user_pins (
                user_id BIGINT PRIMARY KEY,
                pin_hash TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        c.execute("""
            CREATE TABLE IF NOT EXISTS meta (
                key TEXT PRIMARY KEY,
                value TEXT
            )
        """)
        
        c.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id BIGINT PRIMARY KEY,
                username TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        c.execute("""
            CREATE TABLE IF NOT EXISTS entries (
                id SERIAL PRIMARY KEY,
                user_id BIGINT,
                round INTEGER,
                numbers TEXT,
                stake_amount REAL,
                tx_signature TEXT,
                paid INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        c.execute("""
            CREATE TABLE IF NOT EXISTS scheduled_rounds (
                round_id SERIAL PRIMARY KEY,
                round_number INTEGER NOT NULL,
                scheduled_time TIMESTAMP NOT NULL,
                start_time TIMESTAMP,
                end_time TIMESTAMP,
                status TEXT DEFAULT 'pending',
                winning_numbers TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        c.execute("""
            CREATE TABLE IF NOT EXISTS round_stakes (
                id SERIAL PRIMARY KEY,
                round_id INTEGER NOT NULL,
                stake_amount REAL NOT NULL,
                status TEXT DEFAULT 'open',
                winner_user_id BIGINT,
                prize_amount REAL,
                tx_signature TEXT,
                first_stake_time TIMESTAMP,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        c.execute("""
            CREATE TABLE IF NOT EXISTS round_participants (
                id SERIAL PRIMARY KEY,
                round_stake_id INTEGER NOT NULL,
                user_id BIGINT NOT NULL,
                numbers TEXT NOT NULL,
                tx_signature TEXT NOT NULL,
                refunded INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(round_stake_id, user_id)
            )
        """)
        
        c.execute("""
            CREATE TABLE IF NOT EXISTS user_stats (
                user_id BIGINT PRIMARY KEY,
                total_tickets INTEGER DEFAULT 0,
                total_spent REAL DEFAULT 0,
                total_won REAL DEFAULT 0,
                wins INTEGER DEFAULT 0,
                biggest_win REAL DEFAULT 0,
                referral_earnings REAL DEFAULT 0,
                vip_tier INTEGER DEFAULT 0,
                notification_enabled INTEGER DEFAULT 1
            )
        """)
        
        c.execute("""
            CREATE TABLE IF NOT EXISTS referrals (
                id SERIAL PRIMARY KEY,
                referrer_id BIGINT NOT NULL,
                referred_id BIGINT NOT NULL UNIQUE,
                referral_code TEXT,
                bonus_earned REAL DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        c.execute("""
            CREATE TABLE IF NOT EXISTS draw_history (
                id SERIAL PRIMARY KEY,
                round_id INTEGER NOT NULL,
                winning_numbers TEXT NOT NULL,
                seed_data TEXT,
                player_count INTEGER,
                total_pot REAL,
                winner_id BIGINT,
                prize_amount REAL,
                tx_signature TEXT,
                drawn_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        c.execute("""
            CREATE TABLE IF NOT EXISTS jackpot_seeds (
                id SERIAL PRIMARY KEY,
                admin_id BIGINT NOT NULL,
                amount REAL NOT NULL,
                tx_signature TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        try:
            c.execute("INSERT INTO meta (key, value) VALUES (%s, %s) ON CONFLICT (key) DO NOTHING", ('current_round', '1'))
        except:
            pass
        
        try:
            c.execute("CREATE INDEX IF NOT EXISTS idx_wallets_user ON wallets(user_id)")
            c.execute("CREATE INDEX IF NOT EXISTS idx_entries_user ON entries(user_id)")
            c.execute("CREATE INDEX IF NOT EXISTS idx_entries_round ON entries(round)")
            c.execute("CREATE INDEX IF NOT EXISTS idx_scheduled_status ON scheduled_rounds(status)")
            c.execute("CREATE INDEX IF NOT EXISTS idx_round_stakes ON round_stakes(round_id)")
            c.execute("CREATE INDEX IF NOT EXISTS idx_participants_stake ON round_participants(round_stake_id)")
            c.execute("CREATE INDEX IF NOT EXISTS idx_referrals_referrer ON referrals(referrer_id)")
            c.execute("CREATE INDEX IF NOT EXISTS idx_draw_history_round ON draw_history(round_id)")
        except:
            pass
        
    else:
        c.execute("""
            CREATE TABLE IF NOT EXISTS wallets (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                wallet_address TEXT NOT NULL,
                wallet_type TEXT NOT NULL,
                wallet_name TEXT,
                private_key TEXT,
                is_active INTEGER DEFAULT 1,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(user_id, wallet_address)
            )
        """)
        
        c.execute("""
            CREATE TABLE IF NOT EXISTS user_active_wallet (
                user_id INTEGER PRIMARY KEY,
                active_wallet_address TEXT
            )
        """)
        
        c.execute("""
            CREATE TABLE IF NOT EXISTS user_pins (
                user_id INTEGER PRIMARY KEY,
                pin_hash TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        c.execute("""
            CREATE TABLE IF NOT EXISTS meta (
                key TEXT PRIMARY KEY,
                value TEXT
            )
        """)
        
        c.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                username TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        c.execute("""
            CREATE TABLE IF NOT EXISTS entries (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                round INTEGER,
                numbers TEXT,
                stake_amount REAL,
                tx_signature TEXT,
                paid INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        c.execute("""
            CREATE TABLE IF NOT EXISTS scheduled_rounds (
                round_id INTEGER PRIMARY KEY AUTOINCREMENT,
                round_number INTEGER NOT NULL,
                scheduled_time TIMESTAMP NOT NULL,
                start_time TIMESTAMP,
                end_time TIMESTAMP,
                status TEXT DEFAULT 'pending',
                winning_numbers TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        c.execute("""
            CREATE TABLE IF NOT EXISTS round_stakes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                round_id INTEGER NOT NULL,
                stake_amount REAL NOT NULL,
                status TEXT DEFAULT 'open',
                winner_user_id INTEGER,
                prize_amount REAL,
                tx_signature TEXT,
                first_stake_time TIMESTAMP,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        c.execute("""
            CREATE TABLE IF NOT EXISTS round_participants (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                round_stake_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                numbers TEXT NOT NULL,
                tx_signature TEXT NOT NULL,
                refunded INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(round_stake_id, user_id)
            )
        """)
        
        c.execute("""
            CREATE TABLE IF NOT EXISTS user_stats (
                user_id INTEGER PRIMARY KEY,
                total_tickets INTEGER DEFAULT 0,
                total_spent REAL DEFAULT 0,
                total_won REAL DEFAULT 0,
                wins INTEGER DEFAULT 0,
                biggest_win REAL DEFAULT 0,
                referral_earnings REAL DEFAULT 0,
                vip_tier INTEGER DEFAULT 0,
                notification_enabled INTEGER DEFAULT 1
            )
        """)
        
        c.execute("""
            CREATE TABLE IF NOT EXISTS referrals (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                referrer_id INTEGER NOT NULL,
                referred_id INTEGER NOT NULL UNIQUE,
                referral_code TEXT,
                bonus_earned REAL DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        c.execute("""
            CREATE TABLE IF NOT EXISTS draw_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                round_id INTEGER NOT NULL,
                winning_numbers TEXT NOT NULL,
                seed_data TEXT,
                player_count INTEGER,
                total_pot REAL,
                winner_id INTEGER,
                prize_amount REAL,
                tx_signature TEXT,
                drawn_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        c.execute("""
            CREATE TABLE IF NOT EXISTS jackpot_seeds (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                admin_id INTEGER NOT NULL,
                amount REAL NOT NULL,
                tx_signature TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        c.execute("INSERT OR IGNORE INTO meta (key, value) VALUES ('current_round', '1')")
        
        c.execute("CREATE INDEX IF NOT EXISTS idx_wallets_user ON wallets(user_id)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_entries_user ON entries(user_id)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_entries_round ON entries(round)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_scheduled_status ON scheduled_rounds(status)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_round_stakes ON round_stakes(round_id)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_participants_stake ON round_participants(stake_id)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_referrals_referrer ON referrals(referrer_id)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_draw_history_round ON draw_history(round_id)")
    
    conn.commit()
    conn.close()
    print("[Database] All tables initialized")


def q(query: str) -> str:
    """
    Convert SQLite query syntax to PostgreSQL if needed.
    Handles: ? placeholders, INSERT OR IGNORE, INSERT OR REPLACE
    """
    if not USE_POSTGRES:
        return query
    
    result = query.replace("?", "%s")
    
    # Handle INSERT OR IGNORE -> INSERT ... ON CONFLICT DO NOTHING
    if "INSERT OR IGNORE" in result.upper():
        result = result.replace("INSERT OR IGNORE", "INSERT")
        if "ON CONFLICT" not in result.upper():
            # Find the VALUES clause and add ON CONFLICT after it
            if "VALUES" in result.upper():
                # Add ON CONFLICT DO NOTHING at the end
                result = result.rstrip().rstrip(";") + " ON CONFLICT DO NOTHING"
    
    # Handle INSERT OR REPLACE -> INSERT ... ON CONFLICT ... DO UPDATE
    # This is more complex and needs table-specific handling
    if "INSERT OR REPLACE" in result.upper():
        result = result.replace("INSERT OR REPLACE", "INSERT")
        if "ON CONFLICT" not in result.upper():
            result = result.rstrip().rstrip(";") + " ON CONFLICT DO NOTHING"
    
    return result


def insert_ignore(table: str, columns: list, values: tuple) -> str:
    """Generate INSERT OR IGNORE / INSERT ON CONFLICT query"""
    cols = ", ".join(columns)
    if USE_POSTGRES:
        placeholders = ", ".join(["%s"] * len(values))
        return f"INSERT INTO {table} ({cols}) VALUES ({placeholders}) ON CONFLICT DO NOTHING"
    else:
        placeholders = ", ".join(["?"] * len(values))
        return f"INSERT OR IGNORE INTO {table} ({cols}) VALUES ({placeholders})"
