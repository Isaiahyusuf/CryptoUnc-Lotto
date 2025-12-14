import asyncio
import re
from typing import Optional
from .prompts import (
    AI_SYSTEM_PROMPT, 
    FAIRNESS_PROMPT, 
    HOW_TO_PLAY_PROMPT,
    WALLET_HELP_PROMPT,
    STATS_EXPLANATION_PROMPT,
    SUPPORT_PROMPT,
    FAQ_RESPONSES,
    FAQ_KEYWORDS
)

_model = None
_model_loading = False
_model_error = None

def get_model():
    """Lazy load the GPT4All model to avoid startup delays"""
    global _model, _model_loading, _model_error
    
    if _model is not None:
        return _model
    
    if _model_error:
        return None
        
    if not _model_loading:
        _model_loading = True
        try:
            from gpt4all import GPT4All
            _model = GPT4All("ggml-gpt4all-j-v1.3-groovy", allow_download=True)
            print("[AI] Model loaded successfully")
        except Exception as e:
            _model_error = str(e)
            print(f"[AI] Model loading failed: {e}")
            _model = None
        finally:
            _model_loading = False
    
    return _model

def normalize_text(text: str) -> str:
    """Normalize text for better matching"""
    text = text.lower().strip()
    text = re.sub(r'[^\w\s]', '', text)
    text = ' '.join(text.split())
    return text

def find_best_faq_match(question: str) -> Optional[str]:
    """Find the best FAQ match using keyword matching and fuzzy logic"""
    question_lower = normalize_text(question)
    words = set(question_lower.split())
    
    for keyword, response in FAQ_RESPONSES.items():
        keyword_normalized = normalize_text(keyword)
        if keyword_normalized in question_lower:
            return response
        keyword_words = set(keyword_normalized.split())
        if keyword_words and keyword_words.issubset(words):
            return response
    
    for category, keywords in FAQ_KEYWORDS.items():
        for kw in keywords:
            kw_normalized = normalize_text(kw)
            if kw_normalized in question_lower:
                if category == "play":
                    return FAQ_RESPONSES.get("how to play")
                elif category == "ticket":
                    return FAQ_RESPONSES.get("ticket price")
                elif category == "draw":
                    return FAQ_RESPONSES.get("when is draw")
                elif category == "win":
                    return FAQ_RESPONSES.get("how to win")
                elif category == "jackpot":
                    return FAQ_RESPONSES.get("jackpot")
                elif category == "rollover":
                    return FAQ_RESPONSES.get("rollover")
                elif category == "fair":
                    return FAQ_RESPONSES.get("is it fair")
                elif category == "wallet":
                    return FAQ_RESPONSES.get("wallet")
                elif category == "security":
                    return FAQ_RESPONSES.get("wallet security")
                elif category == "help":
                    return FAQ_RESPONSES.get("help")
                elif category == "vip":
                    return FAQ_RESPONSES.get("vip")
                elif category == "greeting":
                    return FAQ_RESPONSES.get("hello")
                elif category == "thanks":
                    return FAQ_RESPONSES.get("thanks")
                elif category == "solana":
                    return FAQ_RESPONSES.get("solana")
    
    return None

def get_smart_response(question: str) -> str:
    """Get an intelligent response without using the AI model"""
    question_lower = normalize_text(question)
    
    faq_match = find_best_faq_match(question)
    if faq_match:
        return faq_match
    
    if len(question_lower.split()) <= 2:
        common_short = {
            "yes": "Great! What would you like to know more about?",
            "no": "Okay! Feel free to ask if you have any questions.",
            "ok": "Perfect! Anything else I can help with?",
            "okay": "Sounds good! Let me know if you need anything.",
            "sure": "Great! What would you like to explore?",
            "maybe": "Take your time! I'm here when you're ready.",
            "cool": "Awesome! What else would you like to know?",
            "nice": "Glad you like it! Any other questions?",
            "wow": "Right? It's pretty exciting! What else interests you?",
            "what": "I can help with:\n- How to play\n- Ticket prices & draws\n- Wallet setup\n- Prize distribution\n- VIP tiers\n\nWhat would you like to know?",
            "why": "Good question! What specifically would you like me to explain?",
            "how": "I'd be happy to explain! What process are you curious about?",
            "huh": "Let me clarify! What would you like me to explain better?",
        }
        for word, response in common_short.items():
            if word in question_lower:
                return response
    
    if any(word in question_lower for word in ["who", "what is", "what's", "tell me about"]):
        if "cryptounc" in question_lower or "lotto" in question_lower:
            return ("CryptoUnc Lotto is a fair, blockchain-powered lottery on Solana!\n\n"
                    "Key features:\n"
                    "- Tickets cost 0.025 SOL\n"
                    "- Pick 5 numbers from 1-40\n"
                    "- Draws every hour (24 per day)\n"
                    "- Match all 5 to win the jackpot\n"
                    "- Provably fair using blockchain randomness\n\n"
                    "Would you like to know how to get started?")
    
    return (
        "Great question! I'm here to help with CryptoUnc Lotto.\n\n"
        "I can answer questions about:\n"
        "- How to play and buy tickets\n"
        "- Ticket prices and draw times\n"
        "- Wallet setup and security\n"
        "- Prizes and jackpot system\n"
        "- VIP tiers and stats\n"
        "- Troubleshooting issues\n\n"
        "Just ask me anything specific, or use the menu buttons for quick access!"
    )

def ask_ai(system_prompt: str, user_prompt: str, max_tokens: int = 500) -> str:
    """
    Generate a response from the AI model.
    Falls back to smart responses if model unavailable.
    """
    smart_response = find_best_faq_match(user_prompt)
    if smart_response:
        return smart_response
    
    model = get_model()
    
    if model is None:
        return get_smart_response(user_prompt)
    
    try:
        combined_prompt = f"{system_prompt}\n\nUser: {user_prompt}\n\nAssistant:"
        response = model.generate(combined_prompt, max_tokens=max_tokens)
        return response.strip() if response else get_smart_response(user_prompt)
    except Exception as e:
        print(f"[AI] Generation error: {e}")
        return get_smart_response(user_prompt)

async def ask_ai_async(system_prompt: str, user_prompt: str, max_tokens: int = 500) -> str:
    """Async wrapper for ask_ai to prevent blocking the event loop"""
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, ask_ai, system_prompt, user_prompt, max_tokens)

def get_fallback_response(user_prompt: str) -> str:
    """Provide fallback responses when AI model is unavailable"""
    return get_smart_response(user_prompt)

def get_quick_answer(question: str) -> Optional[str]:
    """Get quick FAQ answer without using AI model"""
    return find_best_faq_match(question)

async def get_ai_help(question: str) -> str:
    """Get AI help for a general question - responds instantly"""
    quick = get_quick_answer(question)
    if quick:
        return quick
    
    smart = get_smart_response(question)
    if smart:
        return smart
    
    return await ask_ai_async(AI_SYSTEM_PROMPT, question)

async def get_fairness_explanation() -> str:
    """Get AI explanation of lottery fairness"""
    instant_response = FAQ_RESPONSES.get("is it fair")
    if instant_response:
        return (
            f"{instant_response}\n\n"
            "Technical details:\n"
            "- Winning numbers use cryptographic hashes\n"
            "- Seeds come from Solana block data\n"
            "- All results are publicly verifiable\n"
            "- No one can predict or manipulate outcomes\n\n"
            "Play with confidence knowing the system is mathematically fair!"
        )
    return await ask_ai_async(FAIRNESS_PROMPT, "Explain how CryptoUnc Lotto ensures fair and transparent draws.")

async def get_how_to_play() -> str:
    """Get AI explanation of how to play"""
    instant_response = FAQ_RESPONSES.get("how to play")
    if instant_response:
        return (
            f"{instant_response}\n\n"
            "Quick tips:\n"
            "- Buy multiple tickets for better odds\n"
            "- Check draws every hour\n"
            "- Keep enough SOL for fees\n"
            "- Set up wallet security with PIN\n\n"
            "Good luck and play responsibly!"
        )
    return await ask_ai_async(HOW_TO_PLAY_PROMPT, "Walk me through how to play CryptoUnc Lotto step by step.")

async def get_wallet_help(question: str = "") -> str:
    """Get AI help for wallet-related questions"""
    if not question:
        return (
            "Wallet Help\n\n"
            "Creating a Wallet:\n"
            "- 'Create Bot Wallet' - We generate a secure wallet for you\n"
            "- 'Import Wallet' - Use your existing private key\n"
            "- 'Connect External' - Link Phantom or Solflare\n\n"
            "Security Features:\n"
            "- 4-digit PIN protects sensitive operations\n"
            "- Private keys are encrypted\n"
            "- Messages auto-delete after 30 seconds\n"
            "- Security question for PIN recovery\n\n"
            "Max 3 wallets per user. Never share your private key!"
        )
    quick = find_best_faq_match(question)
    if quick:
        return quick
    return await ask_ai_async(WALLET_HELP_PROMPT, question)

async def get_stats_explanation() -> str:
    """Get AI explanation of stats and VIP system"""
    return (
        "Your Stats & VIP System\n\n"
        "VIP Tiers (based on total SOL spent):\n"
        "- Bronze: 0-1 SOL\n"
        "- Silver: 1-5 SOL\n"
        "- Gold: 5-20 SOL\n"
        "- Platinum: 20-50 SOL\n"
        "- Diamond: 50+ SOL\n\n"
        "Statistics Tracked:\n"
        "- Total tickets purchased\n"
        "- Total SOL spent\n"
        "- Total winnings\n"
        "- Win rate percentage\n"
        "- Current VIP tier\n\n"
        "Check 'My Stats' to see your full profile and leaderboard position!"
    )

async def get_support_guidance(issue: str = "") -> str:
    """Get AI support guidance for common issues"""
    if not issue:
        return (
            "Support Guide\n\n"
            "Common Issues & Solutions:\n\n"
            "Transaction Failed?\n"
            "- Check wallet balance (need 0.026+ SOL)\n"
            "- Wait a minute and try again\n"
            "- Solana network might be congested\n\n"
            "Balance Not Updating?\n"
            "- Network may be slow\n"
            "- Wait 1-2 minutes\n"
            "- Try refreshing\n\n"
            "Forgot PIN?\n"
            "- Use security question recovery\n"
            "- Or contact admin for help\n\n"
            "Can't Find Tickets?\n"
            "- Tickets are per round\n"
            "- Check 'My Tickets' for current round\n\n"
            "Still need help? Use the Support button to contact an admin!"
        )
    quick = find_best_faq_match(issue)
    if quick:
        return quick
    return await ask_ai_async(SUPPORT_PROMPT, issue)

def is_ai_available() -> bool:
    """Check if AI model is available - returns True since we have smart responses"""
    return True

async def get_interactive_response(message: str, context: dict = None) -> str:
    """
    Get an interactive AI response based on message and optional context.
    This is the main entry point for conversational AI.
    """
    quick = find_best_faq_match(message)
    if quick:
        return quick
    
    smart = get_smart_response(message)
    return smart
