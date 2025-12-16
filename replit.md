# CryptoUnc Lotto Bot

## Overview
A Telegram-based cryptocurrency lottery bot with real Solana wallet integration. Users can buy lottery tickets with SOL, with automated draws and prize distribution.

**SQLite fully removed. PostgreSQL only.**

## Database
- **PostgreSQL only** - No SQLite fallback
- Connected via `DATABASE_URL` environment variable
- All tables recreated cleanly without old constraints
- Users can buy multiple tickets per round (no UNIQUE constraint on user_id, round_stake_id)
- Optimized indexes for round_id, user_id+round_stake_id, transaction_signature

## Architecture
- **Bot Framework**: aiogram 3.4.1 (Telegram Bot API)
- **Blockchain**: Solana mainnet via solana-py/solders
- **Database**: PostgreSQL (required, no SQLite)
- **AI Assistant**: OpenAI GPT-4o with Gemini and Groq fallbacks
- **Encryption**: cryptography library for wallet private key encryption
- **Caching**: In-memory cache layer for reduced DB/RPC reads
- **Rate Limiting**: Per-user rate limits for spam prevention
- **RPC Management**: Centralized RPC manager with load balancing and failover

## Key Files
- `main.py` - Main bot logic and handlers
- `db.py` - PostgreSQL-only database layer
- `wallet.py` - Solana wallet management
- `wallet_buttons.py` - Wallet action button handlers
- `ai/ai_client.py` - AI assistant client with OpenAI/Gemini/Groq fallback chain
- `ai_fallback.py` - Standalone AI fallback module with three-tier fallback
- `ai/prompts.py` - AI prompts and FAQ responses
- `email_service.py` - Email verification service
- `encryption.py` - Private key encryption
- `rpc_manager.py` - Centralized RPC with load balancing and failover
- `cache_layer.py` - In-memory cache with TTL for reducing reads
- `rate_limiter.py` - Per-user rate limiting and duplicate callback prevention
- `tx_verification_queue.py` - Async transaction verification queue

## AI Assistant Features
- **How to Play** - Step-by-step gameplay guide
- **Fairness Explanation** - How lottery ensures transparency
- **Wallet Help** - Creating, importing, securing wallets
- **Stats & VIP** - Statistics and VIP tier explanations
- **Ask Questions** - Free-form Q&A with fallback FAQ
- **OpenAI + Gemini + Groq Fallback** - Uses OpenAI GPT-4o primary, Google Gemini 2.0 Flash as second fallback, Groq Llama3-8B as final fallback
- **Persistent Chat Sessions** - Conversations saved to database for 3 days
- **User Memory** - AI remembers user names and preferences permanently

Access via "AI Assistant" button in main menu.

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
- `HELIUS_RPC` - Helius RPC endpoint (primary for writes)
- `TEAM_WALLET` - Team Solana wallet for fees
- `SUPPORT_USERNAME` - Support contact
- `ANNOUNCEMENTS_GROUP_ID` - Additional announcement group
- `OPENAI_API_KEY` - OpenAI API key for AI assistant (primary)
- `GEMINI_API_KEY` - Google Gemini API key (second fallback when OpenAI fails)
- `GROQ_API_KEY` - Groq API key (final fallback when both OpenAI and Gemini fail)

## Recent Changes (December 2025)
- **Groq AI Fallback Added** - Added Groq Llama3-8B-8192 as the third AI fallback option (OpenAI -> Gemini -> Groq)
- **Persistent AI Chat Sessions** - Chat history stored in database for 3 days, AI remembers conversations
- **AI User Memory** - AI permanently remembers user names and basic info via user_profiles table
- **Ticket Purchase Announcements Disabled** - Ticket purchases no longer broadcast to groups/channels (other announcements still work)
- **Round Count Reset** - Round counter resets to 1 after every 24th round (24-round cycle)
- **Google Gemini AI Fallback** - Added Gemini 2.0 Flash as fallback when OpenAI fails
- **Forgot PIN Feature** - "Forgot PIN?" button appears after 2 wrong PIN attempts (uses security question)
- **Mandatory Security Question** - First-time PIN setup now requires setting up a security question
- **AI Assistant Added** - OpenAI GPT-5 powered help system with Gemini fallback and FAQ fallback
- **Production-ready refactoring** - Added caching, rate limiting, RPC load balancing
- **RPC Manager** - Centralized RPC with Helius primary, round-robin reads, automatic failover
- **Cache Layer** - In-memory cache for pot, round info, balances (10-60s TTL)
- **Rate Limiter** - Per-user rate limits for buttons, purchases, commands
- **Duplicate Callback Prevention** - Prevents double-click processing
- **Async TX Verification Queue** - Background transaction verification (not yet fully integrated)
- **Database Indexes** - Added indexes for (user_id, round_stake_id), tx_signature
- **SQLite fully removed** - PostgreSQL is now mandatory
- **Multiple tickets per user** - No UNIQUE constraint on (user_id, round_stake_id)

## Running the Bot
1. Set all required environment variables
2. Ensure PostgreSQL database is available
3. Run `python main.py`

The bot will:
- Initialize the PostgreSQL connection pool
- Create all necessary tables
- Initialize cache and rate limiter
- Load AI model (lazy loading on first use)
- Start listening for Telegram commands
