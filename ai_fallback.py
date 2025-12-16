import os
import time
from typing import Optional

_openai_client = None
_gemini_client = None
_groq_client = None

def get_openai_client():
    global _openai_client
    if _openai_client is None:
        api_key = os.environ.get("OPENAI_API_KEY")
        if api_key:
            from openai import OpenAI
            _openai_client = OpenAI(api_key=api_key)
            print("[AI Fallback] OpenAI client initialized")
    return _openai_client

def get_gemini_client():
    global _gemini_client
    if _gemini_client is None:
        api_key = os.environ.get("GEMINI_API_KEY")
        if api_key:
            try:
                from google import genai
                _gemini_client = genai.Client(api_key=api_key)
                print("[AI Fallback] Gemini client initialized")
            except ImportError:
                print("[AI Fallback] google-genai not installed")
            except Exception as e:
                print(f"[AI Fallback] Gemini init failed: {e}")
    return _gemini_client

def get_groq_client():
    global _groq_client
    if _groq_client is None:
        api_key = os.environ.get("GROQ_API_KEY")
        if api_key:
            try:
                from groq import Groq
                _groq_client = Groq(api_key=api_key)
                print("[AI Fallback] Groq client initialized")
            except ImportError:
                print("[AI Fallback] groq not installed")
            except Exception as e:
                print(f"[AI Fallback] Groq init failed: {e}")
    return _groq_client

def generate_ai_response(prompt: str) -> str:
    client = get_openai_client()
    if client is not None:
        try:
            response = client.chat.completions.create(
                model="gpt-4o",
                messages=[{"role": "user", "content": prompt}],
                max_completion_tokens=300,
                temperature=0.4
            )
            return response.choices[0].message.content or ""
        except Exception as e:
            print(f"[AI Fallback] OpenAI failed, switching to Gemini: {e}")
            time.sleep(1)

    gemini = get_gemini_client()
    if gemini is not None:
        try:
            from google.genai import types
            response = gemini.models.generate_content(
                model="gemini-2.0-flash",
                contents=prompt,
                config=types.GenerateContentConfig(max_output_tokens=300)
            )
            if response and response.text:
                return response.text
        except Exception as e:
            print(f"[AI Fallback] Gemini failed, switching to Groq: {e}")
            time.sleep(1)

    groq = get_groq_client()
    if groq is not None:
        try:
            response = groq.chat.completions.create(
                model="llama-3.1-8b-instant",
                messages=[{"role": "user", "content": prompt}],
                temperature=0.4,
                max_tokens=300
            )
            return response.choices[0].message.content or ""
        except Exception as e:
            print(f"[AI Fallback] Groq also failed: {e}")
            time.sleep(1)

    return "AI is currently unavailable. Please try again later."
