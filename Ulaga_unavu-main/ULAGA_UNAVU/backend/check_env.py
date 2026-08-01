
import os
from dotenv import load_dotenv

load_dotenv()
key = os.getenv('GROQ_API_KEY')
print(f"GROQ_API_KEY: {key[:5]}...{key[-5:]}" if key else "GROQ_API_KEY: NOT FOUND")
