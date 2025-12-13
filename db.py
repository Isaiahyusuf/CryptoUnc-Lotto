"""
Database abstraction layer that supports both SQLite (local) and PostgreSQL (Railway).

Usage:
- If DATABASE_URL is set (Railway PostgreSQL), uses PostgreSQL with connection pooling
- Otherwise falls back to SQLite for local development

All functions return connection objects with a cursor() method that works the same way.
"""

import os
import sqlite3
from contextlib import contextmanager
import threading

DATABASE_URL = os.getenv("DATABASE_URL")

# Connection pool for PostgreSQL (reduces connection overhead)
_pg_pool = None
_pool_lock = threading.Lock()

# Check if DATABASE_URL is valid (not empty, contains proper connection info)
def is_valid_database_url(url):
    if not url:
        return False
    url = url.strip()
    if not url:
        return False
    # Must contain postgresql:// or postgres:// and have host info
    if not (url.startswith("postgresql://") or url.startswith("postgres://")):
        print(f"[Database] Invalid DATABASE_URL format - must start with postgresql:// or postgres://")
        print(f"[Database] Got: {url[:20]}..." if len(url) > 20 else f"[Database] Got: {url}")
        return False
    return True

USE_POSTGRES = is_valid_database_url(DATABASE_URL)

if USE_POSTGRES:
    import psycopg2
    from psycopg2 import pool
    from psycopg2.extras import RealDictCursor
    # Print connection info (hide password)
    if DATABASE_URL:
        safe_url = DATABASE_URL.split("@")[-1] if "@" in DATABASE_URL else "configured"
        print(f"[Database] Using PostgreSQL with pooling: ...@{safe_url}")
else:
    print(f"[Database] Using SQLite (local)")
    if DATABASE_URL:
        print(f"[Database] Note: DATABASE_URL was set but invalid, falling back to SQLite")


def init_pg_pool():
    """Initialize PostgreSQL connection pool"""
    global _pg_pool
    if USE_POSTGRES and _pg_pool is None:
        with _pool_lock:
            if _pg_pool is None:
                try:
                    _pg_pool = pool.ThreadedConnectionPool(
                        minconn=2,
                        maxconn=10,
                        dsn=DATABASE_URL
                    )
                    print("[Database] Connection pool initialized (2-10 connections)")
                except Exception as e:
                    print(f"[Database] Failed to create pool: {e}")
                    _pg_pool = None

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
    def __init__(self, conn, from_pool=False):
        self.conn = conn
        self._from_pool = from_pool
    
    def cursor(self):
        return PostgresCursor(self.conn.cursor())
    
    def commit(self):
        self.conn.commit()
    
    def rollback(self):
        self.conn.rollback()
    
    def close(self):
        if self._from_pool and _pg_pool:
            # Return to pool instead of closing
            try:
                _pg_pool.putconn(self.conn)
            except:
                self.conn.close()
        else:
            self.conn.close()
    
    @property
    def rowcount(self):
        return self.conn.cursor().rowcount
    
    def __enter__(self):
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()


def get_db_conn():
    """Get database connection - uses pool for PostgreSQL, direct for SQLite"""
    if USE_POSTGRES:
        # Try to use pool if available
        if _pg_pool:
            try:
                conn = _pg_pool.getconn()
                return PostgresConnection(conn, from_pool=True)
            except Exception as e:
                print(f"[Database] Pool error, using direct connection: {e}")
        # Fallback to direct connection
        try:
            conn = psycopg2.connect(DATABASE_URL)
            return PostgresConnection(conn, from_pool=False)
        except Exception as e:
            print(f"[Database] PostgreSQL connection error: {e}")
            raise
    else:
        return SQLiteConnection(DB_PATH)


def migrate_remove_unique_constraint():
    """Migration: Remove UNIQUE constraint from round_participants to allow unlimited tickets per user"""
    if USE_POSTGRES:
        try:
            conn = get_db_conn()
            c = conn.cursor()
            c.execute("""
                SELECT constraint_name FROM information_schema.table_constraints 
                WHERE table_name = 'round_participants' 
                AND constraint_type = 'UNIQUE'
            """)
            constraints = c.fetchall()
            for row in constraints:
                constraint_name = row[0]
                if 'tx_signature' in constraint_name or 'ticket_id' in constraint_name:
                    continue
                try:
                    c.execute(f"ALTER TABLE round_participants DROP CONSTRAINT {constraint_name}")
                    print(f"[Migration] Dropped UNIQUE constraint: {constraint_name}")
                except Exception as e:
                    print(f"[Migration] Could not drop constraint {constraint_name}: {e}")
            
            c.execute("""
                SELECT indexname FROM pg_indexes 
                WHERE tablename = 'round_participants'
            """)
            indexes = c.fetchall()
            for row in indexes:
                index_name = row[0]
                if 'tx_signature' in index_name or 'ticket_id' in index_name:
                    continue
                if 'round_stake_id' in index_name and 'user_id' in index_name:
                    try:
                        c.execute(f"DROP INDEX IF EXISTS {index_name}")
                        print(f"[Migration] Dropped UNIQUE index: {index_name}")
                    except Exception as e:
                        print(f"[Migration] Could not drop index {index_name}: {e}")
            
            conn.commit()
            conn.close()
        except Exception as e:
            print(f"[Migration] Error removing UNIQUE constraint: {e}")
    else:
        try:
            conn = get_db_conn()
            c = conn.cursor()
            
            needs_migration = False
            
            c.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='round_participants'")
            result = c.fetchone()
            if result:
                table_sql = str(result[0])
                if 'UNIQUE(round_stake_id, user_id)' in table_sql or 'UNIQUE (round_stake_id, user_id)' in table_sql:
                    needs_migration = True
            
            c.execute("SELECT name, sql FROM sqlite_master WHERE type='index' AND tbl_name='round_participants'")
            indexes = c.fetchall()
            for idx_row in indexes:
                idx_name = idx_row[0]
                idx_sql = str(idx_row[1]) if idx_row[1] else ''
                if 'tx_signature' in idx_name or 'ticket_id' in idx_name:
                    continue
                if ('round_stake_id' in idx_sql and 'user_id' in idx_sql) or ('round_stake_id, user_id' in idx_sql):
                    if 'UNIQUE' in idx_sql.upper():
                        print(f"[Migration] Found problematic UNIQUE index: {idx_name}")
                        needs_migration = True
            
            if needs_migration:
                print("[Migration] Recreating round_participants table to remove UNIQUE constraint...")
                c.execute("DROP TABLE IF EXISTS round_participants_new")
                c.execute("""
                    CREATE TABLE round_participants_new (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        ticket_id TEXT,
                        round_stake_id INTEGER NOT NULL,
                        user_id INTEGER NOT NULL,
                        numbers TEXT NOT NULL,
                        tx_signature TEXT NOT NULL,
                        refunded INTEGER DEFAULT 0,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                """)
                c.execute("""
                    INSERT INTO round_participants_new (id, ticket_id, round_stake_id, user_id, numbers, tx_signature, refunded, created_at)
                    SELECT id, ticket_id, round_stake_id, user_id, numbers, tx_signature, refunded, created_at
                    FROM round_participants
                """)
                c.execute("DROP TABLE round_participants")
                c.execute("ALTER TABLE round_participants_new RENAME TO round_participants")
                c.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_participants_tx_sig ON round_participants(tx_signature)")
                c.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_participants_ticket_id ON round_participants(ticket_id)")
                c.execute("CREATE INDEX IF NOT EXISTS idx_participants_stake ON round_participants(round_stake_id)")
                print("[Migration] Successfully recreated round_participants table without UNIQUE constraint")
                conn.commit()
            else:
                print("[Migration] No UNIQUE(round_stake_id, user_id) constraint found - checking for indexes to drop")
                for idx_row in indexes:
                    idx_name = idx_row[0]
                    idx_sql = str(idx_row[1]) if idx_row[1] else ''
                    if 'tx_signature' in idx_name or 'ticket_id' in idx_name or 'idx_participants_stake' in idx_name:
                        continue
                    if 'round_stake_id' in idx_sql and 'user_id' in idx_sql:
                        try:
                            c.execute(f"DROP INDEX IF EXISTS {idx_name}")
                            print(f"[Migration] Dropped index: {idx_name}")
                            conn.commit()
                        except Exception as e:
                            print(f"[Migration] Could not drop index {idx_name}: {e}")
            
            conn.close()
        except Exception as e:
            print(f"[Migration] Error removing UNIQUE constraint for SQLite: {e}")


def migrate_add_ticket_id_column():
    """Migration: Add ticket_id column to round_participants for multiple tickets support"""
    try:
        conn = get_db_conn()
        c = conn.cursor()
        
        if USE_POSTGRES:
            # Check if ticket_id column exists
            c.execute("""
                SELECT column_name FROM information_schema.columns 
                WHERE table_name = 'round_participants' AND column_name = 'ticket_id'
            """)
            if not c.fetchone():
                c.execute("ALTER TABLE round_participants ADD COLUMN ticket_id TEXT")
                print("[Migration] Added ticket_id column to round_participants table")
                # Create unique index on ticket_id
                try:
                    c.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_participants_ticket_id ON round_participants(ticket_id)")
                except:
                    pass
            # Create unique index on tx_signature if not exists
            try:
                c.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_participants_tx_sig ON round_participants(tx_signature)")
            except:
                pass
        else:
            # SQLite - check if column exists
            c.execute("PRAGMA table_info(round_participants)")
            columns = [row[1] for row in c.fetchall()]
            if 'ticket_id' not in columns:
                c.execute("ALTER TABLE round_participants ADD COLUMN ticket_id TEXT")
                print("[Migration] Added ticket_id column to round_participants table")
            # Create unique indexes if not exists
            try:
                c.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_participants_ticket_id ON round_participants(ticket_id)")
                c.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_participants_tx_sig ON round_participants(tx_signature)")
            except:
                pass
        
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"[Migration] Error adding ticket_id column: {e}")


def migrate_add_referral_column():
    """Migration: Add tickets_from_referral column to referrals table if missing"""
    try:
        conn = get_db_conn()
        c = conn.cursor()
        
        if USE_POSTGRES:
            # Check if column exists
            c.execute("""
                SELECT column_name FROM information_schema.columns 
                WHERE table_name = 'referrals' AND column_name = 'tickets_from_referral'
            """)
            if not c.fetchone():
                c.execute("ALTER TABLE referrals ADD COLUMN tickets_from_referral INTEGER DEFAULT 0")
                print("[Migration] Added tickets_from_referral column to referrals table")
        else:
            # SQLite - check if column exists
            c.execute("PRAGMA table_info(referrals)")
            columns = [row[1] for row in c.fetchall()]
            if 'tickets_from_referral' not in columns:
                c.execute("ALTER TABLE referrals ADD COLUMN tickets_from_referral INTEGER DEFAULT 0")
                print("[Migration] Added tickets_from_referral column to referrals table")
        
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"[Migration] Error adding tickets_from_referral column: {e}")


def init_all_tables():
    """Initialize all database tables with correct syntax for current DB type"""
    # Initialize connection pool for PostgreSQL
    if USE_POSTGRES:
        init_pg_pool()
    
    conn = get_db_conn()
    c = conn.cursor()
    
    if USE_POSTGRES:
        # For PostgreSQL, we need to handle existing tables gracefully
        # Check if tables exist first to avoid SERIAL type conflicts
        c.execute("""
            SELECT table_name FROM information_schema.tables 
            WHERE table_schema = 'public'
        """)
        existing_tables = {row[0] for row in c.fetchall()}
        
        if 'wallets' not in existing_tables:
            c.execute("""
                CREATE TABLE wallets (
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
        
        if 'entries' not in existing_tables:
            c.execute("""
                CREATE TABLE entries (
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
        
        if 'scheduled_rounds' not in existing_tables:
            c.execute("""
                CREATE TABLE scheduled_rounds (
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
        
        if 'round_stakes' not in existing_tables:
            c.execute("""
                CREATE TABLE round_stakes (
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
        
        if 'round_participants' not in existing_tables:
            c.execute("""
                CREATE TABLE round_participants (
                    id SERIAL PRIMARY KEY,
                    ticket_id TEXT UNIQUE,
                    round_stake_id INTEGER NOT NULL,
                    user_id BIGINT NOT NULL,
                    numbers TEXT NOT NULL,
                    tx_signature TEXT NOT NULL UNIQUE,
                    refunded INTEGER DEFAULT 0,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
        
        if 'user_stats' not in existing_tables:
            c.execute("""
                CREATE TABLE user_stats (
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
        
        if 'referrals' not in existing_tables:
            c.execute("""
                CREATE TABLE referrals (
                    id SERIAL PRIMARY KEY,
                    referrer_id BIGINT NOT NULL,
                    referred_id BIGINT NOT NULL UNIQUE,
                    referral_code TEXT,
                    bonus_earned REAL DEFAULT 0,
                    tickets_from_referral INTEGER DEFAULT 0,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
        
        if 'draw_history' not in existing_tables:
            c.execute("""
                CREATE TABLE draw_history (
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
        
        if 'jackpot_seeds' not in existing_tables:
            c.execute("""
                CREATE TABLE jackpot_seeds (
                    id SERIAL PRIMARY KEY,
                    admin_id BIGINT NOT NULL,
                    amount REAL NOT NULL,
                    tx_signature TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
        
        if 'wallet_transactions' not in existing_tables:
            c.execute("""
                CREATE TABLE wallet_transactions (
                    id SERIAL PRIMARY KEY,
                    user_id BIGINT NOT NULL,
                    wallet_address TEXT NOT NULL,
                    tx_type TEXT NOT NULL,
                    amount REAL NOT NULL,
                    to_address TEXT,
                    from_address TEXT,
                    tx_signature TEXT,
                    status TEXT DEFAULT 'pending',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
        
        if 'user_emails' not in existing_tables:
            c.execute("""
                CREATE TABLE user_emails (
                    user_id BIGINT PRIMARY KEY,
                    email TEXT NOT NULL UNIQUE,
                    verified INTEGER DEFAULT 0,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
        
        if 'email_verification_codes' not in existing_tables:
            c.execute("""
                CREATE TABLE email_verification_codes (
                    id SERIAL PRIMARY KEY,
                    user_id BIGINT NOT NULL,
                    email TEXT NOT NULL,
                    code TEXT NOT NULL,
                    purpose TEXT NOT NULL,
                    expires_at TIMESTAMP NOT NULL,
                    used INTEGER DEFAULT 0,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
        
        if 'security_questions' not in existing_tables:
            c.execute("""
                CREATE TABLE security_questions (
                    user_id BIGINT PRIMARY KEY,
                    question TEXT NOT NULL,
                    answer_hash TEXT NOT NULL,
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
            c.execute("CREATE INDEX IF NOT EXISTS idx_email_codes_user ON email_verification_codes(user_id)")
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
                ticket_id TEXT UNIQUE,
                round_stake_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                numbers TEXT NOT NULL,
                tx_signature TEXT NOT NULL UNIQUE,
                refunded INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
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
                tickets_from_referral INTEGER DEFAULT 0,
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
        
        c.execute("""
            CREATE TABLE IF NOT EXISTS wallet_transactions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                wallet_address TEXT NOT NULL,
                tx_type TEXT NOT NULL,
                amount REAL NOT NULL,
                to_address TEXT,
                from_address TEXT,
                tx_signature TEXT,
                status TEXT DEFAULT 'pending',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        c.execute("""
            CREATE TABLE IF NOT EXISTS user_emails (
                user_id INTEGER PRIMARY KEY,
                email TEXT NOT NULL UNIQUE,
                verified INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        c.execute("""
            CREATE TABLE IF NOT EXISTS email_verification_codes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                email TEXT NOT NULL,
                code TEXT NOT NULL,
                purpose TEXT NOT NULL,
                expires_at TIMESTAMP NOT NULL,
                used INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        c.execute("""
            CREATE TABLE IF NOT EXISTS security_questions (
                user_id INTEGER PRIMARY KEY,
                question TEXT NOT NULL,
                answer_hash TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        c.execute("""
            CREATE TABLE IF NOT EXISTS announcement_groups (
                chat_id BIGINT PRIMARY KEY,
                chat_type TEXT NOT NULL,
                chat_title TEXT,
                added_by INTEGER,
                is_active INTEGER DEFAULT 1,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        c.execute("INSERT OR IGNORE INTO meta (key, value) VALUES ('current_round', '1')")
        
        c.execute("CREATE INDEX IF NOT EXISTS idx_wallets_user ON wallets(user_id)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_entries_user ON entries(user_id)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_entries_round ON entries(round)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_scheduled_status ON scheduled_rounds(status)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_round_stakes ON round_stakes(round_id)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_participants_stake ON round_participants(round_stake_id)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_referrals_referrer ON referrals(referrer_id)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_draw_history_round ON draw_history(round_id)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_email_codes_user ON email_verification_codes(user_id)")
    
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


# Security Question Functions
import hashlib

def hash_answer(answer: str) -> str:
    """Hash security question answer (case-insensitive, trimmed)"""
    normalized = answer.strip().lower()
    return hashlib.sha256(normalized.encode()).hexdigest()

def save_security_question(user_id: int, question: str, answer: str) -> bool:
    """Save or update user's security question"""
    try:
        print(f"[SecurityQ] Saving for user {user_id}, question: {question[:30] if question else 'None'}...")
        conn = get_db_conn()
        c = conn.cursor()
        answer_hash = hash_answer(answer)
        
        if USE_POSTGRES:
            c.execute("""
                INSERT INTO security_questions (user_id, question, answer_hash)
                VALUES (%s, %s, %s)
                ON CONFLICT (user_id) DO UPDATE SET question = EXCLUDED.question, answer_hash = EXCLUDED.answer_hash
            """, (int(user_id), question, answer_hash))
        else:
            c.execute("""
                INSERT OR REPLACE INTO security_questions (user_id, question, answer_hash)
                VALUES (?, ?, ?)
            """, (int(user_id), question, answer_hash))
        
        conn.commit()
        conn.close()
        print(f"[SecurityQ] Successfully saved for user {user_id}")
        return True
    except Exception as e:
        print(f"[DB] Error saving security question: {e}")
        import traceback
        traceback.print_exc()
        return False

def get_security_question(user_id: int) -> dict:
    """Get user's security question (not the answer)"""
    try:
        conn = get_db_conn()
        c = conn.cursor()
        c.execute(q("SELECT question FROM security_questions WHERE user_id = ?"), (int(user_id),))
        row = c.fetchone()
        conn.close()
        if row:
            return {"question": row[0], "has_question": True}
        return {"has_question": False}
    except Exception as e:
        print(f"[DB] Error getting security question: {e}")
        return {"has_question": False}

def verify_security_answer(user_id: int, answer: str) -> bool:
    """Verify user's security question answer"""
    try:
        conn = get_db_conn()
        c = conn.cursor()
        c.execute(q("SELECT answer_hash FROM security_questions WHERE user_id = ?"), (int(user_id),))
        row = c.fetchone()
        conn.close()
        if row:
            return row[0] == hash_answer(answer)
        return False
    except Exception as e:
        print(f"[DB] Error verifying security answer: {e}")
        return False

def has_security_question(user_id: int) -> bool:
    """Check if user has a security question set"""
    try:
        conn = get_db_conn()
        c = conn.cursor()
        c.execute(q("SELECT 1 FROM security_questions WHERE user_id = ?"), (int(user_id),))
        result = c.fetchone() is not None
        conn.close()
        return result
    except:
        return False


# ===== Announcement Groups Functions =====

def add_announcement_group(chat_id: int, chat_type: str, chat_title: str = None, added_by: int = None) -> bool:  # type: ignore
    """Add a group/channel to receive announcements"""
    try:
        conn = get_db_conn()
        c = conn.cursor()
        if USE_POSTGRES:
            c.execute("""
                INSERT INTO announcement_groups (chat_id, chat_type, chat_title, added_by, is_active)
                VALUES (%s, %s, %s, %s, 1)
                ON CONFLICT (chat_id) DO UPDATE SET 
                    chat_title = EXCLUDED.chat_title,
                    is_active = 1
            """, (chat_id, chat_type, chat_title, added_by))
        else:
            c.execute("""
                INSERT OR REPLACE INTO announcement_groups (chat_id, chat_type, chat_title, added_by, is_active)
                VALUES (?, ?, ?, ?, 1)
            """, (chat_id, chat_type, chat_title, added_by))
        conn.commit()
        conn.close()
        print(f"[DB] Added announcement group: {chat_id} ({chat_title})")
        return True
    except Exception as e:
        print(f"[DB] Error adding announcement group: {e}")
        return False

def remove_announcement_group(chat_id: int) -> bool:
    """Deactivate a group/channel from announcements (soft delete)"""
    try:
        conn = get_db_conn()
        c = conn.cursor()
        c.execute(q("UPDATE announcement_groups SET is_active = 0 WHERE chat_id = ?"), (chat_id,))
        conn.commit()
        conn.close()
        print(f"[DB] Removed announcement group: {chat_id}")
        return True
    except Exception as e:
        print(f"[DB] Error removing announcement group: {e}")
        return False

def get_announcement_groups() -> list:
    """Get all active announcement groups/channels"""
    try:
        conn = get_db_conn()
        c = conn.cursor()
        c.execute(q("SELECT chat_id, chat_type, chat_title FROM announcement_groups WHERE is_active = 1"))
        rows = c.fetchall()
        conn.close()
        return [{"chat_id": row[0], "chat_type": row[1], "chat_title": row[2]} for row in rows]
    except Exception as e:
        print(f"[DB] Error getting announcement groups: {e}")
        return []

def is_announcement_group(chat_id: int) -> bool:
    """Check if a chat is an active announcement group"""
    try:
        conn = get_db_conn()
        c = conn.cursor()
        c.execute(q("SELECT 1 FROM announcement_groups WHERE chat_id = ? AND is_active = 1"), (chat_id,))
        result = c.fetchone() is not None
        conn.close()
        return result
    except:
        return False
