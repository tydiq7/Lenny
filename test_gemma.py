"""Phase 0: confirm Gemma 4 answers through the Gemini API. Run: python test_gemma.py"""
import os
import sys

from dotenv import load_dotenv
from google import genai

from config import MODEL_ID, FALLBACK_MODEL_ID

load_dotenv()  # reads GEMINI_API_KEY from .env
key = os.getenv("GEMINI_API_KEY")
if not key:
    sys.exit("GEMINI_API_KEY missing. Create .env with: GEMINI_API_KEY=your_key")

client = genai.Client(api_key=key)

for model in (MODEL_ID, FALLBACK_MODEL_ID):
    try:
        resp = client.models.generate_content(model=model, contents="Reply with the single word: ready")
        print(f"WORKS: {model} -> {resp.text.strip()[:60]}")
        break
    except Exception as e:
        print(f"FAILED: {model} -> {str(e)[:200]}")
else:
    sys.exit("Neither model ID worked. Check AI Studio for the exact Gemma 4 ID.")
