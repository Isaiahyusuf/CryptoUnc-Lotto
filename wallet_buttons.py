# wallet_buttons.py
import base58
import sqlite3
import asyncio
from aiogram import Router, types
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

from solana.rpc.async_api import AsyncClient
from solana.transaction import Transaction
from solana.system_program import TransferParams, transfer
from solana.keypair import Keypair
from solana.publickey import PublicKey

# Your Mainnet RPC endpoint
RPC_URL = "https://api.mainnet-beta.solana.com"

router = Router()

# ------------------- FSM STATES ------------------- #
class SendSOL(StatesGroup):
    waiting_for_address = State()
    waiting_for_amount = State()

class PrivateKeyAccess(StatesGroup):
    waiting_for_pin = State()

# ------------------- BUTTONS ------------------- #
def wallet_menu():
    buttons = [
        [InlineKeyboardButton(text="💸 Send SOL", callback_data="send_sol")],
        [InlineKeyboardButton(text="🔑 View Private Key", callback_data="view_privkey")],
        [InlineKeyboardButton(text="🗑 Delete Wallet", callback_data="delete_wallet")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)

# ------------------- DATABASE ------------------- #
def get_user_wallet(user_id):
    conn = sqlite3.connect("wallets.db")
    c = conn.cursor()
    c.execute("SELECT public_key, encrypted_private_key, pin FROM wallets WHERE user_id = ?", (user_id,))
    result = c.fetchone()
    conn.close()
    return result

def delete_user_wallet(user_id):
    conn = sqlite3.connect("wallets.db")
    c = conn.cursor()
    c.execute("DELETE FROM wallets WHERE user_id = ?", (user_id,))
    conn.commit()
    conn.close()

# ------------------- CALLBACK HANDLERS ------------------- #

@router.callback_query(lambda c: c.data == "send_sol")
async def send_sol_callback(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.answer("Enter the recipient's wallet address:")
    await state.set_state(SendSOL.waiting_for_address)
    await callback.answer()

@router.message(SendSOL.waiting_for_address)
async def handle_address(message: types.Message, state: FSMContext):
    await state.update_data(address=message.text)
    await message.answer("Now enter the amount of SOL to send:")
    await state.set_state(SendSOL.waiting_for_amount)

@router.message(SendSOL.waiting_for_amount)
async def handle_amount(message: types.Message, state: FSMContext):
    data = await state.get_data()
    address = data["address"]
    amount = float(message.text)

    user_id = message.from_user.id
    wallet_data = get_user_wallet(user_id)

    if not wallet_data:
        await message.answer("⚠️ You don’t have a wallet yet.")
        return

    public_key, encrypted_private_key, _ = wallet_data
    try:
        # decrypt if you encrypted (replace with your decryption logic)
        private_key_bytes = base58.b58decode(encrypted_private_key)
        sender = Keypair.from_secret_key(private_key_bytes)
    except Exception as e:
        await message.answer(f"❌ Error decoding private key: {e}")
        return

    try:
        solana_client = AsyncClient(RPC_URL)
        lamports = int(amount * 1_000_000_000)
        txn = Transaction().add(
            transfer(TransferParams(
                from_pubkey=sender.public_key,
                to_pubkey=PublicKey(address),
                lamports=lamports
            ))
        )

        resp = await solana_client.send_transaction(txn, sender)
        await solana_client.close()

        await message.answer(f"✅ Sent {amount} SOL to `{address}`\n\nTx Signature: `{resp['result']}`")
    except Exception as e:
        await message.answer(f"❌ Transaction failed: {e}")
    finally:
        await state.clear()

# ------------------- PRIVATE KEY VIEW ------------------- #
@router.callback_query(lambda c: c.data == "view_privkey")
async def view_privkey_callback(callback: types.CallbackQuery, state: FSMContext):
    wallet_data = get_user_wallet(callback.from_user.id)
    if not wallet_data:
        await callback.message.answer("⚠️ You don’t have a wallet yet.")
        return
    await callback.message.answer("Enter your 4-digit PIN to view your private key:")
    await state.set_state(PrivateKeyAccess.waiting_for_pin)
    await callback.answer()

@router.message(PrivateKeyAccess.waiting_for_pin)
async def verify_pin(message: types.Message, state: FSMContext):
    user_id = message.from_user.id
    entered_pin = message.text.strip()
    wallet_data = get_user_wallet(user_id)
    if not wallet_data:
        await message.answer("⚠️ You don’t have a wallet yet.")
        await state.clear()
        return

    _, encrypted_private_key, stored_pin = wallet_data
    if entered_pin != stored_pin:
        await message.answer("❌ Incorrect PIN.")
        await state.clear()
        return

    try:
        private_key_bytes = base58.b58decode(encrypted_private_key)
        private_key_str = base58.b58encode(private_key_bytes).decode()
        await message.answer(f"🔑 Your Private Key:\n`{private_key_str}`")
    except Exception as e:
        await message.answer(f"Error decoding key: {e}")

    await state.clear()

# ------------------- DELETE WALLET ------------------- #
@router.callback_query(lambda c: c.data == "delete_wallet")
async def delete_wallet_callback(callback: types.CallbackQuery):
    delete_user_wallet(callback.from_user.id)
    await callback.message.answer("🗑 Wallet deleted successfully.")
    await callback.answer()