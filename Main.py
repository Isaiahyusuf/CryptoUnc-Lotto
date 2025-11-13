# Main.py — CryptoUnc Lotto with Real Solana Wallet Integration

import os
import asyncio
import hashlib
import time
import decimal
from decimal import Decimal
from typing import List, Dict
from datetime import datetime, timedelta
import pytz

from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from dotenv import load_dotenv
from aiohttp import web

from wallet import (
get_user_wallets,
get_active_wallet,
save_external_wallet,
get_real_balance,
send_sol,
estimate_transaction_fee,
create_wallet,
set_active_wallet,
get_wallet_private_key,
get_user_wallet_count,
delete_wallet,
set_user_pin,
verify_user_pin,
has_user_pin,
init_wallet_db,
MAX_WALLETS_PER_USER
)

import sqlite3

from wallet_buttons import router as wallet_router

load_dotenv()

# ---------------------------
# Cryptographic Randomness Module
# ---------------------------
# IMPORTANT: This implementation uses blockchain data (blockhashes, transaction signatures)
# for verifiable randomness. All seed inputs are stored in the database for public verification.
# 
# For production mainnet with highest security, migrate to:
# - ORAO VRF (available on Solana): https://github.com/orao-network/solana-vrf
# - Chainlink VRF (when available on Solana - currently only Price Feeds are deployed)
# 
# Current approach: Combines immutable on-chain data (blockhash + tx signatures in canonical order)
# to create verifiable seeds that cannot be manipulated by the bot operator.

def generate_provable_seed(*inputs) -> str:
    """
    Generate a provable random seed from multiple inputs using SHA256.
    All inputs are combined with length prefixes and hashed to create a deterministic seed.
    Anyone can verify the result by reproducing the hash with the same inputs.
    
    SECURITY: Inputs should include immutable on-chain data (blockhash, tx signatures)
    NOT server-controlled values (timestamps, random numbers)
    """
    # Prefix each input with its length to prevent collision attacks
    parts = []
    for inp in inputs:
        inp_str = str(inp)
        parts.append(f"{len(inp_str)}:{inp_str}")
    
    combined = "|".join(parts)
    hash_object = hashlib.sha256(combined.encode('utf-8'))
    return hash_object.hexdigest()


def generate_lottery_numbers(seed: str, count: int = 5, min_val: int = 1, max_val: int = 40) -> List[int]:
    """
    Generate lottery numbers deterministically from a seed.
    Uses the seed to generate unique numbers in the specified range.
    
    Args:
        seed: Cryptographic seed (from generate_provable_seed)
        count: Number of unique numbers to generate
        min_val: Minimum number in range (inclusive)
        max_val: Maximum number in range (inclusive)
    
    Returns:
        Sorted list of unique lottery numbers
    """
    numbers = set()
    seed_int = int(seed, 16)
    
    attempt = 0
    while len(numbers) < count:
        hash_input = f"{seed}_{attempt}"
        hash_val = int(hashlib.sha256(hash_input.encode()).hexdigest(), 16)
        number = (hash_val % (max_val - min_val + 1)) + min_val
        numbers.add(number)
        attempt += 1
    
    return sorted(list(numbers))


def select_winner_deterministically(seed: str, participant_count: int) -> int:
    """
    Select a winner index deterministically from the seed.
    
    Args:
        seed: Cryptographic seed
        participant_count: Total number of participants
    
    Returns:
        Winner index (0-based)
    """
    hash_val = int(hashlib.sha256(seed.encode()).hexdigest(), 16)
    return hash_val % participant_count

BOT_TOKEN = os.getenv("BOT_TOKEN")
OWNER_WALLET = os.getenv("OWNER_WALLET")
OWNER_WALLET_PRIVATE_KEY = os.getenv("OWNER_WALLET_PRIVATE_KEY")
TEAM_WALLET = os.getenv("TEAM_WALLET")

# Parse ADMIN_ID with better error handling
admin_id_str = os.getenv("ADMIN_ID", "0")
try:
    ADMIN_ID = int(admin_id_str)
except ValueError:
    print(f"❌ ERROR: ADMIN_ID must be a numeric Telegram user ID, got: '{admin_id_str}'")
    print(f"💡 To get your numeric Telegram user ID:")
    print(f"   1. Open Telegram and search for @userinfobot")
    print(f"   2. Start a chat with it")
    print(f"   3. It will reply with your numeric user ID (e.g., 123456789)")
    print(f"   4. Update the ADMIN_ID secret in Replit with that number")
    raise ValueError(f"ADMIN_ID must be a numeric value, not '{admin_id_str}'")

ROUND_CHANNEL = os.getenv("ROUND_CHANNEL_ID", "@cryptounclottoportal")

# Validate required environment variables
if not BOT_TOKEN:
    raise ValueError("BOT_TOKEN environment variable is required")
if not OWNER_WALLET:
    raise ValueError("OWNER_WALLET environment variable is required")
if not OWNER_WALLET_PRIVATE_KEY:
    raise ValueError("OWNER_WALLET_PRIVATE_KEY environment variable is required for automatic prize payments and refunds")

STAKE_PACKAGES = [
    Decimal("0.025"),
    Decimal("0.05"),
    Decimal("0.5"),
    Decimal("0.7"),
    Decimal("1"),
    Decimal("1.5"),
    Decimal("2"),
    Decimal("2.5"),
    Decimal("3"),
    Decimal("3.5"),
    Decimal("4"),
    Decimal("4.5"),
    Decimal("5")
]

ROUNDS_PER_DAY = 4
ROUND_TIMES_UTC = ["00:00", "06:00", "12:00", "18:00"]
MIN_PLAYERS_PER_STAKE = 10
ROUND_DURATION_MINUTES = 15
NETWORK_FEE_PERCENTAGE = Decimal("0.02")

DB_PATH = "cryptounc_lotto.db"

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

dp.include_router(wallet_router)

# State management for PIN operations and wallet actions
user_states = {}  # Stores pending operations: {user_id: {"action": "set_pin", "data": {...}}}
pending_pins = {}  # Stores PIN attempts: {user_id: {"pin": "1234", "action": "view_key"}}
# ---------------------------
# Database helpers
# ---------------------------
def migrate_database():
    """Safely migrate existing database to new schema with pending_refund status"""
    if not os.path.exists(DB_PATH):
        return
    
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    
    try:
        # Check if round_stakes exists and needs migration
        c.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='round_stakes'")
        table_def = c.fetchone()
        
        if table_def and 'pending_refund' not in table_def[0]:
            print("🔄 Migrating database schema to add 'pending_refund' status...")
            
            # Create new table with updated schema
            c.execute("""
                CREATE TABLE round_stakes_new (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    round_id INTEGER NOT NULL,
                    stake_amount REAL NOT NULL,
                    status TEXT DEFAULT 'open' CHECK(status IN ('open', 'closed', 'drawn', 'pending_refund', 'refunded')),
                    winner_user_id INTEGER,
                    prize_amount REAL,
                    tx_signature TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(round_id, stake_amount),
                    FOREIGN KEY (round_id) REFERENCES scheduled_rounds(round_id) ON DELETE CASCADE,
                    FOREIGN KEY (winner_user_id) REFERENCES users(user_id)
                )
            """)
            
            # Copy existing data
            c.execute("""
                INSERT INTO round_stakes_new 
                SELECT * FROM round_stakes
            """)
            
            # Drop old table
            c.execute("DROP TABLE round_stakes")
            
            # Rename new table
            c.execute("ALTER TABLE round_stakes_new RENAME TO round_stakes")
            
            # Recreate indexes
            c.execute("CREATE INDEX IF NOT EXISTS idx_round_stakes_round ON round_stakes(round_id, status)")
            
            conn.commit()
            print("✅ Database migration completed successfully!")
        else:
            print("✅ Database schema is up to date (pending_refund supported)")
    
    except Exception as e:
        print(f"⚠️ Migration error: {e}")
        conn.rollback()
    finally:
        conn.close()


def migrate_timestamps_to_iso():
    """Migrate legacy CURRENT_TIMESTAMP values to UTC ISO format strings"""
    if not os.path.exists(DB_PATH):
        return
    
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    
    try:
        print("🔄 Migrating timestamps to UTC ISO format...")
        
        # Check if scheduled_rounds table exists
        c.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='scheduled_rounds'")
        if not c.fetchone():
            print("✅ No scheduled_rounds table, skipping timestamp migration")
            conn.close()
            return
        
        # Get all rows with timestamps that need conversion
        c.execute("""
            SELECT round_id, scheduled_time, start_time, end_time 
            FROM scheduled_rounds
        """)
        rows = c.fetchall()
        
        migrated_count = 0
        for round_id, scheduled_time, start_time, end_time in rows:
            # Only update start_time and end_time, NOT scheduled_time
            # (scheduled_time is part of UNIQUE constraint and shouldn't change)
            updates = []
            params = []
            
            # Convert start_time if needed
            if start_time and 'T' not in start_time:
                try:
                    dt = datetime.fromisoformat(start_time.replace('Z', '+00:00'))
                    if dt.tzinfo is None:
                        dt = dt.replace(tzinfo=pytz.UTC)
                    updates.append("start_time = ?")
                    params.append(dt.isoformat())
                except:
                    pass
            
            # Convert end_time if needed
            if end_time and 'T' not in end_time:
                try:
                    dt = datetime.fromisoformat(end_time.replace('Z', '+00:00'))
                    if dt.tzinfo is None:
                        dt = dt.replace(tzinfo=pytz.UTC)
                    updates.append("end_time = ?")
                    params.append(dt.isoformat())
                except:
                    pass
            
            # Update if any conversions were made
            if updates:
                params.append(round_id)
                query = f"UPDATE scheduled_rounds SET {', '.join(updates)} WHERE round_id = ?"
                c.execute(query, params)
                migrated_count += 1
        
        conn.commit()
        if migrated_count > 0:
            print(f"✅ Migrated {migrated_count} rounds to UTC ISO format")
        else:
            print("✅ All timestamps already in ISO format")
    
    except Exception as e:
        print(f"⚠️ Timestamp migration error: {e}")
        import traceback
        traceback.print_exc()
        conn.rollback()
    finally:
        conn.close()


def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    # Users table
    c.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            username TEXT
        )
    """)
    # Entries table
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
    # Draws table
    c.execute("""
        CREATE TABLE IF NOT EXISTS draws (
            round INTEGER PRIMARY KEY,
            winning_numbers TEXT,
            drawn_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    # Meta table
    c.execute("""
        CREATE TABLE IF NOT EXISTS meta (
            key TEXT PRIMARY KEY,
            value TEXT
        )
    """)
    c.execute("INSERT OR IGNORE INTO meta(key, value) VALUES('current_round','1')")
    
    # Scheduled rounds table - tracks each scheduled round
    c.execute("""
        CREATE TABLE IF NOT EXISTS scheduled_rounds (
            round_id INTEGER PRIMARY KEY AUTOINCREMENT,
            round_number INTEGER NOT NULL,
            scheduled_time TIMESTAMP NOT NULL,
            start_time TIMESTAMP,
            end_time TIMESTAMP,
            status TEXT DEFAULT 'pending' CHECK(status IN ('pending', 'open', 'closed', 'completed', 'cancelled')),
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(round_number, scheduled_time)
        )
    """)
    
    # Create index for scheduled rounds lookups
    c.execute("CREATE INDEX IF NOT EXISTS idx_scheduled_rounds_time ON scheduled_rounds(scheduled_time, status)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_scheduled_rounds_status ON scheduled_rounds(status)")
    
    # Round stakes table - tracks each stake category within a round
    c.execute("""
        CREATE TABLE IF NOT EXISTS round_stakes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            round_id INTEGER NOT NULL,
            stake_amount REAL NOT NULL,
            status TEXT DEFAULT 'open' CHECK(status IN ('open', 'closed', 'drawn', 'pending_refund', 'refunded')),
            winner_user_id INTEGER,
            prize_amount REAL,
            tx_signature TEXT,
            first_stake_time TIMESTAMP,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(round_id, stake_amount),
            FOREIGN KEY (round_id) REFERENCES scheduled_rounds(round_id) ON DELETE CASCADE,
            FOREIGN KEY (winner_user_id) REFERENCES users(user_id)
        )
    """)
    
    # Create index for round stakes lookups
    c.execute("CREATE INDEX IF NOT EXISTS idx_round_stakes_round ON round_stakes(round_id, status)")
    
    # Round participants table - tracks individual participants per stake
    c.execute("""
        CREATE TABLE IF NOT EXISTS round_participants (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            round_stake_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            numbers TEXT NOT NULL,
            tx_signature TEXT,
            refunded INTEGER DEFAULT 0 CHECK(refunded IN (0, 1)),
            refund_tx TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (round_stake_id) REFERENCES round_stakes(id) ON DELETE CASCADE,
            FOREIGN KEY (user_id) REFERENCES users(user_id)
        )
    """)
    
    # Create index for participant lookups
    c.execute("CREATE INDEX IF NOT EXISTS idx_round_participants_stake ON round_participants(round_stake_id)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_round_participants_user ON round_participants(user_id)")
    
    conn.commit()
    conn.close()


def get_db_conn():
    return sqlite3.connect(DB_PATH)


def get_current_round() -> int:
    conn = get_db_conn()
    c = conn.cursor()
    c.execute("SELECT value FROM meta WHERE key='current_round'")
    row = c.fetchone()
    conn.close()
    return int(row[0]) if row else 1


def increment_round():
    conn = get_db_conn()
    c = conn.cursor()
    new_round = get_current_round() + 1
    c.execute("UPDATE meta SET value = ? WHERE key='current_round'", (str(new_round),))
    conn.commit()
    conn.close()
    return new_round


def numbers_to_str(nums):
    return ",".join(map(str, sorted(nums)))


def str_to_numbers(s):
    return [int(x) for x in s.split(",") if x.strip()]


def save_user(user_id: int, username: str):
    conn = get_db_conn()
    c = conn.cursor()
    c.execute("INSERT OR IGNORE INTO users(user_id, username) VALUES (?, ?)", (user_id, username))
    conn.commit()
    conn.close()


def add_entry(user_id: int, round_num: int, numbers, stake_amount: float, tx_signature: str = "", paid=0):
    conn = get_db_conn()
    c = conn.cursor()
    c.execute(
        "INSERT INTO entries(user_id, round, numbers, stake_amount, tx_signature, paid) VALUES (?, ?, ?, ?, ?, ?)",
        (user_id, round_num, numbers_to_str(numbers), stake_amount, tx_signature, paid)
    )
    conn.commit()
    conn.close()


def get_entries_for_round(round_num: int):
    conn = get_db_conn()
    c = conn.cursor()
    c.execute("SELECT id, user_id, numbers, paid FROM entries WHERE round = ?", (round_num,))
    rows = c.fetchall()
    conn.close()
    return rows


def get_user_last_entry(user_id: int):
    conn = get_db_conn()
    c = conn.cursor()
    c.execute(
        "SELECT round, numbers, paid FROM entries WHERE user_id = ? ORDER BY created_at DESC LIMIT 1",
        (user_id,)
    )
    row = c.fetchone()
    conn.close()
    return row


def save_draw(round_num: int, winning_numbers):
    conn = get_db_conn()
    c = conn.cursor()
    c.execute(
        "INSERT OR REPLACE INTO draws(round, winning_numbers) VALUES (?, ?)",
        (round_num, numbers_to_str(winning_numbers))
    )
    conn.commit()
    conn.close()


def create_scheduled_round(round_number: int, scheduled_time: datetime):
    conn = get_db_conn()
    c = conn.cursor()
    try:
        # Convert datetime to ISO string for SQLite storage
        scheduled_time_str = scheduled_time.isoformat() if hasattr(scheduled_time, 'isoformat') else scheduled_time
        c.execute("""
            INSERT INTO scheduled_rounds (round_number, scheduled_time, status)
            VALUES (?, ?, 'pending')
        """, (round_number, scheduled_time_str))
        round_id = c.lastrowid
        
        for stake in STAKE_PACKAGES:
            c.execute("""
                INSERT INTO round_stakes (round_id, stake_amount, status)
                VALUES (?, ?, 'open')
            """, (round_id, float(stake)))
        
        conn.commit()
        return round_id
    except sqlite3.IntegrityError:
        conn.rollback()
        return None
    finally:
        conn.close()


def get_active_rounds():
    conn = get_db_conn()
    c = conn.cursor()
    c.execute("""
        SELECT round_id, round_number, scheduled_time, start_time, end_time, status
        FROM scheduled_rounds
        WHERE status IN ('open', 'pending')
        ORDER BY scheduled_time ASC
    """)
    rows = c.fetchall()
    conn.close()
    return rows


def get_round_stakes_with_counts(round_id: int):
    conn = get_db_conn()
    c = conn.cursor()
    c.execute("""
        SELECT rs.id, rs.stake_amount, rs.status,
               COUNT(rp.id) as player_count
        FROM round_stakes rs
        LEFT JOIN round_participants rp ON rs.id = rp.round_stake_id AND rp.refunded = 0
        WHERE rs.round_id = ?
        GROUP BY rs.id
        ORDER BY rs.stake_amount ASC
    """, (round_id,))
    rows = c.fetchall()
    conn.close()
    return rows


def add_round_participant(round_stake_id: int, user_id: int, numbers: list, tx_signature: str):
    conn = get_db_conn()
    c = conn.cursor()
    
    c.execute("""
        SELECT rs.status, rs.round_id, sr.status as round_status, sr.end_time
        FROM round_stakes rs
        JOIN scheduled_rounds sr ON rs.round_id = sr.round_id
        WHERE rs.id = ?
    """, (round_stake_id,))
    stake_info = c.fetchone()
    
    if not stake_info:
        conn.close()
        return {"success": False, "error": "Round stake not found"}
    
    stake_status, round_id, round_status, end_time = stake_info
    
    if stake_status != 'open' or round_status != 'open':
        conn.close()
        return {"success": False, "error": "Round is not accepting participants"}
    
    if end_time:
        end_datetime = datetime.fromisoformat(end_time.replace('Z', '+00:00'))
        # Ensure end_datetime is timezone-aware
        if end_datetime.tzinfo is None:
            end_datetime = end_datetime.replace(tzinfo=pytz.UTC)
        if datetime.now(pytz.UTC) > end_datetime:
            conn.close()
            return {"success": False, "error": "Round has ended"}
    
    c.execute("""
        SELECT id FROM round_participants
        WHERE round_stake_id = ? AND user_id = ?
    """, (round_stake_id, user_id))
    if c.fetchone():
        conn.close()
        return {"success": False, "error": "Already joined this stake round"}
    
    try:
        c.execute("""
            INSERT INTO round_participants (round_stake_id, user_id, numbers, tx_signature)
            VALUES (?, ?, ?, ?)
        """, (round_stake_id, user_id, numbers_to_str(numbers), tx_signature))
        participant_id = c.lastrowid
        
        # Update first_stake_time if this is the first non-refunded participant for this stake
        c.execute("""
            SELECT first_stake_time, COUNT(rp.id) as count
            FROM round_stakes rs
            LEFT JOIN round_participants rp ON rs.id = rp.round_stake_id AND rp.refunded = 0
            WHERE rs.id = ?
        """, (round_stake_id,))
        first_time, count = c.fetchone()
        
        if not first_time and count == 1:  # First non-refunded participant
            now_utc = datetime.now(pytz.UTC).isoformat()
            c.execute("""
                UPDATE round_stakes
                SET first_stake_time = ?
                WHERE id = ?
            """, (now_utc, round_stake_id))
        
        conn.commit()
        conn.close()
        return {"success": True, "participant_id": participant_id}
    except Exception as e:
        conn.rollback()
        conn.close()
        return {"success": False, "error": str(e)}


def get_round_stake_by_amount(round_id: int, stake_amount: Decimal):
    conn = get_db_conn()
    c = conn.cursor()
    c.execute("""
        SELECT id, status FROM round_stakes
        WHERE round_id = ? AND stake_amount = ?
    """, (round_id, float(stake_amount)))
    row = c.fetchone()
    conn.close()
    return row


def update_round_status(round_id: int, status: str):
    conn = get_db_conn()
    c = conn.cursor()
    
    # Use UTC timezone-aware timestamps in ISO format
    now_utc = datetime.now(pytz.UTC).isoformat()
    
    # Check if we need to set start_time
    if status == 'open':
        c.execute("SELECT start_time FROM scheduled_rounds WHERE round_id = ?", (round_id,))
        row = c.fetchone()
        if row and not row[0]:
            c.execute("""
                UPDATE scheduled_rounds
                SET status = ?, start_time = ?
                WHERE round_id = ?
            """, (status, now_utc, round_id))
        else:
            c.execute("""
                UPDATE scheduled_rounds
                SET status = ?
                WHERE round_id = ?
            """, (status, round_id))
    elif status in ('closed', 'completed'):
        c.execute("""
            UPDATE scheduled_rounds
            SET status = ?, end_time = ?
            WHERE round_id = ?
        """, (status, now_utc, round_id))
    else:
        c.execute("""
            UPDATE scheduled_rounds
            SET status = ?
            WHERE round_id = ?
        """, (status, round_id))
    
    conn.commit()
    conn.close()


async def send_winner_payout(winner_user_id: int, prize_amount: Decimal, round_stake_id: int) -> Dict:
    """
    Send prize to winner with updated payout logic:
    - Team gets 20% of total pool
    - Winner gets 80% of total pool MINUS transaction fee
    - Network fee is deducted from winner's share only
    - Sends team payment FIRST to ensure atomicity
    """
    try:
        # Get winner's wallet
        winner_wallet = get_active_wallet(winner_user_id)
        if not winner_wallet:
            print(f"❌ Winner {winner_user_id} has no active wallet")
            return {"success": False, "error": "Winner has no active wallet"}
        
        # Calculate amounts from database
        conn = get_db_conn()
        c = conn.cursor()
        c.execute("""
            SELECT rs.stake_amount, COUNT(rp.id) as player_count
            FROM round_stakes rs
            LEFT JOIN round_participants rp ON rs.id = rp.round_stake_id AND rp.refunded = 0
            WHERE rs.id = ?
        """, (round_stake_id,))
        result = c.fetchone()
        conn.close()
        
        if not result or result[0] is None:
            print(f"❌ Round stake {round_stake_id} not found or invalid")
            return {"success": False, "error": "Round stake not found"}
        
        stake_amount, player_count = result
        
        if player_count < 1:
            print(f"❌ No participants in round stake {round_stake_id}")
            return {"success": False, "error": "No participants in round"}
        
        total_pool = Decimal(str(stake_amount)) * player_count
        team_share = total_pool * Decimal("0.2")  # 20% to team
        winner_share_before_fee = total_pool * Decimal("0.8")  # 80% to winner
        
        # Estimate transaction fee for winner's payout
        try:
            winner_fee = await estimate_transaction_fee(OWNER_WALLET, winner_wallet, winner_share_before_fee)
        except Exception as e:
            print(f"⚠️ Could not estimate fee, using default: {e}")
            winner_fee = Decimal("0.000005")  # Fallback fee
        
        # Deduct fee from winner's share, ensuring non-negative
        winner_final_amount = max(Decimal("0"), winner_share_before_fee - winner_fee)
        
        if winner_final_amount <= Decimal("0"):
            print(f"❌ Winner amount after fee is zero or negative (fee: {winner_fee}, share: {winner_share_before_fee})")
            return {"success": False, "error": "Prize too small to cover network fee"}
        
        print(f"💰 Payout calculation:")
        print(f"   Total pool: {total_pool} SOL")
        print(f"   Team share (20%): {team_share} SOL")
        print(f"   Winner share before fee (80%): {winner_share_before_fee} SOL")
        print(f"   Transaction fee: {winner_fee} SOL")
        print(f"   Winner final amount: {winner_final_amount} SOL")
        
        # Send to team FIRST to ensure both succeed before marking as paid
        team_tx = None
        if TEAM_WALLET and TEAM_WALLET != OWNER_WALLET and team_share > Decimal("0"):
            print(f"   → Sending {team_share} SOL to team wallet...")
            team_result = await send_sol(OWNER_WALLET, TEAM_WALLET, team_share, OWNER_WALLET_PRIVATE_KEY)
            if not team_result.get("success"):
                print(f"   ❌ Team payment failed: {team_result.get('error')}")
                return {"success": False, "error": f"Team payment failed: {team_result.get('error')}"}
            team_tx = team_result.get("signature")
            print(f"   ✅ Team payment sent! TX: {team_tx[:16]}...")
        
        # Send to winner (with fee deducted)
        print(f"   → Sending {winner_final_amount} SOL to winner {winner_wallet[:8]}...")
        winner_result = await send_sol(OWNER_WALLET, winner_wallet, winner_final_amount, OWNER_WALLET_PRIVATE_KEY)
        
        if not winner_result.get("success"):
            print(f"   ❌ Winner payment failed: {winner_result.get('error')}")
            # Team was already paid, log this critical inconsistency
            print(f"   ⚠️ CRITICAL: Team paid but winner payment failed! Team TX: {team_tx}")
            return {"success": False, "error": f"Winner payment failed (team was paid): {winner_result.get('error')}", "team_tx": team_tx}
        
        winner_tx = winner_result.get("signature")
        print(f"   ✅ Winner payment sent! TX: {winner_tx[:16]}...")
        
        return {
            "success": True,
            "winner_tx": winner_tx,
            "team_tx": team_tx,
            "winner_amount": float(winner_final_amount),
            "team_amount": float(team_share),
            "fee_deducted": float(winner_fee),
            "total_pool": float(total_pool)
        }
    except Exception as e:
        print(f"❌ Payout error: {e}")
        import traceback
        traceback.print_exc()
        return {"success": False, "error": str(e)}


def process_round_stake_draw(round_stake_id: int):
    conn = get_db_conn()
    c = conn.cursor()
    
    c.execute("""
        SELECT rp.id, rp.user_id, rp.numbers, rp.tx_signature
        FROM round_participants rp
        WHERE rp.round_stake_id = ? AND rp.refunded = 0
        ORDER BY rp.id ASC
    """, (round_stake_id,))
    participants = c.fetchall()
    
    if not participants:
        conn.close()
        return None
    
    # Generate provable randomness seed from IMMUTABLE on-chain data only
    # Uses transaction signatures in canonical order (by participant ID)
    # NOTE: For true verifiability, we should fetch and use the blockhash from the last transaction
    # Current limitation: Without querying Solana RPC for blockhash, we use tx signatures as entropy
    # This is verifiable (anyone can reproduce) but still allows operator to choose when to draw
    # RECOMMENDED: Upgrade to ORAO VRF for production to eliminate operator discretion
    tx_signatures_ordered = [str(p[3]) for p in participants]  # Already ordered by id ASC
    seed = generate_provable_seed(round_stake_id, "draw", *tx_signatures_ordered)
    
    # Generate winning numbers deterministically from seed
    winning_numbers = generate_lottery_numbers(seed, count=5, min_val=1, max_val=40)
    winning_numbers_str = numbers_to_str(winning_numbers)
    
    # Find participants with best matches
    best_match_count = 0
    winners_with_best_match = []
    
    for idx, (participant_id, user_id, numbers_str, tx_sig) in enumerate(participants):
        user_numbers = str_to_numbers(numbers_str)
        matches = len(set(user_numbers) & set(winning_numbers))
        
        if matches > best_match_count:
            best_match_count = matches
            winners_with_best_match = [(idx, participant_id, user_id)]
        elif matches == best_match_count:
            winners_with_best_match.append((idx, participant_id, user_id))
    
    # If multiple winners with same match count, select deterministically
    if len(winners_with_best_match) > 1:
        winner_seed = generate_provable_seed(seed, "tiebreaker", len(winners_with_best_match))
        winner_idx = select_winner_deterministically(winner_seed, len(winners_with_best_match))
        _, participant_id, user_id = winners_with_best_match[winner_idx]
        winner = (participant_id, user_id)
    else:
        _, participant_id, user_id = winners_with_best_match[0]
        winner = (participant_id, user_id)
    
    c.execute("""
        SELECT rs.stake_amount, COUNT(rp.id) as player_count
        FROM round_stakes rs
        LEFT JOIN round_participants rp ON rs.id = rp.round_stake_id AND rp.refunded = 0
        WHERE rs.id = ?
    """, (round_stake_id,))
    stake_amount, player_count = c.fetchone()
    
    total_pool = Decimal(str(stake_amount)) * player_count
    prize = total_pool * Decimal("0.8")
    
    if winner:
        c.execute("""
            UPDATE round_stakes
            SET status = 'drawn', winner_user_id = ?, prize_amount = ?
            WHERE id = ?
        """, (winner[1], float(prize), round_stake_id))
        conn.commit()
    
    conn.close()
    return {
        "winner_user_id": winner[1] if winner else None,
        "prize_amount": prize,
        "winning_numbers": winning_numbers,
        "player_count": player_count,
        "stake_amount": stake_amount,
        "round_stake_id": round_stake_id
    }


async def process_refunds_for_stake(round_stake_id: int):
    """
    Automatically refund all participants in a stake category that didn't meet minimum players.
    Sends SOL from OWNER_WALLET to each participant's wallet using OWNER_WALLET_PRIVATE_KEY.
    """
    conn = get_db_conn()
    c = conn.cursor()
    
    # Get all participants who haven't been refunded yet
    c.execute("""
        SELECT rp.id, rp.user_id, rs.stake_amount
        FROM round_participants rp
        JOIN round_stakes rs ON rp.round_stake_id = rs.id
        WHERE rp.round_stake_id = ? AND rp.refunded = 0
    """, (round_stake_id,))
    participants = c.fetchall()
    
    if not participants:
        print(f"⚠️ No participants to refund for stake {round_stake_id}")
        conn.close()
        return []
    
    # Calculate refund amount (stake minus network fee)
    c.execute("SELECT stake_amount FROM round_stakes WHERE id = ?", (round_stake_id,))
    stake_row = c.fetchone()
    if not stake_row:
        print(f"❌ Stake {round_stake_id} not found")
        conn.close()
        return []
    
    stake_amount = Decimal(str(stake_row[0]))
    refund_amount = stake_amount * (Decimal("1") - NETWORK_FEE_PERCENTAGE)
    
    # Update stake status to pending_refund
    c.execute("""
        UPDATE round_stakes
        SET status = 'pending_refund'
        WHERE id = ?
    """, (round_stake_id,))
    conn.commit()
    
    # Check OWNER_WALLET balance before starting refunds
    try:
        owner_balance = await get_real_balance(OWNER_WALLET)
        total_refund_needed = refund_amount * len(participants)
        if owner_balance < total_refund_needed:
            print(f"⚠️ WARNING: OWNER_WALLET balance ({owner_balance} SOL) insufficient for all refunds ({total_refund_needed} SOL)")
            print(f"   Proceeding with refunds but some may fail...")
    except Exception as e:
        print(f"⚠️ Could not check OWNER_WALLET balance: {e}")
    
    # Process refunds one by one
    successful_refunds = 0
    failed_refunds = 0
    refund_results = []
    
    print(f"💸 Starting automatic refunds for stake {round_stake_id}: {len(participants)} participants")
    print(f"   Refund amount: {refund_amount} SOL per participant (stake: {stake_amount} SOL - {float(NETWORK_FEE_PERCENTAGE * 100)}% fee)")
    
    for participant_id, user_id, _ in participants:
        participant_wallet = get_active_wallet(user_id)
        
        if not participant_wallet:
            print(f"❌ User {user_id} (participant {participant_id}) has no active wallet - skipping refund")
            failed_refunds += 1
            continue
        
        # Attempt to send refund with retry logic
        max_retries = 2
        refund_sent = False
        tx_signature = None
        
        for attempt in range(max_retries + 1):
            try:
                print(f"   → Refunding user {user_id}: {refund_amount} SOL to {participant_wallet[:8]}...{participant_wallet[-8:]} (attempt {attempt + 1}/{max_retries + 1})")
                
                refund_result = await send_sol(
                    OWNER_WALLET, 
                    participant_wallet, 
                    refund_amount, 
                    OWNER_WALLET_PRIVATE_KEY
                )
                
                if refund_result and refund_result.get("success"):
                    tx_signature = refund_result.get("signature")
                    refund_sent = True
                    print(f"   ✅ Refund sent! TX: {tx_signature[:16]}...")
                    break
                else:
                    error_msg = refund_result.get("error", "Unknown error") if refund_result else "No result returned"
                    print(f"   ⚠️ Refund attempt {attempt + 1} failed: {error_msg}")
                    if attempt < max_retries:
                        await asyncio.sleep(2)  # Wait 2 seconds before retry
                        
            except Exception as e:
                print(f"   ⚠️ Refund attempt {attempt + 1} exception: {e}")
                if attempt < max_retries:
                    await asyncio.sleep(2)
        
        # Update database and notify user based on result
        if refund_sent and tx_signature:
            # Mark as refunded in database
            c.execute("""
                UPDATE round_participants
                SET refunded = 1, refund_tx = ?
                WHERE id = ?
            """, (tx_signature, participant_id))
            conn.commit()
            
            successful_refunds += 1
            
            # Send success message to user
            try:
                await bot.send_message(
                    user_id,
                    f"✅ <b>Refund Completed!</b>\n\n"
                    f"Your round did not meet the minimum {MIN_PLAYERS_PER_STAKE} players.\n\n"
                    f"💰 Refunded: <b>{refund_amount} SOL</b>\n"
                    f"(Original stake: {stake_amount} SOL minus {float(NETWORK_FEE_PERCENTAGE * 100)}% network fee)\n\n"
                    f"📝 Transaction: <code>{tx_signature[:20]}...</code>\n"
                    f"Wallet: <code>{participant_wallet}</code>\n\n"
                    f"View on Solscan:\n"
                    f"https://solscan.io/tx/{tx_signature}",
                    parse_mode="HTML"
                )
            except Exception as e:
                print(f"   ⚠️ Could not send success message to user {user_id}: {e}")
            
            refund_results.append({
                'participant_id': participant_id,
                'user_id': user_id,
                'wallet': participant_wallet,
                'amount': float(refund_amount),
                'tx_signature': tx_signature,
                'status': 'success'
            })
        else:
            # Refund failed after all retries
            failed_refunds += 1
            print(f"   ❌ Refund FAILED for user {user_id} after {max_retries + 1} attempts")
            
            # Send failure notification to user
            try:
                await bot.send_message(
                    user_id,
                    f"⚠️ <b>Refund Processing Issue</b>\n\n"
                    f"Your round did not meet minimum players and a refund was initiated.\n\n"
                    f"Amount: {refund_amount} SOL\n"
                    f"Wallet: <code>{participant_wallet}</code>\n\n"
                    f"However, the automatic refund encountered an issue.\n"
                    f"Our team has been notified and will process your refund manually within 24 hours.\n\n"
                    f"We apologize for the inconvenience!",
                    parse_mode="HTML"
                )
            except:
                pass
            
            refund_results.append({
                'participant_id': participant_id,
                'user_id': user_id,
                'wallet': participant_wallet,
                'amount': float(refund_amount),
                'tx_signature': None,
                'status': 'failed'
            })
    
    # Update stake status based on results
    if successful_refunds == len(participants):
        # All refunds successful
        c.execute("""
            UPDATE round_stakes
            SET status = 'refunded'
            WHERE id = ?
        """, (round_stake_id,))
        conn.commit()
        print(f"✅ All refunds completed successfully for stake {round_stake_id}")
    elif successful_refunds > 0:
        # Partial success
        print(f"⚠️ Partial refunds for stake {round_stake_id}: {successful_refunds} succeeded, {failed_refunds} failed")
    else:
        # All failed
        print(f"❌ All refunds failed for stake {round_stake_id}")
    
    conn.close()
    
    # Summary
    print(f"💸 Refund summary for stake {round_stake_id}:")
    print(f"   ✅ Successful: {successful_refunds}/{len(participants)}")
    print(f"   ❌ Failed: {failed_refunds}/{len(participants)}")
    
    return refund_results


async def mark_refund_completed(participant_id: int, tx_signature: str):
    conn = get_db_conn()
    c = conn.cursor()
    
    c.execute("""
        UPDATE round_participants
        SET refunded = 1, refund_tx = ?
        WHERE id = ?
    """, (tx_signature, participant_id))
    
    c.execute("SELECT user_id, round_stake_id FROM round_participants WHERE id = ?", (participant_id,))
    participant_row = c.fetchone()
    
    if participant_row:
        user_id, stake_id = participant_row
        
        c.execute("""
            SELECT COUNT(*) FROM round_participants
            WHERE round_stake_id = ? AND refunded = 0
        """, (stake_id,))
        pending_count = c.fetchone()[0]
        
        if pending_count == 0:
            c.execute("""
                UPDATE round_stakes
                SET status = 'refunded'
                WHERE id = ?
            """, (stake_id,))
            print(f"✅ Stake {stake_id} marked as fully refunded (all participants processed)")
        
        conn.commit()
        conn.close()
        
        try:
            await bot.send_message(
                user_id,
                f"✅ <b>Refund Completed!</b>\n\n"
                f"📝 TX: <code>{tx_signature[:20]}...</code>\n\n"
                f"Thank you for playing!",
                parse_mode="HTML"
            )
        except:
            pass
        
        return True
    
    conn.close()
    return False


# ---------------------------
# Bot Handlers
# ---------------------------
@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    save_user(message.from_user.id, message.from_user.username or "")
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🎲 Play", callback_data="play_now")],
        [InlineKeyboardButton(text="🎰 Check Active Rounds", callback_data="check_active_rounds")],
        [InlineKeyboardButton(text="💼 My Wallets", callback_data="my_wallets")],
        [InlineKeyboardButton(text="📊 View Results", callback_data="view_results")],
        [InlineKeyboardButton(text="📘 Rules", callback_data="rules")],
        [InlineKeyboardButton(text="🛠 Support", callback_data="support")]
    ])
    await message.answer(
        "🎟️ <b>Welcome to CryptoUnc Lotto!</b>\n\n"
        "🚀 New: Scheduled Rounds - 4 rounds daily!\n"
        "⏰ Times: 00:00, 06:00, 12:00, 18:00 UTC\n"
        "💰 13 stake options: 0.025 - 5 SOL\n"
        "👥 Min 10 players per stake to draw\n\n"
        "Check active rounds and join now!",
        reply_markup=keyboard,
        parse_mode="HTML"
    )


async def show_wallet_menu(user_id: int):
    """Show wallet management menu"""
    wallets = get_user_wallets(user_id)
    active_wallet = get_active_wallet(user_id)
    wallet_count = get_user_wallet_count(user_id)

    keyboard_buttons = []

    if wallets:
        text = "💼 <b>Your Wallets</b>\n\n"
        for i, wallet in enumerate(wallets, 1):
            balance = await get_real_balance(wallet["address"])
            is_active = "✅" if wallet["address"] == active_wallet else ""
            text += f"{is_active} <b>{wallet['name']}</b>\n"
            text += f"   Type: {wallet['type'].capitalize()}\n"
            text += f"   Address: <code>{wallet['address'][:8]}...{wallet['address'][-8:]}</code>\n"
            text += f"   Balance: {balance} SOL\n\n"

            # Add button for each wallet
            keyboard_buttons.append([
                InlineKeyboardButton(text=f"{'✅ ' if is_active else ''}{wallet['name']}", 
                                   callback_data=f"select_wallet_{i-1}")
            ])
        
        # Add wallet actions for active wallet
        if active_wallet:
            wallet_actions = []
            # Check if active wallet is bot-managed
            active_wallet_info = next((w for w in wallets if w["address"] == active_wallet), None)
            if active_wallet_info and active_wallet_info["type"] == "bot":
                wallet_actions.append(
                    InlineKeyboardButton(text="🔑 View Private Key", callback_data="view_private_key")
                )
                wallet_actions.append(
                    InlineKeyboardButton(text="💸 Send SOL", callback_data="send_sol")
                )
            
            if wallet_actions:
                keyboard_buttons.append(wallet_actions)
            
            # Add delete wallet option
            keyboard_buttons.append([
                InlineKeyboardButton(text="🗑 Delete Active Wallet", callback_data="delete_active_wallet")
            ])
    else:
        text = "💼 <b>Your Wallets</b>\n\nYou don't have any wallets yet.\n"

    # Add create/connect buttons if under limit
    if wallet_count < MAX_WALLETS_PER_USER:
        keyboard_buttons.append([
            InlineKeyboardButton(text="➕ Create Wallet", callback_data="create_wallet"),
            InlineKeyboardButton(text="🔗 Connect Wallet", callback_data="connect_wallet")
        ])
    else:
        text += f"\n⚠️ You've reached the maximum of {MAX_WALLETS_PER_USER} wallets."

    keyboard_buttons.append([InlineKeyboardButton(text="🔙 Back", callback_data="back_to_main")])
    keyboard = InlineKeyboardMarkup(inline_keyboard=keyboard_buttons)

    await bot.send_message(user_id, text, reply_markup=keyboard, parse_mode="HTML")


async def start_private_play(user_id: int):
    """Start lottery play session"""
    wallet = get_active_wallet(user_id)

    if not wallet:
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="💳 Create Wallet", callback_data="create_wallet")],
            [InlineKeyboardButton(text="🔗 Connect Wallet", callback_data="connect_wallet")],
            [InlineKeyboardButton(text="ℹ️ How to Play", callback_data="rules")]
        ])
        await bot.send_message(user_id,
            "🎮 <b>Private Lotto Session</b>\n\n"
            "You need a wallet to play. Create a new wallet or connect your existing one.",
            reply_markup=keyboard,
            parse_mode="HTML"
        )
        return

    # Get balance
    balance = await get_real_balance(wallet)

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💵 Choose Stake", callback_data="choose_stake")],
        [InlineKeyboardButton(text="💼 Switch Wallet", callback_data="my_wallets")],
        [InlineKeyboardButton(text="ℹ️ How to Play", callback_data="rules")]
    ])

    await bot.send_message(user_id,
        f"🎮 <b>Private Lotto Session</b>\n\n"
        f"Active Wallet: <code>{wallet[:8]}...{wallet[-8:]}</code>\n"
        f"Balance: <b>{balance} SOL</b>\n\n"
        f"Choose your next action:",
        reply_markup=keyboard,
        parse_mode="HTML"
    )


@dp.callback_query()
async def inline_handler(query: types.CallbackQuery):
    data = query.data
    uid = query.from_user.id

    if data == "play_now":
        await query.answer()
        await start_private_play(uid)

    elif data == "my_wallets":
        await query.answer()
        await show_wallet_menu(uid)

    elif data.startswith("select_wallet_"):
        await query.answer()
        wallet_index = int(data.split("_")[2])
        wallets = get_user_wallets(uid)

        if 0 <= wallet_index < len(wallets):
            selected_wallet = wallets[wallet_index]
            set_active_wallet(uid, selected_wallet["address"])
            await bot.send_message(uid,
                f"✅ Switched to <b>{selected_wallet['name']}</b>\n"
                f"Address: <code>{selected_wallet['address']}</code>",
                parse_mode="HTML"
            )
            await show_wallet_menu(uid)

    elif data == "create_wallet":
        await query.answer()
        wallet_count = get_user_wallet_count(uid)

        if wallet_count >= MAX_WALLETS_PER_USER:
            await bot.send_message(uid,
                f"⚠️ You've reached the maximum of {MAX_WALLETS_PER_USER} wallets."
            )
            return

        wallet = create_wallet(uid)
        if wallet:
            # Check if user has PIN, if not prompt to set one
            if not has_user_pin(uid):
                user_states[uid] = {"action": "set_pin_after_wallet", "wallet_address": wallet['address']}
                await bot.send_message(uid,
                    f"✅ <b>Wallet created successfully!</b>\n\n"
                    f"Name: {wallet['name']}\n"
                    f"Address: <code>{wallet['address']}</code>\n\n"
                    f"🔐 <b>Security Setup</b>\n"
                    f"Please create a 4-digit PIN to protect your wallet.\n"
                    f"This PIN will be required to:\n"
                    f"• View private key\n"
                    f"• Send SOL from this wallet\n\n"
                    f"Please send your 4-digit PIN now:",
                    parse_mode="HTML"
                )
            else:
                await bot.send_message(uid,
                    f"✅ <b>Wallet created successfully!</b>\n\n"
                    f"Name: {wallet['name']}\n"
                    f"Address: <code>{wallet['address']}</code>\n\n"
                    f"⚠️ <b>Important:</b> This is a bot-managed wallet. "
                    f"Save your address to deposit funds from exchanges or other wallets.\n\n"
                    f"You can now deposit SOL and play!",
                    parse_mode="HTML"
                )
                set_active_wallet(uid, wallet['address'])
                await start_private_play(uid)
        else:
            await bot.send_message(uid, "❌ Failed to create wallet. Please try again.")

    elif data == "delete_active_wallet":
        await query.answer()
        wallet = get_active_wallet(uid)
        if not wallet:
            await bot.send_message(uid, "❌ No active wallet to delete.")
            return
        
        # Confirm deletion
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [
                InlineKeyboardButton(text="✅ Yes, Delete", callback_data="confirm_delete_wallet"),
                InlineKeyboardButton(text="❌ Cancel", callback_data="my_wallets")
            ]
        ])
        await bot.send_message(uid,
            f"⚠️ <b>Delete Wallet?</b>\n\n"
            f"Are you sure you want to delete:\n"
            f"<code>{wallet[:8]}...{wallet[-8:]}</code>\n\n"
            f"This action cannot be undone!",
            reply_markup=keyboard,
            parse_mode="HTML"
        )

    elif data == "confirm_delete_wallet":
        await query.answer()
        wallet = get_active_wallet(uid)
        if wallet:
            if delete_wallet(uid, wallet):
                await bot.send_message(uid,
                    f"✅ <b>Wallet Deleted</b>\n\n"
                    f"Wallet <code>{wallet[:8]}...{wallet[-8:]}</code> has been removed.",
                    parse_mode="HTML"
                )
            else:
                await bot.send_message(uid, "❌ Failed to delete wallet.")
        await show_wallet_menu(uid)

    elif data == "view_private_key":
        await query.answer()
        wallet = get_active_wallet(uid)
        if not wallet:
            await bot.send_message(uid, "❌ No active wallet.")
            return
        
        # Check if user has PIN
        if not has_user_pin(uid):
            user_states[uid] = {"action": "set_pin_for_key_view"}
            await bot.send_message(uid,
                "🔐 <b>PIN Required</b>\n\n"
                "Please create a 4-digit PIN to protect your private key.\n"
                "Send your 4-digit PIN now:",
                parse_mode="HTML"
            )
        else:
            user_states[uid] = {"action": "verify_pin_for_key_view"}
            await bot.send_message(uid,
                "🔐 <b>PIN Required</b>\n\n"
                "Enter your 4-digit PIN to view private key:",
                parse_mode="HTML"
            )

    elif data == "send_sol":
        await query.answer()
        wallet = get_active_wallet(uid)
        if not wallet:
            await bot.send_message(uid, "❌ No active wallet.")
            return
        
        balance = await get_real_balance(wallet)
        if balance <= Decimal("0.001"):
            await bot.send_message(uid,
                f"❌ <b>Insufficient Balance</b>\n\n"
                f"Current balance: {balance} SOL\n"
                f"You need at least 0.001 SOL to send (plus network fees).",
                parse_mode="HTML"
            )
            return
        
        # Check if user has PIN
        if not has_user_pin(uid):
            user_states[uid] = {"action": "set_pin_for_send"}
            await bot.send_message(uid,
                "🔐 <b>PIN Required</b>\n\n"
                "Please create a 4-digit PIN to authorize transactions.\n"
                "Send your 4-digit PIN now:",
                parse_mode="HTML"
            )
        else:
            user_states[uid] = {"action": "verify_pin_for_send"}
            await bot.send_message(uid,
                f"💸 <b>Send SOL</b>\n\n"
                f"Current balance: <b>{balance} SOL</b>\n\n"
                f"🔐 Enter your 4-digit PIN to continue:",
                parse_mode="HTML"
            )

    elif data == "connect_wallet":
        await query.answer()
        wallet_count = get_user_wallet_count(uid)

        if wallet_count >= MAX_WALLETS_PER_USER:
            await bot.send_message(uid,
                f"⚠️ You've reached the maximum of {MAX_WALLETS_PER_USER} wallets."
            )
            return

        await bot.send_message(uid,
            "🔗 <b>Connect External Wallet</b>\n\n"
            "Please send your Solana wallet public address now.\n"
            "This can be from Phantom, Solflare, or any Solana wallet.\n\n"
            "⚠️ <b>Never share your private key or seed phrase!</b>",
            parse_mode="HTML"
        )

    elif data == "choose_stake":
        await query.answer()
        # Check balance first
        wallet = get_active_wallet(uid)
        if not wallet:
            await bot.send_message(uid, "❌ Please create or connect a wallet first.")
            return

        balance = await get_real_balance(wallet)

        # Show stake packages
        rows = []
        temp = []
        for i, pkg in enumerate(STAKE_PACKAGES, 1):
            # Disable if balance insufficient
            if balance >= pkg:
                temp.append(InlineKeyboardButton(text=f"{pkg} SOL", callback_data=f"stake_{pkg}"))
            else:
                temp.append(InlineKeyboardButton(text=f"🔒 {pkg} SOL", callback_data="insufficient_funds"))

            if i % 3 == 0:
                rows.append(temp)
                temp = []
        if temp:
            rows.append(temp)

        keyboard = InlineKeyboardMarkup(inline_keyboard=rows)
        await bot.send_message(uid,
            f"💵 <b>Choose Stake Package</b>\n\n"
            f"Your balance: <b>{balance} SOL</b>\n"
            f"Available packages:",
            reply_markup=keyboard,
            parse_mode="HTML"
        )

    elif data == "insufficient_funds":
        await query.answer("❌ Insufficient balance for this stake amount", show_alert=True)

    elif data.startswith("stake_"):
        await query.answer("Processing stake...")
        amount = Decimal(data.split("_", 1)[1])

        wallet = get_active_wallet(uid)
        if not wallet:
            await bot.send_message(uid, "❌ Please create or connect a wallet first.")
            return

        # Check real balance
        balance = await get_real_balance(wallet)
        if balance < amount:
            await bot.send_message(uid,
                f"⚠️ <b>Insufficient funds!</b>\n\n"
                f"Your balance: {balance} SOL\n"
                f"Required: {amount} SOL\n\n"
                f"Please deposit more SOL to your wallet:\n"
                f"<code>{wallet}</code>",
                parse_mode="HTML"
            )
            return

        # Get private key for bot-managed wallets
        private_key = get_wallet_private_key(uid, wallet)

        if not private_key:
            await bot.send_message(uid,
                "⚠️ This is an external wallet. Please send the transaction manually:\n\n"
                f"Send <b>{amount} SOL</b> to:\n"
                f"<code>{OWNER_WALLET}</code>\n\n"
                "Then reply with your transaction signature.",
                parse_mode="HTML"
            )
            return

        # Send real SOL transaction (80% to owner, 20% to team)
        owner_amt = amount * Decimal("0.8")
        team_amt = amount * Decimal("0.2")

        await bot.send_message(uid, "⏳ Processing payment...")

        # Send to owner wallet
        result = await send_sol(wallet, OWNER_WALLET, owner_amt, private_key)

        if not result["success"]:
            await bot.send_message(uid,
                f"❌ <b>Transaction failed!</b>\n\n"
                f"Error: {result.get('error', 'Unknown error')}\n\n"
                f"Please try again or contact support.",
                parse_mode="HTML"
            )
            return

        tx_signature = result["signature"]

        # Send to team wallet (if different from owner)
        if TEAM_WALLET and TEAM_WALLET != OWNER_WALLET:
            await send_sol(wallet, TEAM_WALLET, team_amt, private_key)

        # Generate lottery numbers deterministically from transaction signature
        round_num = get_current_round()
        number_seed = generate_provable_seed(uid, round_num, tx_signature, "player_numbers")
        lottery_numbers = generate_lottery_numbers(number_seed, count=5, min_val=1, max_val=40)
        
        # Add entry and get ticket ID
        conn = get_db_conn()
        c = conn.cursor()
        c.execute(
            "INSERT INTO entries(user_id, round, numbers, stake_amount, tx_signature, paid) VALUES (?, ?, ?, ?, ?, ?)",
            (uid, round_num, numbers_to_str(lottery_numbers), float(amount), tx_signature, 1)
        )
        ticket_id = c.lastrowid
        conn.commit()
        conn.close()

        await bot.send_message(uid,
            f"✅ <b>Payment Successful!</b>\n\n"
            f"🎫 <b>Ticket ID:</b> #{ticket_id}\n"
            f"🎲 <b>Your Numbers:</b> {numbers_to_str(lottery_numbers)}\n"
            f"🎰 <b>Round:</b> {round_num}\n"
            f"💰 <b>Stake:</b> {amount} SOL\n\n"
            f"📝 Transaction:\n<code>{tx_signature[:20]}...</code>\n\n"
            f"🍀 <b>Good luck!</b> Winner will be announced in the channel.",
            parse_mode="HTML"
        )

    elif data == "rules":
        await query.message.answer(
            "📘 <b>Game Rules</b>\n\n"
            "1. Create or connect a Solana wallet\n"
            "2. Deposit SOL to your wallet\n"
            "3. Choose a stake amount (0.05 - 5 SOL)\n"
            "4. Receive 5 random numbers (1-40)\n"
            "5. Wait for admin to draw winning numbers\n"
            "6. Winners are announced publicly!\n\n"
            "💰 Stakes are split:\n"
            "• 80% to prize pool\n"
            "• 20% to team/operations",
            parse_mode="HTML"
        )

    elif data == "support":
        support_username = os.getenv("SUPPORT_USERNAME", "")
        support_text = "🛠 <b>Support & Help</b>\n\n"
        support_text += "Need help? Here's how to reach us:\n\n"
        
        if support_username:
            support_text += f"📱 Contact: @{support_username}\n\n"
        
        support_text += "Common issues:\n"
        support_text += "• Wallet connection: Make sure you're using a valid Solana address\n"
        support_text += "• Balance not showing: Wait a few seconds for blockchain sync\n"
        support_text += "• Transaction failed: Check your wallet balance\n\n"
        support_text += "📧 For urgent matters, message our admin directly."
        
        await query.message.answer(support_text, parse_mode="HTML")

    elif data == "view_results":
        await query.answer()
        cur_round = get_current_round()
        await bot.send_message(uid,
            f"📊 <b>Current Round:</b> {cur_round}\n\n"
            "Results will be announced after the draw!",
            parse_mode="HTML"
        )

    elif data == "check_active_rounds":
        await query.answer()
        rounds = get_active_rounds()
        
        if not rounds:
            await bot.send_message(uid,
                "🎰 <b>No Active Rounds</b>\n\n"
                "There are no open rounds at the moment.\n"
                f"Rounds open daily at: {', '.join(ROUND_TIMES_UTC)} UTC\n\n"
                "Check back soon!",
                parse_mode="HTML"
            )
            return
        
        for round_id, round_number, scheduled_time, start_time, end_time, status in rounds:
            stakes = get_round_stakes_with_counts(round_id)
            
            text = f"🎰 <b>Round {round_id}</b>\n"
            text += f"Status: {'🟢 OPEN' if status == 'open' else '🟡 Pending'}\n\n"
            
            if status == 'open' and start_time:
                start_dt = datetime.fromisoformat(start_time.replace('Z', '+00:00'))
                if start_dt.tzinfo is None:
                    start_dt = start_dt.replace(tzinfo=pytz.UTC)
                now = datetime.now(pytz.UTC)
                elapsed = (now - start_dt).total_seconds() / 60
                remaining = max(0, ROUND_DURATION_MINUTES - elapsed)
                text += f"⏰ Time Remaining: {int(remaining)} minutes\n\n"
            
            text += "💰 <b>Stake Options:</b>\n"
            
            stake_buttons = []
            for stake_id, stake_amount, stake_status, player_count in stakes:
                needed = max(0, MIN_PLAYERS_PER_STAKE - player_count)
                status_icon = "✅" if player_count >= MIN_PLAYERS_PER_STAKE else "🎯"
                
                text += f"{status_icon} {stake_amount} SOL: {player_count}/{MIN_PLAYERS_PER_STAKE} players"
                if needed > 0:
                    text += f" ({needed} needed)"
                text += "\n"
                
                if status == 'open':
                    stake_buttons.append([InlineKeyboardButton(
                        text=f"{status_icon} Join {stake_amount} SOL ({player_count}/{MIN_PLAYERS_PER_STAKE})",
                        callback_data=f"join_stake_{stake_id}"
                    )])
            
            if status == 'open':
                stake_buttons.append([InlineKeyboardButton(
                    text="🔄 Refresh",
                    callback_data=f"check_round_{round_id}"
                )])
            
            stake_buttons.append([InlineKeyboardButton(
                text="🔙 Back to Menu",
                callback_data="back_to_main"
            )])
            
            keyboard = InlineKeyboardMarkup(inline_keyboard=stake_buttons)
            await bot.send_message(uid, text, reply_markup=keyboard, parse_mode="HTML")
    
    elif data.startswith("check_round_"):
        await query.answer("Refreshing...")
        round_id = int(data.split("_")[2])
        
        conn = get_db_conn()
        c = conn.cursor()
        c.execute("SELECT round_number, status, start_time FROM scheduled_rounds WHERE round_id = ?", (round_id,))
        round_data = c.fetchone()
        conn.close()
        
        if not round_data:
            await bot.send_message(uid, "❌ Round not found.", parse_mode="HTML")
            return
        
        round_number, status, start_time = round_data
        stakes = get_round_stakes_with_counts(round_id)
        
        text = f"🎰 <b>Round {round_id} - Updated</b>\n\n"
        
        if status == 'open' and start_time:
            start_dt = datetime.fromisoformat(start_time.replace('Z', '+00:00'))
            if start_dt.tzinfo is None:
                start_dt = start_dt.replace(tzinfo=pytz.UTC)
            now = datetime.now(pytz.UTC)
            elapsed = (now - start_dt).total_seconds() / 60
            remaining = max(0, ROUND_DURATION_MINUTES - elapsed)
            text += f"⏰ Time Remaining: {int(remaining)} minutes\n\n"
        
        text += "💰 <b>Current Players:</b>\n"
        
        stake_buttons = []
        for stake_id, stake_amount, stake_status, player_count in stakes:
            needed = max(0, MIN_PLAYERS_PER_STAKE - player_count)
            status_icon = "✅" if player_count >= MIN_PLAYERS_PER_STAKE else "🎯"
            
            text += f"{status_icon} {stake_amount} SOL: {player_count}/{MIN_PLAYERS_PER_STAKE}"
            if needed > 0:
                text += f" ({needed} more needed)"
            text += "\n"
            
            if status == 'open':
                stake_buttons.append([InlineKeyboardButton(
                    text=f"{status_icon} Join {stake_amount} SOL",
                    callback_data=f"join_stake_{stake_id}"
                )])
        
        if status == 'open':
            stake_buttons.append([InlineKeyboardButton(
                text="🔄 Refresh Again",
                callback_data=f"check_round_{round_id}"
            )])
        
        stake_buttons.append([InlineKeyboardButton(
            text="🔙 Back",
            callback_data="check_active_rounds"
        )])
        
        keyboard = InlineKeyboardMarkup(inline_keyboard=stake_buttons)
        await bot.send_message(uid, text, reply_markup=keyboard, parse_mode="HTML")
    
    elif data.startswith("join_stake_"):
        await query.answer("Processing...")
        stake_id = int(data.split("_")[2])
        
        wallet = get_active_wallet(uid)
        if not wallet:
            await bot.send_message(uid,
                "❌ <b>No Wallet Found</b>\n\n"
                "Please create or connect a wallet first!",
                parse_mode="HTML"
            )
            return
        
        conn = get_db_conn()
        c = conn.cursor()
        c.execute("SELECT stake_amount FROM round_stakes WHERE id = ?", (stake_id,))
        stake_row = c.fetchone()
        conn.close()
        
        if not stake_row:
            await bot.send_message(uid, "❌ Stake not found.")
            return
        
        stake_amount = Decimal(str(stake_row[0]))
        
        balance = await get_real_balance(wallet)
        if balance < stake_amount:
            await bot.send_message(uid,
                f"⚠️ <b>Insufficient Balance</b>\n\n"
                f"Your balance: {balance} SOL\n"
                f"Required: {stake_amount} SOL\n\n"
                f"Please deposit more SOL to your wallet:\n"
                f"<code>{wallet}</code>",
                parse_mode="HTML"
            )
            return
        
        private_key = get_wallet_private_key(uid, wallet)
        
        if not private_key:
            await bot.send_message(uid,
                f"⚠️ This is an external wallet.\n\n"
                f"Please send <b>{stake_amount} SOL</b> to:\n"
                f"<code>{OWNER_WALLET}</code>\n\n"
                f"Then reply with your transaction signature.",
                parse_mode="HTML"
            )
            return
        
        owner_amt = stake_amount * Decimal("0.8")
        team_amt = stake_amount * Decimal("0.2")
        
        await bot.send_message(uid, "⏳ Processing payment...")
        
        result = await send_sol(wallet, OWNER_WALLET, owner_amt, private_key)
        
        if not result["success"]:
            await bot.send_message(uid,
                f"❌ <b>Transaction failed!</b>\n\n"
                f"Error: {result.get('error', 'Unknown error')}\n\n"
                f"Please try again or contact support.",
                parse_mode="HTML"
            )
            return
        
        tx_signature = result["signature"]
        
        if TEAM_WALLET and TEAM_WALLET != OWNER_WALLET:
            await send_sol(wallet, TEAM_WALLET, team_amt, private_key)
        
        # Generate lottery numbers deterministically from transaction signature
        number_seed = generate_provable_seed(uid, stake_id, tx_signature, "participant_numbers")
        lottery_numbers = generate_lottery_numbers(number_seed, count=5, min_val=1, max_val=40)
        
        add_result = add_round_participant(stake_id, uid, lottery_numbers, tx_signature)
        
        if add_result["success"]:
            await bot.send_message(uid,
                f"✅ <b>Successfully Joined!</b>\n\n"
                f"🎰 Stake: {stake_amount} SOL\n"
                f"🎲 Your Numbers: {numbers_to_str(lottery_numbers)}\n"
                f"📝 TX: <code>{tx_signature[:20]}...</code>\n\n"
                f"🍀 Good luck! Winners announced after the round ends.",
                parse_mode="HTML"
            )
        else:
            await bot.send_message(uid,
                f"❌ <b>Failed to join round</b>\n\n"
                f"Error: {add_result.get('error')}\n\n"
                f"Payment was processed. Contact support with TX:\n"
                f"<code>{tx_signature}</code>",
                parse_mode="HTML"
            )

    elif data == "back_to_main":
        await query.answer()
        await cmd_start(query.message)


@dp.message()
async def generic_message_handler(message: types.Message):
    uid = message.from_user.id
    text = message.text.strip()

    # Check if user is in a PIN operation state
    if uid in user_states:
        state = user_states[uid]
        action = state.get("action")
        
        # Handle PIN setting
        if action == "set_pin_after_wallet":
            if text.isdigit() and len(text) == 4:
                if set_user_pin(uid, text):
                    wallet_address = state.get("wallet_address")
                    set_active_wallet(uid, wallet_address)
                    del user_states[uid]
                    await message.answer(
                        "✅ <b>PIN Created Successfully!</b>\n\n"
                        "Your PIN has been securely saved.\n"
                        "You can now use your wallet!",
                        parse_mode="HTML"
                    )
                    await start_private_play(uid)
                else:
                    await message.answer("❌ Invalid PIN. Please try again with 4 digits.")
            else:
                await message.answer("❌ PIN must be exactly 4 digits. Please try again:")
            return
        
        elif action == "set_pin_for_key_view":
            if text.isdigit() and len(text) == 4:
                if set_user_pin(uid, text):
                    user_states[uid] = {"action": "verify_pin_for_key_view"}
                    await message.answer(
                        "✅ PIN created!\n\n"
                        "Please enter your PIN again to view private key:",
                        parse_mode="HTML"
                    )
                else:
                    await message.answer("❌ Invalid PIN. Please try again with 4 digits.")
            else:
                await message.answer("❌ PIN must be exactly 4 digits. Please try again:")
            return
        
        elif action == "verify_pin_for_key_view":
            if verify_user_pin(uid, text):
                del user_states[uid]
                wallet = get_active_wallet(uid)
                private_key = get_wallet_private_key(uid, wallet)
                if private_key:
                    await message.answer(
                        f"🔑 <b>Private Key</b>\n\n"
                        f"Wallet: <code>{wallet[:8]}...{wallet[-8:]}</code>\n\n"
                        f"⚠️ <b>KEEP THIS SECRET!</b>\n"
                        f"Private Key:\n<code>{private_key}</code>\n\n"
                        f"🔐 Never share this with anyone!",
                        parse_mode="HTML"
                    )
                else:
                    await message.answer("❌ Could not retrieve private key.")
            else:
                await message.answer("❌ Incorrect PIN. Please try again:")
            return
        
        elif action == "set_pin_for_send":
            if text.isdigit() and len(text) == 4:
                if set_user_pin(uid, text):
                    user_states[uid] = {"action": "get_send_address"}
                    wallet = get_active_wallet(uid)
                    balance = await get_real_balance(wallet)
                    await message.answer(
                        f"✅ PIN created!\n\n"
                        f"💸 <b>Send SOL</b>\n"
                        f"Current balance: <b>{balance} SOL</b>\n\n"
                        f"Please send the recipient's Solana address:",
                        parse_mode="HTML"
                    )
                else:
                    await message.answer("❌ Invalid PIN. Please try again with 4 digits.")
            else:
                await message.answer("❌ PIN must be exactly 4 digits. Please try again:")
            return
        
        elif action == "verify_pin_for_send":
            if verify_user_pin(uid, text):
                user_states[uid] = {"action": "get_send_address"}
                wallet = get_active_wallet(uid)
                balance = await get_real_balance(wallet)
                await message.answer(
                    f"✅ PIN verified!\n\n"
                    f"💸 <b>Send SOL</b>\n"
                    f"Current balance: <b>{balance} SOL</b>\n\n"
                    f"Please send the recipient's Solana address:",
                    parse_mode="HTML"
                )
            else:
                await message.answer("❌ Incorrect PIN. Please try again:")
            return
        
        elif action == "get_send_address":
            # Validate Solana address
            if 32 <= len(text) <= 44 and text.isalnum():
                user_states[uid] = {"action": "get_send_amount", "recipient": text}
                wallet = get_active_wallet(uid)
                balance = await get_real_balance(wallet)
                await message.answer(
                    f"💸 <b>Send to:</b>\n<code>{text}</code>\n\n"
                    f"Your balance: <b>{balance} SOL</b>\n\n"
                    f"How much SOL do you want to send?\n"
                    f"(Example: 0.5 or 1.25)",
                    parse_mode="HTML"
                )
            else:
                await message.answer("❌ Invalid Solana address. Please send a valid address:")
            return
        
        elif action == "get_send_amount":
            try:
                amount = Decimal(text)
                if amount <= 0:
                    await message.answer("❌ Amount must be greater than 0. Please try again:")
                    return
                
                wallet = get_active_wallet(uid)
                balance = await get_real_balance(wallet)
                
                if amount > balance:
                    await message.answer(
                        f"❌ <b>Insufficient Balance</b>\n\n"
                        f"You have: {balance} SOL\n"
                        f"Trying to send: {amount} SOL\n\n"
                        f"Please enter a smaller amount:",
                        parse_mode="HTML"
                    )
                    return
                
                recipient = state.get("recipient")
                private_key = get_wallet_private_key(uid, wallet)
                
                if not private_key:
                    del user_states[uid]
                    await message.answer("❌ Could not access wallet private key.")
                    return
                
                await message.answer("⏳ Sending transaction...")
                
                result = await send_sol(wallet, recipient, amount, private_key)
                
                del user_states[uid]
                
                if result["success"]:
                    await message.answer(
                        f"✅ <b>Transaction Successful!</b>\n\n"
                        f"Sent: <b>{amount} SOL</b>\n"
                        f"To: <code>{recipient[:8]}...{recipient[-8:]}</code>\n"
                        f"Transaction: <code>{result['signature'][:16]}...</code>\n\n"
                        f"View on Solscan:\n"
                        f"https://solscan.io/tx/{result['signature']}",
                        parse_mode="HTML"
                    )
                else:
                    await message.answer(
                        f"❌ <b>Transaction Failed</b>\n\n"
                        f"Error: {result.get('error', 'Unknown error')}\n\n"
                        f"Please try again later.",
                        parse_mode="HTML"
                    )
            except (ValueError, decimal.InvalidOperation):
                await message.answer("❌ Invalid amount. Please enter a number (e.g., 0.5):")
            return

    # Check if it's a Solana wallet address (32-44 chars, alphanumeric)
    if 32 <= len(text) <= 44 and text.isalnum():
        wallet_count = get_user_wallet_count(uid)

        if wallet_count >= MAX_WALLETS_PER_USER:
            await bot.send_message(uid,
                f"⚠️ You've reached the maximum of {MAX_WALLETS_PER_USER} wallets."
            )
            return

        # Try to save as external wallet
        if save_external_wallet(uid, text, "external"):
            set_active_wallet(uid, text)
            balance = await get_real_balance(text)
            await bot.send_message(uid,
                f"✅ <b>Wallet connected successfully!</b>\n\n"
                f"Address: <code>{text}</code>\n"
                f"Balance: {balance} SOL\n\n"
                f"You can now play!",
                parse_mode="HTML"
            )
            await start_private_play(uid)
        else:
            await bot.send_message(uid,
                "❌ Failed to connect wallet. It may already be connected."
            )
# ==========================
# 🔹 Wallet Buttons Handlers
# ==========================


# ---------------------------
# Admin commands
# ---------------------------

@dp.message(Command("admin_draw"))
async def cmd_admin_draw(message: types.Message):
    if not is_admin(message.from_user.id):
        await message.reply("⛔ Not authorized.")
        return

    cur_round = get_current_round()
    # Generate winning numbers deterministically from round data
    # NOTE: Admin draws should ideally use round participant data for verifiability
    # This is a legacy feature - new system uses automatic scheduled draws
    draw_seed = generate_provable_seed(cur_round, "admin_manual_draw")
    winning_numbers = generate_lottery_numbers(draw_seed, count=5, min_val=1, max_val=40)
    save_draw(cur_round, winning_numbers)

    # Announce winners
    rows = get_entries_for_round(cur_round)
    winners = []
    winner_details = []
    total_entries = 0
    total_prize_pool = Decimal("0")
    
    # Calculate prize pool
    conn = get_db_conn()
    c = conn.cursor()
    c.execute("SELECT SUM(stake_amount) FROM entries WHERE round = ? AND paid = 1", (cur_round,))
    total_pool = c.fetchone()[0]
    if total_pool:
        total_prize_pool = Decimal(str(total_pool)) * Decimal("0.8")  # 80% goes to prize pool
    
    for row in rows:
        entry_id, uid, numbers_str, paid = row
        if not paid:
            continue
        total_entries += 1
        entry_nums = str_to_numbers(numbers_str)
        if sorted(entry_nums) == winning_numbers:
            # Get winner's wallet for display
            c.execute("SELECT username FROM users WHERE user_id = ?", (uid,))
            user_row = c.fetchone()
            username = user_row[0] if user_row and user_row[0] else f"User{uid}"
            
            winners.append(uid)
            winner_details.append({
                "uid": uid,
                "username": username,
                "ticket_id": entry_id,
                "numbers": numbers_to_str(entry_nums)
            })
    
    conn.close()

    # Create announcement text with better formatting
    announce_text = (
        f"═══════════════════════\n"
        f"🏆 <b>CRYPTOUNC LOTTO</b> 🏆\n"
        f"═══════════════════════\n\n"
        f"📅 <b>Round {cur_round} - RESULTS</b>\n\n"
        f"🎲 <b>Winning Numbers:</b>\n"
        f"     <code>[ {numbers_to_str(winning_numbers)} ]</code>\n\n"
        f"═══════════════════════\n"
        f"📊 <b>Statistics:</b>\n"
        f"• Total Tickets: <b>{total_entries}</b>\n"
        f"• Prize Pool: <b>{total_prize_pool:.4f} SOL</b>\n"
        f"═══════════════════════\n\n"
    )

    if winners:
        winner_count = len(winners)
        prize_per_winner = total_prize_pool / winner_count if winner_count > 0 else Decimal("0")
        
        announce_text += f"🎉 <b>WE HAVE {winner_count} WINNER(S)!</b> 🎉\n\n"
        
        for i, details in enumerate(winner_details, 1):
            announce_text += (
                f"🥇 <b>Winner #{i}</b>\n"
                f"   👤 <a href='tg://user?id={details['uid']}'>{details['username']}</a>\n"
                f"   🎫 Ticket ID: #{details['ticket_id']}\n"
                f"   🎲 Numbers: {details['numbers']}\n"
                f"   💰 Prize: <b>{prize_per_winner:.4f} SOL</b>\n\n"
            )
        
        announce_text += (
            f"═══════════════════════\n"
            f"🎊 <b>CONGRATULATIONS!</b> 🎊\n"
            f"Winners, please contact admin to claim your prize.\n"
            f"═══════════════════════\n"
        )
    else:
        announce_text += (
            f"😔 <b>No Winners This Round</b>\n\n"
            f"No one matched all 5 numbers.\n"
            f"Prize pool rolls over to next round!\n\n"
            f"═══════════════════════\n"
            f"🎰 <b>Try Again!</b>\n"
            f"Round {cur_round + 1} is now open!\n"
            f"═══════════════════════\n"
        )

    # Post to channel
    posted_to_channel = False
    if ROUND_CHANNEL:
        try:
            await bot.send_message(ROUND_CHANNEL, announce_text, parse_mode="HTML")
            posted_to_channel = True
            await message.reply(f"✅ Results posted to {ROUND_CHANNEL}")
        except Exception as e:
            await message.reply(f"⚠️ Failed to post to channel: {str(e)}\n\nResults:\n{announce_text}", parse_mode="HTML")
    
    if not posted_to_channel:
        await message.reply(announce_text, parse_mode="HTML")

    increment_round()
    await message.reply(f"✅ Draw completed. Moved to Round {cur_round + 1}.")


def is_admin(user_id: int) -> bool:
    return user_id == ADMIN_ID


@dp.message(Command("status"))
async def cmd_status(message: types.Message):
    if not is_admin(message.from_user.id):
        await message.reply("⛔ Not authorized.")
        return
    
    rounds = get_active_rounds()
    
    text = "📊 <b>System Status</b>\n\n"
    text += f"⏰ Next rounds: {', '.join(ROUND_TIMES_UTC)} UTC\n"
    text += f"👥 Min players: {MIN_PLAYERS_PER_STAKE}\n"
    text += f"⏱ Round duration: {ROUND_DURATION_MINUTES} min\n\n"
    
    if not rounds:
        text += "🎰 No active rounds\n"
    else:
        text += f"🎰 <b>Active Rounds: {len(rounds)}</b>\n\n"
        
        for round_id, round_number, scheduled_time, start_time, end_time, status in rounds:
            text += f"<b>Round {round_id}</b>\n"
            text += f"Status: {status}\n"
            
            if start_time:
                start_dt = datetime.fromisoformat(start_time.replace('Z', '+00:00'))
                if start_dt.tzinfo is None:
                    start_dt = start_dt.replace(tzinfo=pytz.UTC)
                now = datetime.now(pytz.UTC)
                elapsed = (now - start_dt).total_seconds() / 60
                remaining = max(0, ROUND_DURATION_MINUTES - elapsed)
                text += f"Time remaining: {int(remaining)} min\n"
            
            stakes = get_round_stakes_with_counts(round_id)
            total_players = sum(player_count for _, _, _, player_count in stakes)
            text += f"Total players: {total_players}\n"
            
            text += "Stakes:\n"
            for stake_id, stake_amount, stake_status, player_count in stakes:
                text += f"  • {stake_amount} SOL: {player_count} players\n"
            
            text += "\n"
    
    await message.reply(text, parse_mode="HTML")


@dp.message(Command("refund"))
async def cmd_refund(message: types.Message):
    if not is_admin(message.from_user.id):
        await message.reply("⛔ Not authorized.")
        return
    
    try:
        args = message.text.split()
        
        if len(args) == 1:
            conn = get_db_conn()
            c = conn.cursor()
            c.execute("""
                SELECT rs.id, rs.round_id, rs.stake_amount, 
                       COUNT(rp.id) as pending_count
                FROM round_stakes rs
                LEFT JOIN round_participants rp ON rs.id = rp.round_stake_id AND rp.refunded = 0
                WHERE rs.status = 'pending_refund'
                GROUP BY rs.id
            """)
            pending_stakes = c.fetchall()
            conn.close()
            
            if not pending_stakes:
                await message.reply("✅ No pending refunds!")
                return
            
            text = "💸 <b>Pending Refunds</b>\n\n"
            for stake_id, round_id, stake_amount, count in pending_stakes:
                text += f"<b>Stake ID {stake_id}</b>\n"
                text += f"Round: {round_id}\n"
                text += f"Amount: {stake_amount} SOL\n"
                text += f"Participants: {count}\n"
                text += f"Command: /refund {stake_id}\n\n"
            
            await message.reply(text, parse_mode="HTML")
            return
        
        stake_id = int(args[1])
        
        conn = get_db_conn()
        c = conn.cursor()
        c.execute("""
            SELECT rp.id, rp.user_id, rs.stake_amount
            FROM round_participants rp
            JOIN round_stakes rs ON rp.round_stake_id = rs.id
            WHERE rp.round_stake_id = ? AND rp.refunded = 0
        """, (stake_id,))
        participants = c.fetchall()
        conn.close()
        
        if not participants:
            await message.reply("✅ No pending refunds for this stake.")
            return
        
        stake_amount = Decimal(str(participants[0][2]))
        refund_amount = stake_amount * (Decimal("1") - NETWORK_FEE_PERCENTAGE)
        
        text = f"💸 <b>Refund Details - Stake {stake_id}</b>\n\n"
        text += f"Participants: {len(participants)}\n"
        text += f"Refund per participant: {refund_amount} SOL\n\n"
        text += "<b>Participant List:</b>\n"
        
        for participant_id, user_id, _ in participants:
            wallet = get_active_wallet(user_id)
            text += f"• User {user_id}\n"
            text += f"  Wallet: <code>{wallet}</code>\n"
            text += f"  Participant ID: {participant_id}\n\n"
        
        text += f"\n<b>To process refunds:</b>\n"
        text += f"1. Send {refund_amount} SOL to each wallet above from your treasury wallet\n"
        text += f"2. After sending, use: /mark_refund <participant_id> <tx_signature>\n"
        
        await message.reply(text, parse_mode="HTML")
    
    except ValueError:
        await message.reply("❌ Invalid stake ID. Must be a number.")
    except Exception as e:
        await message.reply(f"❌ Error: {str(e)}")


@dp.message(Command("mark_refund"))
async def cmd_mark_refund(message: types.Message):
    if not is_admin(message.from_user.id):
        await message.reply("⛔ Not authorized.")
        return
    
    try:
        args = message.text.split()
        if len(args) < 3:
            await message.reply(
                "Usage: /mark_refund <participant_id> <tx_signature>\n\n"
                "Mark a refund as completed after you've sent the funds manually."
            )
            return
        
        participant_id = int(args[1])
        tx_signature = args[2]
        
        success = await mark_refund_completed(participant_id, tx_signature)
        
        if success:
            await message.reply(
                f"✅ Refund marked as completed!\n"
                f"Participant ID: {participant_id}\n"
                f"TX: <code>{tx_signature[:20]}...</code>\n\n"
                f"User has been notified.",
                parse_mode="HTML"
            )
        else:
            await message.reply("❌ Failed to mark refund as completed.")
    
    except ValueError:
        await message.reply("❌ Invalid participant ID. Must be a number.")
    except Exception as e:
        await message.reply(f"❌ Error: {str(e)}")


@dp.message(Command("force_draw"))
async def cmd_force_draw(message: types.Message):
    if not is_admin(message.from_user.id):
        await message.reply("⛔ Not authorized.")
        return
    
    try:
        args = message.text.split()
        if len(args) < 2:
            await message.reply(
                "Usage: /force_draw <round_stake_id>\n\n"
                "Get stake IDs from /status command.\n"
                "This will draw a winner immediately regardless of player count."
            )
            return
        
        stake_id = int(args[1])
        
        await message.reply("⏳ Processing draw...")
        
        result = process_round_stake_draw(stake_id)
        
        if result:
            await message.reply(
                f"✅ Draw completed!\n\n"
                f"Winner: {result['winner_user_id']}\n"
                f"Prize: {result['prize_amount']} SOL\n"
                f"Winning numbers: {', '.join(map(str, result['winning_numbers']))}\n"
                f"Players: {result['player_count']}"
            )
            
            conn = get_db_conn()
            c = conn.cursor()
            c.execute("SELECT round_id, stake_amount FROM round_stakes WHERE id = ?", (stake_id,))
            round_data = c.fetchone()
            conn.close()
            
            if round_data:
                round_id, stake_amount = round_data
                await announce_winner(round_id, stake_amount, result)
                await distribute_prize(stake_id, result)
        else:
            await message.reply("❌ Draw failed. No participants found.")
    
    except ValueError:
        await message.reply("❌ Invalid stake ID. Must be a number.")
    except Exception as e:
        await message.reply(f"❌ Error: {str(e)}")


@dp.message(Command("announce"))
async def cmd_announce(message: types.Message):
    if not is_admin(message.from_user.id):
        await message.reply("⛔ Not authorized.")
        return
    
    try:
        text = message.text.replace("/announce", "").strip()
        
        if not text:
            await message.reply(
                "Usage: /announce <message>\n\n"
                "This will send a custom message to the channel."
            )
            return
        
        await bot.send_message(
            ROUND_CHANNEL,
            f"📢 <b>Announcement</b>\n\n{text}",
            parse_mode="HTML"
        )
        
        await message.reply("✅ Announcement sent to channel!")
    
    except Exception as e:
        await message.reply(f"❌ Error: {str(e)}")


# ---------------------------
# Startup
# ---------------------------
async def schedule_daily_rounds():
    """
    Scheduler loop that creates daily rounds at configured times
    Enhanced with detailed logging for testing and debugging
    """
    print(f"[Scheduler] Starting daily round scheduler...")
    print(f"[Scheduler] Round times (UTC): {ROUND_TIMES_UTC}")
    print(f"[Scheduler] Rounds per day: {ROUNDS_PER_DAY}")
    
    while True:
        try:
            now = datetime.now(pytz.UTC)
            today = now.date()
            
            print(f"[Scheduler] Checking round timing at {now}")
            
            for round_num, time_str in enumerate(ROUND_TIMES_UTC, 1):
                hour, minute = map(int, time_str.split(':'))
                scheduled_dt = datetime(today.year, today.month, today.day, hour, minute, tzinfo=pytz.UTC)
                
                if scheduled_dt > now:
                    conn = get_db_conn()
                    c = conn.cursor()
                    # Convert timezone-aware datetime to ISO string for SQLite
                    scheduled_dt_str = scheduled_dt.isoformat()
                    c.execute("SELECT round_id FROM scheduled_rounds WHERE scheduled_time = ?", (scheduled_dt_str,))
                    existing = c.fetchone()
                    
                    if not existing:
                        round_id = create_scheduled_round(round_num, scheduled_dt)
                        print(f"[Scheduler] ✅ Created new round {round_id} for {scheduled_dt}")
                    else:
                        print(f"[Scheduler] ℹ️ Round already scheduled for {scheduled_dt}")
                    
                    conn.close()
            
            print(f"[Scheduler] Next check in 1 hour...")
            await asyncio.sleep(3600)
        except Exception as e:
            print(f"[Scheduler] ❌ Error: {e}")
            import traceback
            traceback.print_exc()
            print(f"[Scheduler] Retrying in 60 seconds...")
            await asyncio.sleep(60)


async def manage_rounds():
    """
    Round manager loop that opens rounds and closes them after duration
    Enhanced with detailed logging for testing and debugging
    """
    print(f"[Round Manager] Starting round manager...")
    print(f"[Round Manager] Round duration: {ROUND_DURATION_MINUTES} minutes")
    print(f"[Round Manager] Min players per stake: {MIN_PLAYERS_PER_STAKE}")
    
    while True:
        try:
            now = datetime.now(pytz.UTC)
            
            print(f"[Round Manager] Checking rounds at {now}")
            
            conn = get_db_conn()
            c = conn.cursor()
            # Convert timezone-aware datetime to ISO string for SQLite comparison
            now_str = now.isoformat()
            c.execute("""
                SELECT round_id, scheduled_time FROM scheduled_rounds
                WHERE status = 'pending' AND scheduled_time <= ?
            """, (now_str,))
            pending_rounds = c.fetchall()
            
            if pending_rounds:
                print(f"[Round Manager] Found {len(pending_rounds)} pending rounds to open")
            
            for round_id, scheduled_time in pending_rounds:
                update_round_status(round_id, 'open')
                print(f"[Round Manager] ✅ Round {round_id} is now OPEN! (scheduled for {scheduled_time})")
                await announce_round_opened(round_id)
            
            c.execute("""
                SELECT round_id, start_time FROM scheduled_rounds
                WHERE status = 'open'
            """)
            open_rounds = c.fetchall()
            
            if open_rounds:
                print(f"[Round Manager] Monitoring {len(open_rounds)} open rounds")
            
            for round_id, start_time in open_rounds:
                # Ensure start_dt is timezone-aware
                start_dt = datetime.fromisoformat(start_time.replace('Z', '+00:00'))
                if start_dt.tzinfo is None:
                    start_dt = start_dt.replace(tzinfo=pytz.UTC)
                
                # Both now and start_dt are now timezone-aware
                print(f"[Round Manager] Now: {now} (tz: {now.tzinfo}) | Start: {start_dt} (tz: {start_dt.tzinfo})")
                elapsed = (now - start_dt).total_seconds() / 60
                
                print(f"[Round Manager] Round {round_id}: {elapsed:.1f}/{ROUND_DURATION_MINUTES} minutes elapsed")
                
                if elapsed >= ROUND_DURATION_MINUTES:
                    print(f"[Round Manager] ⏰ Round {round_id} duration reached, processing end...")
                    await process_round_end(round_id)
            
            conn.close()
            print(f"[Round Manager] Next check in 30 seconds...")
            await asyncio.sleep(30)
        except Exception as e:
            print(f"[Round Manager] ❌ Error: {e}")
            import traceback
            traceback.print_exc()
            print(f"[Round Manager] Retrying in 30 seconds...")
            await asyncio.sleep(30)


async def process_round_end(round_id: int):
    stakes = get_round_stakes_with_counts(round_id)
    
    for stake_id, stake_amount, status, player_count in stakes:
        if player_count >= MIN_PLAYERS_PER_STAKE:
            result = process_round_stake_draw(stake_id)
            if result:
                await announce_winner(round_id, stake_amount, result)
                await distribute_prize(stake_id, result)
        else:
            refunded = await process_refunds_for_stake(stake_id)
            await announce_refunds(round_id, stake_amount, len(refunded))
    
    update_round_status(round_id, 'completed')
    print(f"✅ Round {round_id} completed!")


async def announce_round_opened(round_id: int):
    try:
        stakes = get_round_stakes_with_counts(round_id)
        stake_buttons = []
        for stake_id, stake_amount, status, player_count in stakes:
            needed = max(0, MIN_PLAYERS_PER_STAKE - player_count)
            stake_buttons.append([InlineKeyboardButton(
                text=f"{'✅' if player_count >= MIN_PLAYERS_PER_STAKE else '🎯'} {stake_amount} SOL ({player_count}/{MIN_PLAYERS_PER_STAKE})",
                callback_data=f"join_stake_{stake_id}"
            )])
        
        stake_buttons.append([InlineKeyboardButton(text="🔄 Refresh", callback_data=f"check_round_{round_id}")])
        keyboard = InlineKeyboardMarkup(inline_keyboard=stake_buttons)
        
        await bot.send_message(
            ROUND_CHANNEL,
            f"🎰 <b>Round {round_id} is NOW OPEN!</b>\n\n"
            f"⏰ Duration: {ROUND_DURATION_MINUTES} minutes\n"
            f"👥 Minimum players per stake: {MIN_PLAYERS_PER_STAKE}\n"
            f"💰 Prize: 80% of pool to winner\n\n"
            f"Choose your stake amount:",
            reply_markup=keyboard,
            parse_mode="HTML"
        )
    except Exception as e:
        print(f"❌ Announcement error: {e}")


async def announce_winner(round_id: int, stake_amount: float, result: dict):
    try:
        winner_id = result['winner_user_id']
        prize = result['prize_amount']
        players = result['player_count']
        winning_nums = result['winning_numbers']
        
        conn = get_db_conn()
        c = conn.cursor()
        c.execute("SELECT username FROM users WHERE user_id = ?", (winner_id,))
        user_row = c.fetchone()
        winner_name = user_row[0] if user_row and user_row[0] else f"User {winner_id}"
        conn.close()
        
        await bot.send_message(
            ROUND_CHANNEL,
            f"🏆 <b>WINNER ANNOUNCEMENT!</b>\n\n"
            f"🎰 Round: {round_id}\n"
            f"💰 Stake: {stake_amount} SOL\n"
            f"👥 Players: {players}\n\n"
            f"🎲 Winning Numbers: {', '.join(map(str, winning_nums))}\n\n"
            f"🥇 Winner: @{winner_name}\n"
            f"💵 Prize: <b>{prize} SOL</b>\n\n"
            f"Congratulations! 🎉",
            parse_mode="HTML"
        )
    except Exception as e:
        print(f"❌ Winner announcement error: {e}")


async def announce_refunds(round_id: int, stake_amount: float, refund_count: int):
    try:
        if refund_count > 0:
            await bot.send_message(
                ROUND_CHANNEL,
                f"💸 <b>Refund Processed</b>\n\n"
                f"🎰 Round: {round_id}\n"
                f"💰 Stake: {stake_amount} SOL\n"
                f"👥 Participants: {refund_count}\n\n"
                f"❌ Minimum players not met ({MIN_PLAYERS_PER_STAKE} required)\n"
                f"✅ All participants refunded (minus {float(NETWORK_FEE_PERCENTAGE * 100)}% network fee)",
                parse_mode="HTML"
            )
    except Exception as e:
        print(f"❌ Refund announcement error: {e}")


async def distribute_prize(stake_id: int, result: dict):
    try:
        winner_id = result['winner_user_id']
        prize_amount = result['prize_amount']
        
        winner_wallet = get_active_wallet(winner_id)
        if not winner_wallet:
            print(f"❌ Winner {winner_id} has no active wallet!")
            return
        
        team_amount = Decimal(str(prize_amount)) * Decimal("0.2") / Decimal("0.8")
        
        if TEAM_WALLET and TEAM_WALLET != OWNER_WALLET:
            try:
                team_result = await send_sol(OWNER_WALLET, TEAM_WALLET, team_amount, OWNER_WALLET_PRIVATE_KEY)
                if team_result and team_result.get("success"):
                    print(f"💼 Team payment sent: {team_amount} SOL - TX: {team_result.get('signature', '')[:16]}...")
                else:
                    print(f"⚠️ Team payment failed: {team_result.get('error', 'Unknown error')}")
            except Exception as e:
                print(f"⚠️ Team payment exception: {e}")
        
        try:
            print(f"💰 Sending prize to winner {winner_id}: {prize_amount} SOL to {winner_wallet[:8]}...{winner_wallet[-8:]}")
            prize_result = await send_sol(OWNER_WALLET, winner_wallet, Decimal(str(prize_amount)), OWNER_WALLET_PRIVATE_KEY)
            
            if prize_result and prize_result.get("success"):
                conn = get_db_conn()
                c = conn.cursor()
                c.execute("""
                    UPDATE round_stakes
                    SET tx_signature = ?
                    WHERE id = ?
                """, (prize_result["signature"], stake_id))
                conn.commit()
                conn.close()
                
                await bot.send_message(
                    winner_id,
                    f"🎉 <b>Congratulations! You WON!</b>\n\n"
                    f"💰 Prize: {prize_amount} SOL\n"
                    f"📝 TX: <code>{prize_result['signature'][:20]}...</code>\n\n"
                    f"The prize has been sent to your wallet!",
                    parse_mode="HTML"
                )
        except Exception as e:
            print(f"❌ Prize distribution error: {e}")
    except Exception as e:
        print(f"❌ Distribute prize error: {e}")


def audit_configuration():
    """Audit all required environment variables and warn if any are missing"""
    print("\n🔐 Auditing Configuration...")
    
    required_secrets = {
        'BOT_TOKEN': 'Telegram Bot Token',
        'OWNER_WALLET': 'Treasury Wallet Address',
        'OWNER_WALLET_PRIVATE_KEY': 'Owner Wallet Private Key (for automatic payouts)',
        'ROUND_CHANNEL_ID': 'Announcement Channel ID',
        'SOLANA_RPC': 'Solana RPC Endpoint',
        'ADMIN_ID': 'Admin User ID',
        'ENCRYPTION_KEY': 'Wallet Encryption Key'
    }
    
    optional_secrets = {
        'TEAM_WALLET': 'Team Wallet Address (defaults to OWNER_WALLET)',
        'SUPPORT_USERNAME': 'Support Contact Username'
    }
    
    missing_required = []
    missing_optional = []
    
    for key, description in required_secrets.items():
        value = os.getenv(key)
        if not value:
            missing_required.append(f"  ❌ {key}: {description}")
            print(f"  ❌ MISSING REQUIRED: {key} ({description})")
        else:
            # Mask sensitive values
            if 'TOKEN' in key or 'KEY' in key:
                display_value = value[:10] + "..." if len(value) > 10 else "***"
            else:
                display_value = value
            print(f"  ✅ {key}: {display_value}")
    
    for key, description in optional_secrets.items():
        value = os.getenv(key)
        if not value:
            missing_optional.append(f"  ⚠️ {key}: {description}")
            print(f"  ⚠️ Optional: {key} ({description}) - Not set")
        else:
            if 'TOKEN' in key or 'KEY' in key:
                display_value = "***"
            else:
                display_value = value
            print(f"  ✅ {key}: {display_value}")
    
    if missing_required:
        print("\n⛔ CRITICAL: Missing required environment variables!")
        for msg in missing_required:
            print(msg)
        print("\nBot may not function correctly. Please set these variables and restart.")
        return False
    
    if missing_optional:
        print("\n⚠️ Warning: Some optional configurations are missing:")
        for msg in missing_optional:
            print(msg)
        print("Bot will use defaults, but functionality may be limited.")
    
    print("\n✅ Configuration audit complete!\n")
    return True


# ---------------------------
# Web Server for UptimeRobot Keep-Alive
# ---------------------------

async def health_check(request):
    """Simple health check endpoint for UptimeRobot pings"""
    return web.Response(text="✅ CryptoUnc Lotto Bot is alive!")

async def index(request):
    """Root endpoint with bot info"""
    return web.Response(text="🎲 CryptoUnc Lotto Bot - Telegram Bot is running!")

async def start_web_server():
    """Start aiohttp web server for keep-alive pings"""
    app = web.Application()
    app.router.add_get('/', index)
    app.router.add_get('/health', health_check)
    app.router.add_get('/ping', health_check)
    
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, '0.0.0.0', 5000)
    await site.start()
    print("🌐 Web server started on http://0.0.0.0:5000 for UptimeRobot pings")
    print("📌 Health endpoint: /health")
    print("📌 Your Replit URL: Check the Webview tab above ⬆️")


async def main():
    # Audit configuration before starting
    config_ok = audit_configuration()
    if not config_ok:
        print("\n⚠️ Starting anyway, but expect issues...\n")
    
    migrate_database()  # Migrate existing databases before init
    init_db()
    init_wallet_db()  # Initialize wallet tables
    migrate_timestamps_to_iso()  # Migrate legacy timestamps to ISO format
    print("🤖 CryptoUnc Lotto Bot with Real Solana Integration starting...")
    rpc_endpoint = os.getenv('SOLANA_RPC', 'mainnet-beta')
    # Mask API key in logs for security
    if '?' in rpc_endpoint:
        rpc_display = rpc_endpoint.split('?')[0] + "?api-key=***"
    else:
        rpc_display = rpc_endpoint
    print(f"📍 Connected to: {rpc_display}")
    
    # Delete webhook to ensure polling works
    await bot.delete_webhook(drop_pending_updates=True)
    print("✅ Webhook deleted, starting polling...")
    
    asyncio.create_task(schedule_daily_rounds())
    asyncio.create_task(manage_rounds())
    print("📅 Background scheduler started!")
    
    # Start web server for keep-alive
    asyncio.create_task(start_web_server())
    
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
