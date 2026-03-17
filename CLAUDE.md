## File Structure

**What goes where:**
- **Deliverables**: Sent emails logged to companies tracker sheet (Google Sheet or CSV)
- **Intermediates**: CV profile, company research, email drafts — all in .tmp, all regenerable

**Directory layout:**
.tmp/                        # Temporary files — regenerated as needed
  profile.json               # Your parsed CV + writing style (built once)
  processed_companies.json   # Companies already applied to
  research/                  # Per-company research results
  drafts/                    # Email drafts pending your approval

tools/                       # Python scripts — deterministic execution only
workflows/                   # Markdown SOPs — one per major task
.env                         # ALL secrets here, nowhere else
cv/                          # Your CV file lives here (PDF or DOCX)
emails/                      # 3-5 sample emails you've written — agent learns your style

**Core principle:** The agent never sends anything without explicit human
approval via Telegram. Approval is a hard gate, not a suggestion.
```

---

## Starter prompt to give your agent in Antigravity
```
Read CLAUDE.md fully before doing anything.

I am building a job application agent called "jobify" using the WAT 
framework. Here is what I need you to build, in this exact order:

PHASE 1 — Build the profile tools first:
1. tools/parse_cv.py — reads cv/ folder, extracts my skills, experience,
   seniority level, tech stack, and target role types into .tmp/profile.json
2. tools/parse_email_style.py — reads 3-5 sample emails from emails/ folder,
   extracts my tone, formality, typical length, signature into .tmp/style.json
3. workflows/build_profile.md — SOP for running both tools above

Run both tools against my actual files and show me the extracted 
profile.json and style.json before moving to Phase 2. 
I need to verify they are accurate before the agent uses them to write emails.
Do not proceed to Phase 2 until I confirm.

PHASE 2 — I will give you the companies list and brief you on next steps.

Constraints that apply to the entire project:
- Never send any email without my explicit Telegram approval
- Never modify processed_companies.json except to add new entries
- Never skip the research step — every email must reference something 
  specific about that company
- If a company contact email cannot be found, flag it and move on — 
  do not guess an email address