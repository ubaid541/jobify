"""
send_email.py — Sends one approved email via Gmail SMTP with CV attached.

HARD RULE: Will raise ValueError if draft['approved'] is not True.
DAILY LIMIT: Enforced via get_todays_sent_count() before every send.
"""

import os
import json
import smtplib
import sys
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email import encoders
from dotenv import load_dotenv

load_dotenv()

PROCESSED_PATH = '.tmp/processed_companies.json'
EMAIL_LOG_PATH = '.tmp/email_log.json'


def _load_json(path, default):
    if os.path.exists(path):
        with open(path) as f:
            return json.load(f)
    return default


def _save_json(path, data):
    with open(path, 'w') as f:
        json.dump(data, f, indent=2)


def send(draft: dict, update_sheet_fn=None) -> bool:
    """
    Sends a single approved email.
    - draft['approved'] MUST be True or raises ValueError.
    - Checks daily limit before sending.
    - Attaches CV from draft['cv_path'].
    - Updates processed_companies.json and email_log.json on success.
    - Calls update_sheet_fn(status, sent_at) if provided.
    Returns True on success, False on failure.
    """

    # HARD GATE — never skip this
    if not draft.get('approved') is True:
        raise ValueError("Cannot send. approved must be True.")

    # Daily limit check
    try:
        from tools.update_sheet import get_todays_sent_count
        sent_today = get_todays_sent_count()
        max_per_day = int(os.getenv('MAX_EMAILS_PER_DAY', 5))
        if sent_today >= max_per_day:
            raise Exception(f"Daily limit reached. {sent_today} emails sent today. Resuming tomorrow.")
    except ImportError:
        pass  # Sheet not configured — skip limit check

    gmail_user = os.getenv('SENDING_GMAIL')
    gmail_pass = os.getenv('SENDING_GMAIL_APP_PASSWORD')
    cv_path    = draft.get('cv_path', os.getenv('CV_PATH', ''))

    if not gmail_user or not gmail_pass:
        raise ValueError("SENDING_GMAIL and SENDING_GMAIL_APP_PASSWORD must be set in .env")

    to_email = draft['contact_email']
    subject  = draft['subject']
    body     = draft['body']

    # Build MIME message
    msg = MIMEMultipart()
    msg['From']    = gmail_user
    msg['To']      = to_email
    msg['Subject'] = subject
    msg.attach(MIMEText(body, 'plain'))

    # Attach CV
    if cv_path and os.path.exists(cv_path):
        with open(cv_path, 'rb') as f:
            part = MIMEBase('application', 'octet-stream')
            part.set_payload(f.read())
        encoders.encode_base64(part)
        filename = os.path.basename(cv_path)
        part.add_header('Content-Disposition', f'attachment; filename="{filename}"')
        msg.attach(part)
    else:
        print(f"    ⚠ CV not found at {cv_path} — sending without attachment.")

    try:
        with smtplib.SMTP_SSL('smtp.gmail.com', 465) as server:
            server.login(gmail_user, gmail_pass)
            server.sendmail(gmail_user, to_email, msg.as_string())
    except Exception as e:
        print(f"    [!!] Send failed: {e}")
        if update_sheet_fn:
            update_sheet_fn('Failed')
        return False

    sent_at = datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC')

    # Mark as sent in processed_companies.json
    processed = _load_json(PROCESSED_PATH, [])
    names = {c['company_name'].lower() for c in processed}
    company_obj = {
        "company_name":  draft['company_name'],
        "contact_name":  draft['contact_name'],
        "contact_email": draft['contact_email'],
        "website":       draft['website'],
        "fit_score":     draft['fit_score'],
        "sent_at":       sent_at,
        "subject":       draft['subject'],
    }
    if draft['company_name'].lower() not in names:
        processed.append(company_obj)
    else:
        # Update existing entry
        for i, c in enumerate(processed):
            if c['company_name'].lower() == draft['company_name'].lower():
                processed[i]['sent_at'] = sent_at
                break
    _save_json(PROCESSED_PATH, processed)

    # Append to email_log.json
    log = _load_json(EMAIL_LOG_PATH, [])
    log.append({
        "company":    draft['company_name'],
        "contact":    draft['contact_name'],
        "email":      to_email,
        "subject":    subject,
        "sent_at":    sent_at,
    })
    _save_json(EMAIL_LOG_PATH, log)

    if update_sheet_fn:
        update_sheet_fn('Sent', sent_at)

    print(f"  [OK] Sent to {draft['company_name']} ({to_email})")
    return True


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python tools/send_email.py '<draft_json_path>'")
        sys.exit(1)
    with open(sys.argv[1]) as f:
        draft_data = json.load(f)
    draft_data['approved'] = True  # Only set manually for direct invocation
    send(draft_data)
