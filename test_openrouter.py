import sys
import os
import json
# Add project root to path
sys.path.append(os.getcwd())

from tools.research_company import research
from tools.generate_email import generate

def test():
    print("--- 1. Testing Research (OpenRouter) ---")
    company = {"company_name": "OpenRouter", "website": "https://openrouter.ai"}
    brief = research(company)
    if brief:
        print(f"[SUCCESS] Research brief generated: {json.dumps(brief, indent=2)}")
    else:
        print("[FAIL] Research brief is None")
        return

    print("\n--- 2. Testing Drafting (OpenRouter) ---")
    draft = generate(company, brief)
    if draft:
        print(f"[SUCCESS] Draft generated: {json.dumps(draft, indent=2)}")
    else:
        print("[FAIL] Draft is None")

if __name__ == "__main__":
    test()
