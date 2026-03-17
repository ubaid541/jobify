import os
import json
import google.generativeai as genai
from dotenv import load_dotenv

load_dotenv()

def parse_email_style(emails_dir, output_path):
    """
    Reads sample emails and extracts tone, formality, length, signature.
    into .tmp/style.json
    """
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        print("Error: GEMINI_API_KEY not found in .env file.")
        return

    genai.configure(api_key=api_key)
    model = genai.GenerativeModel('gemini-2.5-flash')

    email_texts = []
    for filename in os.listdir(emails_dir):
        if filename.endswith(".txt"):
            with open(os.path.join(emails_dir, filename), 'r', encoding='utf-8') as f:
                email_texts.append(f.read())

    if not email_texts:
        print(f"No text files found in {emails_dir}")
        return

    all_emails = "\n\n---\n\n".join(email_texts)

    prompt = f"""
    Analyze these sample emails and extract the writing style into a JSON format:
    - tone: Overall tone (e.g., professional, friendly, direct)
    - formality: Formality level (e.g., Casual, Semi-Formal, Formal)
    - typical_length: Average length of emails (short, medium, long)
    - signature: Typical professional signature used
    - unique_traits: Any specific phrases or stylistic choices that are consistent

    Sample Emails:
    {all_emails}

    Return ONLY valid JSON.
    """

    response = model.generate_content(prompt)
    
    try:
        content = response.text.strip()
        if content.startswith("```json"):
            content = content[7:-3].strip()
        elif content.startswith("```"):
            content = content[3:-3].strip()
            
        style = json.loads(content)
        
        with open(output_path, 'w') as f:
            json.dump(style, f, indent=2)
        print(f"Style saved to {output_path}")
    except Exception as e:
        print(f"Error parsing Gemini response: {e}")
        print("Raw response:", response.text)

if __name__ == "__main__":
    parse_email_style("emails/", ".tmp/style.json")
