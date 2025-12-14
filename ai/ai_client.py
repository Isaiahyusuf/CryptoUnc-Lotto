import asyncio
from typing import Optional
from .prompts import (
    AI_SYSTEM_PROMPT, 
    FAIRNESS_PROMPT, 
    HOW_TO_PLAY_PROMPT,
    WALLET_HELP_PROMPT,
    STATS_EXPLANATION_PROMPT,
    SUPPORT_PROMPT,
    FAQ_RESPONSES
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

def ask_ai(system_prompt: str, user_prompt: str, max_tokens: int = 500) -> str:
    """
    Generate a response from the AI model.
    
    Args:
        system_prompt: The system prompt that sets the AI's behavior
        user_prompt: The user's question or input
        max_tokens: Maximum tokens for response
    
    Returns:
        The AI-generated response or fallback message
    """
    model = get_model()
    
    if model is None:
        return get_fallback_response(user_prompt)
    
    try:
        combined_prompt = f"{system_prompt}\n\nUser: {user_prompt}\n\nAssistant:"
        response = model.generate(combined_prompt, max_tokens=max_tokens)
        return response.strip() if response else get_fallback_response(user_prompt)
    except Exception as e:
        print(f"[AI] Generation error: {e}")
        return get_fallback_response(user_prompt)

async def ask_ai_async(system_prompt: str, user_prompt: str, max_tokens: int = 500) -> str:
    """Async wrapper for ask_ai to prevent blocking the event loop"""
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, ask_ai, system_prompt, user_prompt, max_tokens)

def get_fallback_response(user_prompt: str) -> str:
    """Provide fallback responses when AI model is unavailable"""
    user_prompt_lower = user_prompt.lower()
    
    for keyword, response in FAQ_RESPONSES.items():
        if keyword in user_prompt_lower:
            return response
    
    return (
        "I'm here to help with CryptoUnc Lotto! Here are common topics:\n\n"
        "- How to play the lottery\n"
        "- Ticket prices and draws\n"
        "- Wallet setup and security\n"
        "- Prize distribution\n"
        "- Fairness and transparency\n\n"
        "For specific questions, try /ai_help followed by your question, "
        "or use the Support button to contact an admin."
    )

def get_quick_answer(question: str) -> Optional[str]:
    """Get quick FAQ answer without using AI model"""
    question_lower = question.lower()
    
    for keyword, response in FAQ_RESPONSES.items():
        if keyword in question_lower:
            return response
    
    return None

async def get_ai_help(question: str) -> str:
    """Get AI help for a general question"""
    quick = get_quick_answer(question)
    if quick:
        return quick
    return await ask_ai_async(AI_SYSTEM_PROMPT, question)

async def get_fairness_explanation() -> str:
    """Get AI explanation of lottery fairness"""
    return await ask_ai_async(
        FAIRNESS_PROMPT, 
        "Explain how CryptoUnc Lotto ensures fair and transparent draws."
    )

async def get_how_to_play() -> str:
    """Get AI explanation of how to play"""
    return await ask_ai_async(
        HOW_TO_PLAY_PROMPT,
        "Walk me through how to play CryptoUnc Lotto step by step."
    )

async def get_wallet_help(question: str = "") -> str:
    """Get AI help for wallet-related questions"""
    prompt = question if question else "Explain wallet options and security features."
    return await ask_ai_async(WALLET_HELP_PROMPT, prompt)

async def get_stats_explanation() -> str:
    """Get AI explanation of stats and VIP system"""
    return await ask_ai_async(
        STATS_EXPLANATION_PROMPT,
        "Explain the statistics and VIP tier system."
    )

async def get_support_guidance(issue: str = "") -> str:
    """Get AI support guidance for common issues"""
    prompt = issue if issue else "What are common issues users face and how to resolve them?"
    return await ask_ai_async(SUPPORT_PROMPT, prompt)

def is_ai_available() -> bool:
    """Check if AI model is available"""
    return get_model() is not None
