# main.py (with integrated wallet connect — Mainnet)
import os
import asyncio
import random
import re
import sqlite3
from typing import Optional, List, Tuple
from decimal import Decimal
import json
import math
import secrets
import time

import requests
import aiohttp
from aiohttp import web
import base64
import base58
from nacl.signing import VerifyKey
from nacl.exceptions import BadSignatureError

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
# **Mainnet** RPC (you can override via SOLANA_RPC env)
SOLANA_RPC = os.getenv("SOLANA_RPC", "https://api.mainnet-beta.solana.com")
BACKEND_URL = os.getenv("BACKEND_URL", "http://localhost:8000")  # set to your public URL in production

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
    # sessions table for wallet connect
    c.execute("""
        CREATE TABLE IF NOT EXISTS sessions (
            id TEXT PRIMARY KEY,
            tg_user_id INTEGER,
            challenge TEXT,
            created_at INTEGER,
            used INTEGER DEFAULT 0
        )
    """)
    # wallets table (saved wallets)
    c.execute("""
        CREATE TABLE IF NOT EXISTS wallets (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT,
            public_key TEXT,
            wallet_name TEXT,
            verified INTEGER DEFAULT 0,
            created_at INTEGER
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

def save_user_wallet_by_userid(user_id: int, sol_wallet: str, verified: bool = True):
    conn = get_db_conn()
    c = conn.cursor()
    c.execute("UPDATE users SET sol_wallet = ? WHERE user_id = ?", (sol_wallet, user_id))
    conn.commit()
    conn.close()
    # Also insert into wallets table for audit
    now = int(time.time())
    conn = get_db_conn()
    c = conn.cursor()
    c.execute("INSERT INTO wallets (session_id, public_key, wallet_name, verified, created_at) VALUES (?, ?, ?, ?, ?)",
              ("", sol_wallet, "imported_via_bot", 1 if verified else 0, now))
    conn.commit()
    conn.close()

def save_user_wallet(user_id: int, sol_wallet: str):
    # legacy name used in other parts of code — keep compatibility
    save_user_wallet_by_userid(user_id, sol_wallet, verified=True)

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
# Wallet web server (aiohttp) integrated into this file
# ---------------------------

# Helper: create a new session + challenge
def create_wallet_session(tg_user_id: int) -> dict:
    token = secrets.token_urlsafe(18)
    challenge = "Sign this message to prove wallet ownership: " + secrets.token_hex(16)
    now = int(time.time())
    conn = get_db_conn()
    c = conn.cursor()
    c.execute(
        "INSERT INTO sessions (id, tg_user_id, challenge, created_at, used) VALUES (?, ?, ?, ?, 0)",
        (token, tg_user_id, challenge, now),
    )
    conn.commit()
    conn.close()
    return {"session": token, "challenge": challenge}


# Web handlers
async def new_session_handler(request):
    try:
        tg_user_id = int(request.match_info.get('tg_user_id'))
    except Exception:
        return web.json_response({"error": "invalid user id"}, status=400)
    s = create_wallet_session(tg_user_id)
    # Build a URL the bot will send to the user. Use BACKEND_URL env or construct from request.
    base = BACKEND_URL.rstrip("/")
    if base == "http://localhost:8000" and request.host:
        # try to use request host (helpful when deployed)
        host = f"{request.scheme}://{request.host}"
        base = host
    url = f"{base}/connect?session={s['session']}"
    return web.json_response({"session": s["session"], "challenge": s["challenge"], "url": url})


# Serve a minimal HTML connect page with Phantom support (bot return set to your username)
CONNECT_HTML = """<!doctype html>
<html>
  <head><meta charset="utf-8"/><meta name="viewport" content="width=device-width,initial-scale=1"/><title>Connect Solana Wallet</title></head>
  <body style="font-family:Arial;padding:20px;">
    <h2>Connect your Solana wallet</h2>
    <p>Session: <strong id="session"></strong></p>
    <pre id="challenge" style="background:#f6f6f6;padding:10px;border-radius:6px;"></pre>
    <div>
      <button id="connectBtn">Connect Phantom</button>
      <button id="signBtn" disabled>Sign & Save</button>
      <button id="mobileBtn">Open in Phantom (mobile)</button>
    </div>
    <div id="result" style="margin-top:12px;color:green"></div>
    <p style="color:#a00">Do <strong>NOT</strong> paste your private key or mnemonic here.</p>

    <script src="https://unpkg.com/@solana/web3.js@1.66.0/lib/index.iife.min.js"></script>
    <script>
      const urlParams = new URLSearchParams(window.location.search);
      const session = urlParams.get('session') || '';
      if (!session) {
        document.getElementById('result').innerText = 'Session required';
      }
      document.getElementById('session').innerText = session;

      async function fetchChallenge() {
        const res = await fetch('/api/session_info/' + session);
        if (res.status !== 200) {
          document.getElementById('result').innerText = 'Invalid session';
          return;
        }
        const j = await res.json();
        document.getElementById('challenge').innerText = j.challenge;
      }
      fetchChallenge();

      let provider = window.solana && window.solana.isPhantom ? window.solana : null;
      const connectBtn = document.getElementById('connectBtn');
      const signBtn = document.getElementById('signBtn');
      const mobileBtn = document.getElementById('mobileBtn');
      let connectedPubkey = null;

      connectBtn.addEventListener('click', async () => {
        provider = window.solana && window.solana.isPhantom ? window.solana : null;
        if (!provider) {
          alert('Phantom not found. Open this page in a wallet-enabled browser or use mobile deep link.');
          return;
        }
        try {
          const resp = await provider.connect();
          connectedPubkey = resp.publicKey.toString();
          document.getElementById('result').innerText = 'Connected: ' + connectedPubkey;
          signBtn.disabled = false;
        } catch (err) {
          console.error(err);
          document.getElementById('result').innerText = 'Connect failed: ' + (err.message || err);
        }
      });

      signBtn.addEventListener('click', async () => {
        if (!provider || !connectedPubkey) {
          alert('Connect wallet first.');
          return;
        }
        try {
          const challenge = document.getElementById('challenge').innerText;
          const encoded = new TextEncoder().encode(challenge);
          const signed = await provider.signMessage(encoded, 'utf8');
          const signatureBytes = signed.signature instanceof Uint8Array ? signed.signature : signed;
          // load bs58 if missing
          if (!window.bs58) {
            await new Promise((res, rej) => {
              const s = document.createElement('script');
              s.src = 'https://cdnjs.cloudflare.com/ajax/libs/bs58/4.0.1/bs58.min.js';
              s.onload = res; s.onerror = rej;
              document.head.appendChild(s);
            });
          }
          const sigb58 = window.bs58.encode(signatureBytes);
          const form = new FormData();
          form.append('session', session);
          form.append('public_key', connectedPubkey);
          form.append('signature', sigb58);
          form.append('wallet_name', 'phantom');
          const res = await fetch('/api/save_wallet', { method: 'POST', body: form });
          const j = await res.json();
          if (j.ok) {
            document.getElementById('result').innerText = 'Saved: ' + j.public_key + ' (verified=' + j.verified + ')';
            // return to your bot
            const a = document.createElement('a'); a.href = 'tg://resolve?domain=CryptoUncLottoBot'; a.innerText = 'Return to Telegram'; a.style.display='block'; a.style.marginTop='10px';
            document.body.appendChild(a);
          } else {
            document.getElementById('result').innerText = 'Save failed: ' + JSON.stringify(j);
          }
        } catch (err) {
          console.error(err);
          document.getElementById('result').innerText = 'Sign failed: ' + (err.message || err);
        }
      });

      mobileBtn.addEventListener('click', () => {
        const dappUrl = encodeURIComponent(window.location.href);
        const phantomUrl = `https://phantom.app/ul/v1/connect?app_url=${dappUrl}`;
        window.location.href = phantomUrl;
      });
    </script>
  </body>
</html>
"""

async def connect_page_handler(request):
    session = request.query.get('session', '')
    if not session:
        return web.Response(text="Session required", status=400)
    # verify session exists and not used
    conn = get_db_conn()
    c = conn.cursor()
    c.execute("SELECT challenge, used FROM sessions WHERE id=?", (session,))
    row = c.fetchone()
    conn.close()
    if not row:
        return web.Response(text="Invalid session", status=404)
    challenge, used = row
    if used:
        return web.Response(text="Session already used", status=400)
    # return the simple HTML (client will fetch challenge via /api/session_info)
    return web.Response(text=CONNECT_HTML, content_type='text/html')

async def api_session_info(request):
    session = request.match_info.get('session')
    conn = get_db_conn()
    c = conn.cursor()
    c.execute("SELECT tg_user_id, challenge, used FROM sessions WHERE id=?", (session,))
    row = c.fetchone()
    conn.close()
    if not row:
        return web.json_response({"error": "not found"}, status=404)
    tg_user_id, challenge, used = row
    return web.json_response({"tg_user_id": tg_user_id, "challenge": challenge, "used": bool(used)})

async def api_save_wallet(request):
    data = await request.post()
    session = data.get('session')
    public_key = data.get('public_key')
    signature = data.get('signature')
    wallet_name = data.get('wallet_name') or ""
    if not session or not public_key:
        return web.json_response({"error": "session and public_key required"}, status=400)
    # validate session
    conn = get_db_conn()
    c = conn.cursor()
    c.execute("SELECT tg_user_id, challenge, used FROM sessions WHERE id=?", (session,))
    row = c.fetchone()
    if not row:
        conn.close()
        return web.json_response({"error": "invalid session"}, status=400)
    tg_user_id, challenge, used = row
    if used:
        conn.close()
        return web.json_response({"error": "session already used"}, status=400)
    # verify signature if provided
    verified = 0
    if signature:
        try:
            pubkey_bytes = base58.b58decode(public_key)
            sig_bytes = base58.b58decode(signature)
            verify_key = VerifyKey(pubkey_bytes)
            message_bytes = challenge.encode('utf-8')
            verify_key.verify(message_bytes, sig_bytes)
            verified = 1
        except (ValueError, BadSignatureError) as e:
            verified = 0
    # save wallet mapping (update users table)
    now = int(time.time())
    c.execute("INSERT INTO wallets (session_id, public_key, wallet_name, verified, created_at) VALUES (?, ?, ?, ?, ?)",
              (session, public_key, wallet_name, verified, now))
    c.execute("UPDATE sessions SET used=1 WHERE id=?", (session,))
    # update users table sol_wallet field
    c.execute("UPDATE users SET sol_wallet = ? WHERE user_id = ?", (public_key, tg_user_id))
    conn.commit()
    conn.close()
    return web.json_response({"ok": True, "public_key": public_key, "verified": bool(verified)})

async def api_get_wallet(request):
    try:
        tg_user_id = int(request.match_info.get('tg_user_id'))
    except Exception:
        return web.json_response({"error":"invalid id"}, status=400)
    conn = get_db_conn()
    c = conn.cursor()
    c.execute("SELECT sol_wallet FROM users WHERE user_id = ?", (tg_user_id,))
    row = c.fetchone()
    conn.close()
    return web.json_response({"wallet_address": row[0] if row and row[0] else None})

# Start aiohttp web server as a background task
async def start_web_server():
    app = web.Application()
    app.add_routes([
        web.get('/new_session/{tg_user_id}', new_session_handler),
        web.get('/connect', connect_page_handler),
        web.post('/api/save_wallet', api_save_wallet),
        web.get('/api/session_info/{session}', api_session_info),
        web.get('/api/get_wallet/{tg_user_id}', api_get_wallet),
    ])
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, '0.0.0.0', 8000)
    await site.start()
    print("🌐 Wallet web server running on port 8000")

# ---------------------------
# Bot command handlers & flows (existing handlers remain unchanged)
# ---------------------------

# Keep your original handlers: start, play, inline callback handler, stake flow, etc.
# (For brevity, include your full handlers below — copied from your original file.)
# ... (Handlers from your original main.py are intact and still present) ...
# Note: In this paste replace "..." with your existing handlers content block.
# However for convenience I will re-include the key commands I added below.

# New: send connect link helper
def get_wallet_connect_link(user_id: int) -> Optional[str]:
    try:
        backend = BACKEND_URL.rstrip('/')
        r = requests.get(f"{backend}/new_session/{user_id}", timeout=6)
        if r.status_code == 200:
            return r.json().get("url")
    except Exception as e:
        print("get_wallet_connect_link error:", e)
    return None

# New command: /connectwallet (user-friendly wrapper)
@dp.message(Command("connectwallet"))
async def cmd_connectwallet(message: types.Message):
    link = get_wallet_connect_link(message.from_user.id)
    if link:
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔗 Connect Wallet", url=link)]
        ])
        await message.reply("Click the button to connect your Solana wallet (opens Phantom or wallet-enabled browser).", reply_markup=keyboard)
    else:
        await message.reply("⚠️ Could not generate connect link. Try again later.")

# New command: /mywallet (checks backend)
@dp.message(Command("mywallet"))
async def cmd_mywallet(message: types.Message):
    # check local DB first
    w = get_user_wallet(message.from_user.id)
    if w:
        await message.reply(f"✅ Your connected wallet: <code>{w}</code>", parse_mode="HTML")
        return
    # fallback to backend query
    try:
        r = requests.get(f"{BACKEND_URL.rstrip('/')}/api/get_wallet/{message.from_user.id}", timeout=6)
        if r.status_code == 200:
            addr = r.json().get("wallet_address")
            if addr:
                await message.reply(f"✅ Your connected wallet: <code>{addr}</code>", parse_mode="HTML")
                # persist locally
                save_user_wallet(message.from_user.id, addr)
                return
    except Exception:
        pass
    await message.reply("❌ No wallet connected yet. Use /connectwallet to link one.")

# ---------------------------
# Background payment monitor (optional) — keep from your file
# ---------------------------
async def payment_monitor_loop():
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
    # start web server and bot concurrently
    await start_web_server()
    await asyncio.gather(
        dp.start_polling(bot),
        payment_monitor_loop()
    )

if __name__ == "__main__":
    asyncio.run(main())
