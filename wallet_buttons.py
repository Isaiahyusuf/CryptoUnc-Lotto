# wallet_buttons.py - Wallet management handlers for aiogram 3.x
import os
from decimal import Decimal
from aiogram import Router, F
from aiogram.types import CallbackQuery, Message, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.filters import StateFilter

from wallet import (
    get_user_wallets,
    get_active_wallet,
    get_real_balance,
    send_sol,
    get_wallet_private_key,
    delete_wallet as db_delete_wallet,
    set_active_wallet,
    get_user_wallet_count,
    MAX_WALLETS_PER_USER
)

router = Router()

# FSM States
class SendSOLState(StatesGroup):
    waiting_for_address = State()
    waiting_for_amount = State()

class PinState(StatesGroup):
    waiting_for_pin = State()


# ================ Send SOL Feature ================
@router.callback_query(F.data == "send_sol")
async def handle_send_sol(callback: CallbackQuery, state: FSMContext):
    """Initiate SOL sending process"""
    wallet = get_active_wallet(callback.from_user.id)
    
    if not wallet:
        await callback.message.answer("❌ Please create or connect a wallet first.")
        await callback.answer()
        return
    
    balance = await get_real_balance(wallet)
    
    await callback.message.answer(
        f"💸 <b>Send SOL</b>\n\n"
        f"Your balance: <b>{balance} SOL</b>\n\n"
        f"Please enter the recipient's Solana wallet address:",
        parse_mode="HTML"
    )
    await state.set_state(SendSOLState.waiting_for_address)
    await callback.answer()


@router.message(SendSOLState.waiting_for_address)
async def handle_address(message: Message, state: FSMContext):
    """Handle recipient address input"""
    address = message.text.strip()
    
    # Basic validation
    if not (32 <= len(address) <= 44 and address.replace('1', '').replace('2', '').replace('3', '').replace('4', '').replace('5', '').replace('6', '').replace('7', '').replace('8', '').replace('9', '').replace('0', '').isalpha()):
        await message.answer("❌ Invalid Solana address. Please try again with a valid address.")
        return
    
    await state.update_data(recipient_address=address)
    await message.answer(
        f"✅ Recipient: <code>{address}</code>\n\n"
        f"Now enter the amount of SOL to send:",
        parse_mode="HTML"
    )
    await state.set_state(SendSOLState.waiting_for_amount)


@router.message(SendSOLState.waiting_for_amount)
async def handle_amount(message: Message, state: FSMContext):
    """Handle amount input and send transaction"""
    try:
        amount = Decimal(message.text.strip())
        if amount <= 0:
            await message.answer("❌ Amount must be greater than 0. Please try again.")
            return
    except (ValueError, ArithmeticError):
        await message.answer("❌ Invalid amount. Please enter a number (e.g., 0.5)")
        return
    
    user_id = message.from_user.id
    data = await state.get_data()
    recipient = data.get("recipient_address")
    
    wallet = get_active_wallet(user_id)
    if not wallet:
        await message.answer("❌ No active wallet found.")
        await state.clear()
        return
    
    # Check balance
    balance = await get_real_balance(wallet)
    if balance < amount:
        await message.answer(
            f"⚠️ <b>Insufficient funds!</b>\n\n"
            f"Your balance: {balance} SOL\n"
            f"Required: {amount} SOL",
            parse_mode="HTML"
        )
        await state.clear()
        return
    
    # Get private key (only works for bot-managed wallets)
    private_key = get_wallet_private_key(user_id, wallet)
    
    if not private_key:
        await message.answer(
            "⚠️ This is an external wallet. Bot cannot send transactions from external wallets.\n"
            "Please use your wallet app (Phantom, Solflare, etc.) to send SOL."
        )
        await state.clear()
        return
    
    # Send transaction
    await message.answer("⏳ Processing transaction...")
    
    result = await send_sol(wallet, recipient, amount, private_key)
    
    if result["success"]:
        await message.answer(
            f"✅ <b>Transaction successful!</b>\n\n"
            f"Sent: {amount} SOL\n"
            f"To: <code>{recipient[:8]}...{recipient[-8:]}</code>\n"
            f"Signature: <code>{result['signature'][:16]}...</code>",
            parse_mode="HTML"
        )
    else:
        await message.answer(
            f"❌ <b>Transaction failed!</b>\n\n"
            f"Error: {result.get('error', 'Unknown error')}",
            parse_mode="HTML"
        )
    
    await state.clear()


# ================ Remove Wallet Feature ================
@router.callback_query(F.data == "remove_wallet")
async def handle_remove_wallet(callback: CallbackQuery):
    """Remove active wallet"""
    user_id = callback.from_user.id
    wallet = get_active_wallet(user_id)
    
    if not wallet:
        await callback.message.answer("❌ No active wallet to remove.")
        await callback.answer()
        return
    
    # Get wallet type
    wallets = get_user_wallets(user_id)
    wallet_info = next((w for w in wallets if w["address"] == wallet), None)
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✅ Yes, Delete", callback_data="confirm_delete_wallet"),
            InlineKeyboardButton(text="❌ Cancel", callback_data="cancel_delete")
        ]
    ])
    
    await callback.message.answer(
        f"⚠️ <b>Confirm Wallet Deletion</b>\n\n"
        f"Are you sure you want to delete this wallet?\n\n"
        f"Type: {wallet_info['type'] if wallet_info else 'Unknown'}\n"
        f"Address: <code>{wallet[:8]}...{wallet[-8:]}</code>\n\n"
        f"⚠️ <b>Warning:</b> If this is a bot-managed wallet, make sure to withdraw all funds first!",
        reply_markup=keyboard,
        parse_mode="HTML"
    )
    await callback.answer()


@router.callback_query(F.data == "confirm_delete_wallet")
async def confirm_delete_wallet(callback: CallbackQuery):
    """Confirm wallet deletion"""
    user_id = callback.from_user.id
    wallet = get_active_wallet(user_id)
    
    if wallet:
        db_delete_wallet(user_id, wallet)
        await callback.message.answer("✅ Wallet deleted successfully.")
    else:
        await callback.message.answer("❌ No wallet to delete.")
    
    await callback.answer()


@router.callback_query(F.data == "cancel_delete")
async def cancel_delete(callback: CallbackQuery):
    """Cancel wallet deletion"""
    await callback.message.answer("❌ Wallet deletion cancelled.")
    await callback.answer()


# ================ View Private Key Feature - DISABLED FOR SECURITY ================
# Private key viewing has been disabled for security reasons.
# Bot-managed wallets are encrypted and private keys should never be exposed.
# Users should backup their wallet addresses and use them to receive funds only.
# For withdrawals, users can use the "Send SOL" feature instead of exporting keys.
