import os
import asyncio
import sqlite3
import base64
import json
from aiogram import Bot, Dispatcher, types
from aiogram.utils import executor
from solana.keypair import Keypair
from solana.rpc.async_api import AsyncClient
from solana.publickey import PublicKey

# ---------------------------------------------------------------------
#  🔧 Environment Configuration (Mainnet)
# ---------------------------------------------------------------------
BOT_TOKEN = os.getenv("BOT_TOKEN")  # Telegram BotFather token
SOLANA_RPC = os.getenv("SOLANA_RPC", "https://api.mainnet-beta.solana.com")  # Mainnet only

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(bot)

# ---------------------------------------------------------------------
#  📦 Database (SQLite)
# ---------------------------------------------------------------------
conn = sqlite3.connect("lotto.db")
cur = conn.cursor()
cur.execute("""
CREATE TABLE IF NOT EXISTS wallets (
    user_id INTEGER,
    public_key TEXT,
    private_b64 TEXT,
    secret_json TEXT
)
""")
conn.commit()

# ---------------------------------------------------------------------
#  🪙 Solana Wallet Creation
# ---------------------------------------------------------------------
def create_wallet():
    kp = Keypair()
    secret_bytes = bytes(kp.secret_key)        # 64 bytes (secret + public)
    private_b64 = base64.b64encode(secret_bytes).decode()
    secret_json = json.dumps(list(secret_bytes))  # importable by Phantom
    pub = str(kp.public_key)
    return pub, private_b64, secret_json

@dp.message_handler(commands=["createwallet"])
async def create_wallet_cmd(message: types.Message):
    user_id = message.from_user.id
    cur.execute("SELECT public_key FROM wallets WHERE user_id=?", (user_id,))
    existing = cur.fetchone()
    if existing:
        await message.reply(f"🪙 You already have a wallet!\n\nPublic Key:\n`{existing[0]}`", parse_mode="Markdown")
        return

    pub, priv_b64, secret_json = create_wallet()
    cur.execute("INSERT INTO wallets VALUES (?,?,?,?)", (user_id, pub, priv_b64, secret_json))
    conn.commit()
    await message.reply(
        f"✅ Wallet created on *Solana Mainnet*!\n\nPublic Key:\n`{pub}`\n\nUse `/getprivate` to view your private key.",
        parse_mode="Markdown"
    )

# ---------------------------------------------------------------------
#  🔐 Private Key Access (User-only)
# ---------------------------------------------------------------------
@dp.message_handler(commands=["getprivate"])
async def get_private_cmd(message: types.Message):
    user_id = message.from_user.id
    cur.execute("SELECT private_b64, secret_json FROM wallets WHERE user_id=?", (user_id,))
    row = cur.fetchone()
    if not row:
        await message.reply("❌ No wallet found. Use /createwallet first.")
        return
    priv_b64, secret_json = row
    text = (
        "⚠️ *Your Private Key (KEEP SECRET!)*\n\n"
        f"Base64: `{priv_b64}`\n\n"
        f"JSON (Phantom import): `{secret_json}`"
    )
    await message.reply(text, parse_mode="Markdown")

# ---------------------------------------------------------------------
#  💰 Balance & Stake Check
# ---------------------------------------------------------------------
async def get_balance(pubkey: str) -> float:
    async with AsyncClient(SOLANA_RPC) as client:
        resp = await client.get_balance(PublicKey(pubkey))
        lamports = resp["result"]["value"]
        return lamports / 1e9

@dp.message_handler(commands=["balance"])
async def balance_cmd(message: types.Message):
    user_id = message.from_user.id
    cur.execute("SELECT public_key FROM wallets WHERE user_id=?", (user_id,))
    row = cur.fetchone()
    if not row:
        await message.reply("❌ No wallet found. Use /createwallet first.")
        return
    pubkey = row[0]
    bal = await get_balance(pubkey)
    await message.reply(f"💰 Wallet: `{pubkey}`\n\nMainnet Balance: {bal:.5f} SOL", parse_mode="Markdown")

# ---------------------------------------------------------------------
#  🎟 Lottery Play Example (requires ≥ 0.025 SOL)
# ---------------------------------------------------------------------
STAKE_SOL = 0.025  # change as needed

@dp.message_handler(commands=["play"])
async def play_cmd(message: types.Message):
    user_id = message.from_user.id
    cur.execute("SELECT public_key FROM wallets WHERE user_id=?", (user_id,))
    row = cur.fetchone()
    if not row:
        await message.reply("❌ You need a wallet. Use /createwallet first.")
        return

    pubkey = row[0]
    bal = await get_balance(pubkey)
    if bal < STAKE_SOL:
        await message.reply(
            f"⚠️ Insufficient balance.\n"
            f"You need at least {STAKE_SOL} SOL to play.\n\nCurrent balance: {bal:.5f} SOL"
        )
        return

    await message.reply(
        f"🎟 Entry accepted!\nYou’ve joined this round with {STAKE_SOL} SOL.\n(Games logic continues here...)"
    )

# ---------------------------------------------------------------------
#  🚀 Launch
# ---------------------------------------------------------------------
async def on_startup(dp):
    print("✅ Bot started on Solana Mainnet")

if __name__ == "__main__":
    executor.start_polling(dp, skip_updates=True, on_startup=on_startup)
