"""
research_company.py — Visits website and LinkedIn for one company, extracts research brief.

Usage:
    from tools.research_company import research
    brief = research(company_obj)

Or standalone:
    python tools/research_company.py '{"company_name": "...", "website": "...", ...}'
"""

import os
import json
import sys
import re
import requests
from bs4 import BeautifulSoup
import google.generativeai as genai
from dotenv import load_dotenv

load_dotenv()

RESEARCH_DIR = '.tmp/research'
FAILED_PATH  = '.tmp/failed_urls.json'


def _load_failed():
    if os.path.exists(FAILED_PATH):
        with open(FAILED_PATH) as f:
            return json.load(f)
    return {}


def _save_failed(failures):
    with open(FAILED_PATH, 'w') as f:
        json.dump(failures, f, indent=2)


def _slug(name: str) -> str:
    return re.sub(r'[^a-z0-9_]', '', name.lower().strip().replace(' ', '_').replace('/', '_'))


def _scrape(url: str) -> str:
    """Fetches URL and returns cleaned text. Returns error string on failure."""
    try:
        headers = {'User-Agent': 'Mozilla/5.0 (compatible; Jobify/1.0)'}
        resp = requests.get(url, timeout=12, headers=headers)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, 'html.parser')
        for tag in soup(['script', 'style', 'nav', 'footer', 'head']):
            tag.decompose()
        text = soup.get_text(separator=' ')
        text = ' '.join(text.split())
        return text[:8000]
    except Exception as e:
        return f"ERROR: {e}"


def _gemini():
    api_key = os.getenv('GEMINI_API_KEY')
    if not api_key:
        raise ValueError("GEMINI_API_KEY not set in .env")
    genai.configure(api_key=api_key)
    return genai.GenerativeModel('gemini-2.5-flash')


def research(company: dict) -> dict | None:
    """
    Visits website (and LinkedIn if available), extracts research brief.
    Returns dict or None if website is unreachable.
    """
    name    = company['company_name']
    slug    = _slug(name)
    website = company.get('website', '').strip()
    linkedin = company.get('linkedin', '').strip()

    os.makedirs(RESEARCH_DIR, exist_ok=True)
    output_path = os.path.join(RESEARCH_DIR, f"{slug}.json")
    failures = _load_failed()

    print(f"  Researching {name}...")

    # Scrape website
    website_text = ''
    if website:
        website_text = _scrape(website)
        if website_text.startswith('ERROR:'):
            print(f"    [!!] Website unreachable: {website_text}")
            failures[website] = website_text
            _save_failed(failures)
            return None  # Skip this company

    # Scrape LinkedIn (best-effort, won't crash if blocked)
    linkedin_text = ''
    if linkedin:
        raw = _scrape(linkedin)
        if not raw.startswith('ERROR:'):
            linkedin_text = raw[:3000]

    combined = f"WEBSITE:\n{website_text}\n\nLINKEDIN:\n{linkedin_text}"

    model = _gemini()
    profile_str = json.load(open('.tmp/profile.json')) if os.path.exists('.tmp/profile.json') else {}

    prompt = f"""
You are a job application research analyst.

Given the website content of a company below, extract the following in JSON:
- what_they_do: 2-3 sentences, plain English, what the company does.
- main_product: One sentence describing their core product or service.
- frontend_tech: Specific React, JavaScript, TypeScript, Next.js, or any frontend tech mentioned. Empty list if none.
- company_type: One of startup / scaleup / product company / agency / enterprise.
- recent_hook: A specific observation from the website — a product feature, recent launch, engineering decision, or company philosophy that a React.js developer with SaaS/CRM experience could genuinely connect with. This is the opening line hook for the cold email. Must be specific, not generic.

My background for context:
{json.dumps(profile_str, indent=2)[:800]}

Company website + LinkedIn:
{combined[:10000]}

Return ONLY valid JSON.
"""

    try:
        response = model.generate_content(prompt)
        content = response.text.strip().lstrip('```json').lstrip('```').rstrip('```').strip()
        brief = json.loads(content)
    except Exception as e:
        print(f"    [!!] Gemini parse error: {e}")
        brief = {
            "what_they_do":  "Could not extract.",
            "main_product":  "N/A",
            "frontend_tech": [],
            "company_type":  "unknown",
            "recent_hook":   ""
        }

    brief['company_name'] = name
    brief['website']      = website

    with open(output_path, 'w') as f:
        json.dump(brief, f, indent=2)
    print(f"    [OK] Research saved -> {output_path}")
    return brief


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python tools/research_company.py '<company_json>'")
        sys.exit(1)
    company = json.loads(sys.argv[1])
    result = research(company)
    if result:
        print(json.dumps(result, indent=2))
    else:
        print("Research failed — company skipped.")
