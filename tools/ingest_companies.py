"""
ingest_companies.py — Reads a new Apollo Excel sheet, filters and scores companies.

Usage:
    from tools.ingest_companies import ingest
    batch = ingest("new_companies.xlsx")

Or directly:
    python tools/ingest_companies.py new_companies.xlsx
"""

import os
import json
import sys
import pandas as pd
from dotenv import load_dotenv

load_dotenv()

PROCESSED_PATH = '.tmp/processed_companies.json'
PATTERNS_PATH  = '.tmp/application_patterns.json'
BATCH_PATH     = '.tmp/current_batch.json'


def _load_json(path):
    if os.path.exists(path):
        with open(path) as f:
            return json.load(f)
    return [] if path == PROCESSED_PATH else {}


def _slug(name: str) -> str:
    return name.lower().strip().replace(' ', '_').replace('/', '_')


def score_company(row: dict, patterns: dict) -> int:
    """Score a company 0-10 against application_patterns.json."""
    score = 0

    preferred_industries = [i.lower() for i in patterns.get('preferred_industries', [])]
    common_tech          = [t.lower() for t in patterns.get('common_technologies', [])]
    preferred_types      = [t.lower() for t in patterns.get('company_types_preferred', [])]
    common_keywords      = [k.lower() for k in patterns.get('common_keywords', [])]

    # Industry match (3 points)
    company_keywords_str = str(row.get('Keywords', '')).lower()
    industry_hits = sum(1 for ind in preferred_industries if ind in company_keywords_str)
    score += min(industry_hits, 3)

    # Tech stack overlap (3 points)
    company_tech_str = str(row.get('Technologies', '')).lower()
    tech_hits = sum(1 for tech in common_tech if any(t in company_tech_str for t in tech.split()))
    score += min(tech_hits, 3)

    # Keyword overlap (2 points)
    kw_hits = sum(1 for kw in common_keywords if kw in company_keywords_str)
    score += min(kw_hits, 2)

    # Country match (1 point)
    preferred_countries = [c.lower() for c in patterns.get('countries_applied', [])]
    company_country = str(row.get('Company Country', '')).lower()
    if any(c in company_country for c in preferred_countries):
        score += 1

    # Size match (1 point)
    size_str = patterns.get('preferred_company_size', '').lower()
    try:
        employees = int(row.get('# Employees', 0))
        if ('medium' in size_str and 50 <= employees <= 250) or \
           ('large' in size_str and 250 <= employees <= 1000):
            score += 1
    except (ValueError, TypeError):
        pass

    return min(score, 10)


import re
from tools.update_sheet import _get_service

def _extract_sheet_id(url_or_id: str) -> str:
    """Extracts the Sheet ID from a full URL, or returns the ID if passed directly."""
    match = re.search(r'/d/([a-zA-Z0-9-_]+)', url_or_id)
    if match:
        return match.group(1)
    return url_or_id.strip()

def _get_sheet_data(sheet_id: str) -> list[dict]:
    service = _get_service()
    try:
        # Get the first sheet's name to fetch all its data
        ss = service.spreadsheets().get(spreadsheetId=sheet_id).execute()
        sheet_name = ss['sheets'][0]['properties']['title']

        result = service.spreadsheets().values().get(
            spreadsheetId=sheet_id,
            range=f"'{sheet_name}'"
        ).execute()
        values = result.get('values', [])
    except Exception as e:
        print(f"\n[!!] Failed to read Google Sheet: {e}")
        print("Ensure the Sheet URL is correct and shared with the authenticated account.")
        sys.exit(1)

    if not values or len(values) < 2:
        print("\n[!!] Google Sheet is empty or missing headers.")
        sys.exit(1)

    headers = [str(h).strip() for h in values[0]]
    data = []
    for row in values[1:]:
        # Pad row with empty strings if it's shorter than headers
        padded_row = row + [''] * (len(headers) - len(row))
        data.append(dict(zip(headers, padded_row)))
    
    return data

def ingest(url_or_id: str, companies_per_run: int = 5):
    """
    1. Fetches data from source Google Sheet.
    2. Deduplicates companies within the sheet.
    3. Filters out companies already in processed_companies.json.
    4. Scores them and takes the top N.
    """
    print(f"\n[Step 1/4] Ingesting companies from source sheet...")
    sheet_id = _extract_sheet_id(url_or_id)
    df_dicts = _get_sheet_data(sheet_id)
    
    if not df_dicts:
        print("[!!] No data found in the source sheet.")
        sys.exit(1)

    # Load processed companies (by slug)
    processed = []
    if os.path.exists(PROCESSED_PATH):
        try:
            with open(PROCESSED_PATH) as f:
                processed = json.load(f)
        except:
            processed = []
    
    processed_slugs = { _slug(c['company_name']) for c in processed if 'company_name' in c }

    patterns = {}
    if os.path.exists(PATTERNS_PATH):
        with open(PATTERNS_PATH) as f:
            patterns = json.load(f)

    candidates = []
    seen_in_this_sheet = set()
    skipped_exists = 0
    skipped_no_email = 0
    skipped_duplicate = 0

    for row in df_dicts:
        name = str(row.get('Company', row.get('Company Name', ''))).strip()
        if not name or name.lower() == 'nan':
            continue

        slug = _slug(name)
        
        # 1. Skip if already processed in history
        if slug in processed_slugs:
            skipped_exists += 1
            continue

        # 2. Skip if duplicate within this specific sheet export
        if slug in seen_in_this_sheet:
            skipped_duplicate += 1
            continue
        seen_in_this_sheet.add(slug)

        # 3. Skip if no email
        contact_email = str(row.get('Email', '')).strip()
        if not contact_email or contact_email.lower() == 'nan' or '@' not in contact_email:
            skipped_no_email += 1
            continue

        fit_score = score_company(row, patterns)
        if fit_score < 6:
            continue
            
        def _safe_int(val, default=0):
            try:
                return int(val)
            except (ValueError, TypeError):
                return default

        keywords_raw = str(row.get('Keywords', ''))
        tech_raw = str(row.get('Technologies', ''))

        candidates.append({
            "company_name":    name,
            "website":         str(row.get('Website', '')).strip(),
            "linkedin":        str(row.get('Company Linkedin Url', '')).strip(),
            "contact_name":    f"{row.get('First Name', '')} {row.get('Last Name', '')}".strip(),
            "contact_title":   str(row.get('Title', '')).strip(),
            "contact_email":   contact_email,
            "employees":       _safe_int(row.get('# Employees', '')),
            "country":         str(row.get('Company Country', '')).strip(),
            "city":            str(row.get('Company City', '')).strip(),
            "keywords":        [k.strip() for k in keywords_raw.split(',')] if keywords_raw and keywords_raw.lower() != 'nan' else [],
            "technologies":    [t.strip() for t in tech_raw.split(',')] if tech_raw and tech_raw.lower() != 'nan' else [],
            "fit_score":       fit_score,
        })

    # Sort desc and take top N
    candidates.sort(key=lambda x: x['fit_score'], reverse=True)
    batch = candidates[:companies_per_run]

    if not batch:
        print("No matching companies found in this sheet. Try a new export.")
        sys.exit(0)

    print(f"\n[OK] Ingested {len(batch)} companies (score >=6) out of {len(df_dicts)} rows.")
    print(f"  Skipped (already in processed_companies.json): {skipped_exists}")
    print(f"  Skipped (no contact email): {skipped_no_email}")
    print(f"  Skipped (duplicate in sheet): {skipped_duplicate}")
    for c in batch:
        print(f"  [{c['fit_score']}/10] {c['company_name']} ({c['country']})")

    os.makedirs('.tmp', exist_ok=True)
    with open(BATCH_PATH, 'w') as f:
        json.dump(batch, f, indent=2)
    print(f"\n[OK] Batch saved to {BATCH_PATH}")
    return batch

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python tools/ingest_companies.py <google_sheet_url_or_id>")
        sys.exit(1)
    ingest(sys.argv[1])
