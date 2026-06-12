from google import genai
import os

# The modern SDK automatically scans for your GEMINI_API_KEY variable
client = genai.Client()

response = client.models.generate_content(
    model='gemini-2.5-flash',
    contents='Say hello in one sentence.',
)

print("\n--- NOVA AI Response ---")
print(response.text)
print("------------------------\n")
