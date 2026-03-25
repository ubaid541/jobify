"""
update_sheet.py — All Google Sheets read/write operations for jobify.
Functions:
  append_draft_row(company, draft)    -> adds row with Status=Draft, Approved=Pending, color=yellow
  read_approvals()                    -> rows where Approved is Yes/No and Status is Draft
  update_row_status(row_index, status, sent_at=None) -> updates Status + color
  get_todays_sent_count()             -> count of Sent rows with today's date
  sheet_exists()                      -> verifies sheet is accessible
"""

import os
import json
from datetime import date, datetime
from dotenv import load_dotenv
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build

load_dotenv()

SCOPES = [
    'https://www.googleapis.com/auth/spreadsheets',
    'https://www.googleapis.com/auth/drive'
]
SHEET_TAB = 'Applications'

# Column index map (0-based, A=0)
COL = {
    '#': 0, 'company_name': 1, 'contact_name': 2, 'contact_title': 3,
    'contact_email': 4, 'website': 5, 'linkedin': 6, 'fit_score': 7,
    'subject': 8, 'email_body': 9, 'status': 10, 'approved': 11, 'sent_at': 12
}
TOTAL_COLS = 13

# Row colors
COLOR_YELLOW = {"red": 1.0, "green": 0.95, "blue": 0.6}   # Pending
COLOR_GREEN  = {"red": 0.7, "green": 0.93, "blue": 0.7}   # Sent
COLOR_RED    = {"red": 0.97, "green": 0.7, "blue": 0.7}   # Failed
COLOR_GRAY   = {"red": 0.85, "green": 0.85, "blue": 0.85}  # Skipped

STATUS_COLORS = {
    'Draft':   COLOR_YELLOW,
    'Sent':    COLOR_GREEN,
    'Failed':  COLOR_RED,
    'Skipped': COLOR_GRAY,
}


def _get_creds():
    creds = None
    if os.path.exists('token.json'):
        creds = Credentials.from_authorized_user_file('token.json', SCOPES)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file('credentials.json', SCOPES)
            creds = flow.run_local_server(port=0)
        with open('token.json', 'w') as f:
            f.write(creds.to_json())
    return creds


def _get_service():
    return build('sheets', 'v4', credentials=_get_creds())


def _get_sheet_id():
    sid = os.getenv('GOOGLE_SHEET_ID')
    if not sid:
        raise ValueError("GOOGLE_SHEET_ID not set in .env")
    return sid


def _get_tab_id(service, spreadsheet_id, tab_name):
    """Gets the integer sheetId for a specific tab by name."""
    sheet_metadata = service.spreadsheets().get(spreadsheetId=spreadsheet_id).execute()
    for sheet in sheet_metadata.get('sheets', []):
        if sheet.get('properties', {}).get('title') == tab_name:
            return sheet.get('properties', {}).get('sheetId', 0)
    return 0

def _color_row(service, sheet_id, row_index, color):
    """row_index is 0-based sheet row (header=0, first data row=1)."""
    tab_id = _get_tab_id(service, sheet_id, SHEET_TAB)
    requests = [{
        "repeatCell": {
            "range": {
                "sheetId": tab_id,
                "startRowIndex": row_index,
                "endRowIndex": row_index + 1,
                "startColumnIndex": 0,
                "endColumnIndex": TOTAL_COLS
            },
            "cell": {"userEnteredFormat": {"backgroundColor": color}},
            "fields": "userEnteredFormat.backgroundColor"
        }
    }]
    service.spreadsheets().batchUpdate(
        spreadsheetId=sheet_id,
        body={"requests": requests}
    ).execute()


def sheet_exists():
    """Returns True if the sheet is accessible, False otherwise."""
    try:
        service = _get_service()
        sheet_id = _get_sheet_id()
        service.spreadsheets().get(spreadsheetId=sheet_id).execute()
        return True
    except Exception as e:
        print(f"Sheet not accessible: {e}")
        return False


def append_draft_row(company: dict, draft: dict):
    """
    Appends a new row with Status=Draft, Approved=Pending, color=yellow.
    Returns the 1-based row index of the appended row.
    """
    service = _get_service()
    sheet_id = _get_sheet_id()

    # Get current row count to set # column
    result = service.spreadsheets().values().get(
        spreadsheetId=sheet_id,
        range=f'{SHEET_TAB}!A:A'
    ).execute()
    existing = result.get('values', [])
    row_num = len(existing)  # Next row number (header = row 1, so data starts at 2)

    row = [''] * TOTAL_COLS
    row[COL['#']]             = row_num
    row[COL['company_name']]  = company.get('company_name', '')
    row[COL['contact_name']]  = draft.get('contact_name', '')
    row[COL['contact_title']] = draft.get('contact_title', '')
    row[COL['contact_email']] = draft.get('contact_email', '')
    row[COL['website']]       = company.get('website', '')
    row[COL['linkedin']]      = company.get('linkedin', '')
    row[COL['fit_score']]     = draft.get('fit_score', 0)
    row[COL['subject']]       = draft.get('subject', '')
    row[COL['email_body']]    = draft.get('body', '')
    row[COL['status']]        = 'Draft'
    row[COL['approved']]      = 'Pending'
    row[COL['sent_at']]       = ''

    service.spreadsheets().values().append(
        spreadsheetId=sheet_id,
        range=f'{SHEET_TAB}!A:M',
        valueInputOption='RAW',
        insertDataOption='INSERT_ROWS',
        body={'values': [row]}
    ).execute()

    # Color yellow
    _color_row(service, sheet_id, row_num, COLOR_YELLOW)
    print(f"  -> Sheet row {row_num + 1} added for {company.get('company_name')}")
    return row_num + 1  # 1-based


def read_approvals():
    """
    Returns list of dicts for rows where Approved is 'Yes' or 'No' and Status is 'Draft'.
    Each dict includes row_index (1-based), all sheet fields, and company slugs.
    """
    service = _get_service()
    sheet_id = _get_sheet_id()

    result = service.spreadsheets().values().get(
        spreadsheetId=sheet_id,
        range=f'{SHEET_TAB}!A:M'
    ).execute()
    rows = result.get('values', [])
    if len(rows) < 2:
        return []

    pending = []
    for i, row in enumerate(rows[1:], start=2):  # skip header, i = 1-based row index
        # Pad short rows
        while len(row) < TOTAL_COLS:
            row.append('')
        approved = row[COL['approved']].strip().lower()
        status   = row[COL['status']].strip()
        if approved in ('yes', 'approved', 'y', 'true', 'no', 'skipped', 'n', 'false') and status == 'Draft':
            pending.append({
                'row_index':     i,
                'company_name':  row[COL['company_name']],
                'contact_name':  row[COL['contact_name']],
                'contact_email': row[COL['contact_email']],
                'approved':      approved,
                'status':        status,
                'fit_score':     row[COL['fit_score']],
            })
    return pending


def update_row_status(row_index: int, status: str, sent_at: str = None):
    """
    Updates Status cell and optionally Sent At.
    row_index is 1-based (matching Google Sheets row numbers).
    """
    service = _get_service()
    sheet_id = _get_sheet_id()

    updates = []
    updates.append({
        'range': f'{SHEET_TAB}!K{row_index}',
        'values': [[status]]
    })
    if sent_at:
        updates.append({
            'range': f'{SHEET_TAB}!M{row_index}',
            'values': [[sent_at]]
        })

    service.spreadsheets().values().batchUpdate(
        spreadsheetId=sheet_id,
        body={'valueInputOption': 'RAW', 'data': updates}
    ).execute()


def find_failed_drafts():
    """
    Returns list of rows where Status='Draft' and Email Body contains '[Email generation failed'.
    """
    service = _get_service()
    sheet_id = _get_sheet_id()

    result = service.spreadsheets().values().get(
        spreadsheetId=sheet_id,
        range=f'{SHEET_TAB}!A:M'
    ).execute()
    rows = result.get('values', [])
    if len(rows) < 2:
        return []

    failed = []
    for i, row in enumerate(rows[1:], start=2):
        while len(row) < TOTAL_COLS:
            row.append('')
        
        status = row[COL['status']].strip()
        body   = row[COL['email_body']].strip()
        
        if status == 'Draft' and '[Email generation failed' in body:
            failed.append({
                'row_index':     i,
                'company_name':  row[COL['company_name']],
                'contact_name':  row[COL['contact_name']],
                'contact_title': row[COL['contact_title']],
                'contact_email': row[COL['contact_email']],
                'website':       row[COL['website']],
                'linkedin':      row[COL['linkedin']],
                'fit_score':     row[COL['fit_score']],
                'approved':      row[COL['approved']].strip().lower()
            })
    return failed


def update_row_draft(row_index: int, subject: str, body: str):
    """
    Overwrites the Subject and Email Body cells.
    row_index is 1-based.
    """
    service = _get_service()
    sheet_id = _get_sheet_id()

    updates = [
        {
            'range': f'{SHEET_TAB}!I{row_index}',  # Subject (Col 8, I)
            'values': [[subject]]
        },
        {
            'range': f'{SHEET_TAB}!J{row_index}',  # Email Body (Col 9, J)
            'values': [[body]]
        }
    ]

    service.spreadsheets().values().batchUpdate(
        spreadsheetId=sheet_id,
        body={'valueInputOption': 'RAW', 'data': updates}
    ).execute()


def get_todays_sent_count():
    """Counts rows where Status=Sent and Sent At matches today's date."""
    service = _get_service()
    sheet_id = _get_sheet_id()

    result = service.spreadsheets().values().get(
        spreadsheetId=sheet_id,
        range=f'{SHEET_TAB}!K:M'
    ).execute()
    rows = result.get('values', [])
    today = date.today().strftime('%Y-%m-%d')
    count = 0
    for row in rows[1:]:  # skip header
        if len(row) >= 1 and row[0].strip() == 'Sent':
            sent_at = row[2].strip() if len(row) > 2 else ''
            if sent_at.startswith(today):
                count += 1
    return count


def get_all_rows():
    """Returns all data rows as list of dicts (for watcher status printing)."""
    service = _get_service()
    sheet_id = _get_sheet_id()
    result = service.spreadsheets().values().get(
        spreadsheetId=sheet_id,
        range=f'{SHEET_TAB}!A:M'
    ).execute()
    rows = result.get('values', [])
    if len(rows) < 2:
        return []
    all_rows = []
    for i, row in enumerate(rows[1:], start=2):
        while len(row) < TOTAL_COLS:
            row.append('')
        all_rows.append({
            'row_index':     i,
            'company_name':  row[COL['company_name']],
            'contact_email': row[COL['contact_email']],
            'approved':      row[COL['approved']].strip(),
            'status':        row[COL['status']].strip(),
        })
    return all_rows
