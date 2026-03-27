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
from tools.utils import get_slug

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


from typing import Optional
from tools.utils import get_slug

def run_phase3_logic(sheet_url_or_id: str, dry_run: bool = False, thread_ts: Optional[str] = None, channel_id: Optional[str] = None):
    """
    Core logic for processing companies. 
    If thread_ts is provided, updates are sent to Slack.
    """
    from tools.slack_client import slack_client
    
    # Use provided channel or fallback to .env
    target_channel = channel_id or os.getenv("SLACK_CHANNEL_ID")

    def notify(text, blocks=None):
        if thread_ts and target_channel:
            try:
                if blocks:
                    slack_client.client.chat_postMessage(channel=target_channel, text=text, blocks=blocks, thread_ts=thread_ts)
                else:
                    slack_client.client.chat_postMessage(channel=target_channel, text=text, thread_ts=thread_ts)
            except Exception as e:
                print(f"Failed to send Slack message: {e}")
        try:
            print(text)
        except UnicodeEncodeError:
            # Fallback for Windows terminals without UTF-8 support
            print(text.encode('ascii', 'ignore').decode('ascii'))

    try:
        notify("🔍 Starting Jobify process...")
        check_prerequisites(dry_run=dry_run)

        sheet_id = os.getenv('GOOGLE_SHEET_ID', '')
        companies_per_day = int(os.getenv('COMPANIES_PER_DAY', 10))

        # Step 1: Ingest new companies
        notify("📥 Ingesting companies from source sheet...")
        if dry_run:
            batch = [{"company_name": "DryRun Corp", "website": "https://example.com",
                      "contact_email": "test@example.com"}]
        else:
            from tools.ingest_companies import ingest
            # Pass a high number to ingest so we get everything, we'll limit it ourselves
            batch = ingest(sheet_url_or_id, companies_per_run=100)

        if not batch:
            notify("✅ No new companies to process. Sheet is complete!")
            return

        # Filter out companies already processed (consistent with ingest)
        processed = _load_json(PROCESSED_PATH, [])
        processed_slugs = {get_slug(c['company_name']) for c in processed if 'company_name' in c}
        
        to_process = [c for c in batch if get_slug(c['company_name']) not in processed_slugs]
        
        if not to_process:
            notify("✅ All companies in this sheet have already been processed.")
            return

        # Check daily limit
        today = datetime.now().strftime("%Y-%m-%d")
        processed_today_count = sum(1 for c in processed if c.get('processed_at', '').startswith(today))
        
        remaining_today = companies_per_day - processed_today_count
        if remaining_today <= 0:
            notify(f"⚠️ Daily limit of {companies_per_day} reached. I'll continue tomorrow!")
            return

        chunk = to_process[:remaining_today]
        notify(f"🚀 Found {len(to_process)} new companies. Processing a batch of {len(chunk)} today.")

        from tools.update_sheet import append_draft_row
        from tools.research_company import research
        from tools.generate_email import generate

        for i, company in enumerate(chunk, 1):
            name = company['company_name']
            notify(f"🔄 [{i}/{len(chunk)}] Researching *{name}*...")
            
            # Research
            try:
                brief = research(company)
                if brief is None:
                    notify(f"❌ Research failed for {name}. Skipping.")
                    continue
            except Exception as e:
                notify(f"❌ Error during research for {name}: {str(e)}")
                continue

            notify(f"✍️ Generating email draft for *{name}*...")

            # Generate email with retry if it fails or has error message
            try:
                draft = generate(company, brief)
                
                # Check for common error strings in the draft body
                error_indicators = ["[Email generation failed", "please fill manually", "error generating email"]
                if not draft or any(indicator in draft.get('body', '') for indicator in error_indicators):
                    notify(f"⚠️ Draft for {name} had an error. Retrying generation...")
                    draft = generate(company, brief) # Simple one-time retry
                
                if not draft or any(indicator in draft.get('body', '') for indicator in error_indicators):
                    notify(f"❌ Email generation failed for {name} after retry. Manual intervention needed in the Google Sheet.")
                    # Still save the company as processed but mark it as needing manual fix
                    company['manual_review_needed'] = True
                else:
                    # Append to Google Sheet only if draft is good
                    row_index = None
                    if not dry_run:
                        row_index = append_draft_row(company, draft)
                        draft['row_index'] = row_index
                        # Re-save draft with row_index
                        # Re-save draft with row_index
                        slug = get_slug(name)
                        out_path = os.path.join('.tmp/drafts', f"{slug}.json")
                        with open(out_path, 'w') as f:
                            json.dump(draft, f, indent=2)
            except Exception as e:
                notify(f"❌ Error during email generation for {name}: {str(e)}")
                continue
            
            # Mark as processed
            company['processed_at'] = datetime.now().isoformat()
            processed.append(company)
            with open(PROCESSED_PATH, 'w') as f:
                json.dump(processed, f, indent=2)

            # Send approval buttons
            blocks = [
                {
                    "type": "section",
                    "text": {"type": "mrkdwn", "text": f"✅ Draft ready for *{name}*!\nView it in the Google Sheet or approve here."}
                },
                {
                    "type": "actions",
                    "elements": [
                        {
                            "type": "button",
                            "text": {"type": "plain_text", "text": "Approve & Send"},
                            "style": "primary",
                            "value": f"approve|{name}|{row_index}",
                            "action_id": "approve_draft"
                        },
                        {
                            "type": "button",
                            "text": {"type": "plain_text", "text": "Reject"},
                            "style": "danger",
                            "value": f"reject|{name}|{row_index}",
                            "action_id": "reject_draft"
                        }
                    ]
                }
            ]
            notify(f"Draft for {name} is ready!", blocks=blocks)

        if len(to_process) <= len(chunk):
            notify(f"🏆 *Sheet Complete!* All {len(to_process)} new companies have been processed.")
        else:
            notify(f"📅 Finished today's batch. {len(to_process) - len(chunk)} companies remaining in the sheet.")

    except Exception as e:
        error_msg = f"CRITICAL ERROR in Jobify process: {str(e)}"
        notify(error_msg)
        import traceback
        print(traceback.format_exc())


def run_phase3(sheet_url_or_id: str, dry_run: bool = False):
    """CLI wrapper for run_phase3_logic"""
    run_phase3_logic(sheet_url_or_id, dry_run=dry_run)


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if not a.startswith('--')]
    dry  = '--dry-run' in sys.argv

    if not args:
        print("Usage: python run_phase3.py <google_sheet_url_or_id> [--dry-run]")
        sys.exit(1)

    run_phase3(args[0], dry_run=dry)
