import asyncio
import os
import re
import time
from datetime import datetime, timedelta
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

OPENAI_MODEL = "gpt-4o"
GEMINI_MODEL = "gemini-2.0-flash"
GROQ_MODEL = "llama-3.1-8b-instant"

_openai_client = None
_gemini_client = None
_groq_client = None

CHAT_HISTORY_RETENTION_DAYS = 3
MAX_HISTORY_MESSAGES = 20

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

def get_groq_client():
    """Get or create Groq client as final fallback"""
    global _groq_client
    if _groq_client is None:
        api_key = os.environ.get("GROQ_API_KEY")
        if api_key:
            try:
                from groq import Groq
                _groq_client = Groq(api_key=api_key)
                print("[AI] Groq client initialized successfully (final fallback)")
            except ImportError:
                print("[AI] groq not installed - Groq fallback unavailable")
            except Exception as e:
                print(f"[AI] Groq client initialization failed: {e}")
        else:
            print("[AI] GROQ_API_KEY not found - Groq fallback unavailable")
    return _groq_client

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
    """Get chat history for a user from the database (last 3 days)"""
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

CRYPTOUNC_SYSTEM_PROMPT = """You are CryptoUnc Lotto's friendly AI assistant! You're a helpful, conversational AI that helps users with everything about the CryptoUnc Lotto lottery system on Solana blockchain.

Your personality:
- Friendly, approachable, and enthusiastic
- Clear and easy to understand
- Helpful and patient with all questions
- Responsible - never encourage gambling or promise winnings
- You remember previous conversations and user preferences

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
- Never predict lottery outcomes or guarantee winnings
- If the user told you their name, use it occasionally to be friendly
- Reference previous conversations when relevant"""

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

async def ask_gemini_async(system_prompt: str, user_prompt: str, max_tokens: int = 500, history: List[Dict] = None) -> Optional[str]:
    """Try to get response from Gemini as fallback"""
    client = get_gemini_client()
    if client is None:
        return None
    
    try:
        from google.genai import types
        
        full_prompt = f"{system_prompt}\n\n"
        
        if history:
            full_prompt += "Previous conversation:\n"
            for msg in history[-10:]:
                role = "User" if msg["role"] == "user" else "Assistant"
                full_prompt += f"{role}: {msg['content']}\n"
            full_prompt += "\n"
        
        full_prompt += f"User question: {user_prompt}"
        
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

async def ask_groq_async(system_prompt: str, user_prompt: str, max_tokens: int = 300, history: List[Dict] = None) -> Optional[str]:
    """Try to get response from Groq as final fallback"""
    client = get_groq_client()
    if client is None:
        return None
    
    try:
        full_prompt = f"{system_prompt}\n\n"
        
        if history:
            full_prompt += "Previous conversation:\n"
            for msg in history[-10:]:
                role = "User" if msg["role"] == "user" else "Assistant"
                full_prompt += f"{role}: {msg['content']}\n"
            full_prompt += "\n"
        
        full_prompt += f"User question: {user_prompt}"
        
        response = await asyncio.get_event_loop().run_in_executor(
            None,
            lambda: client.chat.completions.create(
                model=GROQ_MODEL,
                messages=[{"role": "user", "content": full_prompt}],
                temperature=0.4,
                max_tokens=max_tokens
            )
        )
        
        if response and response.choices[0].message.content:
            print("[AI] Groq fallback response successful")
            return response.choices[0].message.content
        return None
    except Exception as e:
        print(f"[AI] Groq error: {e}")
        return None

async def chat_with_ai(user_id: int, message: str, context: str = "") -> str:
    """
    Have a conversational chat with the AI.
    This is the main entry point for interactive AI conversations.
    Uses OpenAI first, then Gemini, then Groq as fallbacks.
    Persists chat history to database for 3 days.
    Remembers user info permanently.
    """
    client = get_openai_client()
    
    history = get_chat_history(user_id)
    profile = get_user_profile(user_id)
    
    system_prompt = CRYPTOUNC_SYSTEM_PROMPT
    if profile:
        profile_context = []
        if profile.get("preferred_name"):
            profile_context.append(f"User's name: {profile['preferred_name']}")
        if profile.get("notes"):
            profile_context.append(f"Notes about user: {profile['notes']}")
        if profile_context:
            system_prompt += f"\n\nUser information: {', '.join(profile_context)}"
    
    if client is not None:
        try:
            messages = [{"role": "system", "content": system_prompt}]
            
            if context:
                messages.append({
                    "role": "system", 
                    "content": f"Additional context: {context}"
                })
            
            for msg in history[-MAX_HISTORY_MESSAGES:]:
                messages.append(msg)
            
            messages.append({"role": "user", "content": message})
            
            response = await asyncio.get_event_loop().run_in_executor(
                None,
                lambda: client.chat.completions.create(
                    model=OPENAI_MODEL,
                    messages=messages,
                    max_completion_tokens=500
                )
            )
            
            ai_response = response.choices[0].message.content or ""
            
            save_chat_message(user_id, "user", message)
            save_chat_message(user_id, "assistant", ai_response)
            
            user_info = extract_user_info_from_message(message, ai_response)
            if user_info:
                update_user_profile(user_id, **user_info)
            
            return ai_response
            
        except Exception as e:
            print(f"[AI] OpenAI error: {e}, trying Gemini fallback...")
            await asyncio.sleep(1)
    
    gemini_response = await ask_gemini_async(system_prompt, message, history=history)
    if gemini_response:
        save_chat_message(user_id, "user", message)
        save_chat_message(user_id, "assistant", gemini_response)
        
        user_info = extract_user_info_from_message(message, gemini_response)
        if user_info:
            update_user_profile(user_id, **user_info)
        
        return gemini_response
    
    print("[AI] Gemini failed, switching to Groq...")
    await asyncio.sleep(1)
    
    groq_response = await ask_groq_async(system_prompt, message, history=history)
    if groq_response:
        save_chat_message(user_id, "user", message)
        save_chat_message(user_id, "assistant", groq_response)
        
        user_info = extract_user_info_from_message(message, groq_response)
        if user_info:
            update_user_profile(user_id, **user_info)
        
        return groq_response
    
    faq_match = find_best_faq_match(message)
    if faq_match:
        return faq_match
    return "AI is currently unavailable. Please try again later."

async def ask_ai_async(system_prompt: str, user_prompt: str, max_tokens: int = 500) -> str:
    """Async AI request with OpenAI, Gemini, Groq fallback chain"""
    client = get_openai_client()
    
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
            await asyncio.sleep(1)
    
    gemini_response = await ask_gemini_async(system_prompt, user_prompt, max_tokens)
    if gemini_response:
        return gemini_response
    
    print("[AI] Gemini failed, switching to Groq...")
    await asyncio.sleep(1)
    
    groq_response = await ask_groq_async(system_prompt, user_prompt, min(max_tokens, 300))
    if groq_response:
        return groq_response
    
    faq_match = find_best_faq_match(user_prompt)
    if faq_match:
        return faq_match
    return "AI is currently unavailable. Please try again later."

def ask_ai(system_prompt: str, user_prompt: str, max_tokens: int = 500) -> str:
    """Synchronous AI request with OpenAI, Gemini, Groq fallback chain"""
    client = get_openai_client()
    
    if client is not None:
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
            print(f"[AI] OpenAI error: {e}, trying Gemini fallback...")
            time.sleep(1)
    
    gemini = get_gemini_client()
    if gemini is not None:
        try:
            from google.genai import types
            full_prompt = f"{system_prompt}\n\nUser question: {user_prompt}"
            response = gemini.models.generate_content(
                model=GEMINI_MODEL,
                contents=full_prompt,
                config=types.GenerateContentConfig(max_output_tokens=max_tokens)
            )
            if response and response.text:
                print("[AI] Gemini fallback response successful")
                return response.text
        except Exception as e:
            print(f"[AI] Gemini error: {e}, switching to Groq...")
            time.sleep(1)
    
    groq = get_groq_client()
    if groq is not None:
        try:
            full_prompt = f"{system_prompt}\n\nUser question: {user_prompt}"
            response = groq.chat.completions.create(
                model=GROQ_MODEL,
                messages=[{"role": "user", "content": full_prompt}],
                temperature=0.4,
                max_tokens=min(max_tokens, 300)
            )
            if response and response.choices[0].message.content:
                print("[AI] Groq fallback response successful")
                return response.choices[0].message.content
        except Exception as e:
            print(f"[AI] Groq also failed: {e}")
    
    faq_match = find_best_faq_match(user_prompt)
    if faq_match:
        return faq_match
    return "AI is currently unavailable. Please try again later."

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
    """Check if AI is available (OpenAI, Gemini, or Groq)"""
    return get_openai_client() is not None or get_gemini_client() is not None or get_groq_client() is not None or True

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

def get_user_history(user_id: int) -> List[Dict]:
    """Get conversation history for a user - now uses database"""
    return get_chat_history(user_id)

def add_to_history(user_id: int, role: str, content: str):
    """Add a message to user's conversation history - now uses database"""
    save_chat_message(user_id, role, content)

def clear_history(user_id: int):
    """Clear a user's conversation history"""
    clear_chat_history(user_id)
