# Wallet.py - Real Solana Mainnet Wallet Management
import os
import sqlite3
from decimal import Decimal
from typing import Optional, List, Dict
import asyncio

try:
    from solders.keypair import Keypair
    from solders.pubkey import Pubkey
    from solders.system_program import transfer, TransferParams
    from solders.transaction import Transaction
    from solders.message import Message
except ImportError:
    from solana.keypair import Keypair
    from solana.publickey import PublicKey as Pubkey

from solana.rpc.async_api import AsyncClient
from solana.rpc.commitment import Confirmed

# Constants
SOLANA_RPC = os.getenv("SOLANA_RPC", "https://api.mainnet-beta.solana.com")
MAX_WALLETS_PER_USER = 3

DB_PATH = "cryptounc_lotto.db"


def get_db_conn():
    """Get database connection"""
    return sqlite3.connect(DB_PATH)


def init_wallet_db():
    """Initialize wallet tables in database"""
    conn = get_db_conn()
    c = conn.cursor()

    # Wallets table - stores user wallets
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

    # User active wallet tracker
    c.execute("""
        CREATE TABLE IF NOT EXISTS user_active_wallet (
            user_id INTEGER PRIMARY KEY,
            active_wallet_address TEXT,
            FOREIGN KEY (active_wallet_address) REFERENCES wallets(wallet_address)
        )
    """)

    conn.commit()
    conn.close()


async def get_real_balance(wallet_address: str) -> Decimal:
    """
    Fetch real balance from Solana mainnet
    Returns balance in SOL
    """
    try:
        async with AsyncClient(SOLANA_RPC) as client:
            pubkey = Pubkey.from_string(wallet_address)
            response = await client.get_balance(pubkey, commitment=Confirmed)

            if response.value is not None:
                lamports = response.value
                sol_balance = Decimal(lamports) / Decimal(1_000_000_000)
                return sol_balance
            return Decimal("0")
    except Exception as e:
        print(f"Error fetching balance for {wallet_address}: {e}")
        return Decimal("0")


def get_user_wallets(user_id: int) -> List[Dict]:
    """
    Get all wallets for a user
    Returns list of wallet dicts
    """
    conn = get_db_conn()
    c = conn.cursor()
    c.execute("""
        SELECT wallet_address, wallet_type, wallet_name, is_active 
        FROM wallets 
        WHERE user_id = ? AND is_active = 1
        ORDER BY created_at ASC
    """, (user_id,))
    rows = c.fetchall()
    conn.close()

    wallets = []
    for row in rows:
        wallets.append({
            "address": row[0],
            "type": row[1],
            "name": row[2] or "Wallet",
            "is_active": bool(row[3])
        })
    return wallets


def get_user_wallet_count(user_id: int) -> int:
    """Get number of active wallets for a user"""
    conn = get_db_conn()
    c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM wallets WHERE user_id = ? AND is_active = 1", (user_id,))
    count = c.fetchone()[0]
    conn.close()
    return count


def get_active_wallet(user_id: int) -> Optional[str]:
    """Get user's currently active wallet address"""
    conn = get_db_conn()
    c = conn.cursor()
    c.execute("SELECT active_wallet_address FROM user_active_wallet WHERE user_id = ?", (user_id,))
    row = c.fetchone()
    conn.close()
    return row[0] if row else None


def set_active_wallet(user_id: int, wallet_address: str) -> bool:
    """Set which wallet is active for the user"""
    conn = get_db_conn()
    c = conn.cursor()

    # Verify wallet belongs to user
    c.execute("SELECT 1 FROM wallets WHERE user_id = ? AND wallet_address = ?", (user_id, wallet_address))
    if not c.fetchone():
        conn.close()
        return False

    # Update or insert active wallet
    c.execute("""
        INSERT INTO user_active_wallet (user_id, active_wallet_address) 
        VALUES (?, ?)
        ON CONFLICT(user_id) DO UPDATE SET active_wallet_address = ?
    """, (user_id, wallet_address, wallet_address))

    conn.commit()
    conn.close()
    return True


def create_wallet(user_id: int, wallet_name: Optional[str] = None) -> Optional[Dict]:
    """
    Create a new bot-managed wallet for the user
    Returns wallet dict with address and private key
    """
    # Check wallet limit
    if get_user_wallet_count(user_id) >= MAX_WALLETS_PER_USER:
        return None

    # Generate new keypair
    keypair = Keypair()
    wallet_address = str(keypair.pubkey())
    private_key = bytes(keypair).hex()  # Store securely

    if not wallet_name:
        count = get_user_wallet_count(user_id) + 1
        wallet_name = f"Bot Wallet {count}"

    conn = get_db_conn()
    c = conn.cursor()

    try:
        c.execute("""
            INSERT INTO wallets (user_id, wallet_address, wallet_type, wallet_name, private_key)
            VALUES (?, ?, ?, ?, ?)
        """, (user_id, wallet_address, "bot", wallet_name, private_key))

        # Set as active if it's the first wallet
        if get_user_wallet_count(user_id) == 0:
            c.execute("""
                INSERT INTO user_active_wallet (user_id, active_wallet_address)
                VALUES (?, ?)
            """, (user_id, wallet_address))

        conn.commit()
        conn.close()

        return {
            "address": wallet_address,
            "type": "bot",
            "name": wallet_name,
            "private_key": private_key
        }
    except sqlite3.IntegrityError:
        conn.close()
        return None


def save_external_wallet(user_id: int, wallet_address: str, wallet_type: str = "external", wallet_name: Optional[str] = None) -> bool:
    """
    Save an external wallet (Phantom, Solflare, etc.)
    """
    # Check wallet limit
    if get_user_wallet_count(user_id) >= MAX_WALLETS_PER_USER:
        return False

    if not wallet_name:
        count = get_user_wallet_count(user_id) + 1
        wallet_name = f"{wallet_type.capitalize()} Wallet {count}"

    conn = get_db_conn()
    c = conn.cursor()

    try:
        c.execute("""
            INSERT INTO wallets (user_id, wallet_address, wallet_type, wallet_name)
            VALUES (?, ?, ?, ?)
        """, (user_id, wallet_address, wallet_type, wallet_name))

        # Set as active if it's the first wallet
        if get_user_wallet_count(user_id) == 0:
            c.execute("""
                INSERT INTO user_active_wallet (user_id, active_wallet_address)
                VALUES (?, ?)
            """, (user_id, wallet_address))

        conn.commit()
        conn.close()
        return True
    except sqlite3.IntegrityError:
        conn.close()
        return False


def get_wallet_private_key(user_id: int, wallet_address: str) -> Optional[str]:
    """Get private key for a bot-managed wallet"""
    conn = get_db_conn()
    c = conn.cursor()
    c.execute("""
        SELECT private_key FROM wallets 
        WHERE user_id = ? AND wallet_address = ? AND wallet_type = 'bot'
    """, (user_id, wallet_address))
    row = c.fetchone()
    conn.close()
    return row[0] if row else None


async def send_sol(from_address: str, to_address: str, amount_sol: Decimal, private_key_hex: str) -> Dict:
    """
    Send SOL from one address to another
    Returns transaction result dict
    """
    try:
        # Convert amount to lamports
        lamports = int(amount_sol * Decimal(1_000_000_000))

        # Recreate keypair from private key
        private_key_bytes = bytes.fromhex(private_key_hex)
        keypair = Keypair.from_bytes(private_key_bytes)

        async with AsyncClient(SOLANA_RPC) as client:
            # Get recent blockhash
            recent_blockhash = await client.get_latest_blockhash()

            # Create transfer instruction
            from_pubkey = Pubkey.from_string(from_address)
            to_pubkey = Pubkey.from_string(to_address)

            transfer_ix = transfer(
                TransferParams(
                    from_pubkey=from_pubkey,
                    to_pubkey=to_pubkey,
                    lamports=lamports
                )
            )

            # Create and sign transaction
            message = Message.new_with_blockhash(
                [transfer_ix],
                from_pubkey,
                recent_blockhash.value.blockhash
            )
            transaction = Transaction([keypair], message, recent_blockhash.value.blockhash)

            # Send transaction
            result = await client.send_transaction(transaction)

            return {
                "success": True,
                "signature": str(result.value),
                "amount": float(amount_sol)
            }
    except Exception as e:
        print(f"Error sending SOL: {e}")
        return {
            "success": False,
            "error": str(e)
        }


def delete_wallet(user_id: int, wallet_address: str) -> bool:
    """Soft delete a wallet (mark as inactive)"""
    conn = get_db_conn()
    c = conn.cursor()

    c.execute("""
        UPDATE wallets 
        SET is_active = 0 
        WHERE user_id = ? AND wallet_address = ?
    """, (user_id, wallet_address))

    # If this was the active wallet, clear it
    c.execute("""
        DELETE FROM user_active_wallet 
        WHERE user_id = ? AND active_wallet_address = ?
    """, (user_id, wallet_address))

    conn.commit()
    affected = c.rowcount > 0
    conn.close()
    return affected


# Legacy compatibility functions for Main.py
def get_user_wallet(user_id: int) -> Optional[str]:
    """Get user's active wallet address (legacy compatibility)"""
    return get_active_wallet(user_id)


def save_user_wallet(user_id: int, wallet_address: str):
    """Save external wallet (legacy compatibility)"""
    return save_external_wallet(user_id, wallet_address, "external")


async def get_wallet_balance(user_id: int) -> Decimal:
    """Get balance of user's active wallet"""
    wallet_address = get_active_wallet(user_id)
    if not wallet_address:
        return Decimal("0")
    return await get_real_balance(wallet_address)


def deduct_wallet_balance(user_id: int, amount: Decimal):
    """This is a no-op since we're using real balances now"""
    pass


def add_funds_to_wallet(wallet_address: str, amount: Decimal):
    """This is a no-op since we're using real balances now"""
    pass


# Initialize database on import
init_wallet_db()