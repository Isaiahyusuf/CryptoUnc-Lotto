# main.py — CryptoUnc Lotto with Wallet Integration

import os
import asyncio
import random
from decimal import Decimal

from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from dotenv import load_dotenv

from wallet import (
    get_user_wallet,
    create_wallet,
    get_wallet_balance,
    deduct_wallet_balance,
    add_funds_to_wallet,
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


def add_entry(user_id: int, round_num: int, numbers, paid=0):
    conn = get_db_conn()
    c = conn.cursor()
    c.execute(
        "INSERT INTO entries(user_id, round, numbers, paid) VALUES (?, ?, ?, ?)",
        (user_id, round_num, numbers_to_str(numbers), paid)
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
        [InlineKeyboardButton(text="📊 View Results", callback_data="view_results")],
        [InlineKeyboardButton(text="📘 Rules", callback_data="rules")],
        [InlineKeyboardButton(text="🛠 Support", callback_data="support")]
    ])
    await message.answer(
        "🎟️ <b>Welcome to CryptoUnc Lotto!</b>\n\nPick 5 numbers (1–40). Choose stake from available packages.\n",
        reply_markup=keyboard,
        parse_mode="HTML"
    )


async def start_private_play(user_id: int):
    # Check wallet first
    wallet = get_user_wallet(user_id)
    keyboard = InlineKeyboardMarkup()
    if wallet:
        # User has wallet
        keyboard.inline_keyboard = [
            [InlineKeyboardButton(text="💵 Choose Stake", callback_data="choose_stake")],
            [InlineKeyboardButton(text="Add Funds", callback_data="add_funds")],
            [InlineKeyboardButton(text="ℹ️ How to Play", callback_data="rules")]
        ]
        await bot.send_message(user_id,
            f"🎮 <b>Private Lotto Session</b>\n\nWallet detected: <code>{wallet}</code>\nChoose your next action.",
            reply_markup=keyboard,
            parse_mode="HTML"
        )
    else:
        # Offer create/connect wallet
        keyboard.inline_keyboard = [
            [InlineKeyboardButton(text="💳 Create Wallet", callback_data="create_wallet")],
            [InlineKeyboardButton(text="🔗 Connect Wallet", callback_data="connect_wallet")],
            [InlineKeyboardButton(text="ℹ️ How to Play", callback_data="rules")]
        ]
        await bot.send_message(user_id,
            "🎮 <b>Private Lotto Session</b>\n\nYou need a wallet to play. Choose an option below.",
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

    elif data == "create_wallet":
        await query.answer()
        pubkey = create_wallet(uid)
        await bot.send_message(uid,
            f"✅ Wallet created successfully!\nYour wallet: <code>{pubkey}</code>\nYou can now add funds and play.",
            parse_mode="HTML"
        )
        await start_private_play(uid)

    elif data == "connect_wallet":
        await query.answer()
        await bot.send_message(uid, "🔗 Please send your existing wallet public key now:")

    elif data == "choose_stake":
        await query.answer()
        # show stake packages
        rows = []
        temp = []
        for i, pkg in enumerate(STAKE_PACKAGES, 1):
            temp.append(InlineKeyboardButton(text=f"{pkg} SOL", callback_data=f"stake_{pkg}"))
            if i % 3 == 0:
                rows.append(temp)
                temp = []
        if temp:
            rows.append(temp)
        keyboard = InlineKeyboardMarkup(inline_keyboard=rows)
        await bot.send_message(uid, "💵 Choose a stake package:", reply_markup=keyboard)

    elif data.startswith("stake_"):
        await query.answer()
        amount = Decimal(data.split("_", 1)[1])
        wallet_balance = get_wallet_balance(uid)
        if wallet_balance < amount:
            await bot.send_message(uid,
                f"⚠️ Insufficient funds in wallet. Your balance: {wallet_balance} SOL.\nAdd funds to play.",
                parse_mode="HTML"
            )
            return
        # Deduct funds (split 80/20)
        owner_amt = round(amount * Decimal("0.8"), 9)
        team_amt = amount - owner_amt
        deduct_wallet_balance(uid, amount)  # subtract total
        add_funds_to_wallet(OWNER_WALLET, owner_amt)
        add_funds_to_wallet(TEAM_WALLET, team_amt)

        # Generate numbers
        round_num = get_current_round()
        lottery_numbers = sorted(random.sample(range(1, 41), 5))
        add_entry(uid, round_num, lottery_numbers, paid=1)
        await bot.send_message(uid,
            f"✅ Stake paid!\n🎲 Your lottery numbers for Round {round_num}:\n<b>{numbers_to_str(lottery_numbers)}</b>\nGood luck!",
            parse_mode="HTML"
        )

    elif data == "rules":
        await query.message.answer(
            "📘 <b>Game Rules</b>\n1. Connect wallet\n2. Add funds if needed\n3. Choose stake\n4. Receive 5 random numbers\n5. Wait for admin draw",
            parse_mode="HTML"
        )

    elif data == "add_funds":
        await query.answer()
        await bot.send_message(uid,
            "💰 Add funds to your wallet using your Solana wallet. This feature can be connected to real payment flow later.",
            parse_mode="HTML"
        )


@dp.message()
async def generic_message_handler(message: types.Message):
    uid = message.from_user.id
    text = message.text.strip()
    # If user is connecting wallet
    if len(text) > 30:  # crude check for a public key
        pubkey = text
        from wallet import save_user_wallet
        save_user_wallet(uid, pubkey)
        await bot.send_message(uid,
            f"✅ Wallet connected: <code>{pubkey}</code>\nNow you can play!",
            parse_mode="HTML"
        )
        await start_private_play(uid)


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

    # announce winners
    rows = get_entries_for_round(cur_round)
    winners = []
    for row in rows:
        entry_id, uid, numbers_str, paid = row
        if not paid:
            continue
        entry_nums = str_to_numbers(numbers_str)
        if sorted(entry_nums) == winning_numbers:
            winners.append(uid)

    announce_text = f"🏆 <b>CryptoUnc Lotto — Round {cur_round} Results</b>\nWinning Numbers: <code>{numbers_to_str(winning_numbers)}</code>\n\n"
    if winners:
        mentions = [f"<a href='tg://user?id={w}'>Player</a>" for w in winners]
        announce_text += "Winners:\n" + "\n".join(mentions)
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
    await message.reply(f"✅ Draw completed. Moved to next round.")


# ---------------------------
# Startup
# ---------------------------
async def main():
    init_db()
    print("🤖 CryptoUnc Lotto TG Bot with Wallet Integration starting...")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
