# Workflow: Phase 3 — Apply to New Companies

## Purpose
End-to-end job application pipeline: ingest → research → generate → approve → send.

## Prerequisites
Before running Phase 3, ensure:
1. **Phase 1 complete**: `.tmp/profile.json` and `.tmp/style.json` exist.
2. **Phase 2 complete**: `.tmp/application_patterns.json` and `.tmp/processed_companies.json` exist.
3. **Google Sheets setup**: `credentials.json` in project root, `GOOGLE_SHEET_ID` in `.env`.
4. **Gmail credentials**: `SENDING_GMAIL` and `SENDING_GMAIL_APP_PASSWORD` in `.env`.
5. **CV file**: PDF placed in `cv/` folder, path set in `CV_PATH` `.env`.

## One-Time Setup (First Run Only)
```bash
python tools/setup_google_sheets.py
```
Follow the terminal instructions to create credentials and the Google Sheet.

## Running a Batch
```bash
python run_phase3.py "https://docs.google.com/spreadsheets/d/your-sheet-id-here"
```
This runs the full sequence:
1. **Ingest** — Reads the new Apollo export directly from the provided Google Sheet URL. Skips companies already in `processed_companies.json` (already applied) and any row with a missing contact email. Scores the rest against your history using `application_patterns.json`, keeps the top 5 scoring ≥6/10.
2. **Research** — Visits each company's website (from sheet URL, never searched). Extracts what they do, frontend tech, and a specific hook for your opening line.
3. **Generate** — Writes personalized cold email using your `style.json` and research brief. Saves to `.tmp/drafts/<slug>.json`.
4. **Sheet Update** — Appends each draft to your Google Sheet with Status=Draft, Approved=Pending.
5. **Watch** — Polls sheet every 2 minutes. Sends approved emails automatically with 60s gap.

## Approving Applications
Open your Google Sheet, change `Approved` column from `Pending` to `Yes` or `No`:
- **Yes** → email is sent with CV attached
- **No** → row marked Skipped, gray
- **Leave Pending** → watcher keeps waiting (up to 4 hours)

## Daily Limit
Maximum 5 emails per day (configurable via `MAX_EMAILS_PER_DAY` in `.env`). Watcher exits cleanly when limit is reached.

## Resuming Interrupted Runs
If the watcher timed out or you stopped it:
```bash
python approve.py
```
Shows remaining daily capacity and processes any pending approvals.

## Dry Run (Testing)
```bash
python run_phase3.py any_file.xlsx --dry-run
```
No API calls — tests the full flow with mock data.

## Tool Reference
| Tool | Purpose |
|------|---------|
| `tools/setup_google_sheets.py` | One-time OAuth setup + sheet creation |
| `tools/update_sheet.py` | All Sheet read/write operations (never called directly) |
| `tools/ingest_companies.py` | Filter + score new companies |
| `tools/research_company.py` | Website visit + hook extraction |
| `tools/generate_email.py` | Personalized email generation |
| `tools/send_email.py` | Gmail send with CV attachment |
| `tools/watch_approvals.py` | Automated approval watcher |
| `approve.py` | Manual resume for interrupted batches |
| `run_phase3.py` | Master orchestrator |

## Outputs
| File | Description |
|------|-------------|
| `.tmp/current_batch.json` | Current batch of scored companies |
| `.tmp/research/<slug>.json` | Per-company research brief |
| `.tmp/drafts/<slug>.json` | Per-company email draft |
| `.tmp/processed_companies.json` | All companies sent to (updated after each send) |
| `.tmp/email_log.json` | Full log of every sent email |
| `.tmp/failed_urls.json` | Websites that couldn't be reached |

## Key Rules
- **Never send without approval** — `send_email.py` raises `ValueError` if `approved != True`
- **Hard excludes** — blank `Email Sent` rows from any Excel sheet are permanently excluded
- **No duplicate sends** — agent checks `processed_companies.json` before every send
- **Never modify processed_companies.json by hand** — agent appends only after confirmed send

## Relationship to Phase 2
`processed_companies.json` is the shared state between Phase 2 (historical analysis) and Phase 3 (active sending). Phase 3 only appends new entries — it never modifies or overwrites Phase 2 data.
