# CryptoUnc Lotto Telegram Bot

## Overview

CryptoUnc Lotto is a decentralized lottery bot for Telegram that enables users to play lottery games with real Solana (SOL) cryptocurrency. The bot integrates directly with the Solana blockchain mainnet, allowing users to create wallets, deposit SOL, participate in lottery rounds with various stake levels, and receive automatic prize distributions. The system uses cryptographic randomness based on blockchain data for verifiable fairness.

**Current Status:** Production-ready and live on Replit (as of November 9, 2025)

## User Preferences

Preferred communication style: Simple, everyday language.

## System Architecture

### Core Technology Stack

**Language & Framework:**
- Python 3.11 as the runtime environment
- Aiogram 3.4.1 for Telegram Bot API integration
- Asynchronous programming model using asyncio for concurrent operations

**Blockchain Integration:**
- Solana mainnet integration via solana-py 0.30.2 and solders 0.18.1
- Direct RPC communication with Solana blockchain for transaction verification
- Support for both bot-managed wallets and external wallet connections (Phantom, Solflare)

**Data Persistence:**
- SQLite database (cryptounc_lotto.db) for local file-based storage
- Tables for users, wallets, lottery entries, rounds, stakes, draws, and transaction records
- Transaction signatures and blockchain data stored for audit trail and verification

**Security:**
- Fernet encryption (cryptography 41.0.7) for storing wallet private keys
- PBKDF2 key derivation with 100,000 iterations from master ENCRYPTION_KEY
- 4-digit PIN system for sensitive wallet operations
- Private keys never transmitted or logged

### Wallet Management Architecture

**Multi-Wallet Support:**
- Users can create up to 3 wallets per account
- Support for bot-managed wallets (with encrypted private key storage)
- Support for external wallet connections via signature verification
- Active wallet selection system for transaction operations

**Wallet Operations:**
- Real-time balance checking from Solana blockchain
- SOL transfers between wallets with transaction signing
- Private key viewing (PIN-protected)
- Wallet deletion with security confirmations

### Lottery System Design

**Stake-Based Rounds:**
- Multiple concurrent lottery rounds with different stake levels (0.025 SOL to 5 SOL)
- Each stake level maintains separate participant pools
- Minimum 10 players required per stake level to trigger a draw

**Draw Triggers:**
- Automatic draw when 10 players join a stake level
- Time-based draw trigger (30 minutes after first participant joins)
- Draws process asynchronously via background scheduler

**Prize Distribution:**
- 80% of total pool goes to winner
- 20% goes to team wallet
- Transaction fees deducted from winner's portion
- Automatic SOL transfers using owner wallet private key
- Transaction signatures stored and announced publicly

**Refund System:**
- Automatic refunds if minimum players not reached
- Refund amount = stake minus 2% network fee
- Retry logic with up to 3 attempts per refund
- All participants notified via Telegram

### Cryptographic Randomness

**Seed Generation:**
- SHA256-based cryptographic hashing
- Uses blockchain transaction signatures as entropy source
- Combines multiple entropy sources: blockhashes, transaction data, timestamps
- All seed inputs stored in database for public verification
- Results are deterministic and independently verifiable

**Design Rationale:**
- Chose blockchain-based randomness for transparency and verifiability
- Alternative considered: Chainlink VRF (deferred to Phase 2 for cost reasons)
- Current approach allows anyone to verify draw results using stored seed data

### State Management

**FSM (Finite State Machine):**
- Aiogram FSMContext for managing multi-step user interactions
- States for PIN creation, wallet operations, SOL transfers
- Session data persisted across callback queries

**Database Schema:**
- Users table: Telegram user data and registration timestamps
- Wallets table: Wallet addresses, types, encrypted private keys
- Entries table: Lottery tickets with generated numbers
- Round stakes: Participant tracking, stake amounts, first join timestamps
- Draws table: Winning numbers, winners, prize amounts, transaction signatures

### Background Processing

**Scheduler:**
- Continuous background task checking for drawable rounds
- Monitors both player count and time elapsed conditions
- Processes refunds for expired rounds
- Runs independently from main bot polling loop

**Async Architecture:**
- Web server (port 8080) runs concurrently with bot
- Health check endpoints for uptime monitoring
- Non-blocking Solana RPC calls
- Concurrent handling of multiple user interactions

### Payment Verification Flow

**Stake Payment Process (Keyboard Input):**
1. User taps "Stake" button
2. Bot displays current balance and stake range (0.025 - 5 SOL)
3. User types desired stake amount via keyboard
4. Bot validates: minimum (0.025 SOL), maximum (5 SOL), and balance
5. Bot initiates SOL transfer to OWNER_WALLET (80%) and TEAM_WALLET (20%)
6. Transaction signature verified and stored
7. Entry created only after successful payment confirmation
8. User receives 5 lottery numbers (1-40)

**Transaction Validation:**
- Every stake requires on-chain transaction signature
- Balance verification before accepting entries
- All transactions logged with amounts, addresses, and signatures

### Administrative Functions

**Admin Commands:**
- Manual draw triggering (though automated draws are primary)
- System configuration viewing
- Round management capabilities
- Accessible only to configured ADMIN_ID

### Web Server for Uptime

**Purpose:**
- Keep-alive mechanism for Replit free tier
- HTTP server on port 8080
- Health check endpoints: `/`, `/health`, `/ping`
- Enables 24/7 operation with UptimeRobot monitoring

**Design Decision:**
- Chose simple HTTP server over more complex solutions
- Runs concurrently with bot using asyncio
- Minimal resource overhead

## External Dependencies

### Third-Party Services

**Solana RPC:**
- Mainnet endpoint for blockchain interactions
- Default: https://api.mainnet-beta.solana.com
- Recommended: Premium RPC providers (Helius, QuickNode) for production
- Used for: balance queries, transaction broadcasting, blockhash fetching

**Telegram Bot API:**
- Primary user interface through Telegram
- Webhook mode disabled (polling used instead)
- Requires BOT_TOKEN from @BotFather

**UptimeRobot (Recommended):**
- External monitoring service for 24/7 uptime
- Pings health endpoint every 5 minutes
- Prevents Replit from sleeping inactive projects

### Environment Variables Required

**Critical Configuration (9 variables):**
1. `BOT_TOKEN` - Telegram Bot API authentication
2. `OWNER_WALLET` - Main treasury address (receives 80% of stakes)
3. `OWNER_WALLET_PRIVATE_KEY` - For automated prize distributions
4. `TEAM_WALLET` - Receives 20% of prize pools
5. `ADMIN_ID` - Telegram user ID for administrative access
6. `ROUND_CHANNEL_ID` - Public announcement channel
7. `SOLANA_RPC` - Blockchain endpoint URL
8. `ENCRYPTION_KEY` - Master key for wallet encryption (min 32 chars)
9. `SUPPORT_USERNAME` - Telegram support contact

### Python Package Dependencies

**Core Libraries:**
- aiogram 3.4.1 - Telegram bot framework
- solana 0.30.2 - Solana blockchain SDK
- solders 0.18.1 - Solana data structures
- cryptography 41.0.7 - Encryption for private keys
- aiohttp 3.9.1 - Async HTTP client/server
- python-dotenv 1.0.0 - Environment variable management
- pytz - Timezone handling for round scheduling
- base58 2.1.1 - Address encoding/decoding

### Database

**SQLite:**
- File-based database (cryptounc_lotto.db)
- No external database server required
- Simple backup via file copy
- Suitable for current scale
- Migration path to PostgreSQL considered for Phase 2 scaling

### Wallet Connection Flow

**External Wallet Integration:**
- HTML interface (Index.html) for wallet signature verification
- Supports Phantom and Solflare mobile/browser wallets
- Challenge-response authentication pattern
- Session-based verification using server-generated challenges
- Public key extraction without exposing private keys

### Recent Changes (December 5, 2025 - Latest)

**Multiple Tickets & Announcements Update:**
- Multiple tickets per user: Removed duplicate check in add_round_participant() - users can now buy as many tickets as they want
- Each ticket counts as 1 player toward the minimum 10-player requirement
- Added `announce_new_ticket()` function to post ticket purchases to announcements channel
- Ticket announcements include: Player username/Telegram ID, ticket number, lottery numbers, stake amount, current player count
- Updated `send_to_announcements()` to include bot redirect link for forwarded messages
- All three stake joining flows now call announce_new_ticket after successful purchase

**Private Key Safety Reminders:**
- Added prominent safety warnings when creating new wallets
- Added safety warnings when importing wallets with private key
- Warnings include: NEVER share key, CryptoUnc team will NEVER ask for key, anyone with key can steal funds

**Lottery Timing Configuration:**
- 15-minute wait before drawing when 10+ players join a stake level
- 30-minute refund timeout for rounds that don't reach minimum players
- Each ticket = 1 player (so one user buying 10 tickets = 10 players)

### Previous Changes (December 5, 2025)

**Platform Authorization (UPDATED):**
- Bot now verifies it's running on Railway OR Replit platform before starting
- Checks for RAILWAY_ENVIRONMENT and RAILWAY_PROJECT_ID environment variables (Railway)
- Also accepts REPL_ID or REPLIT_DEPLOYMENT (Replit)
- Optional RAILWAY_DEPLOY_SECRET / EXPECTED_DEPLOY_SECRET for additional verification
- Exits with clear error message if not running on authorized instance
- Security model documented in main.py header comments

**Transaction Fix (CRITICAL):**
- Fixed "'solders.transaction.Transaction' object has no attribute 'recent_blockhash'" error
- Changed from `client.send_transaction(transaction)` to `client.send_raw_transaction(bytes(transaction))`
- The solders Transaction object is immutable - must serialize to bytes before sending
- Updated both `send_sol()` and `sign_and_send_transaction()` functions

**Helius RPC with Automatic Fallback (NEW):**
- Added HELIUS_RPC environment variable for primary Helius RPC endpoint
- Automatic fallback to public mainnet RPC (https://api.mainnet-beta.solana.com)
- RPC_ENDPOINTS list built with deduplication for reliable failover
- All wallet functions (get_real_balance, estimate_transaction_fee, send_sol) use consistent failover
- Enhanced logging for RPC endpoint usage and balance checking

**Enhanced Transaction Processing:**
- Balance check before every transaction includes network fee buffer (~0.00002 SOL)
- Latest blockhash fetched right before creating each transaction
- Comprehensive logging: wallet address, balance, amount, RPC endpoint used
- Transaction signature logged on success

**Announcements Group Feature:**
- Added optional `ANNOUNCEMENTS_GROUP_ID` environment variable to post round updates to a Telegram group
- All announcements (round opened, round cancelled, draw results, winner announcements, refunds) now post to both the main channel AND the announcements group
- Helper function `send_to_announcements()` handles dual-channel broadcasting
- The group ID should be a numeric ID (e.g., -100123456789) - you can get this by forwarding a message from the group to @userinfobot
- If not set, announcements only go to ROUND_CHANNEL_ID as before

**Migration & Bug Fixes:**
- Migrated from deprecated `Transaction.new()` to correct `Transaction([keypair], message, blockhash)` API for solders 0.18.x
- Fixed wallet duplication bug - wallets are now checked BEFORE insert, first wallet set as active
- Added real-time transaction functions: `build_unsigned_transaction()`, `sign_and_send_transaction()`, `execute_automatic_transfer()`
- Added balance validation and RPC error classification to transaction helpers

### Recent Changes (December 4, 2025)

**Import Wallet Feature (MAJOR UPDATE):**
- Replaced "Connect Wallet" with "Import Wallet" for real-time wallet import
- Users can import existing Solana wallets using private keys
- Supported formats: Hex (128 chars), Base58 (Phantom), JSON array (Solflare)
- Function: `import_wallet_from_private_key()` in wallet.py
- Security measures:
  - User's private key message is IMMEDIATELY deleted
  - Private keys are encrypted before database storage
  - Success confirmation message auto-deletes after 30 seconds
  - Strong security warnings before import

**Navigation System:**
- Added Start and Back buttons to all prompts for consistent navigation
- Helper functions: `get_start_button()`, `get_back_button()`, `create_keyboard_with_nav()`
- All major screens now include navigation buttons at the bottom

**Security Enhancements:**
- Auto-delete for private key messages (30 seconds after viewing)
- Clear warning displayed before deletion countdown
- Security notice sent after auto-deletion
- Helper function: `schedule_private_key_deletion()`

**UI/UX Improvements:**
- Consistent keyboard layouts across all prompts
- Clear visual hierarchy with emoji indicators
- Better error messages with navigation options
- Imported wallets support: View Private Key, Send SOL, Delete