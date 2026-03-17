import os
import json
import google.generativeai as genai
from pypdf import PdfReader
from dotenv import load_dotenv

load_dotenv()

def parse_cv(cv_dir, output_path):
    """
    Reads CV from cv/ folder and extracts skills, experience, etc.
    into .tmp/profile.json
    """
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        print("Error: GEMINI_API_KEY not found in .env file.")
        return

    genai.configure(api_key=api_key)
    model = genai.GenerativeModel('gemini-2.5-flash')

    # Find the first PDF in the CV directory
    cv_files = [f for f in os.listdir(cv_dir) if f.endswith('.pdf')]
    if not cv_files:
        print(f"No PDF files found in {cv_dir}")
        return

    cv_path = os.path.join(cv_dir, cv_files[0])
    print(f"Parsing {cv_path}...")

    reader = PdfReader(cv_path)
    text = ""
    for page in reader.pages:
        text += page.extract_text()

    prompt = f"""
    You are an expert recruiter. Extract the following information from the resume text provided below into a JSON format:
    - skills: List of technical and soft skills
    - experience: Summary of work history
    - seniority: Seniority level (e.g., Junior, Mid, Senior, Lead)
    - tech_stack: Key technologies used
    - target_roles: Types of roles this person is qualified for

    Resume Text:
    {text}

    Return ONLY valid JSON.
    """

    response = model.generate_content(prompt)
    
    try:
        # Extract JSON from potential markdown formatting
        content = response.text.strip()
        if content.startswith("```json"):
            content = content[7:-3].strip()
        elif content.startswith("```"):
            content = content[3:-3].strip()
            
        profile = json.loads(content)
        
        with open(output_path, 'w') as f:
            json.dump(profile, f, indent=2)
        print(f"Profile saved to {output_path}")
    except Exception as e:
        print(f"Error parsing Gemini response: {e}")
        print("Raw response:", response.text)

if __name__ == "__main__":
    parse_cv("cv/", ".tmp/profile.json")
