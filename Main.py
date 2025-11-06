# Main.py — CryptoUnc Lotto with Real Solana Wallet Integration

import os
import asyncio
import random
from decimal import Decimal

from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from dotenv import load_dotenv

from Wallet import (
    get_user_wallets,
    get_active_wallet,
    set_active_wallet,
    create_wallet,
    save_external_wallet,
    get_real_balance,
    send_sol,
    get_wallet_private_key,
    get_user_wallet_count,
    delete_wallet,
    MAX_WALLETS_PER_USER
)

import sqlite3

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
OWNER_WALLET = os.getenv("OWNER_WALLET")
TEAM_WALLET = os.getenv("TEAM_WALLET")
ADMIN_ID = int(os.getenv("ADMIN_ID", 0))
ROUND_CHANNEL = os.getenv("ROUND_CHANNEL_ID", "@cryptounclottoportal")

STAKE_PACKAGES = [
    Decimal("0.05"),
    Decimal("0.1"),
    Decimal("0.3"),
    Decimal("0.5"),
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

DB_PATH = "cryptounc_lotto.db"

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()


# ---------------------------
# Database helpers
# ---------------------------
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


# ---------------------------
# Bot Handlers
# ---------------------------
@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    save_user(message.from_user.id, message.from_user.username or "")
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🎲 Play", callback_data="play_now")],
        [InlineKeyboardButton(text="💼 My Wallets", callback_data="my_wallets")],
        [InlineKeyboardButton(text="📊 View Results", callback_data="view_results")],
        [InlineKeyboardButton(text="📘 Rules", callback_data="rules")],
        [InlineKeyboardButton(text="🛠 Support", callback_data="support")]
    ])
    await message.answer(
        "🎟️ <b>Welcome to CryptoUnc Lotto!</b>\n\n"
        "Play the lottery with real SOL on Solana mainnet!\n"
        "Pick 5 numbers (1–40) and choose your stake.\n",
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
        
        # Generate lottery numbers
        round_num = get_current_round()
        lottery_numbers = sorted(random.sample(range(1, 41), 5))
        add_entry(uid, round_num, lottery_numbers, float(amount), tx_signature, paid=1)
        
        await bot.send_message(uid,
            f"✅ <b>Payment successful!</b>\n\n"
            f"Transaction: <code>{tx_signature[:16]}...</code>\n"
            f"Amount: {amount} SOL\n\n"
            f"🎲 <b>Your lottery numbers for Round {round_num}:</b>\n"
            f"<b>{numbers_to_str(lottery_numbers)}</b>\n\n"
            f"Good luck! 🍀",
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
        await query.message.answer(
            "🛠 <b>Support</b>\n\n"
            "For help or questions, contact our support team.\n"
            "We're here to assist you!",
            parse_mode="HTML"
        )

    elif data == "view_results":
        await query.answer()
        cur_round = get_current_round()
        await bot.send_message(uid,
            f"📊 <b>Current Round:</b> {cur_round}\n\n"
            "Results will be announced after the draw!",
            parse_mode="HTML"
        )

    elif data == "back_to_main":
        await query.answer()
        await cmd_start(query.message)


@dp.message()
async def generic_message_handler(message: types.Message):
    uid = message.from_user.id
    text = message.text.strip()
    
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


# ---------------------------
# Admin commands
# ---------------------------
def is_admin(user_id):
    return user_id == ADMIN_ID


@dp.message(Command("admin_draw"))
async def cmd_admin_draw(message: types.Message):
    if not is_admin(message.from_user.id):
        await message.reply("⛔ Not authorized.")
        return
    
    cur_round = get_current_round()
    winning_numbers = sorted(random.sample(range(1, 41), 5))
    save_draw(cur_round, winning_numbers)

    # Announce winners
    rows = get_entries_for_round(cur_round)
    winners = []
    for row in rows:
        entry_id, uid, numbers_str, paid = row
        if not paid:
            continue
        entry_nums = str_to_numbers(numbers_str)
        if sorted(entry_nums) == winning_numbers:
            winners.append(uid)

    announce_text = (
        f"🏆 <b>CryptoUnc Lotto — Round {cur_round} Results</b>\n"
        f"Winning Numbers: <code>{numbers_to_str(winning_numbers)}</code>\n\n"
    )
    
    if winners:
        mentions = [f"<a href='tg://user?id={w}'>Player</a>" for w in winners]
        announce_text += "🎉 Winners:\n" + "\n".join(mentions)
    else:
        announce_text += "No winners this round. Better luck next time!"

    if ROUND_CHANNEL:
        try:
            await bot.send_message(ROUND_CHANNEL, announce_text, parse_mode="HTML")
        except Exception:
            await message.reply(announce_text, parse_mode="HTML")
    else:
        await message.reply(announce_text, parse_mode="HTML")

    increment_round()
    await message.reply(f"✅ Draw completed. Moved to Round {cur_round + 1}.")


# ---------------------------
# Startup
# ---------------------------
async def main():
    init_db()
    print("🤖 CryptoUnc Lotto Bot with Real Solana Integration starting...")
    print(f"📍 Connected to: {os.getenv('SOLANA_RPC', 'mainnet-beta')}")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
