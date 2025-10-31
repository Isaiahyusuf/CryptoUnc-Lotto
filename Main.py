# main.py
import os
import asyncio
import random
import re
import sqlite3
from typing import Optional, List
from decimal import Decimal

import aiohttp
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
OWNER_WALLET = os.getenv("OWNER_WALLET", "AdsUp4UT3AAGv9m8fYAYXY5mMMAxkJXneVyd6MMwwBVR")
STAKE_AMOUNT_SOL = Decimal(os.getenv("STAKE_AMOUNT_SOL", "0.1"))
ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))  # set to your Telegram user id for admin commands
ROUND_CHANNEL = os.getenv("ROUND_CHANNEL_ID", "")  # optional: public announcements
SOLANA_RPC = os.getenv("SOLANA_RPC", "")  # optional: enable on-chain verification if set

if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN missing in .env")

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

DB_PATH = "cryptounc_lotto.db"

# ---------------------------
# Database helpers (SQLite)
# ---------------------------
def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    # users table
    c.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            username TEXT,
            sol_wallet TEXT
        )
    """)
    # entries table (each entry is a ticket for a round)
    c.execute("""
        CREATE TABLE IF NOT EXISTS entries (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            round INTEGER,
            numbers TEXT,
            paid INTEGER DEFAULT 0,
            tx_signature TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    # draws table
    c.execute("""
        CREATE TABLE IF NOT EXISTS draws (
            round INTEGER PRIMARY KEY,
            winning_numbers TEXT,
            drawn_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    # meta (current round)
    c.execute("""
        CREATE TABLE IF NOT EXISTS meta (
            key TEXT PRIMARY KEY,
            value TEXT
        )
    """)
    # ensure there's a current round
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
    cur = get_current_round() + 1
    c.execute("UPDATE meta SET value = ? WHERE key='current_round'", (str(cur),))
    conn.commit()
    conn.close()
    return cur

# ---------------------------
# Utilities
# ---------------------------
SOLANA_ADDR_REGEX = re.compile(r"^[1-9A-HJ-NP-Za-km-z]{32,44}$")

def validate_solana_address(addr: str) -> bool:
    return bool(SOLANA_ADDR_REGEX.fullmatch(addr.strip()))

def numbers_to_str(nums: List[int]) -> str:
    return ",".join(map(str, sorted(nums)))

def str_to_numbers(s: str) -> List[int]:
    return [int(x) for x in s.split(",") if x.strip()]

# ---------------------------
# Solana on-chain verification (optional)
# ---------------------------
async def verify_solana_payment(to_address: str, from_address: str, amount_sol: Decimal, rpc_url: str) -> Optional[str]:
    """
    Optional helper to check if a transaction of >= amount_sol was made to 'to_address' from 'from_address'.
    If SOLANA_RPC is not set, this function returns None.
    This is a best-effort check and may require adjustments for production (pagination, signatures).
    Returns the tx signature if found, else None.
    """
    if not rpc_url:
        return None

    lamports_needed = int(amount_sol * Decimal(10**9))

    async with aiohttp.ClientSession() as session:
        # 1) get signatures for address (most recent)
        payload = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "getSignaturesForAddress",
            "params": [to_address, {"limit": 50}]
        }
        try:
            async with session.post(rpc_url, json=payload, timeout=10) as resp:
                data = await resp.json()
        except Exception:
            return None

        sigs = data.get("result", [])
        for s in sigs:
            sig = s.get("signature")
            # fetch transaction details
            payload_tx = {"jsonrpc": "2.0", "id": 1, "method": "getTransaction", "params": [sig, "jsonParsed"]}
            async with session.post(rpc_url, json=payload_tx) as r2:
                tx_data = await r2.json()
            result = tx_data.get("result")
            if not result:
                continue
            # parse postBalances vs preBalances to find lamport change for owner
            meta = result.get("meta", {})
            # find inner instructions or message accountKeys - approximate method:
            # check if to_address is among account keys and if difference indicates incoming amount
            # Note: This heuristic may miss some tx types (spl transfers). For production, use a proper parser.
            pre_balances = meta.get("preBalances", [])
            post_balances = meta.get("postBalances", [])
            acc_keys = result.get("transaction", {}).get("message", {}).get("accountKeys", [])
            try:
                idx = acc_keys.index(to_address)
            except ValueError:
                continue
            change = post_balances[idx] - pre_balances[idx]
            if change >= lamports_needed:
                # optionally verify from_address is present in account keys too
                return sig
        return None

# ---------------------------
# Database operations (simple wrappers)
# ---------------------------
def save_user(user_id: int, username: str):
    conn = get_db_conn()
    c = conn.cursor()
    c.execute("INSERT OR REPLACE INTO users(user_id, username) VALUES (?, ?)", (user_id, username))
    conn.commit()
    conn.close()

def save_user_wallet(user_id: int, sol_wallet: str):
    conn = get_db_conn()
    c = conn.cursor()
    c.execute("UPDATE users SET sol_wallet = ? WHERE user_id = ?", (sol_wallet, user_id))
    conn.commit()
    conn.close()

def get_user_wallet(user_id: int) -> Optional[str]:
    conn = get_db_conn()
    c = conn.cursor()
    c.execute("SELECT sol_wallet FROM users WHERE user_id = ?", (user_id,))
    row = c.fetchone()
    conn.close()
    return row[0] if row and row[0] else None

def add_entry(user_id: int, round_num: int, numbers: List[int], paid: int=0, tx_signature: Optional[str]=None):
    conn = get_db_conn()
    c = conn.cursor()
    c.execute("INSERT INTO entries(user_id, round, numbers, paid, tx_signature) VALUES (?, ?, ?, ?, ?)",
              (user_id, round_num, numbers_to_str(numbers), paid, tx_signature))
    conn.commit()
    conn.close()

def mark_entry_paid_by_user(user_id: int, round_num: int, tx_sig: Optional[str]=None):
    conn = get_db_conn()
    c = conn.cursor()
    c.execute("UPDATE entries SET paid = 1, tx_signature = ? WHERE user_id = ? AND round = ?",
              (tx_sig, user_id, round_num))
    conn.commit()
    conn.close()

def get_entries_for_round(round_num: int):
    conn = get_db_conn()
    c = conn.cursor()
    c.execute("SELECT id, user_id, numbers, paid, tx_signature FROM entries WHERE round = ?", (round_num,))
    rows = c.fetchall()
    conn.close()
    return rows

def get_user_last_entry(user_id: int):
    conn = get_db_conn()
    c = conn.cursor()
    c.execute("SELECT round, numbers, paid, tx_signature FROM entries WHERE user_id = ? ORDER BY created_at DESC LIMIT 1", (user_id,))
    row = c.fetchone()
    conn.close()
    return row

def save_draw(round_num: int, winning_numbers: List[int]):
    conn = get_db_conn()
    c = conn.cursor()
    c.execute("INSERT OR REPLACE INTO draws(round, winning_numbers) VALUES (?, ?)", (round_num, numbers_to_str(winning_numbers)))
    conn.commit()
    conn.close()

# ---------------------------
# Bot command handlers
# ---------------------------
@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    save_user(message.from_user.id, message.from_user.username or "")
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton("🎲 Play", callback_data="play_now")],
        [InlineKeyboardButton("📊 View Results", callback_data="view_results")],
        [InlineKeyboardButton("📘 Rules", callback_data="rules")],
        [InlineKeyboardButton("🛠 Support", callback_data="support")],
        [InlineKeyboardButton("💳 Connect Wallet", callback_data="connect_wallet")]
    ])
    await message.answer(
        f"🎟️ <b>CryptoUnc Lotto</b>\n\nPick 5 numbers (1–40). Stake: <b>{STAKE_AMOUNT_SOL} SOL</b>\n\nAdmin Wallet:\n<code>{OWNER_WALLET}</code>\n\nUse the buttons below to start.",
        reply_markup=keyboard,
        parse_mode="HTML"
    )

@dp.message(Command("help"))
async def cmd_help(message: types.Message):
    await message.reply(
        "Commands:\n"
        "/start - show menu\n"
        "/play - start a private play session\n"
        "/connect_wallet - save your Solana wallet address\n"
        "/stake - get a deep link to pay the stake\n        /my_numbers - view your last entry\n"
        "/rules - game rules\n"
        "/support - contact support\n"
        "Admin commands (admin only):\n"
        "/admin_draw - draw winners for current round\n"
        "/admin_list - list entries for current round\n"
        "/admin_reset - reset current round\n    "
    )

@dp.message(Command("play"))
async def cmd_play(message: types.Message):
    await start_private_play(message.from_user.id)

async def start_private_play(user_id: int):
    try:
        save_user(user_id, "")  # ensure user exists
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton("💳 Connect Wallet", callback_data="connect_wallet")],
            [InlineKeyboardButton("💵 Pay Stake", callback_data="pay_stake")],
            [InlineKeyboardButton("ℹ️ How to Play", callback_data="rules")]
        ])
        await bot.send_message(user_id,
            "🎮 <b>Private Lotto Session</b>\n\n"
            "1) Connect your Solana wallet\n2) Pay the stake\n3) Confirm payment -> receive your 5 numbers privately",
            reply_markup=keyboard,
            parse_mode="HTML"
        )
    except Exception:
        # user may have blocked DMs
        return

@dp.callback_query()
async def inline_menu_handler(query: types.CallbackQuery):
    data = query.data
    uid = query.from_user.id

    if data == "play_now":
        await query.answer()
        await start_private_play(uid)
    elif data == "view_results":
        round_num = get_current_round()
        draws = get_entries_for_round(round_num)
        # try to get stored winning numbers
        conn = get_db_conn()
        c = conn.cursor()
        c.execute("SELECT winning_numbers FROM draws WHERE round = ?", (round_num,))
        r = c.fetchone()
        conn.close()
        if r:
            await query.message.answer(f"📊 Round {round_num} Winning Numbers: <b>{r[0]}</b>", parse_mode="HTML")
        else:
            await query.message.answer(f"📊 Round {round_num} — not drawn yet.", parse_mode="HTML")
    elif data == "rules":
        await query.message.answer(
            "📘 <b>Game Rules</b>\n"
            f"• Pick 5 unique numbers from 1–40.\n"
            f"• Stake: {STAKE_AMOUNT_SOL} SOL per entry.\n"
            "• Match all 5 numbers to win the jackpot.\n"
            "• Entries must be paid and confirmed before draw.\n",
            parse_mode="HTML"
        )
    elif data == "support":
        await query.message.answer("🛠 Support: Describe your issue here or contact the admin directly.")
    elif data == "connect_wallet":
        await query.answer()
        await bot.send_message(uid, "🔗 Please send your Solana wallet address (paste the public key):")
    elif data == "pay_stake":
        await query.answer()
        sol_uri = f"solana:{OWNER_WALLET}?amount={str(STAKE_AMOUNT_SOL)}"
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text=f"💵 Pay {STAKE_AMOUNT_SOL} SOL", url=sol_uri)],
            [InlineKeyboardButton(text="✅ I Paid", callback_data="confirm_paid")]
        ])
        await bot.send_message(uid, f"Send {STAKE_AMOUNT_SOL} SOL to:\n<code>{OWNER_WALLET}</code>", reply_markup=keyboard, parse_mode="HTML")
    elif data == "confirm_paid":
        await query.answer()
        await handle_paid_confirmation(uid, query.message.chat.id)

@dp.message()
async def generic_message_handler(message: types.Message):
    text = message.text.strip()
    user_id = message.from_user.id

    # If message looks like a Solana address, treat it as wallet input
    if validate_solana_address(text):
        save_user(user_id, message.from_user.username or "")
        save_user_wallet(user_id, text)
        await bot.send_message(user_id, f"✅ Saved Solana wallet: <code>{text}</code>\nNow pay the stake via /stake or press 'Pay Stake' in the menu.", parse_mode="HTML")
        return

    # If user types 5 numbers, try to parse new entry
    parts = text.split()
    if len(parts) == 5:
        try:
            nums = [int(x) for x in parts]
            if len(set(nums)) != 5:
                await message.reply("⚠️ Numbers must be unique.")
                return
            if any(n < 1 or n > 40 for n in nums):
                await message.reply("⚠️ Numbers must be between 1 and 40.")
                return
            # save entry with paid=0 for now
            round_num = get_current_round()
            add_entry(user_id, round_num, nums, paid=0)
            await message.reply(
                f"🎟️ Entry saved for round {round_num}. Your numbers: {numbers_to_str(nums)}\n"
                f"Now send {STAKE_AMOUNT_SOL} SOL to the pool wallet ({OWNER_WALLET}) and confirm with 'I Paid' (or press 'Pay Stake').",
                parse_mode="HTML"
            )
            return
        except ValueError:
            pass

    # default reply
    await message.reply("I didn't understand. Use /help to see commands or press the buttons in the menu.")

@dp.message(Command("connect_wallet"))
async def cmd_connect_wallet(message: types.Message):
    await message.reply("🔗 Please send your Solana wallet address (public key). Example:\nAdsUp4UT3AAGv9m8fYAYXY5mMMAxkJXneVyd6MMwwBVR")

@dp.message(Command("stake"))
async def cmd_stake(message: types.Message):
    sol_uri = f"solana:{OWNER_WALLET}?amount={str(STAKE_AMOUNT_SOL)}"
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=f"💵 Pay {STAKE_AMOUNT_SOL} SOL", url=sol_uri)],
        [InlineKeyboardButton(text="✅ I Paid", callback_data="confirm_paid")]
    ])
    await message.reply(f"Send {STAKE_AMOUNT_SOL} SOL to:\n<code>{OWNER_WALLET}</code>", reply_markup=keyboard, parse_mode="HTML")

@dp.message(Command("my_numbers"))
async def cmd_my_numbers(message: types.Message):
    row = get_user_last_entry(message.from_user.id)
    if not row:
        await message.reply("You have not entered any numbers yet. Use /play to start.")
        return
    round_num, nums, paid, tx = row
    paid_text = "Yes" if paid else "No"
    await message.reply(f"Round: {round_num}\nNumbers: {nums}\nPaid: {paid_text}\nTx: {tx or 'N/A'}")

@dp.message(Command("rules"))
async def cmd_rules(message: types.Message):
    await message.reply(
        "📘 Game Rules:\n"
        "• Pick 5 unique numbers from 1–40.\n"
        f"• Each entry costs {STAKE_AMOUNT_SOL} SOL.\n"
        "• Match all 5 to win the jackpot.\n",
        parse_mode="HTML"
    )

@dp.message(Command("support"))
async def cmd_support(message: types.Message):
    await message.reply("🛠 Support is not yet configured. Please contact the admin directly.")

# ---------------------------
# Payment confirmation flow
# ---------------------------
async def handle_paid_confirmation(user_id: int, reply_chat_id: int):
    """
    When user presses 'I Paid' — we either:
      - Check on-chain (if SOLANA_RPC provided) for a matching tx
      - Or accept manual confirmation and mark paid (admin should verify later)
    """
    round_num = get_current_round()
    user_wallet = get_user_wallet(user_id)
    if not user_wallet:
        await bot.send_message(user_id, "⚠️ You must save your wallet first (use Connect Wallet).")
        return

    # if RPC configured, try to auto-verify tx
    if SOLANA_RPC:
        await bot.send_message(user_id, "🔎 Checking Solana blockchain for payment (this may take a few seconds)...")
        sig = await verify_solana_payment(OWNER_WALLET, user_wallet, STAKE_AMOUNT_SOL, SOLANA_RPC)
        if sig:
            mark_entry_paid_by_user(user_id, round_num, tx_sig=sig)
            await bot.send_message(user_id, f"✅ Payment verified on-chain (tx: <code>{sig}</code>). Your entry is confirmed. Good luck!", parse_mode="HTML")
            return
        else:
            await bot.send_message(user_id, "⚠️ No matching on-chain payment found. If you already paid, wait a few confirmations and try again, or contact support.")
            return
    else:
        # manual flow: mark paid=1 but record no tx (admin may verify)
        mark_entry_paid_by_user(user_id, round_num, tx_sig=None)
        await bot.send_message(user_id, "✅ Payment marked as received (manual confirmation). Your entry is confirmed. Good luck!")

# ---------------------------
# Admin commands
# ---------------------------
def admin_only(func):
    async def wrapper(message: types.Message):
        if message.from_user.id != ADMIN_ID:
            await message.reply("⛔ You are not authorized to use this command.")
            return
        await func(message)
    return wrapper

@dp.message(Command("admin_list"))
async def cmd_admin_list(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        await message.reply("⛔ Not authorized.")
        return
    r = get_current_round()
    rows = get_entries_for_round(r)
    if not rows:
        await message.reply(f"No entries for round {r}.")
        return
    out = [f"ID:{row[0]} UID:{row[1]} NUMS:{row[2]} PAID:{'Yes' if row[3] else 'No'} TX:{row[4] or 'N/A'}" for row in rows]
    # chunk output to avoid huge messages
    for i in range(0, len(out), 20):
        await message.reply("\n".join(out[i:i+20]))

@dp.message(Command("admin_reset"))
async def cmd_admin_reset(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        await message.reply("⛔ Not authorized.")
        return
    conn = get_db_conn()
    c = conn.cursor()
    cur_round = get_current_round()
    c.execute("DELETE FROM entries WHERE round = ?", (cur_round,))
    conn.commit()
    conn.close()
    await message.reply(f"✅ Cleared entries for round {cur_round}.")

@dp.message(Command("admin_draw"))
async def cmd_admin_draw(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        await message.reply("⛔ Not authorized.")
        return
    # draw winners for current round
    cur_round = get_current_round()
    winning_numbers = sorted(random.sample(range(1, 41), 5))
    save_draw(cur_round, winning_numbers)

    # find winners (paid entries that match all 5 numbers)
    rows = get_entries_for_round(cur_round)
    winners = []
    for row in rows:
        entry_id, uid, numbers_str, paid, tx = row
        if not paid:
            continue
        entry_nums = str_to_numbers(numbers_str)
        if sorted(entry_nums) == winning_numbers:
            winners.append(uid)

    # announce
    announce_text = f"🏆 <b>CryptoUnc Lotto — Round {cur_round} Results</b>\nWinning Numbers: <code>{numbers_to_str(winning_numbers)}</code>\n\n"
    if winners:
        mentions = []
        for w in winners:
            mentions.append(f"<a href='tg://user?id={w}'>Player</a>")
        announce_text += "Winners:\n" + "\n".join(mentions)
    else:
        announce_text += "No winners this round. Better luck next time!"

    # send to configured channel or reply to admin
    if ROUND_CHANNEL:
        try:
            await bot.send_message(ROUND_CHANNEL, announce_text, parse_mode="HTML")
        except Exception:
            await message.reply("Could not post to ROUND_CHANNEL. Announcing to the admin instead.")
            await message.reply(announce_text, parse_mode="HTML")
    else:
        await message.reply(announce_text, parse_mode="HTML")

    # increment round for next lottery
    new_round = increment_round()
    await message.reply(f"✅ Draw completed. Moved to round {new_round}.")

# ---------------------------
# Startup
# ---------------------------
if __name__ == "__main__":
    init_db()
    print("🤖 CryptoUnc Lotto TG Bot starting...")
    asyncio.run(dp.start_polling(bot))
