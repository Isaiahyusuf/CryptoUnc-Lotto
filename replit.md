# CryptoUnc Lotto Bot

## Overview
A Telegram-based cryptocurrency lottery bot with real Solana wallet integration. Users can buy lottery tickets with SOL, with automated draws and prize distribution.

**SQLite fully removed. PostgreSQL only.**

## Database
- **PostgreSQL only** - No SQLite fallback
- Connected via `DATABASE_URL` environment variable
- All tables recreated cleanly without old constraints
- Users can buy multiple tickets per round (no UNIQUE constraint on user_id, round_stake_id)

## Architecture
- **Bot Framework**: aiogram 3.4.1 (Telegram Bot API)
- **Blockchain**: Solana mainnet via solana-py/solders
- **Database**: PostgreSQL (required, no SQLite)
- **Encryption**: cryptography library for wallet private key encryption

## Key Files
- `main.py` - Main bot logic and handlers
- `db.py` - PostgreSQL-only database layer
- `wallet.py` - Solana wallet management
- `wallet_buttons.py` - Wallet action button handlers
- `email_service.py` - Email verification service
- `encryption.py` - Private key encryption

## Required Environment Variables
- `BOT_TOKEN` - Telegram Bot API token
- `DATABASE_URL` - PostgreSQL connection string (required)
- `OWNER_WALLET` - Bot's Solana wallet public address
- `OWNER_WALLET_PRIVATE_KEY` - Bot's Solana wallet private key
- `ENCRYPTION_KEY` - Strong random key for wallet encryption
- `ADMIN_ID` - Admin's numeric Telegram user ID
- `ROUND_CHANNEL_ID` - Telegram channel for announcements

## Optional Environment Variables
- `SOLANA_RPC` - Custom Solana RPC endpoint
- `TEAM_WALLET` - Team Solana wallet for fees
- `SUPPORT_USERNAME` - Support contact
- `ANNOUNCEMENTS_GROUP_ID` - Additional announcement group

## Recent Changes (December 2025)
- **SQLite fully removed** - PostgreSQL is now mandatory
- **Clean database reset** - All tables dropped and recreated
- **Multiple tickets per user** - No UNIQUE constraint on (user_id, round_stake_id)
- **Single runtime verification** - Prevents duplicate bot instances
- **Railway restriction removed** - Bot can run on any platform with DATABASE_URL

## Running the Bot
1. Set all required environment variables
2. Ensure PostgreSQL database is available
3. Run `python main.py`

The bot will:
- Initialize the PostgreSQL connection pool
- Create all necessary tables
- Start listening for Telegram commands
