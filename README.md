# CryptoUnc-Lotto

CryptoUnc Lotto TG Bot is a decentralized-style Telegram lottery system where anyone can play directly inside Telegram.
Players connect a wallet privately, get 5 random numbers from 1–40, and join transparent public draws — all managed by the bot.

The system ensures that:
	•	Wallet addresses and numbers remain private.
	•	Draw results and winners are posted publicly.
	•	Stakes go to the admin’s wallet (you’ll configure this in your .env file).


Key Features

Feature
Description
🎲 Play Directly in Telegram
Users interact via buttons, no external site needed.
🔒 Private Lotto Session
Each player connects their wallet and receives numbers privately in DM.
🧮 Random 5-Number Generator (1–40)
The bot generates 5 unique numbers per play.
💳 Wallet Connection (Simulated)
Secure wallet connection placeholder, ready for Web3 integration.
🏆 Public Draw Results
Admin posts public winning numbers and winners.
💬 Support System
Dedicated /support command and button (to be linked later).
🪙 Admin Prize Wallet
All stakes go directly to your provided wallet address.


Tech Stack
Component
Description
🧠 Language
Python 3.10+
🤖 Framework
Aiogram 3.x
🔐 Environment
.env for token & wallet configuration
🗂 Database (optional)
SQLite/PostgreSQL (for Phase 2)
💵 Wallet Integration
WalletConnect (planned for Phase 2)


Folder Structure


cryptounc-lotto-tg/
│
├── main.py               # Core bot logic
├── .env                  # Environment variables (token, wallet)
├── requirements.txt      # Dependencies
└── README.md             # Documentation

Commands & Functions

Command / Button
Action
/start
Opens main menu with Play / Results / Rules / Support
🎲 Play Now
Opens a private DM session to play
💳 Connect Wallet
Simulates wallet connection
📊 View Results
Displays last draw
📘 Game Rules
Shows how to play
🛠 Support
Links to help channel (customizable)
/support
Opens the support section

🧩 How It Works
	1.	Player joins the bot and taps Play Now.
	2.	Bot opens a private session (DM).
	3.	Player connects their wallet (simulated).
	4.	Bot generates 5 random numbers from 1–40.
	5.	Player receives the numbers privately.
	6.	Admin later posts the winning combination publicly.

⸻

🧠 Example Flow


Phase 2 

Feature
Description
🪙 Real WalletConnect Integration
Players connect actual wallets securely.
💰 On-Chain Payment Validation
Automatic stake deposits to admin wallet.
🧮 Database for Players
Store and track plays.
🎯 Chainlink VRF RNG
True random number generation on-chain.
🌐 WebApp UI
Modern dashboard inside Telegram.


