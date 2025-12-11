# CryptoUnc Lotto Telegram Bot

## Overview

CryptoUnc Lotto is a decentralized Telegram lottery bot operating on the Solana blockchain. Its primary purpose is to allow users to participate in lottery games using real Solana (SOL) cryptocurrency. The bot supports wallet creation, SOL deposits, participation in hourly lottery rounds with varying stake levels, and automatic prize distribution. A key feature is its use of blockchain-based cryptographic randomness to ensure verifiable fairness in draw results. The project aims to provide an engaging and transparent lottery experience within Telegram, with features like referral systems, VIP tiers, leaderboards, and personal statistics to enhance user engagement and retention.

## User Preferences

Preferred communication style: Simple, everyday language.

## System Architecture

### Core Technology Stack

- **Language & Framework:** Python 3.11, Aiogram 3.4.1 (asynchronous programming with asyncio).
- **Blockchain Integration:** Solana mainnet via `solana-py` and `solders` for direct RPC communication, supporting bot-managed and external wallets.
- **Data Persistence:** SQLite (`cryptounc_lotto.db`) for user, wallet, lottery entry, and transaction data.
- **Security:** Fernet encryption for private keys, PBKDF2 for key derivation, 4-digit PIN for sensitive operations, and private keys are never transmitted or logged.

### Wallet Management

- **Multi-Wallet Support:** Users can create up to 3 bot-managed wallets or connect external wallets.
- **Operations:** Real-time SOL balance checks, transfers, PIN-protected private key viewing, and secure wallet deletion.

### Lottery System Design

- **Hourly Rounds:** 24 rounds daily, each 60 minutes.
- **Ticket Price:** 0.025 SOL per ticket.
- **Gameplay:** Players pick their own 5 numbers (1-40).
- **Winning Condition:** Match all 5 numbers to win the entire jackpot.
- **Jackpot:** 80% of ticket price contributes to the jackpot (Owner Wallet), 20% to the Team Wallet. Jackpot = owner wallet balance (live on-chain).
- **Prize Rollover:** If no winner, prize stays in owner wallet and rolls over to next round. No partial prizes.
- **Draws:** Automated at round end. Winning numbers are generated at round creation using cryptographic randomness.
- **Engagement Features:**
    - **Referral System:** Unique codes/links, 5% bonus for referred ticket purchases.
    - **VIP Tier System:** 5 tiers (Bronze to Diamond) based on tickets purchased, with badges and future perks.
    - **Leaderboard:** Ranks top winners and players by tickets purchased, including VIP badges.
    - **Personal Statistics:** Dashboard for total tickets, spending, winnings, VIP tier, and referral earnings.
    - **Notification System:** User-toggleable notifications for round reminders.
    - **Admin Jackpot Seeding:** Admins can manually seed the jackpot.

### Cryptographic Randomness

- **Seed Generation:** Uses SHA256 hashing with blockchain transaction signatures, blockhashes, and timestamps as entropy sources for verifiable fairness.
- **Verifiability:** All seed inputs are stored in the database for public verification of draw results.

### State Management & Background Processing

- **FSM:** Aiogram `FSMContext` for multi-step user interactions (e.g., PIN creation, wallet operations).
- **Scheduler:** Continuous background task to manage round progression, trigger draws, and process refunds, running independently.
- **Async Architecture:** Non-blocking Solana RPC calls and concurrent handling of user interactions.

### Payment Verification Flow

- **Stake Process:** Users input desired SOL stake. Bot validates amount and balance, initiates SOL transfer to Owner and Team Wallets, verifies transaction signature, and creates lottery entry.
- **Transaction Validation:** On-chain signature required for every stake; balances checked pre-transaction.

### Administrative Functions

- **Admin Commands:** Manual draw triggering, system configuration viewing, round management (accessible via `ADMIN_ID`).

### Web Server

- **Purpose:** Simple HTTP server on port 8080 for Replit uptime monitoring and health checks (`/`, `/health`, `/ping`).

## External Dependencies

### Third-Party Services

- **Solana RPC:** Mainnet endpoint (e.g., `https://api.mainnet-beta.solana.com`, with Helius/QuickNode recommended) for all blockchain interactions.
- **Telegram Bot API:** Core interface for user interaction; polling mode used.
- **UptimeRobot (Recommended):** External monitoring to keep Replit projects active.

### Environment Variables

- `BOT_TOKEN`: Telegram Bot API token.
- `OWNER_WALLET`: Main jackpot wallet address.
- `OWNER_WALLET_PRIVATE_KEY`: For automated prize distributions.
- `TEAM_WALLET`: Receives a percentage of stakes.
- `ADMIN_ID`: Telegram user ID for administrative access.
- `ROUND_CHANNEL_ID`: Public Telegram channel for announcements.
- `SOLANA_RPC`: Primary Solana RPC endpoint URL.
- `ENCRYPTION_KEY`: Master key for private key encryption.
- `SUPPORT_USERNAME`: Telegram support contact.
- `DATABASE_URL` (Required for Railway): PostgreSQL connection string provided by Railway.
- `HELIUS_RPC` (Optional): Secondary RPC endpoint for failover.
- `ANNOUNCEMENTS_GROUP_ID` (Optional): Telegram group for additional announcements.

### Python Package Dependencies

- `aiogram`: Telegram bot framework.
- `solana`, `solders`: Solana blockchain SDK and data structures.
- `cryptography`: Encryption for private keys.
- `aiohttp`: Async HTTP client/server.
- `python-dotenv`: Environment variable management.
- `pytz`: Timezone handling.
- `base58`: Address encoding/decoding.

### Database

- **PostgreSQL (Railway):** When `DATABASE_URL` environment variable is set, uses PostgreSQL for persistent storage across deployments.
- **SQLite (Fallback):** If no `DATABASE_URL`, falls back to file-based SQLite for local development.
- **Data Persistence:** All user data, wallets, and lottery entries are now persistent across Railway deployments.

### Wallet Connection Flow

- **External Wallet Integration:** HTML interface (Index.html) for signature verification with Phantom and Solflare wallets, using a challenge-response authentication pattern to extract public keys securely.

## Recent Changes (December 11, 2025)

### Player Number Selection
- Players now **pick their own 5 numbers** (1-40) instead of getting random numbers
- Interactive 8x5 grid of numbers to tap and select
- Visual feedback shows selected numbers with checkmarks (✅)
- Confirm button appears after selecting exactly 5 numbers
- Clear All and Cancel buttons for easy navigation
- Bot still generates winning numbers for each round using cryptographic randomness (provably fair)
- Payment only processed after player confirms their number selection
- FSM states added: `NumberSelectionStates.selecting_numbers`, `confirming_purchase`

### Engagement Features
1. **Referral System:** Coming soon (tracking only, no rewards yet)
2. **VIP Tier System:** Bronze → Silver → Gold → Platinum → Diamond
3. **Leaderboard:** Top winners and top players
4. **Personal Statistics Dashboard:** Tickets, spending, winnings, VIP tier
5. **Check Jackpot Button:** Live view of current prize pool (owner wallet balance)
6. **Admin Jackpot Seeding:** `/seedjackpot <amount>` command
7. **Prize Rollover:** No winner = jackpot carries forward to next round

### Database Migration (December 11, 2025)
- Migrated from SQLite to PostgreSQL for persistent storage on Railway
- Data now survives GitHub pushes and Railway redeployments
- Set `DATABASE_URL` environment variable in Railway to enable PostgreSQL
- Without `DATABASE_URL`, falls back to SQLite (local development only)

### New Database Tables
- `user_stats`: Tracks tickets, spending, winnings, VIP tier, referral earnings
- `referrals`: Stores referrer/referred relationships and bonus tracking
- `draw_history`: Complete draw records for provably fair verification
- `jackpot_seeds`: Admin seeding records
- `wallet_transactions`: Complete transaction history for all wallet operations (send, receive, lottery stakes, wins, refunds)

### Wallet System Improvements (December 11, 2025)
- **Transaction History Tracking:** All wallet operations (sends, lottery stakes, wins, refunds) are logged to `wallet_transactions` table
- **Wallet Summary:** Users can view total sent, received, staked, won, and refunded SOL
- **Address Validation:** Proper base58 validation for Solana addresses with helpful error messages
- **Balance Refresh:** Real-time balance checking from Solana network
- **PostgreSQL Compatibility:** All wallet queries use q() wrapper for automatic SQLite/PostgreSQL compatibility
- **Production-Ready:** Wallet system comparable to other Solana wallets with full transaction history

### PIN Security Improvements (December 11, 2025)
- **Immediate PIN Deletion:** PIN messages are deleted immediately after entry for security
- **PIN Confirmation:** First-time PIN setup requires entering PIN twice to confirm match
- **Auto-Delete Flow:** User enters PIN → message deleted → verify by re-entering → message deleted → action proceeds
- **Mismatch Handling:** If PINs don't match during setup, user is prompted to start over with new PIN
- **Persistent PINs:** PINs are now persistent - set once and reuse for all future operations (no more re-entering PIN every time)
- **user_id Consistency:** All PIN functions use int(user_id) for consistent database lookups

### Security Question System (December 11, 2025)
- **Security Questions:** Users can set up a security question for PIN recovery
- **5 Preset Questions:** Common options like mother's maiden name, first pet, etc.
- **Custom Questions:** Users can create their own security question
- **PIN Reset via Security Question:** Forgot PIN? Answer your security question to reset
- **Settings Menu:** New ⚙️ Settings button in main menu for security settings
- **Answer Hashing:** Answers are hashed with SHA256 for security (case-insensitive)

### Database Performance Improvements (December 11, 2025)
- **PostgreSQL Connection Pooling:** 2-10 pooled connections for faster queries
- **New Tables:** `security_questions` for PIN recovery
- **Answer Hashing:** Security question answers are hashed with SHA256

### Button Response Speed Fix (December 11, 2025)
- **Balance Caching:** Jackpot balance is now cached for 30 seconds to speed up Start/Back button responses
- **Faster UI:** No more waiting for Solana RPC on every button press
- **Referral Query Fix:** All referral functions now use q() wrapper for PostgreSQL compatibility
- **Fixed IndexError:** Resolved "tuple index out of range" error in referral code lookup

### Railway-Only Deployment (December 11, 2025)
- **Platform Restriction:** Bot now runs ONLY on Railway platform
- **Conflict Prevention:** Blocks execution on Replit/other platforms to prevent Telegram polling conflicts
- **Automatic Detection:** Uses Railway environment variables (RAILWAY_ENVIRONMENT, RAILWAY_PROJECT_ID) to verify platform
- **Exit on Unauthorized:** Immediately exits with clear message if not running on Railway

### Performance Optimizations (December 11, 2025)
- **5-Second RPC Timeout:** Each RPC call now times out after 5 seconds to speed up failover
- **Parallel Balance Fetching:** Wallet menu fetches all wallet balances simultaneously instead of one-by-one
- **Fixed Security Question Saving:** PostgreSQL upsert syntax corrected (uses EXCLUDED.column)
- **Fixed Referral LIKE Query:** PostgreSQL LIKE pattern with % now handled correctly