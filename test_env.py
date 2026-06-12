import os
from dotenv import load_dotenv

load_dotenv()

print("--- Key Detection Diagnostic ---")
print(True if os.environ.get("GEMINI_API_KEY") else False, "- Gemini Key Detected")
print(True if os.environ.get("GROQ_API_KEY") else False, "- Groq Key Detected")
print(True if os.environ.get("GITHUB_TOKEN") else False, "- GitHub Key Detected")
print(True if os.environ.get("OPENROUTER_API_KEY") else False, "- OpenRouter Key Detected")
