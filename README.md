CryptoUnc Lotto Telegram Bot 🎲

CryptoUnc Lotto is a decentralized-style lottery bot for Telegram, designed to allow users to play lottery games directly inside Telegram. Players can connect wallets, deposit funds, and receive lottery numbers, all while keeping wallet addresses private and maintaining transparency for draws and winners.


Table of Contents
	1.	Features￼
	2.	Tech Stack￼
	3.	Installation￼
	4.	Configuration￼
	5.	Usage￼
	6.	Commands & Buttons￼
	7.	Lottery Flow￼
	8.	Phase 2 Roadmap￼
	9.	Security & Privacy￼
	10.	License￼


Features

Feature
Description
🎲 Play in Telegram
Users can play directly in the bot — no external website required.
🔒 Private Lotto Session
Players connect wallets privately via DM and receive their numbers safely.
🧮 Random 5-Number Generator
Bot generates 5 unique numbers from 1–40 for each entry.
💳 Wallet Integration
WalletConnect-ready for Phantom, Solflare, and other wallets. Users can also create an internal bot wallet.
💰 Stake Management
Choose from multiple stake packages (0.05 SOL – 5 SOL). Stakes are split 80/20 between prize pool and team.
🏆 Public Draw Results
Admin posts winning numbers and winners publicly.
💬 Support System
/support command and dedicated button for user assistance.
🗂 Database Tracking
Tracks users, wallets, entries, draws, and payments.

Tech Stack 🛠


Component
Description
Language
Python 3.10+
Framework
Aiogram 3.x
Database
SQLite (Phase 2 can upgrade to PostgreSQL)
Blockchain
Solana (Mainnet)
Wallet
WalletConnect-ready (Phantom, Solflare, Sollet)
Hosting
Replit (Workflows recommended)

Installation

pip install -r requirements.txt

Setup environment variables
Create a .env file or use Replit Secrets with the following:


BOT_TOKEN=YOUR_TELEGRAM_BOT_TOKEN
OWNER_WALLET=YOUR_MAIN_WALLET_PUBLIC_KEY
TEAM_WALLET=YOUR_TEAM_WALLET_PUBLIC_KEY
ADMIN_ID=YOUR_TELEGRAM_USER_ID
ROUND_CHANNEL_ID=@yourchannelusername
SOLANA_RPC=https://api.devnet.solana.com  # or mainnet endpoint
STAKE_AMOUNT_SOL=0.1


Initialize database
python main.py

This will automatically create the SQLite database and tables.


Usage
1.	Start the bot via Telegram with /start.
	2.	Navigate the buttons to:
	•	Play a lottery
	•	Connect your wallet
	•	View past results
	•	Access rules and support
	3.	Private session steps:
	•	Connect your wallet or create a bot wallet
	•	Choose a stake package
	•	Confirm payment (bot verifies on-chain or via deposit address)
	•	Receive 5 random lottery numbers
	4.	Admin commands:
	•	/admin_draw — draw winners
	•	/admin_list — view all entries
	•	/admin_reset — reset current round

Commands & Buttons

Command / Button
Action
/start
Opens main menu with Play / Results / Rules / Support
🎲 Play Now
Opens private DM session for lottery play
💳 Connect Wallet
Link wallet via WalletConnect or paste public key
💵 Choose Stake
Choose stake amount for current round
📊 View Results
Shows last draw results
📘 Game Rules
Displays how to play
🛠 Support
Links to support or admin
/my_numbers
Shows your last entered numbers

Lottery Flow 🧩
	1.	User taps Play Now
	2.	Bot opens a private DM session
	3.	User connects wallet or creates internal bot wallet
	4.	Bot generates 5 unique numbers (1–40)
	5.	User chooses stake and pays the 80/20 split
	6.	Bot verifies payment (automatically via Solana RPC or manually)
	7.	Admin draws winning numbers
	8.	Winners are announced publicly

Phase 2 Roadmap 🚀

Feature
Status
Real WalletConnect integration
Planned
On-chain payment verification
Planned
Bot-created internal wallets
Implemented
Chainlink VRF RNG for true randomness
Planned
Multi-chain support
Planned
Modern Telegram dashboard
Planned

Security & Privacy 🔒
	•	Users’ wallet private keys never leave their devices.
	•	Bot stores only public keys or bot-generated keys for internal wallets.
	•	Draw results are publicly verifiable.
	•	All database operations are local to bot and optional for Phase 2 migration to PostgreSQL.

⸻

License 📄

This project is free to use for personal or team projects.
Redistribution or commercial use requires permission from the author.

⸻

🎉 Notes / Tips
	•	Use Replit Workflows to run the bot 24/7.
	•	Ensure all secrets (BOT_TOKEN, wallet keys, etc.) are safely stored in Replit Secrets or .env.
	•	For fun, you can customize messages, emoji reactions, or add gamification features like streaks or jackpots.


