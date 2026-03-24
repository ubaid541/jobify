"""
setup_google_sheets.py — One-time interactive setup for Google Sheets integration.

RESUME-SAFE: Each step is skipped if already complete.
  - If token.json exists and is valid -> skips OAuth browser flow.
  - If GOOGLE_SHEET_ID already in .env -> skips sheet creation, goes straight to verify.
"""

import os
import sys
import json

# ── helpers ─────────────────────────────────────────────────────────────────

SCOPES = [
    'https://www.googleapis.com/auth/spreadsheets',
    'https://www.googleapis.com/auth/drive'
]

def _get_creds():
    """Returns valid credentials, reusing token.json if possible."""
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow
    from google.auth.transport.requests import Request

    creds = None

    # Reuse existing token if present
    if os.path.exists('token.json'):
        try:
            creds = Credentials.from_authorized_user_file('token.json', SCOPES)
        except Exception:
            creds = None

    # Refresh if expired
    if creds and creds.expired and creds.refresh_token:
        try:
            creds.refresh(Request())
            with open('token.json', 'w') as f:
                f.write(creds.to_json())
            print("[OK] Token refreshed automatically.")
            return creds
        except Exception as e:
            print(f"  Token refresh failed ({e}), re-authenticating...")
            creds = None

    # Full OAuth flow only if no valid token exists
    if not creds or not creds.valid:
        if not os.path.exists('credentials.json'):
            print("[!!] credentials.json not found. Place it in the project root and try again.")
            sys.exit(1)
        print("\nOpening browser for Google sign-in...")
        print("(A browser window will open — sign in and grant access.)\n")
        flow = InstalledAppFlow.from_client_secrets_file('credentials.json', SCOPES)
        creds = flow.run_local_server(port=0)
        with open('token.json', 'w') as f:
            f.write(creds.to_json())
        print("[OK] Authentication successful. token.json saved.")
    else:
        print("[OK] Existing token.json is valid — skipping OAuth browser flow.")

    return creds


def _get_sheets_service(creds):
    from googleapiclient.discovery import build
    return build('sheets', 'v4', credentials=creds)


def _get_sheet_id_from_env() -> str:
    """Read GOOGLE_SHEET_ID from .env, return empty string if missing/blank."""
    from dotenv import dotenv_values
    env = dotenv_values('.env')
    val = env.get('GOOGLE_SHEET_ID', '').strip()
    # Treat comment-only values as empty
    if val.startswith('#') or not val:
        return ''
    return val


def _write_sheet_id_to_env(sheet_id: str):
    """Replace the GOOGLE_SHEET_ID line in .env."""
    env_path = '.env'
    if not os.path.exists(env_path):
        with open(env_path, 'w') as f:
            f.write(f'GOOGLE_SHEET_ID={sheet_id}\n')
        return
    with open(env_path, 'r') as f:
        lines = f.readlines()
    updated = False
    new_lines = []
    for line in lines:
        if line.strip().startswith('GOOGLE_SHEET_ID'):
            new_lines.append(f'GOOGLE_SHEET_ID={sheet_id}\n')
            updated = True
        else:
            new_lines.append(line)
    if not updated:
        new_lines.append(f'\nGOOGLE_SHEET_ID={sheet_id}\n')
    with open(env_path, 'w') as f:
        f.writelines(new_lines)
    print(f"[OK] GOOGLE_SHEET_ID written to .env automatically.")


def create_sheet(creds) -> str:
    """Creates the Jobify Application Tracker sheet and returns its ID."""
    service = _get_sheets_service(creds)

    # Create spreadsheet
    body = {
        'properties': {'title': 'Jobify — Application Tracker'},
        'sheets': [{'properties': {'title': 'Applications'}}]
    }
    ss = service.spreadsheets().create(body=body, fields='spreadsheetId,sheets').execute()
    spreadsheet_id = ss['spreadsheetId']
    # Get the actual sheetId (NOT assumed to be 0)
    real_sheet_id = ss['sheets'][0]['properties']['sheetId']
    print(f"[OK] Sheet created: https://docs.google.com/spreadsheets/d/{spreadsheet_id}")

    # Write headers
    headers = [['#', 'Company Name', 'Contact Name', 'Contact Title', 'Contact Email',
                 'Website', 'LinkedIn', 'Fit Score', 'Subject', 'Email Body',
                 'Status', 'Approved', 'Sent At']]
    service.spreadsheets().values().update(
        spreadsheetId=spreadsheet_id,
        range='Applications!A1:M1',
        valueInputOption='RAW',
        body={'values': headers}
    ).execute()

    # Format sheet — use real_sheet_id in every request
    requests = [
        # Freeze header row
        {
            "updateSheetProperties": {
                "properties": {"sheetId": real_sheet_id, "gridProperties": {"frozenRowCount": 1}},
                "fields": "gridProperties.frozenRowCount"
            }
        },
        # Bold header + dark background + white text
        {
            "repeatCell": {
                "range": {"sheetId": real_sheet_id, "startRowIndex": 0, "endRowIndex": 1},
                "cell": {
                    "userEnteredFormat": {
                        "textFormat": {
                            "bold": True,
                            "foregroundColor": {"red": 1.0, "green": 1.0, "blue": 1.0}
                        },
                        "backgroundColor": {"red": 0.18, "green": 0.18, "blue": 0.18}
                    }
                },
                "fields": "userEnteredFormat(textFormat,backgroundColor)"
            }
        },
        # Email Body column (J = index 9) -> 500px wide
        {
            "updateDimensionProperties": {
                "range": {"sheetId": real_sheet_id, "dimension": "COLUMNS", "startIndex": 9, "endIndex": 10},
                "properties": {"pixelSize": 500},
                "fields": "pixelSize"
            }
        }
    ]

    service.spreadsheets().batchUpdate(
        spreadsheetId=spreadsheet_id,
        body={"requests": requests}
    ).execute()
    print("[OK] Sheet formatted: headers, dropdown, column widths, freeze row.")
    return spreadsheet_id


def verify_sheet(creds, sheet_id: str):
    """Writes and reads a test cell to confirm access."""
    service = _get_sheets_service(creds)
    try:
        service.spreadsheets().values().update(
            spreadsheetId=sheet_id,
            range='Applications!A2',
            valueInputOption='RAW',
            body={'values': [['VERIFY_OK']]}
        ).execute()
        result = service.spreadsheets().values().get(
            spreadsheetId=sheet_id,
            range='Applications!A2'
        ).execute()
        assert result.get('values') == [['VERIFY_OK']], "Read-back mismatch."
        service.spreadsheets().values().clear(
            spreadsheetId=sheet_id,
            range='Applications!A2'
        ).execute()
        print("[OK] Sheet read/write verified successfully.")
    except Exception as e:
        print(f"[!!] Verification failed: {e}")
        sys.exit(1)


# ── main ────────────────────────────────────────────────────────────────────

def main():
    print("""
=== Google Sheets Setup ===

If you haven't created credentials yet:

  Step 1: Go to https://console.cloud.google.com
  Step 2: Create or select a project called "Jobify"
  Step 3: Enable APIs: Google Sheets API + Google Drive API
  Step 4: Credentials -> Create -> OAuth 2.0 Client ID -> Desktop App
  Step 5: Download JSON -> rename to credentials.json -> put in project root

Press Enter when credentials.json is in place (or just press Enter to reuse existing)...
""")
    input()

    # Verify credentials.json exists
    if not os.path.exists('credentials.json'):
        print("[!!] credentials.json not found. Please add it to the project root.")
        sys.exit(1)
    print("[OK] credentials.json found.")

    # Step 1: Get/reuse credentials
    creds = _get_creds()

    # Step 2: Create sheet (skip if GOOGLE_SHEET_ID already set)
    existing_id = _get_sheet_id_from_env()
    if existing_id:
        print(f"\n[OK] GOOGLE_SHEET_ID already in .env ({existing_id[:20]}...) — skipping sheet creation.")
        sheet_id = existing_id
    else:
        print("\nCreating 'Jobify — Application Tracker' sheet...")
        sheet_id = create_sheet(creds)
        _write_sheet_id_to_env(sheet_id)

    # Step 3: Verify
    print("\nVerifying sheet access...")
    verify_sheet(creds, sheet_id)

    print(f"""
==============================================
[OK] Google Sheets connected successfully!

Sheet URL:
https://docs.google.com/spreadsheets/d/{sheet_id}

GOOGLE_SHEET_ID has been written to your .env automatically.

You are ready to run Phase 3:
  python run_phase3.py "Estonia IT Companies.xlsx"
==============================================
""")


if __name__ == "__main__":
    main()
