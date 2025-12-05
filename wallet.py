# Wallet.py - Real Solana Mainnet Wallet Management
import os
import sqlite3
from decimal import Decimal
from typing import Optional, List, Dict
import asyncio

from encryption import encrypt_private_key, decrypt_private_key, is_encryption_configured

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

# ==============================================================================
# SOLANA RPC CONFIGURATION WITH AUTOMATIC FALLBACK
# ==============================================================================
# Uses HELIUS_RPC as primary (from Railway secrets) with public RPC as fallback.
# Automatically switches to fallback if primary RPC has errors.
# The RPC list always includes all distinct endpoints for reliable failover.

HELIUS_RPC = os.getenv("HELIUS_RPC")
FALLBACK_RPC = "https://api.mainnet-beta.solana.com"
LEGACY_RPC = os.getenv("SOLANA_RPC")

# Build the ordered list of RPC endpoints (deduplicated)
def _build_rpc_list() -> list:
    """Build ordered list of distinct RPC endpoints for failover."""
    endpoints = []
    seen = set()
    
    # Priority 1: Helius RPC (if configured)
    if HELIUS_RPC and HELIUS_RPC not in seen:
        endpoints.append(HELIUS_RPC)
        seen.add(HELIUS_RPC)
    
    # Priority 2: Legacy SOLANA_RPC (if configured and different)
    if LEGACY_RPC and LEGACY_RPC not in seen:
        endpoints.append(LEGACY_RPC)
        seen.add(LEGACY_RPC)
    
    # Priority 3: Public fallback (always included)
    if FALLBACK_RPC not in seen:
        endpoints.append(FALLBACK_RPC)
        seen.add(FALLBACK_RPC)
    
    return endpoints

RPC_ENDPOINTS = _build_rpc_list()
SOLANA_RPC = RPC_ENDPOINTS[0]  # Primary RPC for compatibility

MAX_WALLETS_PER_USER = 3


def get_rpc_list() -> list:
    """
    Get the ordered list of RPC endpoints for failover.
    Always returns at least the public fallback RPC.
    """
    return RPC_ENDPOINTS.copy()


async def get_working_rpc() -> str:
    """
    Get a working RPC endpoint, trying each in order until one succeeds.
    Returns the RPC URL that successfully connects.
    """
    for rpc in RPC_ENDPOINTS:
        try:
            async with AsyncClient(rpc) as client:
                response = await client.get_health()
                if response:
                    return rpc
        except Exception as e:
            print(f"RPC {rpc[:30]}... failed: {e}")
            continue
    
    return FALLBACK_RPC

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

    # User PINs table - stores encrypted 4-digit PINs for wallet security
    c.execute("""
        CREATE TABLE IF NOT EXISTS user_pins (
            user_id INTEGER PRIMARY KEY,
            pin_hash TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    conn.commit()
    conn.close()


async def get_real_balance(wallet_address: str) -> Decimal:
    """
    Fetch real balance from Solana mainnet using lamports conversion.
    Uses all configured RPC endpoints with automatic failover.
    Returns balance in SOL.
    """
    last_error = None
    for rpc in RPC_ENDPOINTS:
        try:
            print(f"Checking balance for {wallet_address[:8]}... using RPC: {rpc[:30]}...")
            async with AsyncClient(rpc) as client:
                pubkey = Pubkey.from_string(wallet_address)
                response = await client.get_balance(pubkey, commitment=Confirmed)

                if response.value is not None:
                    lamports = response.value
                    sol_balance = Decimal(lamports) / Decimal(1_000_000_000)
                    print(f"Balance: {sol_balance} SOL ({lamports} lamports)")
                    return sol_balance
                return Decimal("0")
        except Exception as e:
            last_error = e
            print(f"RPC error ({rpc[:30]}...): {e}, trying next endpoint...")
            continue
    
    print(f"Error fetching balance for {wallet_address}: {last_error}")
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
    Returns wallet dict with address (private key is ENCRYPTED in database)
    
    IMPORTANT: This function checks for existing wallets FIRST and reuses them.
    A new wallet is only created if the user has less than MAX_WALLETS_PER_USER wallets.
    """
    # Check wallet limit FIRST - never exceed MAX_WALLETS_PER_USER
    current_count = get_user_wallet_count(user_id)
    if current_count >= MAX_WALLETS_PER_USER:
        return None
    
    # Check if this is the user's first wallet (before inserting)
    is_first_wallet = current_count == 0
    
    # Verify encryption is configured
    if not is_encryption_configured():
        raise ValueError("Encryption not configured. Set ENCRYPTION_KEY environment variable.")

    # Generate new keypair
    keypair = Keypair()
    wallet_address = str(keypair.pubkey())
    private_key_hex = bytes(keypair).hex()
    
    # ENCRYPT the private key before storing
    encrypted_private_key = encrypt_private_key(private_key_hex)

    if not wallet_name:
        wallet_name = f"Bot Wallet {current_count + 1}"

    conn = get_db_conn()
    c = conn.cursor()

    try:
        # Store ENCRYPTED private key in database
        c.execute("""
            INSERT INTO wallets (user_id, wallet_address, wallet_type, wallet_name, private_key)
            VALUES (?, ?, ?, ?, ?)
        """, (user_id, wallet_address, "bot", wallet_name, encrypted_private_key))

        # Set as active if it's the first wallet (checked BEFORE insert)
        if is_first_wallet:
            c.execute("""
                INSERT INTO user_active_wallet (user_id, active_wallet_address)
                VALUES (?, ?)
                ON CONFLICT(user_id) DO UPDATE SET active_wallet_address = ?
            """, (user_id, wallet_address, wallet_address))

        conn.commit()
        conn.close()

        return {
            "address": wallet_address,
            "type": "bot",
            "name": wallet_name
        }
    except sqlite3.IntegrityError:
        conn.close()
        return None


def save_external_wallet(user_id: int, wallet_address: str, wallet_type: str = "external", wallet_name: Optional[str] = None) -> bool:
    """
    Save an external wallet (Phantom, Solflare, etc.)
    
    IMPORTANT: Checks for existing wallets FIRST to prevent duplicates.
    """
    # Check wallet limit FIRST
    current_count = get_user_wallet_count(user_id)
    if current_count >= MAX_WALLETS_PER_USER:
        return False
    
    # Check if this is the user's first wallet (before inserting)
    is_first_wallet = current_count == 0

    if not wallet_name:
        wallet_name = f"{wallet_type.capitalize()} Wallet {current_count + 1}"

    conn = get_db_conn()
    c = conn.cursor()

    try:
        c.execute("""
            INSERT INTO wallets (user_id, wallet_address, wallet_type, wallet_name)
            VALUES (?, ?, ?, ?)
        """, (user_id, wallet_address, wallet_type, wallet_name))

        # Set as active if it's the first wallet (checked BEFORE insert)
        if is_first_wallet:
            c.execute("""
                INSERT INTO user_active_wallet (user_id, active_wallet_address)
                VALUES (?, ?)
                ON CONFLICT(user_id) DO UPDATE SET active_wallet_address = ?
            """, (user_id, wallet_address, wallet_address))

        conn.commit()
        conn.close()
        return True
    except sqlite3.IntegrityError:
        conn.close()
        return False


def import_wallet_from_private_key(user_id: int, private_key_input: str, wallet_name: Optional[str] = None) -> Dict:
    """
    Import a wallet using private key (hex or base58 format)
    Returns dict with success status, address, or error message
    
    SECURITY: Private key is encrypted before storage
    """
    import base58
    
    # Check wallet limit
    if get_user_wallet_count(user_id) >= MAX_WALLETS_PER_USER:
        return {"success": False, "error": f"Maximum {MAX_WALLETS_PER_USER} wallets allowed"}
    
    # Verify encryption is configured
    if not is_encryption_configured():
        return {"success": False, "error": "Encryption not configured"}
    
    private_key_input = private_key_input.strip()
    private_key_bytes = None
    
    try:
        # Try to parse as hex (128 chars = 64 bytes)
        if len(private_key_input) == 128 and all(c in '0123456789abcdefABCDEF' for c in private_key_input):
            private_key_bytes = bytes.fromhex(private_key_input)
        # Try to parse as base58 (typical Phantom export format, ~88 chars)
        elif len(private_key_input) >= 64 and len(private_key_input) <= 100:
            try:
                private_key_bytes = base58.b58decode(private_key_input)
            except:
                pass
        # Try to parse as JSON array (Solflare format)
        elif private_key_input.startswith('[') and private_key_input.endswith(']'):
            import json
            try:
                key_array = json.loads(private_key_input)
                if isinstance(key_array, list) and len(key_array) == 64:
                    private_key_bytes = bytes(key_array)
            except:
                pass
        
        if not private_key_bytes or len(private_key_bytes) != 64:
            return {
                "success": False, 
                "error": "Invalid private key format. Expected hex (128 chars), base58, or JSON array [64 numbers]"
            }
        
        # Create keypair from private key bytes
        keypair = Keypair.from_bytes(private_key_bytes)
        wallet_address = str(keypair.pubkey())
        private_key_hex = private_key_bytes.hex()
        
        # Check if wallet already exists for this user
        conn = get_db_conn()
        c = conn.cursor()
        c.execute("SELECT 1 FROM wallets WHERE user_id = ? AND wallet_address = ?", (user_id, wallet_address))
        if c.fetchone():
            conn.close()
            return {"success": False, "error": "This wallet is already imported"}
        conn.close()
        
        # Encrypt the private key
        encrypted_private_key = encrypt_private_key(private_key_hex)
        
        if not wallet_name:
            count = get_user_wallet_count(user_id) + 1
            wallet_name = f"Imported Wallet {count}"
        
        conn = get_db_conn()
        c = conn.cursor()
        
        c.execute("""
            INSERT INTO wallets (user_id, wallet_address, wallet_type, wallet_name, private_key)
            VALUES (?, ?, ?, ?, ?)
        """, (user_id, wallet_address, "imported", wallet_name, encrypted_private_key))
        
        # Set as active wallet
        c.execute("""
            INSERT INTO user_active_wallet (user_id, active_wallet_address)
            VALUES (?, ?)
            ON CONFLICT(user_id) DO UPDATE SET active_wallet_address = ?
        """, (user_id, wallet_address, wallet_address))
        
        conn.commit()
        conn.close()
        
        return {
            "success": True,
            "address": wallet_address,
            "name": wallet_name
        }
        
    except Exception as e:
        return {"success": False, "error": f"Failed to import wallet: {str(e)}"}


def _is_hex_string(s: str) -> bool:
    """Check if a string is a valid hex string"""
    try:
        int(s, 16)
        return len(s) == 128  # Solana private keys are 64 bytes = 128 hex chars
    except (ValueError, TypeError):
        return False


def _migrate_plaintext_key(user_id: int, wallet_address: str, plaintext_key: str) -> bool:
    """
    Migrate a plaintext private key to encrypted format
    Returns True if migration successful
    """
    try:
        # Encrypt the plaintext key
        encrypted_key = encrypt_private_key(plaintext_key)
        
        # Update database with encrypted key
        conn = get_db_conn()
        c = conn.cursor()
        c.execute("""
            UPDATE wallets 
            SET private_key = ? 
            WHERE user_id = ? AND wallet_address = ? AND wallet_type = 'bot'
        """, (encrypted_key, user_id, wallet_address))
        conn.commit()
        conn.close()
        
        print(f"✅ Migrated plaintext key to encrypted for wallet {wallet_address[:8]}...")
        return True
    except Exception as e:
        print(f"❌ Failed to migrate key for wallet {wallet_address[:8]}: {e}")
        return False


def get_wallet_private_key(user_id: int, wallet_address: str) -> Optional[str]:
    """
    Get DECRYPTED private key for a bot-managed or imported wallet.
    Supports both 'bot' and 'imported' wallet types.
    Automatically migrates plaintext keys AND legacy-encrypted keys to new encryption.
    Returns the decrypted hex private key, or None if not found or no private key stored.
    """
    conn = get_db_conn()
    c = conn.cursor()
    c.execute("""
        SELECT private_key, wallet_type FROM wallets 
        WHERE user_id = ? AND wallet_address = ? AND wallet_type IN ('bot', 'imported')
    """, (user_id, wallet_address))
    row = c.fetchone()
    conn.close()
    
    if not row or not row[0]:
        return None
    
    stored_key = row[0]
    wallet_type = row[1]
    
    # Check if this is a plaintext hex key (legacy format)
    if _is_hex_string(stored_key):
        print(f"⚠️ Detected plaintext key for {wallet_address[:8]}..., migrating to encrypted format")
        if _migrate_plaintext_key_any_type(user_id, wallet_address, stored_key, wallet_type):
            return stored_key
        else:
            return stored_key
    
    # It's an encrypted key, decrypt it
    try:
        decrypted_key = decrypt_private_key(stored_key)
        return decrypted_key
    except Exception as e:
        print(f"Error decrypting private key: {e}")
        return None


def _migrate_plaintext_key_any_type(user_id: int, wallet_address: str, plaintext_key: str, wallet_type: str) -> bool:
    """
    Migrate a plaintext private key to encrypted format for any wallet type.
    Returns True if migration successful.
    """
    try:
        encrypted_key = encrypt_private_key(plaintext_key)
        conn = get_db_conn()
        c = conn.cursor()
        c.execute("""
            UPDATE wallets 
            SET private_key = ? 
            WHERE user_id = ? AND wallet_address = ? AND wallet_type = ?
        """, (encrypted_key, user_id, wallet_address, wallet_type))
        conn.commit()
        conn.close()
        print(f"✅ Migrated plaintext key to encrypted for {wallet_type} wallet {wallet_address[:8]}...")
        return True
    except Exception as e:
        print(f"❌ Failed to migrate key for wallet {wallet_address[:8]}: {e}")
        return False


async def estimate_transaction_fee(from_address: str, to_address: str, amount_sol: Decimal) -> Decimal:
    """
    Estimate the transaction fee for a SOL transfer.
    Uses all configured RPC endpoints with automatic failover.
    Returns fee in SOL (typically ~0.00002 SOL for simple transfers).
    NOTE: Does not require private key - only estimates the fee for a transfer.
    """
    # Standard network fee for SOL transfers (includes buffer for network fees)
    NETWORK_FEE = Decimal("0.00002")
    
    for rpc in RPC_ENDPOINTS:
        try:
            lamports = int(amount_sol * Decimal(1_000_000_000))

            async with AsyncClient(rpc) as client:
                recent_blockhash_resp = await client.get_latest_blockhash()
                recent_blockhash = recent_blockhash_resp.value.blockhash

                from_pubkey = Pubkey.from_string(from_address)
                to_pubkey = Pubkey.from_string(to_address)

                transfer_ix = transfer(
                    TransferParams(
                        from_pubkey=from_pubkey,
                        to_pubkey=to_pubkey,
                        lamports=lamports
                    )
                )

                message = Message.new_with_blockhash(
                    [transfer_ix],
                    from_pubkey,
                    recent_blockhash
                )
                
                fee_response = await client.get_fee_for_message(message)
                if fee_response.value is not None:
                    fee_lamports = fee_response.value
                    return Decimal(fee_lamports) / Decimal(1_000_000_000)
                
                return NETWORK_FEE
        except Exception as e:
            print(f"Fee estimation error ({rpc[:30]}...): {e}, trying fallback...")
            continue
    
    print(f"Using default network fee: {NETWORK_FEE} SOL")
    return NETWORK_FEE


async def send_sol(from_address: str, to_address: str, amount_sol: Decimal, private_key_hex: str) -> Dict:
    """
    Send SOL from one address to another.
    Uses primary RPC with automatic fallback to ensure transaction success.
    Always fetches latest blockhash right before creating transaction.
    Returns transaction result dict.
    
    Updated to use correct solders 0.18.x transaction format.
    """
    # Network fee buffer for transaction
    NETWORK_FEE = Decimal("0.00002")
    
    # Check balance before attempting transaction
    current_balance = await get_real_balance(from_address)
    required_amount = amount_sol + NETWORK_FEE
    
    print(f"Transaction: {from_address[:8]}... -> {to_address[:8]}...")
    print(f"  Amount: {amount_sol} SOL + {NETWORK_FEE} SOL fee = {required_amount} SOL required")
    print(f"  Current balance: {current_balance} SOL")
    
    if current_balance < required_amount:
        error_msg = f"Insufficient balance. Have {current_balance} SOL, need {required_amount} SOL (including ~{NETWORK_FEE} SOL network fee)"
        print(f"  ERROR: {error_msg}")
        return {
            "success": False,
            "error": error_msg
        }
    
    last_error = None
    for rpc in RPC_ENDPOINTS:
        try:
            lamports = int(amount_sol * Decimal(1_000_000_000))
            private_key_bytes = bytes.fromhex(private_key_hex)
            keypair = Keypair.from_bytes(private_key_bytes)

            print(f"  Using RPC: {rpc[:30]}...")
            
            async with AsyncClient(rpc) as client:
                recent_blockhash_resp = await client.get_latest_blockhash()
                recent_blockhash = recent_blockhash_resp.value.blockhash
                print(f"  Latest blockhash: {str(recent_blockhash)[:20]}...")

                from_pubkey = Pubkey.from_string(from_address)
                to_pubkey = Pubkey.from_string(to_address)

                transfer_ix = transfer(
                    TransferParams(
                        from_pubkey=from_pubkey,
                        to_pubkey=to_pubkey,
                        lamports=lamports
                    )
                )

                message = Message.new_with_blockhash(
                    [transfer_ix],
                    from_pubkey,
                    recent_blockhash
                )
                
                transaction = Transaction([keypair], message, recent_blockhash)
                result = await client.send_raw_transaction(bytes(transaction))
                
                signature = str(result.value)
                print(f"  Transaction sent! Signature: {signature[:20]}...")

                return {
                    "success": True,
                    "signature": signature,
                    "amount": float(amount_sol),
                    "rpc_used": rpc[:30]
                }
        except Exception as e:
            last_error = e
            print(f"  RPC error ({rpc[:30]}...): {e}, trying fallback...")
            continue
    
    print(f"Error sending SOL after all RPC attempts: {last_error}")
    import traceback
    traceback.print_exc()
    return {
        "success": False,
        "error": str(last_error)
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


def set_user_pin(user_id: int, pin: str) -> bool:
    """
    Set or update user's 4-digit PIN
    PIN is hashed before storage
    """
    import hashlib
    
    # Validate PIN is 4 digits
    if not pin.isdigit() or len(pin) != 4:
        return False
    
    # Hash the PIN
    pin_hash = hashlib.sha256(pin.encode()).hexdigest()
    
    conn = get_db_conn()
    c = conn.cursor()
    c.execute("""
        INSERT INTO user_pins (user_id, pin_hash)
        VALUES (?, ?)
        ON CONFLICT(user_id) DO UPDATE SET pin_hash = ?
    """, (user_id, pin_hash, pin_hash))
    conn.commit()
    conn.close()
    return True


def verify_user_pin(user_id: int, pin: str) -> bool:
    """
    Verify user's PIN
    Returns True if PIN matches
    """
    import hashlib
    
    # Validate PIN format
    if not pin.isdigit() or len(pin) != 4:
        return False
    
    # Hash the provided PIN
    pin_hash = hashlib.sha256(pin.encode()).hexdigest()
    
    conn = get_db_conn()
    c = conn.cursor()
    c.execute("SELECT pin_hash FROM user_pins WHERE user_id = ?", (user_id,))
    row = c.fetchone()
    conn.close()
    
    if not row:
        return False
    
    return row[0] == pin_hash


def has_user_pin(user_id: int) -> bool:
    """Check if user has set a PIN"""
    conn = get_db_conn()
    c = conn.cursor()
    c.execute("SELECT 1 FROM user_pins WHERE user_id = ?", (user_id,))
    result = c.fetchone() is not None
    conn.close()
    return result


# ==============================================================================
# REAL-TIME TRANSACTION FUNCTIONS
# ==============================================================================
# These functions enable automatic Solana transactions signed by the bot.
# They build, sign, and send transactions in real-time using stored private keys.
#
# FLOW:
# 1. build_transaction() - Creates UNSIGNED message and instructions
# 2. sign_and_send_transaction() - Signs once and sends atomically
#
# Note: The primary send_sol() function above is the recommended way to send SOL.
# These helper functions are provided for more granular control if needed.

async def build_unsigned_transaction(sender_address: str, receiver_address: str, amount_sol: Decimal) -> Dict:
    """
    Build an UNSIGNED Solana SOL transfer transaction.
    Uses RPC_ENDPOINTS for automatic failover.
    """
    try:
        if amount_sol <= Decimal("0"):
            return {"success": False, "error": "Amount must be greater than 0"}
        
        lamports = int(amount_sol * Decimal(1_000_000_000))
        sender_pubkey = Pubkey.from_string(sender_address)
        to_pubkey = Pubkey.from_string(receiver_address)
        
        last_error = None
        for rpc in RPC_ENDPOINTS:
            try:
                async with AsyncClient(rpc) as client:
                    balance_resp = await client.get_balance(sender_pubkey, commitment=Confirmed)
                    if balance_resp.value is None:
                        continue
                    
                    balance_lamports = balance_resp.value
                    estimated_fee = 20000
                    
                    if balance_lamports < lamports + estimated_fee:
                        return {
                            "success": False, 
                            "error": f"Insufficient balance. Have: {balance_lamports/1e9:.6f} SOL, Need: {(lamports + estimated_fee)/1e9:.6f} SOL"
                        }
                    
                    recent_blockhash_resp = await client.get_latest_blockhash()
                    recent_blockhash = recent_blockhash_resp.value.blockhash
                    
                    transfer_ix = transfer(
                        TransferParams(
                            from_pubkey=sender_pubkey,
                            to_pubkey=to_pubkey,
                            lamports=lamports
                        )
                    )
                    
                    message = Message.new_with_blockhash(
                        [transfer_ix],
                        sender_pubkey,
                        recent_blockhash
                    )
                    
                    return {
                        "success": True,
                        "message": message,
                        "blockhash": recent_blockhash,
                        "sender_pubkey": sender_pubkey,
                        "receiver": receiver_address,
                        "amount_lamports": lamports,
                        "rpc_used": rpc
                    }
            except Exception as e:
                last_error = e
                print(f"Build tx RPC error ({rpc[:30]}...): {e}")
                continue
        
        return {"success": False, "error": str(last_error) if last_error else "All RPC endpoints failed"}
            
    except Exception as e:
        print(f"Error building unsigned transaction: {e}")
        import traceback
        traceback.print_exc()
        return {"success": False, "error": str(e)}


async def sign_and_send_transaction(message, blockhash, private_key_hex: str, rpc_url: Optional[str] = None) -> Dict:
    """
    Sign a transaction message and send it atomically.
    Uses RPC_ENDPOINTS for automatic failover.
    """
    try:
        if not private_key_hex or len(private_key_hex) != 128:
            return {"success": False, "error": "Invalid private key format"}
        
        private_key_bytes = bytes.fromhex(private_key_hex)
        keypair = Keypair.from_bytes(private_key_bytes)
        signed_tx = Transaction([keypair], message, blockhash)
        
        rpc_list = ([rpc_url] if rpc_url else []) + list(RPC_ENDPOINTS)
        
        last_error = None
        for rpc in rpc_list:
            if not rpc:
                continue
            try:
                async with AsyncClient(rpc) as client:
                    try:
                        result = await client.send_raw_transaction(bytes(signed_tx))
                    except Exception as rpc_error:
                        error_msg = str(rpc_error)
                        if "insufficient funds" in error_msg.lower():
                            return {"success": False, "error": "Insufficient funds for transaction"}
                        elif "blockhash" in error_msg.lower():
                            return {"success": False, "error": "Blockhash expired, please retry"}
                        else:
                            last_error = error_msg
                            continue
                    
                    signature = str(result.value)
                    
                    confirmed = False
                    for attempt in range(15):
                        await asyncio.sleep(1)
                        try:
                            status = await client.get_signature_statuses([result.value])
                            if status.value and status.value[0]:
                                if status.value[0].confirmation_status:
                                    confirmed = True
                                    break
                                if status.value[0].err:
                                    return {
                                        "success": False,
                                        "error": f"Transaction failed: {status.value[0].err}",
                                        "signature": signature
                                    }
                        except Exception:
                            pass
                    
                    return {
                        "success": True,
                        "signature": signature,
                        "confirmed": confirmed
                    }
            except Exception as e:
                last_error = str(e)
                print(f"Sign/send RPC error ({rpc[:30]}...): {e}")
                continue
        
        return {"success": False, "error": f"All RPC endpoints failed: {last_error}"}
            
    except ValueError as ve:
        return {"success": False, "error": f"Invalid key format: {ve}"}
    except Exception as e:
        print(f"Error signing and sending transaction: {e}")
        import traceback
        traceback.print_exc()
        return {"success": False, "error": str(e)}


async def execute_automatic_transfer(sender_private_key_hex: str, receiver_address: str, amount_sol: Decimal) -> Dict:
    """
    Complete automatic SOL transfer: build, sign, and send in one call.
    
    This is the main function for real-time automatic transactions.
    The bot signs using the stored private key and sends immediately.
    
    NOTE: For most use cases, prefer the send_sol() function which handles
    everything in a single call. This function provides the same functionality
    but is structured as a helper for the build/sign/send workflow.
    
    Args:
        sender_private_key_hex: The sender's private key in hex format
        receiver_address: The recipient's Solana wallet address
        amount_sol: Amount of SOL to transfer
    
    Returns:
        Dict with 'success', 'signature', 'amount', 'confirmed' or 'error'
    """
    try:
        # Validate inputs
        if not sender_private_key_hex or len(sender_private_key_hex) != 128:
            return {"success": False, "error": "Invalid private key format"}
        
        if not receiver_address:
            return {"success": False, "error": "Receiver address required"}
        
        if amount_sol <= Decimal("0"):
            return {"success": False, "error": "Amount must be greater than 0"}
        
        # Get sender address from private key
        private_key_bytes = bytes.fromhex(sender_private_key_hex)
        keypair = Keypair.from_bytes(private_key_bytes)
        sender_address = str(keypair.pubkey())
        
        # Step 1: Build unsigned transaction (validates balance)
        build_result = await build_unsigned_transaction(sender_address, receiver_address, amount_sol)
        if not build_result.get("success"):
            return {"success": False, "error": build_result.get("error", "Build failed")}
        
        # Step 2: Sign and send atomically (single signing)
        # Use the same RPC endpoint that was used to build the transaction
        send_result = await sign_and_send_transaction(
            build_result["message"],
            build_result["blockhash"],
            sender_private_key_hex,
            build_result.get("rpc_used")
        )
        if not send_result.get("success"):
            return {"success": False, "error": send_result.get("error", "Send failed")}
        
        return {
            "success": True,
            "signature": send_result["signature"],
            "amount": float(amount_sol),
            "confirmed": send_result.get("confirmed", False),
            "sender": sender_address,
            "receiver": receiver_address
        }
        
    except ValueError as ve:
        return {"success": False, "error": f"Invalid input: {ve}"}
    except Exception as e:
        print(f"Error in automatic transfer: {e}")
        import traceback
        traceback.print_exc()
        return {
            "success": False,
            "error": str(e)
        }