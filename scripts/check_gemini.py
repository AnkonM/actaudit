"""One-off manual check that GEMINI_API_KEY works. Not part of the app or test suite.

Usage: python scripts/check_gemini.py [model_id]
"""
import os
import sys

from dotenv import load_dotenv
from google import genai

DEFAULT_MODEL = "gemini-3.8-flash"  # blueprint §10: do not revert to gemini-2.5-flash


def main() -> int:
    load_dotenv()
    key = os.getenv("GEMINI_API_KEY")
    if not key or key == "your-key-here":
        print("GEMINI_API_KEY is missing: copy .env.example to .env and paste your key.")
        return 1
    model = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_MODEL
    try:
        client = genai.Client(api_key=key)
        response = client.models.generate_content(model=model, contents="Reply with the word OK")
    except Exception as exc:  # report any auth/model/network failure plainly
        print(f"FAILED ({model}): {type(exc).__name__}: {exc}")
        return 1
    if not response.text:
        print(f"FAILED ({model}): empty response")
        return 1
    print(f"OK ({model}): {response.text.strip()}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
