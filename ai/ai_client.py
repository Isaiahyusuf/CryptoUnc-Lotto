"""
CryptoUnc Lotto AI Client - Groq Only
Uses Groq's Llama model for fast, reliable AI responses.
All other providers (OpenAI, Gemini) have been removed for performance.
"""

import asyncio
import os
import re
import time
import hashlib
from datetime import datetime, timedelta
from typing import Optional, List, Dict
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

# Groq is the ONLY AI provider
GROQ_MODEL = "llama-3.1-8b-instant"

_groq_client = None

# Chat history settings - keep minimal for speed
CHAT_HISTORY_RETENTION_DAYS = 3
MAX_HISTORY_MESSAGES = 5  # Reduced from 20 to 5 for speed

# In-memory response cache: {cache_key: {"response": str, "timestamp": float}}
_response_cache: Dict[str, Dict] = {}
CACHE_TTL_SECONDS = 300  # 5 minutes cache


def get_groq_client():
    """Get or create Groq client - the only AI provider"""
    global _groq_client
    if _groq_client is None:
        api_key = os.environ.get("GROQ_API_KEY")
        if api_key:
            try:
                from groq import Groq
                _groq_client = Groq(api_key=api_key)
                print("[AI] Groq client initialized - single AI provider active")
            except ImportError:
                print("[AI] ERROR: groq package not installed")
            except Exception as e:
                print(f"[AI] Groq client initialization failed: {e}")
        else:
            print("[AI] WARNING: GROQ_API_KEY not found - AI features disabled")
    return _groq_client


def get_cache_key(user_id: int, prompt: str) -> str:
    """Generate cache key from user_id and prompt hash"""
    prompt_hash = hashlib.md5(prompt.encode()).hexdigest()[:16]
    return f"{user_id}:{prompt_hash}"


def get_cached_response(user_id: int, prompt: str) -> Optional[str]:
    """Get cached response if available and not expired"""
    cache_key = get_cache_key(user_id, prompt)
    if cache_key in _response_cache:
        cached = _response_cache[cache_key]
        if time.time() - cached["timestamp"] < CACHE_TTL_SECONDS:
            print(f"[AI] Cache hit for user {user_id}")
            return cached["response"]
        else:
            del _response_cache[cache_key]
    return None


def cache_response(user_id: int, prompt: str, response: str):
    """Cache a response for future use"""
    cache_key = get_cache_key(user_id, prompt)
    _response_cache[cache_key] = {
        "response": response,
        "timestamp": time.time()
    }
    
    # Clean old cache entries (keep max 1000)
    if len(_response_cache) > 1000:
        oldest_keys = sorted(_response_cache.keys(), 
                            key=lambda k: _response_cache[k]["timestamp"])[:200]
        for key in oldest_keys:
            del _response_cache[key]


def get_db_connection():
    """Get database connection - imported lazily to avoid circular imports"""
    try:
        from db import get_db_conn
        return get_db_conn()
    except Exception as e:
        print(f"[AI] Database connection error: {e}")
        return None


def save_chat_message(user_id: int, role: str, content: str):
    """Save a chat message to the database"""
    conn = get_db_connection()
    if conn is None:
        return
    try:
        c = conn.cursor()
        c.execute(
            "INSERT INTO ai_chat_history (user_id, role, content) VALUES (%s, %s, %s)",
            (user_id, role, content)
        )
        conn.commit()
    except Exception as e:
        print(f"[AI] Error saving chat message: {e}")
    finally:
        conn.close()


def get_chat_history(user_id: int) -> List[Dict]:
    """Get chat history for a user - limited to 5 messages for speed"""
    conn = get_db_connection()
    if conn is None:
        return []
    try:
        c = conn.cursor()
        cutoff = datetime.now() - timedelta(days=CHAT_HISTORY_RETENTION_DAYS)
        c.execute(
            """SELECT role, content FROM ai_chat_history 
               WHERE user_id = %s AND created_at > %s 
               ORDER BY created_at DESC LIMIT %s""",
            (user_id, cutoff, MAX_HISTORY_MESSAGES)
        )
        rows = c.fetchall()
        messages = [{"role": row[0], "content": row[1]} for row in reversed(rows)]
        return messages
    except Exception as e:
        print(f"[AI] Error getting chat history: {e}")
        return []
    finally:
        conn.close()


def clear_chat_history(user_id: int):
    """Clear all chat history for a user"""
    conn = get_db_connection()
    if conn is None:
        return
    try:
        c = conn.cursor()
        c.execute("DELETE FROM ai_chat_history WHERE user_id = %s", (user_id,))
        conn.commit()
        print(f"[AI] Cleared chat history for user {user_id}")
    except Exception as e:
        print(f"[AI] Error clearing chat history: {e}")
    finally:
        conn.close()


def cleanup_old_chat_history():
    """Remove chat messages older than retention period"""
    conn = get_db_connection()
    if conn is None:
        return
    try:
        c = conn.cursor()
        cutoff = datetime.now() - timedelta(days=CHAT_HISTORY_RETENTION_DAYS)
        c.execute("DELETE FROM ai_chat_history WHERE created_at < %s", (cutoff,))
        deleted = c._cursor.rowcount
        conn.commit()
        if deleted > 0:
            print(f"[AI] Cleaned up {deleted} old chat messages")
    except Exception as e:
        print(f"[AI] Error cleaning up chat history: {e}")
    finally:
        conn.close()


def get_user_profile(user_id: int) -> Optional[Dict]:
    """Get user profile with permanent info AI should remember"""
    conn = get_db_connection()
    if conn is None:
        return None
    try:
        c = conn.cursor()
        c.execute(
            "SELECT display_name, preferred_name, notes FROM user_profiles WHERE user_id = %s",
            (user_id,)
        )
        row = c.fetchone()
        if row:
            return {
                "display_name": row[0],
                "preferred_name": row[1],
                "notes": row[2]
            }
        return None
    except Exception as e:
        print(f"[AI] Error getting user profile: {e}")
        return None
    finally:
        conn.close()


def update_user_profile(user_id: int, display_name: str = None, preferred_name: str = None, notes: str = None):
    """Update or create user profile with permanent info"""
    conn = get_db_connection()
    if conn is None:
        return
    try:
        c = conn.cursor()
        c.execute("SELECT user_id FROM user_profiles WHERE user_id = %s", (user_id,))
        exists = c.fetchone()
        
        if exists:
            updates = []
            params = []
            if display_name is not None:
                updates.append("display_name = %s")
                params.append(display_name)
            if preferred_name is not None:
                updates.append("preferred_name = %s")
                params.append(preferred_name)
            if notes is not None:
                updates.append("notes = %s")
                params.append(notes)
            updates.append("last_interaction = CURRENT_TIMESTAMP")
            params.append(user_id)
            
            if updates:
                c.execute(
                    f"UPDATE user_profiles SET {', '.join(updates)} WHERE user_id = %s",
                    tuple(params)
                )
        else:
            c.execute(
                """INSERT INTO user_profiles (user_id, display_name, preferred_name, notes) 
                   VALUES (%s, %s, %s, %s)""",
                (user_id, display_name, preferred_name, notes)
            )
        conn.commit()
    except Exception as e:
        print(f"[AI] Error updating user profile: {e}")
    finally:
        conn.close()


def extract_user_info_from_message(message: str, response: str) -> Dict:
    """Extract user info like names from conversation"""
    info = {}
    
    name_patterns = [
        r"(?:my name is|i'm|i am|call me|they call me)\s+([A-Z][a-z]+)",
        r"(?:I'm|Im)\s+([A-Z][a-z]+)",
    ]
    
    for pattern in name_patterns:
        match = re.search(pattern, message, re.IGNORECASE)
        if match:
            name = match.group(1).strip()
            if len(name) > 1 and name.lower() not in ['the', 'a', 'an', 'just', 'here']:
                info['preferred_name'] = name
                break
    
    return info


# System prompt for the AI - includes tiered prize system details
CRYPTOUNC_SYSTEM_PROMPT = """You are CryptoUnc Lotto's friendly AI assistant on Solana blockchain.

CRITICAL RULES:
- Be helpful, concise, and friendly
- NEVER predict lottery outcomes or guarantee winnings
- NEVER encourage excessive gambling
- NEVER reveal private wallet information

TIERED PRIZE SYSTEM (IMPORTANT):
- Players pick 5 numbers from 1-40
- Prize pool = 80% of ticket sales + rollover from previous rounds
- 3 ways to win:
  * 5-Match: 70% of prize pool (JACKPOT tier)
  * 4-Match: 20% of prize pool
  * 3-Match: 10% of prize pool
- Multiple winners in a tier split that tier's allocation equally
- If NO winners in a tier, that allocation ROLLS OVER to next round
- Unclaimed tiers accumulate, making future prizes bigger!

LOTTERY DETAILS:
- Ticket price: 0.025 SOL
- 24 hourly draws (every hour on the hour)
- Maximum 3 wallets per user
- 4-digit PIN for security
- Private keys encrypted, auto-delete after 30 seconds

VIP TIERS (by SOL spent):
- Bronze: 0-1 SOL
- Silver: 1-5 SOL
- Gold: 5-20 SOL
- Platinum: 20-50 SOL
- Diamond: 50+ SOL

Keep responses under 150 words. Be conversational and helpful."""


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
    """Get an intelligent response without using AI"""
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


async def ask_groq_async(system_prompt: str, user_prompt: str, max_tokens: int = 1500, history: List[Dict] = None) -> Optional[str]:
    """
    Get response from Groq using asyncio.to_thread for non-blocking execution.
    This prevents the bot from lagging during AI calls.
    """
    client = get_groq_client()
    if client is None:
        return None
    
    try:
        # Build messages list with limited history
        messages = [{"role": "system", "content": system_prompt}]
        
        if history:
            # Only use last 5 messages to keep context small
            for msg in history[-5:]:
                messages.append(msg)
        
        messages.append({"role": "user", "content": user_prompt})
        
        # Run Groq in thread pool to avoid blocking
        response = await asyncio.to_thread(
            client.chat.completions.create,
            model=GROQ_MODEL,
            messages=messages,
            temperature=0.4,
            max_tokens=max_tokens
        )
        
        if response and response.choices[0].message.content:
            return response.choices[0].message.content
        return None
    except Exception as e:
        print(f"[AI] Groq error: {e}")
        return None


async def chat_with_ai(user_id: int, message: str, context: str = "") -> str:
    """
    Main entry point for AI conversations.
    Uses Groq only with caching and non-blocking execution.
    """
    # Check cache first for fast response
    cached = get_cached_response(user_id, message)
    if cached:
        return cached
    
    # Try FAQ match first (instant response)
    faq_match = find_best_faq_match(message)
    if faq_match:
        return faq_match
    
    # Get chat history (limited to 5 messages)
    history = get_chat_history(user_id)
    profile = get_user_profile(user_id)
    
    # Build system prompt with user context
    system_prompt = CRYPTOUNC_SYSTEM_PROMPT
    if profile:
        profile_context = []
        if profile.get("preferred_name"):
            profile_context.append(f"User's name: {profile['preferred_name']}")
        if profile.get("notes"):
            profile_context.append(f"Notes: {profile['notes']}")
        if profile_context:
            system_prompt += f"\n\nUser info: {', '.join(profile_context)}"
    
    if context:
        system_prompt += f"\n\nAdditional context: {context}"
    
    # Call Groq (non-blocking)
    ai_response = await ask_groq_async(system_prompt, message, max_tokens=1500, history=history)
    
    if ai_response:
        # Save to history
        save_chat_message(user_id, "user", message)
        save_chat_message(user_id, "assistant", ai_response)
        
        # Cache the response
        cache_response(user_id, message, ai_response)
        
        # Extract user info if present
        user_info = extract_user_info_from_message(message, ai_response)
        if user_info:
            update_user_profile(user_id, **user_info)
        
        return ai_response
    
    # Fallback to smart response
    return get_smart_response(message)


async def ask_ai_async(system_prompt: str, user_prompt: str, max_tokens: int = 1500) -> str:
    """Async AI request using Groq only"""
    response = await ask_groq_async(system_prompt, user_prompt, max_tokens)
    if response:
        return response
    
    # Fallback to FAQ
    faq_match = find_best_faq_match(user_prompt)
    if faq_match:
        return faq_match
    return "AI is currently unavailable. Please try again later."


def ask_ai(system_prompt: str, user_prompt: str, max_tokens: int = 1500) -> str:
    """Synchronous AI request using Groq only"""
    client = get_groq_client()
    
    if client is not None:
        try:
            response = client.chat.completions.create(
                model=GROQ_MODEL,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                temperature=0.4,
                max_tokens=max_tokens
            )
            if response and response.choices[0].message.content:
                return response.choices[0].message.content
        except Exception as e:
            print(f"[AI] Groq sync error: {e}")
    
    # Fallback to FAQ
    faq_match = find_best_faq_match(user_prompt)
    if faq_match:
        return faq_match
    return "AI is currently unavailable. Please try again later."


# Convenience functions using the common prompts
async def get_ai_help(question: str, user_id: int = 0) -> str:
    """Get general AI help with caching"""
    cached = get_cached_response(user_id, question)
    if cached:
        return cached
    
    response = await ask_ai_async(AI_SYSTEM_PROMPT, question, 1500)
    if user_id:
        cache_response(user_id, question, response)
    return response


async def get_fairness_explanation(user_id: int = 0) -> str:
    """Explain how the lottery is fair"""
    prompt = "Explain how CryptoUnc Lotto is provably fair"
    cached = get_cached_response(user_id, prompt)
    if cached:
        return cached
    
    response = await ask_ai_async(FAIRNESS_PROMPT, prompt, 1500)
    if user_id:
        cache_response(user_id, prompt, response)
    return response


async def get_how_to_play(user_id: int = 0) -> str:
    """Get how to play instructions"""
    prompt = "How do I play CryptoUnc Lotto?"
    cached = get_cached_response(user_id, prompt)
    if cached:
        return cached
    
    response = await ask_ai_async(HOW_TO_PLAY_PROMPT, prompt, 1500)
    if user_id:
        cache_response(user_id, prompt, response)
    return response


async def get_wallet_help(question: str, user_id: int = 0) -> str:
    """Get wallet-related help"""
    cached = get_cached_response(user_id, question)
    if cached:
        return cached
    
    response = await ask_ai_async(WALLET_HELP_PROMPT, question, 1500)
    if user_id:
        cache_response(user_id, question, response)
    return response


async def get_stats_explanation(user_id: int = 0) -> str:
    """Explain stats and VIP system"""
    prompt = "Explain the VIP tiers and stats system"
    cached = get_cached_response(user_id, prompt)
    if cached:
        return cached
    
    response = await ask_ai_async(STATS_EXPLANATION_PROMPT, prompt, 1500)
    if user_id:
        cache_response(user_id, prompt, response)
    return response


async def get_support_guidance(issue: str, user_id: int = 0) -> str:
    """Get support guidance for an issue"""
    cached = get_cached_response(user_id, issue)
    if cached:
        return cached
    
    response = await ask_ai_async(SUPPORT_PROMPT, issue, 1500)
    if user_id:
        cache_response(user_id, issue, response)
    return response


def is_ai_available() -> bool:
    """Check if AI is available"""
    return get_groq_client() is not None


async def get_interactive_response(user_id: int, message: str, context: str = "") -> str:
    """Get an interactive AI response - wrapper for chat_with_ai"""
    return await chat_with_ai(user_id, message, context)


def clear_history(user_id: int):
    """Clear a user's conversation history"""
    clear_chat_history(user_id)
