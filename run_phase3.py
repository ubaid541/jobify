"""
run_phase3.py — Main orchestrator for Phase 3.

Usage:
    python run_phase3.py "https://docs.google.com/spreadsheets/d/..."
    python run_phase3.py <sheet_id> --dry-run
"""

import os
import sys
import json
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

BATCH_PATH = '.tmp/current_batch.json'
PROCESSED_PATH = '.tmp/processed_companies.json'


def _load_json(path, default):
    if os.path.exists(path):
        with open(path) as f:
            return json.load(f)
    return default


def check_prerequisites(dry_run: bool = False):
    """Verify all required .env keys exist."""
    def _is_missing(key):
        val = os.getenv(key, '')
        val = val.strip().split('#')[0].strip()  # strip inline comments
        return not val

    required = ['GEMINI_API_KEY', 'GOOGLE_SHEET_ID'] if dry_run else \
               ['GEMINI_API_KEY', 'GOOGLE_SHEET_ID', 'SENDING_GMAIL', 'SENDING_GMAIL_APP_PASSWORD']
    missing = [k for k in required if _is_missing(k)]
    if missing:
        for k in missing:
            if k == 'GOOGLE_SHEET_ID':
                print(f"[!!] {k} not set. Run: python tools/setup_google_sheets.py first.")
            elif k in ('SENDING_GMAIL', 'SENDING_GMAIL_APP_PASSWORD'):
                print(f"[!!] {k} not set in .env")
                print(f"     Get Gmail App Password at: myaccount.google.com/apppasswords")
            else:
                print(f"[!!] {k} not set in .env")
        sys.exit(1)
    print("[OK] All prerequisites found.")


def check_incomplete_batch():
    """Ask to resume previous batch if one exists with unresolved rows."""
    if not os.path.exists(BATCH_PATH):
        return False

    with open(BATCH_PATH) as f:
        batch = json.load(f)

    if not batch:
        return False

    # Check if any company in batch still has pending sheet rows
    # (Simple check: see if batch file exists and is non-empty)
    print(f"\nPrevious incomplete batch found ({len(batch)} companies).")
    ans = input("Resume it? (y/n): ").strip().lower()
    return ans == 'y'


def run_phase3(sheet_url_or_id: str, dry_run: bool = False):
    print("\n" + "=" * 44)
    print("  Jobify — Phase 3")
    print("=" * 44)

    check_prerequisites(dry_run=dry_run)

    sheet_id = os.getenv('GOOGLE_SHEET_ID', '')
    companies_per_run = int(os.getenv('COMPANIES_PER_RUN', 5))

    # Step 1: Check for resume
    if check_incomplete_batch():
        print("Resuming existing batch — skipping ingestion.")
        with open(BATCH_PATH) as f:
            batch = json.load(f)
    else:
        # Step 2: Ingest new companies from Google Sheet
        print(f"\n[Step 1/4] Ingesting companies from source sheet...")
        if dry_run:
            print("  DRY RUN — skipping API calls. Using mock batch.")
            batch = [{"company_name": "DryRun Corp", "website": "https://example.com",
                      "linkedin": "", "contact_name": "Test User", "contact_title": "HR",
                      "contact_email": "test@example.com", "fit_score": 8,
                      "employees": 100, "country": "Netherlands", "city": "Amsterdam",
                      "keywords": [], "technologies": []}]
        else:
            from tools.ingest_companies import ingest
            batch = ingest(sheet_url_or_id)

    if not batch:
        print("No companies to process. Exiting.")
        sys.exit(0)

    from tools.update_sheet import sheet_exists, append_draft_row

    if not dry_run and not sheet_exists():
        print("[!!] Google Sheet not accessible. Run setup_google_sheets.py first.")
        sys.exit(1)

    print(f"\n[Step 2/4] Researching {len(batch)} companies and generating emails...")
    successful = []

    for i, company in enumerate(batch, 1):
        name = company['company_name']
        print(f"\n  [{i}/{len(batch)}] {name}")

        if dry_run:
            print("    DRY RUN — skipping research and generation.")
            successful.append(company)
            continue

        # Research
        from tools.research_company import research
        brief = research(company)
        if brief is None:
            print(f"    [SKIP] Research failed for {name}.")
            continue

        # Generate email
        from tools.generate_email import generate
        draft = generate(company, brief)
        if not draft:
            print(f"    [SKIP] Email generation failed for {name}.")
            continue

        # Append to Google Sheet
        print(f"    Adding to Google Sheet...")
        append_draft_row(company, draft)
        successful.append(company)

    if not successful:
        print("\nNo companies successfully processed. Check .tmp/failed_urls.json.")
        sys.exit(1)

    print(f"\n[Step 3/4] {len(successful)} draft(s) added to Google Sheet.")

    # Step 4: Print instructions and watch
    sheet_url = f"https://docs.google.com/spreadsheets/d/{sheet_id}"
    print(f"""
============================================
{len(successful)} draft(s) added to your Google Sheet.

Open the sheet and set Approved to Yes or No:
{sheet_url}

The agent is now watching for your approvals every 2 minutes.
Daily limit: {int(os.getenv('MAX_EMAILS_PER_DAY', 5))} emails per day.
Press Ctrl+C to stop watching (run python approve.py later to resume).
============================================
""")

    if dry_run:
        print("DRY RUN complete. Watcher not started.")
        return

    print("[Step 4/4] Starting watcher...")
    from tools.watch_approvals import watch
    watch()


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if not a.startswith('--')]
    dry  = '--dry-run' in sys.argv

    if not args:
        print("Usage: python run_phase3.py <google_sheet_url_or_id> [--dry-run]")
        sys.exit(1)

    run_phase3(args[0], dry_run=dry)
