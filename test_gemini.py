import os
os.environ["GOOGLE_API_KEY"] = "AQ.Ab8RN6JgSPLx5iMb8weIVJ9E-8sR9pvyYSR-82lxmHKUYIWQsw"

import google.generativeai as genai
genai.configure(api_key=os.environ["GOOGLE_API_KEY"])

model = genai.GenerativeModel("gemini-2.0-flash")
response = model.generate_content("say hello in one sentence")
print(response.text)