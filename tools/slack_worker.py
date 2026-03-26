import os
import sys
import re
import threading
from slack_bolt import App
from slack_bolt.adapter.socket_mode import SocketModeHandler
from dotenv import load_dotenv

# Add project root to sys.path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import logging
# Set logging to WARNING to hide noisy Slack/SSL debug logs
logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
# Specifically silence noisy slack_bolt logs
logging.getLogger("slack_bolt.App").setLevel(logging.WARNING)
logging.getLogger("slack_bolt.adapter.socket_mode.threading_handler").setLevel(logging.ERROR)

from tools.slack_client import slack_client
import run_phase3
from tools.send_email import send as send_email
from tools.update_sheet import update_row_status, get_all_rows, _get_service, _get_sheet_id, SHEET_TAB
import json

load_dotenv()

app = App(token=os.getenv("SLACK_BOT_TOKEN"))

# Keep track of events being processed to avoid duplicate threads
processing_events = set()

@app.event("app_mention")
@app.event("message")
def handle_incoming_message(event, say, logger):
    event_id = event.get("event_ts")
    if event_id in processing_events:
        return
    
    # Ignore bot messages and edited messages
    if event.get("bot_id") or event.get("subtype") == "message_changed":
        return

    text = event.get("text", "")
    channel = event.get("channel")
    thread_ts = event.get("ts")
    
    # We only respond if either:
    # 1. It's an app_mention
    # 2. It's a DM (channel starts with D)
    # 3. It's in the designated channel AND starts with "process" (some users might not mention)
    is_mention = event.get("type") == "app_mention"
    is_dm = channel.startswith("D")
    is_relevant = is_mention or is_dm or ("process" in text.lower())

    if not is_relevant:
        return

    # More robust regex for Google Sheet URL
    # Slack wraps URLs like <https://...|text> or just <https://...>
    url_pattern = r"(https://docs\.google\.com/spreadsheets/d/[a-zA-Z0-9-_]+)"
    match = re.search(url_pattern, text)
    
    if "process" in text.lower() and match:
        sheet_url = match.group(1)
        say(text=f"🚀 Received! Starting to process: {sheet_url}", thread_ts=thread_ts)
        
        # Run processing in a separate thread
        def run_with_cleanup():
            try:
                run_phase3.run_phase3_logic(sheet_url, thread_ts=thread_ts, channel_id=channel)
            finally:
                if event_id in processing_events:
                    processing_events.remove(event_id)

        processing_events.add(event_id)
        thread = threading.Thread(target=run_with_cleanup)
        thread.start()
    elif "approvals" in text.lower():
        # Scan .tmp/drafts for pending ones
        drafts_dir = ".tmp/drafts"
        if not os.path.exists(drafts_dir):
            say(text="No pending drafts found.", thread_ts=thread_ts)
            return

        pending_count = 0
        for filename in os.listdir(drafts_dir):
            if filename.endswith(".json"):
                try:
                    with open(os.path.join(drafts_dir, filename)) as f:
                        draft = json.load(f)
                    
                    if not draft.get("sent_at") and not draft.get("approved"):
                        pending_count += 1
                        name = draft["company_name"]
                        blocks = [
                            {
                                "type": "section",
                                "text": {"type": "mrkdwn", "text": f"📋 *Pending Approval:* {name}\nSubject: {draft['subject']}"}
                            },
                            {
                                "type": "actions",
                                "elements": [
                                    {
                                        "type": "button",
                                        "text": {"type": "plain_text", "text": "Approve & Send"},
                                        "style": "primary",
                                        "value": f"approve|{name}",
                                        "action_id": "approve_draft"
                                    },
                                    {
                                        "type": "button",
                                        "text": {"type": "plain_text", "text": "Reject"},
                                        "style": "danger",
                                        "value": f"reject|{name}",
                                        "action_id": "reject_draft"
                                    }
                                ]
                            }
                        ]
                        say(blocks=blocks, thread_ts=thread_ts)
                except:
                    continue
        
        if pending_count == 0:
            say(text="All caught up! No pending approvals found.", thread_ts=thread_ts)
        else:
            say(text=f"Sent cards for {pending_count} pending drafts.", thread_ts=thread_ts)

    elif "process" in text.lower():
        say(text="I saw 'process' but couldn't find a valid Google Sheet URL. Use: `@Jobify process <URL>`", thread_ts=thread_ts)

@app.action("approve_draft")
def handle_approve(ack, body, say):
    ack()
    user_id = body["user"]["id"]
    action_value = body["actions"][0]["value"] # "approve|company_name|contact_email"
    parts = action_value.split("|")
    company_name = parts[1]
    
    # Locate the draft file
    from tools.utils import get_slug
    slug = get_slug(company_name)
    draft_path = os.path.join(".tmp/drafts", f"{slug}.json")
    
    if not os.path.exists(draft_path):
        say(text=f"❌ Could not find draft for {company_name} at {draft_path}")
        return

    with open(draft_path) as f:
        draft = json.load(f)
    
    # --- SYNC WITH GOOGLE SHEET ---
    row_index = draft.get('row_index')
    try:
        service = _get_service()
        sid = _get_sheet_id()
        if not row_index:
            # Try to find the row by company name if index is missing in JSON
            all_rows = get_all_rows()
            for r in all_rows:
                if r['company_name'] == company_name:
                    row_index = r['row_index']
                    break
        
        if row_index:
            # Read current row from sheet (Subject is Col I [8], Body is Col J [9])
            range_name = f"'{SHEET_TAB}'!I{row_index}:J{row_index}"
            res = service.spreadsheets().values().get(spreadsheetId=sid, range=range_name).execute()
            values = res.get('values', [[]])[0]
            if len(values) >= 2:
                sheet_subject = values[0].strip()
                sheet_body = values[1].strip()
                # Use sheet content if it's not empty and different from generated
                if sheet_subject and sheet_subject != draft['subject']:
                    draft['subject'] = sheet_subject
                if sheet_body and sheet_body != draft['body']:
                    draft['body'] = sheet_body
    except Exception as e:
        print(f"Warning: Could not sync with Google Sheet: {e}")
    # ---------------------------------

    draft['approved'] = True
    say(text=f"⏳ <@{user_id}> approved the draft for *{company_name}*. Sending email now...")
    
    try:
        success = send_email(draft)
        if success:
            say(text=f"✅ Email sent successfully to *{company_name}* ({draft['contact_email']})!")
            # Update Sheet Status to Sent
            if row_index:
                from datetime import datetime
                sent_at = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                update_row_status(row_index, 'Sent', sent_at=sent_at)
        else:
            say(text=f"❌ Failed to send email to *{company_name}*. Check logs.")
    except Exception as e:
        say(text=f"❌ Error sending email: {str(e)}")

@app.action("reject_draft")
def handle_reject(ack, body, say):
    ack()
    user_id = body["user"]["id"]
    action_value = body["actions"][0]["value"] # "reject|company_name"
    company_name = action_value.split("|")[1]
    say(text=f"❌ <@{user_id}> rejected the draft for *{company_name}*.")

if __name__ == "__main__":
    handler = SocketModeHandler(app, os.getenv("SLACK_APP_TOKEN"))
    print("⚡️ Jobify Slack Worker is running!")
    handler.start()
