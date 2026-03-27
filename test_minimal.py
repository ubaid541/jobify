import sys
import os
import json
sys.path.append(os.getcwd())
from tools.research_company import research

def test_minimal():
    company = {"company_name": "OpenAI", "website": "https://openai.com"}
    print("TEST: Researching OpenAI via OpenRouter...")
    brief = research(company)
    print(f"RESULT: {json.dumps(brief, indent=2) if brief else 'NONE'}")

if __name__ == "__main__":
    test_minimal()
