"""
watch_approvals.py — Polls Google Sheet every POLL_INTERVAL_SECONDS.
Detects Yes/No approvals, sends approved emails with 60s gap, enforces daily limit.
Stops when: batch resolved, daily limit hit, or 4-hour timeout.
"""

import os
import json
import time
import re
from datetime import datetime, timedelta
from dotenv import load_dotenv

load_dotenv()

DRAFTS_DIR  = '.tmp/drafts'
BATCH_PATH  = '.tmp/current_batch.json'
PROCESSED_PATH = '.tmp/processed_companies.json'


def _slug(name: str) -> str:
    return re.sub(r'[^a-z0-9_]', '', name.lower().strip().replace(' ', '_').replace('/', '_'))


def _load_json(path, default):
    if os.path.exists(path):
        with open(path) as f:
            return json.load(f)
    return default


def _is_sent(company_name: str) -> bool:
    """Check if company already sent — prevents duplicates."""
    processed = _load_json(PROCESSED_PATH, [])
    for c in processed:
        if c['company_name'].lower() == company_name.lower() and c.get('sent_at'):
            return True
    return False


def _print_status(rows, sent_today, max_per_day):
    now = datetime.now().strftime('%H:%M:%S')
    pending  = sum(1 for r in rows if r['approved'].lower() == 'pending' and r['status'] == 'Draft')
    approved = sum(1 for r in rows if r['approved'].lower() in ('yes', 'approved', 'y', 'true') and r['status'] == 'Draft')
    skipped  = sum(1 for r in rows if r['status'] in ('Skipped', 'Failed') or (r['approved'].lower() in ('no', 'skipped', 'n', 'false') and r['status'] == 'Draft'))
    print(f"[{now}] Watching sheet... Pending: {pending} | Approved: {approved} | Skipped: {skipped} | Sent today: {sent_today}/{max_per_day}")


def watch():
    from tools.update_sheet import read_approvals, update_row_status, get_todays_sent_count, get_all_rows
    from tools.send_email import send

    poll_interval = int(os.getenv('POLL_INTERVAL_SECONDS', 120))
    max_per_day   = int(os.getenv('MAX_EMAILS_PER_DAY', 5))
    timeout_hours = int(os.getenv('APPROVAL_TIMEOUT_HOURS', 4))
    sheet_id      = os.getenv('GOOGLE_SHEET_ID', '')

    deadline = datetime.now() + timedelta(hours=timeout_hours)
    sent_count    = 0
    skipped_count = 0
    failed_count  = 0

    print(f"\nWatching sheet for approvals (every {poll_interval}s, timeout {timeout_hours}h)...")
    print(f"Sheet: https://docs.google.com/spreadsheets/d/{sheet_id}\n")

    while datetime.now() < deadline:
        try:
            sent_today = get_todays_sent_count()

            # Daily limit check
            if sent_today >= max_per_day:
                print(f"\n[{datetime.now().strftime('%H:%M:%S')}] Daily limit reached ({sent_today}/{max_per_day} sent today).")
                print("Watching will resume automatically tomorrow.")
                print("Exiting watcher. Run python approve.py tomorrow to continue.")
                break

            all_rows  = get_all_rows()
            pending_approvals = read_approvals()  # Only Yes/No where Status=Draft

            _print_status(all_rows, sent_today, max_per_day)

            for row in pending_approvals:
                company_name = row['company_name']
                row_index    = row['row_index']
                approved_val = row['approved'].lower()

                if approved_val in ('no', 'skipped', 'n', 'false'):
                    update_row_status(row_index, 'Skipped')
                    print(f"  [!!] Skipped {company_name}")
                    skipped_count += 1
                    continue

                if approved_val in ('yes', 'approved', 'y', 'true'):
                    # Duplicate send guard
                    if _is_sent(company_name):
                        print(f"  ⚠ {company_name} already sent — skipping duplicate.")
                        update_row_status(row_index, 'Sent')
                        continue

                    # Load draft
                    slug = _slug(company_name)
                    draft_path = os.path.join(DRAFTS_DIR, f"{slug}.json")
                    if not os.path.exists(draft_path):
                        print(f"  [!!] Draft not found for {company_name}: {draft_path}")
                        update_row_status(row_index, 'Failed')
                        failed_count += 1
                        continue

                    with open(draft_path) as f:
                        draft = json.load(f)

                    draft['approved'] = True  # Set only after reading Yes from sheet

                    now_str = datetime.now().strftime('%H:%M:%S')
                    print(f"[{now_str}] Approved: {company_name} — sending now...")

                    def make_callback(ri):
                        def callback(status, sent_at=None):
                            update_row_status(ri, status, sent_at)
                        return callback

                    success = send(draft, update_sheet_fn=make_callback(row_index))
                    if success:
                        sent_count  += 1
                        sent_today  += 1
                        print(f"[{datetime.now().strftime('%H:%M:%S')}] [OK] Sent to {company_name} ({draft['contact_email']}) — {sent_today}/{max_per_day} today")
                        if sent_today >= max_per_day:
                            print(f"\nDaily limit reached. Exiting watcher. Run python approve.py tomorrow to continue.")
                            _print_summary(sent_count, skipped_count, failed_count, sheet_id)
                            return
                        print(f"  Waiting 60s before next send...")
                        time.sleep(60)
                    else:
                        failed_count += 1

            # Check if entire batch is resolved
            remaining = [r for r in all_rows if r['status'] == 'Draft']
            if not remaining:
                print("\nAll rows resolved.")
                break

        except Exception as e:
            print(f"  ⚠ Poll error: {e}")

        time.sleep(poll_interval)

    if datetime.now() >= deadline:
        print(f"\nTimeout after {timeout_hours} hours. Run python approve.py to resume.")

    _print_summary(sent_count, skipped_count, failed_count, sheet_id)


def _print_summary(sent, skipped, failed, sheet_id):
    processed = []
    if os.path.exists(PROCESSED_PATH):
        with open(PROCESSED_PATH) as f:
            processed = json.load(f)
    total = len(processed)
    print(f"""
============================================
Batch complete

Sent:    {sent}
Skipped: {skipped}
Failed:  {failed}

Total applied to date: {total}
Sheet: https://docs.google.com/spreadsheets/d/{sheet_id}
============================================""")


if __name__ == "__main__":
    watch()
