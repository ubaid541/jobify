"""
approve.py — Manual resume script for interrupted approval batches.

Usage: python approve.py
Reads GOOGLE_SHEET_ID from .env, finds rows with Approved=Yes and Status=Draft,
checks remaining daily send capacity, processes them with 60s gap.
"""

import os
import json
import time
import re
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

DRAFTS_DIR = '.tmp/drafts'
PROCESSED_PATH = '.tmp/processed_companies.json'


def _slug(name: str) -> str:
    return re.sub(r'[^a-z0-9_]', '', name.lower().strip().replace(' ', '_').replace('/', '_'))


def _is_sent(company_name: str) -> bool:
    if os.path.exists(PROCESSED_PATH):
        with open(PROCESSED_PATH) as f:
            processed = json.load(f)
        for c in processed:
            if c['company_name'].lower() == company_name.lower() and c.get('sent_at'):
                return True
    return False


def main():
    from tools.update_sheet import read_approvals, update_row_status, get_todays_sent_count, get_all_rows
    from tools.send_email import send

    max_per_day = int(os.getenv('MAX_EMAILS_PER_DAY', 5))
    sheet_id    = os.getenv('GOOGLE_SHEET_ID', '')

    sent_today = get_todays_sent_count()
    remaining  = max_per_day - sent_today
    print(f"\nResuming approval run...")
    print(f"Sent today: {sent_today}/{max_per_day} — {max(remaining, 0)} send(s) remaining today.")

    if remaining <= 0:
        print("Daily limit already reached. Come back tomorrow.")
        return

    pending = read_approvals()
    print(f"Found {len(pending)} approved row(s) pending send.\n")

    if not pending:
        print("Nothing to do.")
        return

    sent_count    = 0
    skipped_count = 0
    failed_count  = 0

    for row in pending:
        if sent_count >= remaining:
            print(f"\nDaily limit reached ({max_per_day}/day). Resume tomorrow.")
            break

        company_name = row['company_name']
        row_index    = row['row_index']
        approved_val = row['approved'].lower()

        if approved_val in ('no', 'skipped', 'n', 'false'):
            update_row_status(row_index, 'Skipped')
            print(f"[!!] Skipped {company_name}")
            skipped_count += 1
            continue

        if approved_val in ('yes', 'approved', 'y', 'true'):
            if _is_sent(company_name):
                print(f"⚠ {company_name} already sent — skipping duplicate.")
                update_row_status(row_index, 'Sent')
                continue

            slug = _slug(company_name)
            draft_path = os.path.join(DRAFTS_DIR, f"{slug}.json")
            if not os.path.exists(draft_path):
                print(f"[!!] Draft not found for {company_name}")
                update_row_status(row_index, 'Failed')
                failed_count += 1
                continue

            with open(draft_path) as f:
                draft = json.load(f)
            draft['approved'] = True  # Only set after reading Yes from sheet

            def make_callback(ri):
                def callback(status, sat=None):
                    update_row_status(ri, status, sat)
                return callback

            success = send(draft, update_sheet_fn=make_callback(row_index))
            if success:
                sent_count += 1
                sent_today += 1
                print(f"[OK] Sent to {company_name} — {sent_today}/{max_per_day} today")
                if sent_count < remaining and len(pending) > 1:
                    print("  Waiting 60s before next send...")
                    time.sleep(60)
            else:
                failed_count += 1

    # Final summary
    if os.path.exists(PROCESSED_PATH):
        with open(PROCESSED_PATH) as f:
            total_processed = len(json.load(f))
    else:
        total_processed = 0

    print(f"""
============================================
Approval run complete

Sent:    {sent_count}
Skipped: {skipped_count}
Failed:  {failed_count}

Total applied to date: {total_processed}
============================================""")


if __name__ == "__main__":
    main()
