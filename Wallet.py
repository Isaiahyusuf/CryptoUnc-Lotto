# wallet.py
import os
import secrets
from decimal import Decimal

try:
    from solders.keypair import Keypair
except ImportError:
    from solana.keypair import Keypair

# In-memory wallet storage (for demo - replace with DB for production)
user_wallets = {}  # {user_id: {"address": str, "balance": Decimal, "type": str}}
wallet_balances = {}  # {wallet_address: Decimal} - for OWNER_WALLET and TEAM_WALLET

def get_user_wallet(user_id):
    """
    Get user's wallet address
    Returns: wallet address (str) or None
    """
    if user_id in user_wallets:
        return user_wallets[user_id]["address"]
    return None


def create_wallet(user_id):
    """
    Creates an internal wallet for the user
    Returns: public key (str)
    """
    keypair = Keypair()
    pubkey = str(keypair.pubkey())
    
    user_wallets[user_id] = {
        "address": pubkey,
        "balance": Decimal("0"),
        "type": "bot"
    }
    
    return pubkey


def save_user_wallet(user_id, wallet_address):
    """
    Save an external wallet address for a user
    """
    user_wallets[user_id] = {
        "address": wallet_address,
        "balance": Decimal("0"),
        "type": "external"
    }


def get_wallet_balance(user_id):
    """
    Get user's wallet balance
    Returns: Decimal balance
    """
    if user_id in user_wallets:
        return user_wallets[user_id]["balance"]
    return Decimal("0")


def deduct_wallet_balance(user_id, amount):
    """
    Deduct amount from user's wallet balance
    """
    if user_id in user_wallets:
        user_wallets[user_id]["balance"] -= Decimal(str(amount))


def add_funds_to_wallet(wallet_address, amount):
    """
    Add funds to a wallet (used for OWNER_WALLET, TEAM_WALLET, or user wallets)
    """
    # Check if it's a user wallet
    for user_id, wallet_data in user_wallets.items():
        if wallet_data["address"] == wallet_address:
            wallet_data["balance"] += Decimal(str(amount))
            return
    
    # Otherwise track in wallet_balances (for owner/team wallets)
    if wallet_address not in wallet_balances:
        wallet_balances[wallet_address] = Decimal("0")
    wallet_balances[wallet_address] += Decimal(str(amount))


def add_user_funds(user_id, amount):
    """
    Add funds to a user's wallet balance (for testing/demo purposes)
    """
    if user_id not in user_wallets:
        return False
    
    user_wallets[user_id]["balance"] += Decimal(str(amount))
    return True
