"""
generate_email.py — Writes one personalized cold email from a research brief.

Usage:
    from tools.generate_email import generate
    draft = generate(company, research_brief)
"""

import os
import json
import sys
import re
from datetime import datetime
import google.generativeai as genai
from dotenv import load_dotenv

load_dotenv()

DRAFTS_DIR   = '.tmp/drafts'
PROFILE_PATH = '.tmp/profile.json'
STYLE_PATH   = '.tmp/style.json'


def _slug(name: str) -> str:
    return re.sub(r'[^a-z0-9_]', '', name.lower().strip().replace(' ', '_').replace('/', '_'))


def _gemini():
    api_key = os.getenv('GEMINI_API_KEY')
    if not api_key:
        raise ValueError("GEMINI_API_KEY not set in .env")
    genai.configure(api_key=api_key)
    return genai.GenerativeModel('gemini-2.5-flash')


def generate(company: dict, brief: dict) -> dict:
    """
    Generates a personalized cold email draft and saves to .tmp/drafts/<slug>.json.
    Returns the draft dict.
    """
    os.makedirs(DRAFTS_DIR, exist_ok=True)

    with open(PROFILE_PATH) as f:
        profile = json.load(f)
    with open(STYLE_PATH) as f:
        style = json.load(f)

    loom_url     = os.getenv('LOOM_URL', '')
    sending_email= os.getenv('SENDING_GMAIL', '')
    cv_path      = os.getenv('CV_PATH', 'cv/Ubaid-Ur-Rehman-Resume.pdf')

    prompt = f"""
You are a professional job application writer. Write one cold outreach email for a React.js developer applying remotely to a company in the Netherlands.

STRICT EMAIL STRUCTURE — follow exactly:
1. Subject: Specific to this company. References their product, tech, or something concrete from research. Never generic.
2. Opening line: One sentence. Genuine observation about something specific from the research hook — not a generic compliment. No "I came across your company" type openers.
3. Paragraph 1: Self-introduction. 3+ years React.js, SaaS and CRM experience, what I build.
4. Paragraph 2: Why this company specifically — connects my React.js/SaaS skills to something specific from their research brief.
5. CTA: One clear ask for a quick chat. Include this exact Loom URL: {loom_url}
6. Signature: Best regards,\nUbaid Ur Rehman\nReact.js Developer\n{sending_email}

TONE RULES from style profile:
- Tone: {style.get('tone')}
- Formality: {style.get('formality')}
- Length: {style.get('typical_length')} — keep it SHORT
- Use contractions (I'm, I've, you're)
- No corporate filler phrases
- Unique traits: {json.dumps(style.get('unique_traits', []))}

MY PROFILE:
{json.dumps(profile, indent=2)[:1200]}

COMPANY RESEARCH:
- Company: {brief.get('company_name')}
- What they do: {brief.get('what_they_do')}
- Main product: {brief.get('main_product')}
- Frontend tech: {brief.get('frontend_tech')}
- Company type: {brief.get('company_type')}
- Hook (use this as the opening line basis): {brief.get('recent_hook')}

CONTACT:
- Name: {company.get('contact_name', 'Hiring Manager')}
- Title: {company.get('contact_title', '')}
- Email: {company.get('contact_email', '')}

Return ONLY valid JSON with two keys:
{{"subject": "...", "body": "..."}}

The body should be the full email text starting with "Hi [First Name]," and ending with the signature.
"""

    model = _gemini()
    import time
    from google.api_core.exceptions import ResourceExhausted

    max_retries = 3
    for attempt in range(max_retries):
        try:
            response = model.generate_content(prompt)
            content = response.text.strip().lstrip('```json').lstrip('```').rstrip('```').strip()
            result = json.loads(content)
            subject = result['subject']
            body    = result['body']
            break
        except ResourceExhausted as e:
            if attempt < max_retries - 1:
                wait_time = 30 * (attempt + 1)
                print(f"    [!!] Rate limit (429) hit. Pausing {wait_time}s and retrying ({attempt+1}/{max_retries})...")
                time.sleep(wait_time)
            else:
                print(f"    [!!] Gemini rate limit exceeded after {max_retries} retries.")
                subject = f"React.js Developer — {company.get('company_name')}"
                body    = "[Email generation failed — please fill manually]"
        except Exception as e:
            print(f"    [!!] Gemini error generating email: {e}")
            subject = f"React.js Developer — {company.get('company_name')}"
            body    = "[Email generation failed — please fill manually]"
            break

    name  = company.get('company_name', '')
    slug  = _slug(name)
    draft = {
        "company_name":   name,
        "contact_name":   company.get('contact_name', ''),
        "contact_title":  company.get('contact_title', ''),
        "contact_email":  company.get('contact_email', ''),
        "website":        company.get('website', ''),
        "linkedin":       company.get('linkedin', ''),
        "subject":        subject,
        "body":           body,
        "cv_path":        cv_path,
        "approved":       False,
        "fit_score":      company.get('fit_score', 0),
        "generated_at":   datetime.utcnow().isoformat(),
        "sent_at":        None
    }

    out_path = os.path.join(DRAFTS_DIR, f"{slug}.json")
    with open(out_path, 'w') as f:
        json.dump(draft, f, indent=2)
    print(f"    [OK] Draft saved -> {out_path}")
    print(f"      Subject: {subject}")
    return draft


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: python tools/generate_email.py '<company_json>' '<brief_json>'")
        sys.exit(1)
    company = json.loads(sys.argv[1])
    brief   = json.loads(sys.argv[2])
    draft   = generate(company, brief)
    print(json.dumps(draft, indent=2))
