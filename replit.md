# CryptoUnc Lotto Telegram Bot

## Overview
A decentralized-style lottery bot for Telegram built with Python. Users can play lottery games, connect Solana wallets, deposit funds, and receive lottery numbers directly in Telegram.

## Project Status
✅ **Fully configured and running on Replit**

## Tech Stack
- **Language**: Python 3.11
- **Framework**: Aiogram 2.25.1 (Telegram Bot)
- **Blockchain**: Solana
- **Database**: SQLite (local file-based database)
- **Hosting**: Replit

## Recent Changes (Nov 6, 2025)
- Installed Python 3.11 and all dependencies from requirements.txt
- Fixed import issues between Main.py and Wallet.py (changed `wallet` to `Wallet`)
- Created `.gitignore` for Python project
- Set up required environment variables (BOT_TOKEN, OWNER_WALLET, TEAM_WALLET, ADMIN_ID)
- Configured workflow to run the bot continuously
- Resolved Telegram webhook conflict by deleting existing webhook
- Bot is now running successfully with polling mode

## Project Architecture

### File Structure
```
/
├── Main.py           # Main bot file with handlers and commands
├── Wallet.py         # Wallet management (create, balance, transactions)
├── Index.html        # Wallet connection interface (future use)
├── requirements.txt  # Python dependencies
├── .env             # Environment variables (BOT_TOKEN, OWNER_WALLET)
└── cryptounc_lotto.db # SQLite database (auto-created)
```

### Database Tables
- **users**: Tracks Telegram users (user_id, username)
- **entries**: Lottery entries (user_id, round, numbers, paid status)
- **draws**: Draw results (round, winning_numbers, timestamp)
- **meta**: System metadata (current_round)

## Environment Variables (Secrets)
All stored in Replit Secrets:
- `BOT_TOKEN`: Telegram bot token from @BotFather
- `OWNER_WALLET`: Main Solana wallet (receives 80% of stakes)
- `TEAM_WALLET`: Team Solana wallet (receives 20% of stakes)
- `ADMIN_ID`: Telegram user ID with admin privileges
- `ROUND_CHANNEL_ID`: Optional channel for posting results (defaults to @cryptounclottoportal)
- `SOLANA_RPC`: Solana RPC endpoint (optional, defaults to mainnet)

## How It Works

### User Flow
1. User starts bot with `/start`
2. User clicks "🎲 Play" to begin
3. Bot opens private DM session
4. User creates or connects wallet
5. User chooses stake package (0.05 SOL - 5 SOL)
6. Bot generates 5 random numbers (1-40)
7. Payment is deducted from wallet balance
8. Admin draws winning numbers with `/admin_draw`
9. Winners are announced publicly

### Wallet System
- **Bot-created wallets**: Internal wallets managed by the bot
- **External wallets**: Users can connect existing Phantom/Solflare wallets
- **In-memory storage**: Currently uses in-memory dict (Phase 2: database integration)
- **Balance tracking**: Each user has a balance in SOL

### Admin Commands
- `/admin_draw` - Draw winning numbers for current round
- `/admin_list` - View all entries (if implemented)
- `/admin_reset` - Reset current round (if implemented)

## Workflow Configuration
- **Name**: telegram-bot
- **Command**: `python Main.py`
- **Type**: Console (background process)
- **Auto-restart**: Yes

## Development Notes

### Known Limitations
- Wallet balances are in-memory (reset on restart)
- No real Solana blockchain integration yet (placeholder functions)
- WalletConnect integration is planned for Phase 2
- Index.html wallet interface is not currently connected to the bot

### Future Improvements (Phase 2)
- Real WalletConnect integration
- On-chain payment verification
- Persistent wallet storage in database
- Chainlink VRF for true randomness
- Multi-chain support
- Modern Telegram dashboard

## Testing the Bot
1. Open Telegram and search for your bot using the bot token
2. Send `/start` to begin
3. Try creating a wallet with "Create Wallet" button
4. Add funds manually (demo mode)
5. Choose a stake and receive lottery numbers
6. Use `/admin_draw` command to draw winners

## Troubleshooting

### Bot Not Responding
- Check workflow status (should be "RUNNING")
- Verify BOT_TOKEN is correct
- Check logs for errors: View workflow logs in Replit

### Webhook Conflicts
If you see "webhook is active" error:
```python
python -c "import asyncio; from aiogram import Bot; import os; from dotenv import load_dotenv; load_dotenv(); bot = Bot(token=os.getenv('BOT_TOKEN')); asyncio.run(bot.delete_webhook(drop_pending_updates=True))"
```

### Import Errors
Make sure to import from `Wallet` (capital W), not `wallet`, to avoid conflicts with the `wallet-py3k` package.

## Security Notes
- Never commit `.env` file to version control
- Bot token and wallet private keys are stored securely in Replit Secrets
- User wallet private keys never leave their devices (external wallets)
- Bot-created wallet keys are stored securely (currently in-memory)

## License
Free to use for personal or team projects. Redistribution or commercial use requires permission from the author.
