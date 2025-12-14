AI_SYSTEM_PROMPT = """You are CryptoUnc Lotto AI Assistant. Your job is to help users understand the CryptoUnc Lotto system. Always explain clearly and in plain language. Never promise winnings, never predict outcomes, never give financial advice, and never encourage gambling. Answer politely and responsibly. If a user asks about errors or problems, provide general troubleshooting steps or explain common causes, but do not access or reveal any private wallet information. Always remind users that the system is for entertainment and they should play responsibly."""

FAIRNESS_PROMPT = """You are CryptoUnc Lotto AI Assistant. Explain clearly and professionally how CryptoUnc Lotto is fair. Cover the ticket purchase process, how randomness works, how winners are selected, how the system uses Solana for on-chain verification, and how results are transparent. Emphasize that the AI does not control the outcome, does not handle funds, and cannot guarantee winnings. Make the explanation simple, trustworthy, and understandable for any user. Remind users to play responsibly."""

HOW_TO_PLAY_PROMPT = """You are CryptoUnc Lotto AI Assistant. Explain step-by-step how to play CryptoUnc Lotto:
1. Start the bot and create or connect a Solana wallet
2. Set up a 4-digit PIN for security
3. Deposit SOL to your wallet (minimum 0.025 SOL + fees)
4. Tap "Play Now" and then "Buy Ticket"
5. Pick 5 numbers from 1-40
6. Confirm your selection and the payment is processed automatically
7. Wait for the hourly draw - if your numbers match all 5 winning numbers, you win the entire jackpot!

Key points:
- Ticket price: 0.025 SOL
- 24 rounds per day (one every hour)
- 80% goes to prize pool, 20% to team
- Match all 5 numbers to win
- If no winner, jackpot rolls over

Keep explanations simple and encourage responsible play."""

WALLET_HELP_PROMPT = """You are CryptoUnc Lotto AI Assistant helping with wallet-related questions. Explain:
- Users can create a bot-managed wallet (recommended for beginners)
- Users can import an existing wallet using private key
- Users can connect external wallets (Phantom, Solflare)
- Maximum 3 wallets per user
- A 4-digit PIN is required for security operations
- Private keys are encrypted and stored securely
- Auto-delete feature removes private key messages after 30 seconds

Emphasize security:
- Never share your private key with anyone
- Your PIN is required for viewing private keys and sending SOL
- Set up a security question for PIN recovery

Never reveal private key information or help bypass security."""

STATS_EXPLANATION_PROMPT = """You are CryptoUnc Lotto AI Assistant. Explain user statistics and the VIP system:

VIP Tiers (based on total amount spent):
- Bronze: 0-1 SOL spent
- Silver: 1-5 SOL spent  
- Gold: 5-20 SOL spent
- Platinum: 20-50 SOL spent
- Diamond: 50+ SOL spent

Statistics tracked:
- Total tickets purchased
- Total SOL spent
- Total winnings
- Win rate percentage
- Current VIP tier

Leaderboards show top winners and most active players. Encourage playing but remind about responsible gambling."""

SUPPORT_PROMPT = """You are CryptoUnc Lotto AI Assistant providing support guidance. Help users with:

Common issues:
- "Transaction failed" - Check wallet balance, ensure enough for ticket + fees (~0.001 SOL)
- "Can't see my tickets" - Tickets are tied to the current round, check "My Tickets"
- "Balance not updating" - Solana network may be congested, wait a few minutes
- "PIN forgot" - Use security question recovery or contact admin
- "Wallet limit reached" - Maximum 3 wallets per user, delete one to add new

For unresolved issues, direct users to contact support through the Support button or @admin username.

Never access user wallets, never promise refunds, never share private information."""

FAQ_RESPONSES = {
    # Basic gameplay
    "how to play": "Getting started is easy!\n\n1. Tap 'Play Now' from the main menu\n2. Create or connect your Solana wallet\n3. Set up your 4-digit security PIN\n4. Buy a ticket for 0.025 SOL\n5. Pick 5 lucky numbers (1-40)\n6. Wait for the hourly draw!\n\nMatch all 5 numbers to win the entire jackpot!",
    "play": "Getting started is easy!\n\n1. Tap 'Play Now' from the main menu\n2. Create or connect your Solana wallet\n3. Set up your 4-digit security PIN\n4. Buy a ticket for 0.025 SOL\n5. Pick 5 lucky numbers (1-40)\n6. Wait for the hourly draw!\n\nMatch all 5 numbers to win the entire jackpot!",
    "start": "Welcome to CryptoUnc Lotto!\n\nTo get started:\n1. Tap /start if you haven't already\n2. Use the 'Play Now' button\n3. Set up your wallet and PIN\n4. Buy tickets and pick your numbers!\n\nNeed help? Just ask me anything!",
    
    # Ticket info
    "ticket price": "Each ticket costs 0.025 SOL (about $4-5 depending on SOL price).\n\nYou can buy unlimited tickets per round to increase your chances! Each ticket lets you pick 5 different numbers.",
    "price": "Ticket price: 0.025 SOL\n\nYou'll also need a tiny bit extra (~0.001 SOL) for Solana network fees. So have at least 0.026 SOL in your wallet to buy a ticket.",
    "cost": "Each ticket costs 0.025 SOL plus a small network fee (~0.001 SOL).\n\nMake sure you have at least 0.026 SOL in your wallet!",
    "buy ticket": "To buy a ticket:\n\n1. Go to 'Play Now' from main menu\n2. Tap 'Buy Ticket'\n3. Pick 5 numbers from 1-40\n4. Confirm your selection\n5. The payment happens automatically!\n\nEach ticket costs 0.025 SOL. Good luck!",
    
    # Draw timing
    "when is draw": "Draws happen every hour on the hour, 24 times per day!\n\nFor example: 12:00, 1:00, 2:00, 3:00... and so on.\n\nThe next draw will be at the top of the next hour.",
    "draw time": "Draws run every hour, 24/7!\n\nThe drawing happens automatically at :00 of every hour (UTC time). Check 'Current Round' to see the countdown!",
    "next draw": "The next draw happens at the top of the next hour!\n\nWe have 24 draws per day - one every hour. Check the 'Current Round' info for the exact countdown.",
    "when": "Draws happen every hour on the hour!\n\n24 rounds per day means 24 chances to win. The jackpot keeps growing until someone matches all 5 numbers!",
    
    # Winning
    "how to win": "To win the JACKPOT:\n\nMatch ALL 5 of your chosen numbers with the 5 winning numbers drawn!\n\nThe winning numbers are generated using blockchain randomness - completely fair and verifiable. If you match all 5, you take home the entire prize pool!",
    "win": "To win:\n\nPick 5 numbers between 1-40 when buying your ticket. If all 5 match the winning numbers drawn, you win the ENTIRE jackpot!\n\nNo partial prizes - it's all or nothing! That's why the jackpot keeps growing until someone wins.",
    "odds": "Each ticket picks 5 numbers from 1-40.\n\nThe odds of matching all 5 winning numbers are challenging, but that's what makes the jackpot grow so big! Every ticket you buy is another chance to win it all.",
    
    # Jackpot rollover
    "what happens if no winner": "If no one matches all 5 numbers:\n\nThe jackpot ROLLS OVER to the next round! It keeps growing until someone wins.\n\n80% of each ticket sale adds to the prize pool. No winner = bigger jackpot next round!",
    "no winner": "No worries! If no one wins, the jackpot rolls over and grows even bigger!\n\nThe prize pool keeps accumulating until someone matches all 5 numbers. This is how jackpots get MASSIVE!",
    "rollover": "Yes! The jackpot rolls over if there's no winner.\n\n80% of every ticket sale goes to the prize pool. If no one wins, all that money carries forward to the next round. Jackpots can get huge!",
    "jackpot": "The jackpot is the total prize pool that the winner takes home!\n\nHow it works:\n- 80% of ticket sales go to the jackpot\n- If no one wins, it rolls over\n- Match all 5 numbers = you get EVERYTHING!\n\nCheck 'Current Round' to see the current jackpot size.",
    
    # Fairness
    "is it fair": "Absolutely! Here's how we ensure fairness:\n\n1. Winning numbers use blockchain randomness\n2. Results are cryptographically verified\n3. All draws are transparent and auditable\n4. No one can predict or manipulate results\n\nThe system is provably fair - you can verify every draw!",
    "fair": "100% fair and transparent!\n\nWinning numbers are generated using Solana blockchain data - cryptographic randomness that no one can control or predict. Every result is verifiable on-chain.",
    "rigged": "Not at all! CryptoUnc Lotto uses blockchain-based randomness.\n\nThe winning numbers come from cryptographic hashes of Solana blockchain data. This is mathematically impossible to manipulate. Anyone can verify the results!",
    "random": "The random number selection is powered by Solana blockchain data!\n\nWe use cryptographic hashes of block data and transaction signatures to generate provably fair random numbers. No one - not even the bot operators - can predict or control the results.",
    
    # Prizes
    "how prizes work": "Prize distribution is simple:\n\n- 80% of ticket sales go to the prize pool\n- 20% goes to the team (operations & development)\n- If you match all 5 numbers, you win the ENTIRE 80%!\n\nNo partial prizes - winner takes all!",
    "prizes": "All prizes go to the jackpot winner!\n\n80% of every ticket sale goes to the prize pool. Match all 5 winning numbers and you take home everything. The jackpot keeps growing until someone wins!",
    "payout": "Winners receive the full jackpot automatically!\n\nWhen you win, the prize is sent directly to your connected wallet. 80% of all ticket sales make up the prize pool - and you get it ALL if you match 5 numbers!",
    
    # Wallet
    "wallet security": "Your wallet security is our priority!\n\n- Private keys are encrypted with military-grade encryption\n- 4-digit PIN required for sensitive operations\n- Private key messages auto-delete after 30 seconds\n- Security questions for PIN recovery\n\nNever share your private key or PIN with anyone!",
    "wallet": "Wallet options:\n\n1. Create Bot Wallet - We generate a secure wallet for you\n2. Import Wallet - Use your existing private key\n3. Connect External - Link Phantom or Solflare\n\nMax 3 wallets per user. All keys are encrypted!",
    "private key": "Your private key is your ultimate security!\n\nWe encrypt it with strong encryption. When you view it, the message auto-deletes after 30 seconds.\n\nNEVER share your private key with anyone - not even support staff!",
    "pin": "Your 4-digit PIN protects sensitive operations:\n\n- Viewing private keys\n- Sending SOL\n- Deleting wallets\n\nForgot your PIN? Use your security question to reset it. Keep your PIN secret!",
    
    # Balance & transactions
    "balance": "To check your balance:\n\n1. Go to 'Wallet' from the main menu\n2. Your SOL balance appears at the top\n\nBalance not updating? The Solana network might be congested. Wait a few minutes and try again!",
    "deposit": "To deposit SOL:\n\n1. Go to 'Wallet' > 'Deposit'\n2. Copy your wallet address\n3. Send SOL from any exchange or wallet\n4. Wait for confirmation (usually 30 seconds)\n\nMinimum needed: 0.026 SOL (ticket + fees)",
    "withdraw": "To withdraw SOL:\n\n1. Go to 'Wallet' > 'Send SOL'\n2. Enter the destination address\n3. Enter the amount\n4. Confirm with your PIN\n\nMake sure to leave some SOL for network fees!",
    
    # Support
    "support": "Need help? Here's what to do:\n\n1. Try asking me - I can answer most questions!\n2. Check the FAQ in the menu\n3. Use the Support button to contact an admin\n\nCommon issues I can help with: transactions, wallet setup, gameplay questions, and more!",
    "help": "I'm here to help! You can ask me about:\n\n- How to play and buy tickets\n- Wallet setup and security\n- Prize distribution and draws\n- Transaction issues\n- VIP tiers and stats\n\nJust type your question and I'll do my best to assist!",
    "contact": "To contact support:\n\n1. Use the 'Support' button in the menu\n2. Describe your issue clearly\n3. Include any error messages or transaction IDs\n\nI can also help with most questions right here!",
    
    # VIP & Stats
    "vip": "VIP Tiers based on total SOL spent:\n\n- Bronze: 0-1 SOL\n- Silver: 1-5 SOL\n- Gold: 5-20 SOL\n- Platinum: 20-50 SOL\n- Diamond: 50+ SOL\n\nHigher tiers = exclusive perks! Check your stats to see your current tier.",
    "stats": "Your stats track:\n\n- Total tickets purchased\n- Total SOL spent\n- Total winnings\n- Win rate percentage\n- Current VIP tier\n\nGo to 'My Stats' to see your full profile!",
    "leaderboard": "The leaderboard shows:\n\n- Top winners by prize amount\n- Most active players\n- VIP tier rankings\n\nPlay more to climb the ranks!",
    
    # Referral
    "referral": "Referral program coming soon!\n\nYou'll be able to share your unique referral link and earn bonuses when friends play. Stay tuned for updates!",
    "referral program": "The referral program is coming soon!\n\nShare your link, invite friends, earn rewards. Watch for announcements about the launch!",
    
    # Errors & Troubleshooting
    "transaction failed": "Transaction failed? Here's what to check:\n\n1. Wallet balance - need 0.026+ SOL\n2. Network congestion - try again in a minute\n3. Wallet connection - reconnect if needed\n\nStill having issues? Contact support with the error message!",
    "error": "Getting an error? Common fixes:\n\n1. Check your wallet balance\n2. Make sure you have enough for fees (~0.001 SOL)\n3. Try refreshing or restarting the bot\n4. Wait a minute and try again\n\nIf it persists, contact support with the error details!",
    "not working": "Something not working? Try these steps:\n\n1. Type /start to restart the bot\n2. Check your wallet balance\n3. Wait a minute and try again\n4. Make sure Solana network isn't congested\n\nStill stuck? Use the Support button to get help!",
    
    # Greetings & casual
    "hello": "Hey there! Welcome to CryptoUnc Lotto!\n\nI'm your AI assistant. Ask me anything about:\n- How to play\n- Wallet setup\n- Prizes and draws\n- Any other questions!\n\nWhat can I help you with today?",
    "hi": "Hi! Great to have you here!\n\nI'm the CryptoUnc Lotto AI assistant. I can help you understand how the lottery works, set up your wallet, and answer any questions.\n\nWhat would you like to know?",
    "hey": "Hey! Welcome!\n\nI'm here to help with anything about CryptoUnc Lotto. Just ask away!",
    "thanks": "You're welcome! Happy to help!\n\nIf you have any more questions, just ask. Good luck with your tickets!",
    "thank you": "My pleasure! That's what I'm here for.\n\nGood luck in the next draw! Remember to play responsibly.",
    
    # Solana specific
    "solana": "CryptoUnc Lotto runs on the Solana blockchain!\n\nWhy Solana?\n- Super fast transactions (< 1 second)\n- Very low fees (~$0.001)\n- Secure and decentralized\n- Perfect for fair lottery draws!\n\nYou'll need SOL tokens to buy tickets.",
    "sol": "SOL is the native token of the Solana blockchain.\n\nYou need SOL to:\n- Buy lottery tickets (0.025 SOL each)\n- Pay network fees (~0.001 SOL)\n\nYou can buy SOL on exchanges like Coinbase, Binance, or through Phantom wallet.",
    "gas": "On Solana, we call them 'network fees' not gas!\n\nSolana fees are super low - about 0.001 SOL per transaction (less than $0.01). Always keep a little extra SOL in your wallet for fees.",
    "fees": "Fees on Solana are minimal!\n\nNetwork fees: ~0.001 SOL per transaction\nTeam fee: 20% of ticket sales (for operations)\nWinner gets: 80% of ticket sales\n\nThat's it! No hidden fees.",
}

# Extended keyword matching for better response rates
FAQ_KEYWORDS = {
    "play": ["how to play", "play", "start", "begin", "get started", "new player", "newbie", "first time"],
    "ticket": ["ticket price", "price", "cost", "ticket", "buy", "purchase", "how much"],
    "draw": ["when is draw", "draw time", "next draw", "when", "what time", "schedule", "timing"],
    "win": ["how to win", "win", "odds", "chance", "winning", "winner"],
    "jackpot": ["jackpot", "prize", "pot", "pool", "reward", "money", "payout"],
    "rollover": ["rollover", "no winner", "what happens", "carries over"],
    "fair": ["fair", "rigged", "random", "legit", "scam", "trust", "honest"],
    "wallet": ["wallet", "balance", "deposit", "withdraw", "send", "receive", "address"],
    "security": ["pin", "private key", "security", "password", "protect", "safe", "secure"],
    "help": ["help", "support", "contact", "issue", "problem", "error", "stuck", "not working"],
    "vip": ["vip", "tier", "level", "rank", "stats", "leaderboard"],
    "greeting": ["hello", "hi", "hey", "yo", "sup", "greetings"],
    "thanks": ["thanks", "thank you", "thx", "ty", "appreciate"],
    "solana": ["solana", "sol", "gas", "fees", "blockchain", "crypto", "token"],
}
