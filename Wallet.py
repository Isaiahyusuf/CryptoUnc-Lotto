# wallet.py
import os
import secrets
from solana.publickey import PublicKey
from solana.keypair import Keypair
from solana.rpc.async_api import AsyncClient

# Constants
SOLANA_RPC = os.getenv("SOLANA_RPC", "https://api.mainnet-beta.solana.com")
ADMIN_WALLET = os.getenv("ADMIN_WALLET")  # admin wallet to receive stakes

# In-memory wallet storage for demo (replace with DB for production)
user_wallets = {}  # {telegram_id: {"wallets": [{"address":..., "type":"phantom"/"bot"}], "active_wallet":...}}

# ------------------------
# Bot Wallet Creation
# ------------------------
def create_bot_wallet():
    """
    Creates an internal wallet for the bot (for the user)
    """
    keypair = Keypair()
    return {
        "address": str(keypair.public_key),
        "secret": keypair.secret_key.hex(),  # store securely if persistent
        "balance": 0,
        "type": "bot"
    }

# ------------------------
# Connect External Wallet
# ------------------------
def connect_external_wallet(telegram_id, wallet_address, wallet_type="phantom"):
    """
    Connect an external wallet (Phantom, Solflare, etc.)
    """
    wallet = {
        "address": wallet_address,
        "type": wallet_type,
        "balance": 0  # will fetch from chain
    }
    if telegram_id not in user_wallets:
        user_wallets[telegram_id] = {"wallets": [], "active_wallet": wallet_address}
    user_wallets[telegram_id]["wallets"].append(wallet)
    user_wallets[telegram_id]["active_wallet"] = wallet_address
    return wallet

# ------------------------
# Fetch Balance
# ------------------------
async def get_wallet_balance(wallet_address):
    """
    Fetch the balance of a Solana wallet
    """
    async with AsyncClient(SOLANA_RPC) as client:
        resp = await client.get_balance(PublicKey(wallet_address))
        lamports = resp['result']['value']
        sol_balance = lamports / 1_000_000_000
        return sol_balance

# ------------------------
# Get User Wallets
# ------------------------
def get_user_wallets(telegram_id):
    """
    Return a list of user wallets
    """
    if telegram_id in user_wallets:
        return user_wallets[telegram_id]["wallets"]
    return []

# ------------------------
# Get Active Wallet
# ------------------------
def get_active_wallet(telegram_id):
    """
    Return user's active wallet
    """
    if telegram_id in user_wallets:
        return user_wallets[telegram_id]["active_wallet"]
    return None

# ------------------------
# Select Wallet
# ------------------------
def set_active_wallet(telegram_id, wallet_address):
    """
    Set which wallet the user wants to use for a play
    """
    if telegram_id in user_wallets:
        for w in user_wallets[telegram_id]["wallets"]:
            if w["address"] == wallet_address:
                user_wallets[telegram_id]["active_wallet"] = wallet_address
                return True
    return False

# ------------------------
# Generate WalletConnect Link (Placeholder)
# ------------------------
def get_walletconnect_link(wallet_type="phantom"):
    """
    Return a WalletConnect link or QR code URL for the bot.
    Placeholder: implement actual WalletConnect session for Phantom/Solflare.
    """
    session_id = secrets.token_hex(8)
    return f"https://walletconnect.com/connect?session={session_id}&type={wallet_type}"

# ------------------------
# Deposit / Update Balance
# ------------------------
def add_funds(telegram_id, wallet_address, amount):
    """
    Add funds to a user's wallet (internal or external)
    """
    if telegram_id in user_wallets:
        for w in user_wallets[telegram_id]["wallets"]:
            if w["address"] == wallet_address:
                w["balance"] += amount
                return w["balance"]
    return None
