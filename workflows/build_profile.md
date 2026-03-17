# Workflow: Build Profile

SOP for initializing the agent's profile and writing style.

## Steps

1. **Setup API Key**:
   - Get a Gemini API key from [Google AI Studio](https://aistudio.google.com/).
   - Open `.env` and replace `your_gemini_api_key_here` with your actual key.

2. **Place Documents**: 
   - Add your CV (PDF) to the `cv/` folder (e.g., `Ubaid-Ur-Rehman-Resume.pdf`).
   - Add 3-5 sample emails you've written to the `emails/` folder as `.txt` files.

3. **Run CV Parser**:
   ```bash
   python tools/parse_cv.py
   ```
   This will generate `.tmp/profile.json` using Gemini Flash.

4. **Run Email Style Parser**:
   ```bash
   python tools/parse_email_style.py
   ```
   This will generate `.tmp/style.json` using Gemini Flash.

5. **Verify Artifacts**:
   - Check `.tmp/profile.json` for accuracy (skills, experience, etc.).
   - Check `.tmp/style.json` for style capture (tone, formality, etc.).
