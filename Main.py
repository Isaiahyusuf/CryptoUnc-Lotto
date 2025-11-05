import os
import asyncio
import random
import re
import sqlite3
from typing import Optional, List, Tuple
from decimal import Decimal
import json
import math

import aiohttp
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from dotenv import load_dotenv

# Solana libs
from solders.keypair import Keypair
from solders.pubkey import Pubkey
from solana.rpc.async_api import AsyncClient
from solana.rpc.commitment import Confirmed

load_dotenv()

# ---------------------------
# Config (from Replit secrets / .env)
# ---------------------------
BOT_TOKEN = os.getenv("BOT_TOKEN")
OWNER_WALLET = os.getenv("OWNER_WALLET", "AdsUp4UT3AAGv9m8fYAYXY5mMMAxkJXneVyd6MMwwBVR")
TEAM_WALLET = os.getenv("TEAM_WALLET", "7GVdD9ZPFb3mHdMJ8zhNeGvoSTZxoeWDgvJcGdp1Utiv")
STAKE_AMOUNT_DEFAULT = Decimal(os.getenv("STAKE_AMOUNT_SOL", "0.1"))
ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))
ROUND_CHANNEL = os.getenv("ROUND_CHANNEL_ID", "@cryptounclottoportal")
SOLANA_RPC = os.getenv("SOLANA_RPC", "https://api.devnet.solana.com")  # use devnet by default for testing

if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN missing in environment")

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
            sol_wallet TEXT,
            deposit_address TEXT,
            deposit_keypair TEXT,
            last_checked_signature TEXT
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

def split_amount(amount: Decimal) -> Tuple[Decimal, Decimal]:
    """
    Returns (owner_amount, team_amount) with proper rounding to 9 decimals (lamports precision)
    """
    # lamports precision
    lamports = int((amount * Decimal(10**9)).to_integral_value(rounding="ROUND_DOWN"))
    owner_lamports = (lamports * 80) // 100
    team_lamports = lamports - owner_lamports
    owner = Decimal(owner_lamports) / Decimal(10**9)
    team = Decimal(team_lamports) / Decimal(10**9)
    return owner, team

# ---------------------------
# Deposit address system (per-user deposit keys) - keep to support auto-detect if desired
# ---------------------------
def generate_deposit_address(user_id: int) -> tuple[str, str]:
    """
    Generate a unique Solana deposit address for a user (keypair stored in DB).
    Returns (public_key_str, keypair_json_str)
    """
    keypair = Keypair()
    public_key = str(keypair.pubkey())
    keypair_bytes = list(bytes(keypair))
    keypair_json = json.dumps(keypair_bytes)
    return public_key, keypair_json

def get_or_create_deposit_address(user_id: int) -> str:
    conn = get_db_conn()
    c = conn.cursor()
    c.execute("SELECT deposit_address, deposit_keypair FROM users WHERE user_id = ?", (user_id,))
    row = c.fetchone()
    if row and row[0]:
        conn.close()
        return row[0]
    public_key, keypair_json = generate_deposit_address(user_id)
    c.execute("INSERT OR REPLACE INTO users(user_id, username, deposit_address, deposit_keypair) VALUES (?, ?, ?, ?)",
              (user_id, "", public_key, keypair_json))
    conn.commit()
    conn.close()
    return public_key

# ---------------------------
# On-chain checking helpers
# ---------------------------
async def find_incoming_payment_for_address(to_address: str, min_amount_sol: Decimal, rpc_url: str, limit_signatures: int=50) -> Optional[str]:
    """
    Look up recent transactions for the 'to_address' and return a signature where
    the balance increase to that address is >= min_amount_sol. Returns signature or None.
    """
    if not rpc_url:
        return None

    try:
        async with AsyncClient(rpc_url) as client:
            # get signatures for address
            res = await client.get_signatures_for_address(Pubkey.from_string(to_address), limit=limit_signatures)
            if not res.value:
                return None
            for sig_info in res.value:
                sig = str(sig_info.signature)
                tx = await client.get_transaction(sig, max_supported_transaction_version=0)
                if not tx.value:
                    continue
                meta = tx.value.transaction.meta
                if not meta:
                    continue
                # find index of to_address in account keys
                try:
                    keys = tx.value.transaction.transaction.message.account_keys
                    idx = keys.index(Pubkey.from_string(to_address))
                except Exception:
                    continue
                pre_bal = meta.pre_balances[idx]
                post_bal = meta.post_balances[idx]
                if post_bal - pre_bal >= int(min_amount_sol * Decimal(10**9)):
                    return sig
            return None
    except Exception as e:
        print(f"Error in find_incoming_payment_for_address: {e}")
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
# Stake packages (exact list as requested)
# ---------------------------
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

# ---------------------------
# Bot command handlers & flows
# ---------------------------

@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    save_user(message.from_user.id, message.from_user.username or "")
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🎲 Play", callback_data="play_now")],
        [InlineKeyboardButton(text="📊 View Results", callback_data="view_results")],
        [InlineKeyboardButton(text="📘 Rules", callback_data="rules")],
        [InlineKeyboardButton(text="🛠 Support", callback_data="support")],
        [InlineKeyboardButton(text="💳 Connect Wallet", callback_data="connect_wallet")]
    ])
    await message.answer(
        f"🎟️ <b>CryptoUnc Lotto</b>\n\nPick 5 numbers (1–40). Choose stake from available packages.\n\nAdmin Wallet: <code>{OWNER_WALLET}</code>\nTeam Wallet: <code>{TEAM_WALLET}</code>\n\nUse the buttons below to start.",
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
        "/stake - choose a stake package and get payment links\n"
        "/my_numbers - view your last entry\n"
        "/rules - game rules\n"
        "/support - contact support\n"
        "Admin commands (admin only):\n"
        "/admin_draw - draw winners for current round\n"
        "/admin_list - list entries for current round\n"
        "/admin_reset - reset current round\n"
    )

@dp.message(Command("play"))
async def cmd_play(message: types.Message):
    await start_private_play(message.from_user.id)

async def start_private_play(user_id: int):
    try:
        save_user(user_id, "")  # ensure user exists
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="💳 Connect Wallet", callback_data="connect_wallet")],
            [InlineKeyboardButton(text="💵 Choose Stake", callback_data="choose_stake")],
            [InlineKeyboardButton(text="ℹ️ How to Play", callback_data="rules")]
        ])
        await bot.send_message(user_id,
            "🎮 <b>Private Lotto Session</b>\n\n"
            "1) Connect your Solana wallet\n2) Choose stake package\n3) Pay the split (80/20) -> Confirm payment -> receive your 5 numbers privately",
            reply_markup=keyboard,
            parse_mode="HTML"
        )
    except Exception:
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
            f"• Choose a stake package from the list.\n"
            f"• Stake is split 80% prize pool / 20% team.\n"
            f"• Entries must be paid and confirmed before draw.\n",
            parse_mode="HTML"
        )

    elif data == "support":
        await query.message.answer("🛠 Support: Describe your issue here or contact the admin directly.")

    elif data == "connect_wallet":
        await query.answer()
        # Show wallet provider buttons
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [
                InlineKeyboardButton(text="Phantom (Open App)", callback_data="provider_phantom"),
                InlineKeyboardButton(text="Solflare (Open App)", callback_data="provider_solflare")
            ],
            [
                InlineKeyboardButton(text="Sollet / Other", callback_data="provider_sollet")
            ],
            [
                InlineKeyboardButton(text="Paste Public Key (I have a wallet)", callback_data="paste_pubkey")
            ]
        ])
        await bot.send_message(uid,
            "🔗 <b>Connect Your Wallet</b>\n\n"
            "Choose your wallet provider (this will open an instruction). If you already have a public key, tap 'Paste Public Key' and paste it.",
            reply_markup=keyboard,
            parse_mode="HTML"
        )

    elif data.startswith("provider_"):
        await query.answer()
        provider = data.split("_", 1)[1]
        # Just show instructions — deep linking is wallet-specific and may not work universally
        if provider == "phantom":
            await bot.send_message(uid,
                "📱 Phantom instructions:\n\n"
                "1) Open Phantom on your device.\n"
                "2) Tap your wallet and copy your public key (address).\n"
                "3) Paste it here in this chat.\n\n"
                "If you want automatic/web-based connect later, we'll add WalletConnect support.",
                parse_mode="HTML"
            )
        elif provider == "solflare":
            await bot.send_message(uid,
                "📱 Solflare instructions:\n\n"
                "1) Open Solflare wallet app.\n"
                "2) Copy your public key and paste it here.\n\n"
                "If you prefer web-based connect later we'll add that.",
                parse_mode="HTML"
            )
        else:
            await bot.send_message(uid,
                "📱 Sollet/Other wallet instructions:\n\n"
                "1) Open your wallet app or extension.\n"
                "2) Copy the public key and paste it into this chat.",
                parse_mode="HTML"
            )

    elif data == "paste_pubkey":
        await query.answer()
        await bot.send_message(uid, "🔁 Please paste your Solana public key (public address) now:")

    elif data == "choose_stake":
        await query.answer()
        # build keyboard with packages (3 per row)
        rows = []
        temp = []
        for i, pkg in enumerate(STAKE_PACKAGES, 1):
            temp.append(InlineKeyboardButton(text=f"{pkg} SOL", callback_data=f"stake_{pkg}"))
            if i % 3 == 0:
                rows.append(temp)
                temp = []
        if temp:
            rows.append(temp)
        rows.append([InlineKeyboardButton(text="⬅️ Back", callback_data="play_now")])
        keyboard = InlineKeyboardMarkup(inline_keyboard=rows)
        await bot.send_message(uid, "💵 Choose a stake package:", reply_markup=keyboard)

    elif data.startswith("stake_"):
        await query.answer()
        amount_str = data.split("_", 1)[1]
        try:
            amount = Decimal(amount_str)
        except Exception:
            await bot.send_message(uid, "❌ Invalid stake selected.")
            return

        owner_amt, team_amt = split_amount(amount)
        # Generate two solana deep links
        owner_link = f"solana:{OWNER_WALLET}?amount={str(owner_amt)}"
        team_link = f"solana:{TEAM_WALLET}?amount={str(team_amt)}"

        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text=f"💰 Pay Prize Pool {owner_amt} SOL", url=owner_link)],
            [InlineKeyboardButton(text=f"🧾 Pay Team {team_amt} SOL", url=team_link)],
            [InlineKeyboardButton(text="✅ I Paid (Check On-Chain)", callback_data=f"confirm_paid_{amount}")],
            [InlineKeyboardButton(text="⬅️ Back", callback_data="choose_stake")]
        ])

        # Save pending stake choice for user in users table via deposit_address field for convenience
        conn = get_db_conn()
        c = conn.cursor()
        c.execute("UPDATE users SET deposit_address = ? WHERE user_id = ?", (str(amount), uid))
        conn.commit()
        conn.close()

        await bot.send_message(uid,
            f"🔔 You selected <b>{amount} SOL</b>.\nThis will be split as <b>{owner_amt} SOL</b> (prize pool) and <b>{team_amt} SOL</b> (team share).\n\n"
            "Tap each link to pay with your wallet app. After paying both, press 'I Paid' to let me verify on-chain.",
            reply_markup=keyboard,
            parse_mode="HTML"
        )

    elif data.startswith("confirm_paid_"):
        await query.answer()
        # parse chosen amount
        amount_str = data.split("_", 2)[1]
        try:
            chosen_amount = Decimal(amount_str)
        except Exception:
            await bot.send_message(uid, "❌ Invalid amount stored. Please choose again.")
            return

        owner_amt, team_amt = split_amount(chosen_amount)

        # Try to detect payments to owner and team wallets (best-effort)
        await bot.send_message(uid, "🔎 Checking for payments to both wallets... this may take a few seconds.")

        sig_owner = await find_incoming_payment_for_address(OWNER_WALLET, owner_amt, SOLANA_RPC)
        sig_team = await find_incoming_payment_for_address(TEAM_WALLET, team_amt, SOLANA_RPC)

        if sig_owner and sig_team:
            # mark entry paid and generate numbers
            round_num = get_current_round()
            lottery_numbers = sorted(random.sample(range(1, 41), 5))
            add_entry(uid, round_num, lottery_numbers, paid=1, tx_signature=f"{sig_owner}|{sig_team}")
            await bot.send_message(uid,
                f"✅ Payments detected!\n\n"
                f"🎲 Your lottery numbers for Round {round_num}:\n<b>{numbers_to_str(lottery_numbers)}</b>\n\n"
                f"Owner tx: <code>{sig_owner}</code>\nTeam tx: <code>{sig_team}</code>\n\nGood luck!",
                parse_mode="HTML"
            )
        else:
            # If not found, inform user. Allow manual claiming (admin verification later)
            msg = "⚠️ Could not detect both payments automatically."
            if not sig_owner:
                msg += f"\n• Prize pool payment ({owner_amt} SOL) not found."
            if not sig_team:
                msg += f"\n• Team payment ({team_amt} SOL) not found."
            msg += "\n\nIf you paid, wait a minute and try again. Or contact support for manual verification."
            await bot.send_message(uid, msg)

@dp.message()
async def generic_message_handler(message: types.Message):
    text = message.text.strip()
    user_id = message.from_user.id

    # If message looks like a Solana address, treat it as wallet input
    if validate_solana_address(text):
        save_user(user_id, message.from_user.username or "")
        save_user_wallet(user_id, text)
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="💵 Choose Stake", callback_data="choose_stake")],
            [InlineKeyboardButton(text="📘 Rules", callback_data="rules")]
        ])
        await bot.send_message(user_id,
            f"✅ <b>Wallet Connected!</b>\n\nYour wallet: <code>{text}</code>\n\n"
            f"Next step: Choose a stake package and pay the split (80/20).",
            reply_markup=keyboard,
            parse_mode="HTML")
        return

    # If user types 5 numbers, try to parse new entry (manual entry mode)
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
                f"Now choose a stake package and pay the split (80/20). Use /stake or press 'Choose Stake'.",
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
    # show packages
    rows = []
    temp = []
    for i, pkg in enumerate(STAKE_PACKAGES, 1):
        temp.append(InlineKeyboardButton(text=f"{pkg} SOL", callback_data=f"stake_{pkg}"))
        if i % 3 == 0:
            rows.append(temp)
            temp = []
    if temp:
        rows.append(temp)
    rows.append([InlineKeyboardButton(text="⬅️ Back", callback_data="play_now")])
    keyboard = InlineKeyboardMarkup(inline_keyboard=rows)
    await message.reply("💵 Choose a stake package:", reply_markup=keyboard)

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
        "📘 <b>CryptoUnc Lotto - Game Rules</b>\n\n"
        "🎲 <b>How to Play:</b>\n"
        "1. Connect your Solana wallet\n"
        "2. Choose a stake package (0.05 – 5 SOL)\n"
        "3. Pay the split: 80% prize pool / 20% team\n"
        "4. Press 'I Paid' to let the bot verify payments\n"
        "5. Receive 5 random numbers (1-40)\n"
        "6. Admin draws winners and announces in the channel\n\n"
        "🏆 <b>Winning:</b>\n"
        "• Match all 5 numbers to win the jackpot\n"
        f"• Each entry must be paid: prize pool gets 80%, team gets 20%\n",
        parse_mode="HTML"
    )

@dp.message(Command("support"))
async def cmd_support(message: types.Message):
    await message.reply("🛠 Support is not yet fully configured. Contact the admin for manual help.")

# ---------------------------
# Admin commands
# ---------------------------
def is_admin(user_id: int) -> bool:
    return user_id == ADMIN_ID

@dp.message(Command("admin_list"))
async def cmd_admin_list(message: types.Message):
    if not is_admin(message.from_user.id):
        await message.reply("⛔ Not authorized.")
        return
    r = get_current_round()
    rows = get_entries_for_round(r)
    if not rows:
        await message.reply(f"No entries for round {r}.")
        return
    out = [f"ID:{row[0]} UID:{row[1]} NUMS:{row[2]} PAID:{'Yes' if row[3] else 'No'} TX:{row[4] or 'N/A'}" for row in rows]
    for i in range(0, len(out), 20):
        await message.reply("\n".join(out[i:i+20]))

@dp.message(Command("admin_reset"))
async def cmd_admin_reset(message: types.Message):
    if not is_admin(message.from_user.id):
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
    if not is_admin(message.from_user.id):
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
# Background payment monitor (optional)
# ---------------------------
async def payment_monitor_loop():
    """
    Periodically check for new payments to per-user deposit addresses and auto-generate entries.
    This is optional because we now use split links — but it still supports per-user deposit addresses
    if you want that workflow.
    """
    await asyncio.sleep(5)  # small delay on startup
    while True:
        try:
            conn = get_db_conn()
            c = conn.cursor()
            c.execute("SELECT user_id, deposit_address FROM users WHERE deposit_address IS NOT NULL")
            users = c.fetchall()
            conn.close()
            current_round = get_current_round()
            for user_id, deposit_addr in users:
                # ensure user doesn't already have a paid entry for this round
                conn = get_db_conn()
                c = conn.cursor()
                c.execute("SELECT id FROM entries WHERE user_id = ? AND round = ? AND paid = 1", (user_id, current_round))
                existing = c.fetchone()
                conn.close()
                if existing:
                    continue
                # check incoming payment to deposit address
                sig = await find_incoming_payment_for_address(deposit_addr, STAKE_AMOUNT_DEFAULT, SOLANA_RPC)
                if sig:
                    # generate numbers and save
                    lottery_numbers = sorted(random.sample(range(1, 41), 5))
                    add_entry(user_id, current_round, lottery_numbers, paid=1, tx_signature=sig)
                    try:
                        await bot.send_message(user_id,
                            f"🎉 Payment detected to your deposit address!\n"
                            f"🎲 Your numbers for Round {current_round}: <b>{numbers_to_str(lottery_numbers)}</b>",
                            parse_mode="HTML"
                        )
                    except Exception:
                        pass
        except Exception as e:
            print("Payment monitor error:", e)
        await asyncio.sleep(30)

# ---------------------------
# Startup
# ---------------------------
async def main():
    init_db()
    print("🤖 CryptoUnc Lotto TG Bot starting...")
    print(f"Round channel: {ROUND_CHANNEL}")
    # run bot and monitor concurrently
    await asyncio.gather(
        dp.start_polling(bot),
        payment_monitor_loop()
    )

if __name__ == "__main__":
    asyncio.run(main())
