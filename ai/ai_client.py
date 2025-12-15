import asyncio
import os
import re
from typing import Optional, List, Dict
from openai import OpenAI
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

OPENAI_MODEL = "gpt-5"
GEMINI_MODEL = "gemini-2.5-flash"

_openai_client = None
_gemini_client = None

def get_openai_client():
    """Get or create OpenAI client"""
    global _openai_client
    if _openai_client is None:
        api_key = os.environ.get("OPENAI_API_KEY")
        if api_key:
            _openai_client = OpenAI(api_key=api_key)
            print("[AI] OpenAI client initialized successfully")
        else:
            print("[AI] OPENAI_API_KEY not found - will try Gemini fallback")
    return _openai_client

def get_gemini_client():
    """Get or create Gemini client as fallback"""
    global _gemini_client
    if _gemini_client is None:
        api_key = os.environ.get("GEMINI_API_KEY")
        if api_key:
            try:
                from google import genai
                _gemini_client = genai.Client(api_key=api_key)
                print("[AI] Gemini client initialized successfully (fallback)")
            except ImportError:
                print("[AI] google-genai not installed - Gemini fallback unavailable")
            except Exception as e:
                print(f"[AI] Gemini client initialization failed: {e}")
        else:
            print("[AI] GEMINI_API_KEY not found - Gemini fallback unavailable")
    return _gemini_client

CRYPTOUNC_SYSTEM_PROMPT = """You are CryptoUnc Lotto's friendly AI assistant! You're a helpful, conversational AI that helps users with everything about the CryptoUnc Lotto lottery system on Solana blockchain.

Your personality:
- Friendly, approachable, and enthusiastic
- Clear and easy to understand
- Helpful and patient with all questions
- Responsible - never encourage gambling or promise winnings

Key facts about CryptoUnc Lotto:
- Ticket price: 0.025 SOL
- Pick 5 numbers from 1-40
- Match all 5 to win the entire jackpot
- 24 draws per day (every hour on the hour)
- 80% of ticket sales go to prize pool, 20% to team
- If no winner, jackpot rolls over to next round
- Uses cryptographic blockchain randomness - provably fair
- Maximum 3 wallets per user
- 4-digit PIN required for security
- Private keys are encrypted and auto-delete after 30 seconds

VIP Tiers (by SOL spent):
- Bronze: 0-1 SOL
- Silver: 1-5 SOL
- Gold: 5-20 SOL
- Platinum: 20-50 SOL
- Diamond: 50+ SOL

When answering:
- Be conversational and natural
- Give helpful, specific answers
- Use emojis sparingly for friendliness
- Keep responses concise but complete
- For technical issues, provide clear troubleshooting steps
- Always remind users to play responsibly when appropriate
- Never reveal private wallet information or help bypass security
- Never predict lottery outcomes or guarantee winnings"""

conversation_history: Dict[int, List[Dict]] = {}
MAX_HISTORY = 10

def get_user_history(user_id: int) -> List[Dict]:
    """Get conversation history for a user"""
    if user_id not in conversation_history:
        conversation_history[user_id] = []
    return conversation_history[user_id]

def add_to_history(user_id: int, role: str, content: str):
    """Add a message to user's conversation history"""
    history = get_user_history(user_id)
    history.append({"role": role, "content": content})
    if len(history) > MAX_HISTORY * 2:
        conversation_history[user_id] = history[-MAX_HISTORY * 2:]

def clear_history(user_id: int):
    """Clear a user's conversation history"""
    conversation_history[user_id] = []

def normalize_text(text: str) -> str:
    """Normalize text for better matching"""
    text = text.lower().strip()
    text = re.sub(r'[^\w\s]', '', text)
    text = ' '.join(text.split())
    return text

def find_best_faq_match(question: str) -> Optional[str]:
    """Find the best FAQ match using keyword matching"""
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
                category_responses = {
                    "play": "how to play",
                    "ticket": "ticket price",
                    "draw": "when is draw",
                    "win": "how to win",
                    "jackpot": "jackpot",
                    "rollover": "rollover",
                    "fair": "is it fair",
                    "wallet": "wallet",
                    "security": "wallet security",
                    "help": "help",
                    "vip": "vip",
                    "greeting": "hello",
                    "thanks": "thanks",
                    "solana": "solana",
                }
                if category in category_responses:
                    return FAQ_RESPONSES.get(category_responses[category])
    
    return None

def get_smart_response(question: str) -> str:
    """Get an intelligent response without using OpenAI"""
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
            "what": "I can help with:\n- How to play\n- Ticket prices & draws\n- Wallet setup\n- Prize distribution\n- VIP tiers\n\nWhat would you like to know?",
            "why": "Good question! What specifically would you like me to explain?",
            "how": "I'd be happy to explain! What process are you curious about?",
        }
        for word, response in common_short.items():
            if word in question_lower:
                return response
    
    return (
        "I'm here to help with CryptoUnc Lotto!\n\n"
        "I can answer questions about:\n"
        "- How to play and buy tickets\n"
        "- Ticket prices and draw times\n"
        "- Wallet setup and security\n"
        "- Prizes and jackpot system\n"
        "- VIP tiers and stats\n\n"
        "Just ask me anything!"
    )

async def ask_gemini_async(system_prompt: str, user_prompt: str, max_tokens: int = 500) -> Optional[str]:
    """Try to get response from Gemini as fallback"""
    client = get_gemini_client()
    if client is None:
        return None
    
    try:
        from google.genai import types
        
        full_prompt = f"{system_prompt}\n\nUser question: {user_prompt}"
        
        response = await asyncio.get_event_loop().run_in_executor(
            None,
            lambda: client.models.generate_content(
                model=GEMINI_MODEL,
                contents=full_prompt,
                config=types.GenerateContentConfig(
                    max_output_tokens=max_tokens
                )
            )
        )
        
        if response and response.text:
            print("[AI] Gemini fallback response successful")
            return response.text
        return None
    except Exception as e:
        print(f"[AI] Gemini error: {e}")
        return None

async def chat_with_ai(user_id: int, message: str, context: str = "") -> str:
    """
    Have a conversational chat with the AI.
    This is the main entry point for interactive AI conversations.
    Uses OpenAI first, then Gemini as fallback.
    """
    client = get_openai_client()
    
    # Try OpenAI first
    if client is not None:
        try:
            history = get_user_history(user_id)
            
            messages = [{"role": "system", "content": CRYPTOUNC_SYSTEM_PROMPT}]
            
            if context:
                messages.append({
                    "role": "system", 
                    "content": f"Additional context: {context}"
                })
            
            for msg in history[-MAX_HISTORY * 2:]:
                messages.append(msg)
            
            messages.append({"role": "user", "content": message})
            
            response = await asyncio.get_event_loop().run_in_executor(
                None,
                lambda: client.chat.completions.create(
                    model=OPENAI_MODEL,
                    messages=messages,  # type: ignore
                    max_completion_tokens=500
                )
            )
            
            ai_response = response.choices[0].message.content or ""
            
            add_to_history(user_id, "user", message)
            add_to_history(user_id, "assistant", ai_response)
            
            return ai_response
            
        except Exception as e:
            print(f"[AI] OpenAI error: {e}, trying Gemini fallback...")
    
    # Try Gemini fallback
    gemini_response = await ask_gemini_async(CRYPTOUNC_SYSTEM_PROMPT, message)
    if gemini_response:
        add_to_history(user_id, "user", message)
        add_to_history(user_id, "assistant", gemini_response)
        return gemini_response
    
    # Final fallback to FAQ/smart responses
    faq_match = find_best_faq_match(message)
    if faq_match:
        return faq_match
    return get_smart_response(message)

async def ask_ai_async(system_prompt: str, user_prompt: str, max_tokens: int = 500) -> str:
    """Async AI request with OpenAI, Gemini fallback"""
    client = get_openai_client()
    
    # Try OpenAI first
    if client is not None:
        try:
            response = await asyncio.get_event_loop().run_in_executor(
                None,
                lambda: client.chat.completions.create(
                    model=OPENAI_MODEL,
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt}
                    ],
                    max_completion_tokens=max_tokens
                )
            )
            return response.choices[0].message.content or ""
        except Exception as e:
            print(f"[AI] OpenAI error: {e}, trying Gemini fallback...")
    
    # Try Gemini fallback
    gemini_response = await ask_gemini_async(system_prompt, user_prompt, max_tokens)
    if gemini_response:
        return gemini_response
    
    # Final fallback
    faq_match = find_best_faq_match(user_prompt)
    if faq_match:
        return faq_match
    return get_smart_response(user_prompt)

def ask_ai(system_prompt: str, user_prompt: str, max_tokens: int = 500) -> str:
    """Synchronous AI request"""
    client = get_openai_client()
    
    if client is None:
        faq_match = find_best_faq_match(user_prompt)
        if faq_match:
            return faq_match
        return get_smart_response(user_prompt)
    
    try:
        response = client.chat.completions.create(
            model=OPENAI_MODEL,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            max_completion_tokens=max_tokens
        )
        return response.choices[0].message.content or ""
    except Exception as e:
        print(f"[AI] OpenAI error: {e}")
        faq_match = find_best_faq_match(user_prompt)
        if faq_match:
            return faq_match
        return get_smart_response(user_prompt)

def get_fallback_response(user_prompt: str) -> str:
    """Provide fallback responses"""
    return get_smart_response(user_prompt)

def get_quick_answer(question: str) -> Optional[str]:
    """Get quick FAQ answer"""
    return find_best_faq_match(question)

async def get_ai_help(question: str, user_id: int = 0) -> str:
    """Get AI help for a general question - uses conversational AI"""
    if user_id > 0:
        return await chat_with_ai(user_id, question)
    
    quick = get_quick_answer(question)
    if quick:
        return quick
    
    return await ask_ai_async(CRYPTOUNC_SYSTEM_PROMPT, question)

async def get_fairness_explanation() -> str:
    """Get AI explanation of lottery fairness"""
    return await ask_ai_async(
        CRYPTOUNC_SYSTEM_PROMPT,
        "Explain in detail how CryptoUnc Lotto ensures fair and transparent draws. "
        "Cover the blockchain randomness, verification process, and why users can trust the system."
    )

async def get_how_to_play() -> str:
    """Get AI explanation of how to play"""
    return await ask_ai_async(
        CRYPTOUNC_SYSTEM_PROMPT,
        "Walk me through how to play CryptoUnc Lotto step by step, from creating a wallet to buying tickets to checking results."
    )

async def get_wallet_help(question: str = "") -> str:
    """Get AI help for wallet-related questions"""
    if not question:
        question = "Explain all the wallet options, how to set them up, and security features."
    return await ask_ai_async(WALLET_HELP_PROMPT, question)

async def get_stats_explanation() -> str:
    """Get AI explanation of stats and VIP system"""
    return await ask_ai_async(
        CRYPTOUNC_SYSTEM_PROMPT,
        "Explain the user statistics tracking and VIP tier system in CryptoUnc Lotto."
    )

async def get_support_guidance(issue: str = "") -> str:
    """Get AI support guidance for common issues"""
    if not issue:
        issue = "What are the most common issues users face and how can they be resolved?"
    return await ask_ai_async(SUPPORT_PROMPT, issue)

def is_ai_available() -> bool:
    """Check if AI is available (OpenAI or Gemini)"""
    return get_openai_client() is not None or get_gemini_client() is not None or True

async def get_interactive_response(message: str, user_id: int = 0, context: dict = None) -> str:
    """
    Get an interactive AI response based on message and optional context.
    This is the main entry point for conversational AI in the bot.
    """
    context_str = ""
    if context:
        context_str = ", ".join([f"{k}: {v}" for k, v in context.items()])
    
    if user_id > 0:
        return await chat_with_ai(user_id, message, context_str)
    
    quick = find_best_faq_match(message)
    if quick:
        return quick
    
    return await ask_ai_async(CRYPTOUNC_SYSTEM_PROMPT, message)
