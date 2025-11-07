# Main.py — CryptoUnc Lotto with Real Solana Wallet Integration

import os
import asyncio
import random
import decimal
from decimal import Decimal

from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from dotenv import load_dotenv

from wallet import (
get_user_wallets,
get_active_wallet,
save_external_wallet,
get_real_balance,
send_sol,
create_wallet,
set_active_wallet,
get_wallet_private_key,
get_user_wallet_count,
delete_wallet,
set_user_pin,
verify_user_pin,
has_user_pin,
MAX_WALLETS_PER_USER
)

import sqlite3

from wallet_buttons import router as wallet_router

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
OWNER_WALLET = os.getenv("OWNER_WALLET")
TEAM_WALLET = os.getenv("TEAM_WALLET")
ADMIN_ID = int(os.getenv("ADMIN_ID", 0))
ROUND_CHANNEL = os.getenv("ROUND_CHANNEL_ID", "@cryptounclottoportal")

# Validate required environment variables
if not BOT_TOKEN:
    raise ValueError("BOT_TOKEN environment variable is required")
if not OWNER_WALLET:
    raise ValueError("OWNER_WALLET environment variable is required")

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

dp.include_router(wallet_router)

# State management for PIN operations and wallet actions
user_states = {}  # Stores pending operations: {user_id: {"action": "set_pin", "data": {...}}}
pending_pins = {}  # Stores PIN attempts: {user_id: {"pin": "1234", "action": "view_key"}}
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
    total_entries = 0
    
    for row in rows:
        entry_id, uid, numbers_str, paid = row
        if not paid:
            continue
        total_entries += 1
        entry_nums = str_to_numbers(numbers_str)
        if sorted(entry_nums) == winning_numbers:
            winners.append(uid)

    announce_text = (
        f"🏆 <b>CryptoUnc Lotto — Round {cur_round} Results</b>\n\n"
        f"🎲 Winning Numbers: <code>{numbers_to_str(winning_numbers)}</code>\n"
        f"📊 Total Entries: {total_entries}\n\n"
    )

    if winners:
        winner_count = len(winners)
        mentions = [f"<a href='tg://user?id={w}'>Winner #{i+1}</a>" for i, w in enumerate(winners)]
        announce_text += f"🎉 <b>{winner_count} Winner(s)!</b>\n\n" + "\n".join(mentions)
        announce_text += f"\n\n🎊 Congratulations to all winners!"
    else:
        announce_text += "😔 No winners this round. Better luck next time!\n\n"
        announce_text += "🎰 Try again in the next round!"

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


# ---------------------------
# Startup
# ---------------------------
async def main():
    init_db()
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
    
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
