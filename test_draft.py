import sys
import os
import json
sys.path.append(os.getcwd())
from tools.generate_email import generate

def test_draft():
    company = {"company_name": "TestCorp", "contact_name": "John Doe"}
    brief = {
        "what_they_do": "TestCorp builds high-performance CRM software using React and Node.js.",
        "main_product": "TestCRM",
        "frontend_tech": ["React", "TypeScript"],
        "company_type": "product company",
        "recent_hook": "their focus on accessibility in the latest CRM update."
    }
    print("TEST: Generating email via OpenRouter...")
    draft = generate(company, brief)
    if draft and "[Email generation failed]" not in draft.get('body', ''):
        print(f"RESULT: SUCCESS! Draft generated for {company['company_name']}")
        print(f"Subject: {draft['subject']}")
    else:
        print(f"RESULT: FAIL! {draft}")

if __name__ == "__main__":
    test_draft()
