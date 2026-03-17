import os
import json
import pandas as pd
import requests
from bs4 import BeautifulSoup
import google.generativeai as genai
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

def get_gemini_model():
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise ValueError("GEMINI_API_KEY not found in .env file.")
    genai.configure(api_key=api_key)
    return genai.GenerativeModel('gemini-2.5-flash')

def scrape_website(url):
    try:
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # Remove script and style elements
        for script in soup(["script", "style"]):
            script.extract()
            
        text = soup.get_text(separator=' ')
        # Clean up whitespace
        lines = (line.strip() for line in text.splitlines())
        chunks = (phrase.strip() for line in lines for phrase in line.split("  "))
        text = '\n'.join(chunk for chunk in chunks if chunk)
        
        return text[:10000] # Cap text to avoid token limits
    except Exception as e:
        return f"Error: {e}"

def analyze_company(website_text, model):
    prompt = f"""
    Analyze the following website content from a company and extract:
    1. what_they_do: What the company actually does in plain English.
    2. main_product: Their main product or service.
    3. tech_mentions: Any technologies, frameworks, or engineering practices mentioned.
    4. company_type: One of 'startup', 'scaleup', 'enterprise', 'agency', or 'product company'.

    Website content:
    {website_text}

    Return ONLY valid JSON.
    """
    response = model.generate_content(prompt)
    try:
        content = response.text.strip()
        if content.startswith("```json"):
            content = content[7:-3].strip()
        elif content.startswith("```"):
            content = content[3:-3].strip()
        return json.loads(content)
    except Exception as e:
        print(f"Error parsing Gemini response for company analysis: {e}")
        return {
            "what_they_do": "Verification failed",
            "main_product": "Verification failed",
            "tech_mentions": [],
            "company_type": "unknown"
        }

def analyze_patterns(companies_data, model):
    data_str = json.dumps(companies_data, indent=2)
    prompt = f"""
    From the following list of companies I have already applied to, extract application patterns into a JSON format:
    - preferred_industries: List of industries common among these companies.
    - preferred_company_size: General size preference (e.g., Small, Medium, Large, Mixed).
    - common_technologies: Technologies mentioned frequently or common across these companies.
    - contact_titles_targeted: The titles of people I have been contacting (e.g., HR Manager, CTO).
    - countries_applied: List of countries where these companies are located.
    - company_types_preferred: List of company types (startup, agency, etc.).
    - common_keywords: Keywords that appear frequently in their descriptions or my notes.
    - summary: A plain English summary of what types of companies I have been targeting, what they have in common, and what pattern to follow when selecting new companies.

    Companies Data:
    {data_str}

    Return ONLY valid JSON.
    """
    response = model.generate_content(prompt)
    try:
        content = response.text.strip()
        if content.startswith("```json"):
            content = content[7:-3].strip()
        elif content.startswith("```"):
            content = content[3:-3].strip()
        return json.loads(content)
    except Exception as e:
        print(f"Error parsing Gemini response for patterns analysis: {e}")
        return {}

def main():
    excel_file = "Netherlands IT companies updated.xlsx"
    if not os.path.exists(excel_file):
        print(f"Error: {excel_file} not found.")
        return

    print(f"Reading {excel_file}...")
    df = pd.read_excel(excel_file)
    
    # Identify companies to process (Sent) and exclude (Blank)
    # The user said 13 have "Sent" and 9 have blank.
    # We filter ONLY "Sent".
    mask_sent = df['Email Sent'].fillna('').str.strip().str.lower() == 'sent'
    sent_df = df[mask_sent]
    
    if len(sent_df) == 0:
        print("No 'Sent' companies found.")
        return

    print(f"Processing {len(sent_df)} companies...")
    
    # Map headers
    mapping = {
        "Company Name": "company_name",
        "Website": "website",
        "Company Linkedin Url": "linkedin",
        "First Name": "first_name",
        "Last Name": "last_name",
        "Title": "contact_title",
        "Email": "contact_email",
        "# Employees": "employees",
        "Company Country": "country",
        "Company City": "city",
        "Keywords": "keywords_raw",
        "Technologies": "tech_raw"
    }
    
    # Initialize containers
    processed_companies = []
    failed_urls = {}
    model = get_gemini_model()
    
    for _, row in sent_df.iterrows():
        name = row['Company Name']
        url = row['Website']
        print(f"Processing {name} ({url})...")
        
        company_obj = {
            "company_name": name,
            "website": url,
            "linkedin": row.get('Company Linkedin Url', ''),
            "contact_name": f"{row.get('First Name', '')} {row.get('Last Name', '')}".strip(),
            "contact_title": row.get('Title', ''),
            "contact_email": row.get('Email', ''),
            "employees": int(row.get('# Employees', 0)) if pd.notnull(row.get('# Employees')) else 0,
            "country": row.get('Company Country', ''),
            "city": row.get('Company City', ''),
            "keywords": [k.strip() for k in str(row.get('Keywords', '')).split(',')] if pd.notnull(row.get('Keywords')) else [],
            "technologies": [t.strip() for t in str(row.get('Technologies', '')).split(',')] if pd.notnull(row.get('Technologies')) else [],
        }
        
        # Scrape and analyze
        website_text = scrape_website(url)
        if website_text.startswith("Error:"):
            print(f"  Failed: {website_text}")
            failed_urls[url] = website_text
            company_obj.update({
                "what_they_do": "Website unreachable",
                "main_product": "N/A",
                "tech_mentions": [],
                "company_type": "unknown"
            })
        else:
            analysis = analyze_company(website_text, model)
            company_obj.update(analysis)
            print(f"  Analysis complete: {analysis.get('company_type')}")
            
        processed_companies.append(company_obj)

    # Save outputs
    os.makedirs(".tmp", exist_ok=True)
    
    with open(".tmp/processed_companies.json", "w") as f:
        json.dump(processed_companies, f, indent=2)
        
    with open(".tmp/failed_urls.json", "w") as f:
        json.dump(failed_urls, f, indent=2)

    # Step 4: Analyze patterns
    print("Generating application patterns...")
    patterns = analyze_patterns(processed_companies, model)
    with open(".tmp/application_patterns.json", "w") as f:
        json.dump(patterns, f, indent=2)

    # Step 5: Summary
    print("\n=== TRAINING COMPLETE ===\n")
    print(f"Companies processed: {len(processed_companies)}")
    print(f"Websites visited successfully: {len(processed_companies) - len(failed_urls)}")
    print(f"Websites failed: {len(failed_urls)} (see .tmp/failed_urls.json)")
    
    print(f"\nIndustries found: {', '.join(patterns.get('preferred_industries', []))}")
    print(f"Company types: {', '.join(patterns.get('company_types_preferred', []))}")
    print(f"Common tech: {', '.join(patterns.get('common_technologies', []))}")
    print(f"Contact titles: {', '.join(patterns.get('contact_titles_targeted', []))}")
    print(f"Countries: {', '.join(patterns.get('countries_applied', []))}")
    
    print(f"\nProfile saved to: .tmp/application_patterns.json")
    print(f"Companies saved to: .tmp/processed_companies.json")
    print("\nReady for Phase 3.")

if __name__ == "__main__":
    main()
