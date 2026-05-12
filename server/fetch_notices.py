import requests
from bs4 import BeautifulSoup
import PyPDF2
import io
import json
import os
import google.generativeai as genai
from datetime import datetime

os.makedirs('data', exist_ok=True)
DATA_FILE = 'data/daily_notices.json'

def fetch_latest_notices_pdf():
    print("Fetching daily notices page...")
    base_url = "https://www.kingshigh.school.nz"
    page_url = f"{base_url}/whats-on/daily-notices/"
    
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
    }
    
    response = requests.get(page_url, headers=headers)
    response.raise_for_status()
    
    soup = BeautifulSoup(response.text, 'html.parser')
    
    # Find the most recent PDF document link
    pdf_div = soup.find('div', class_='document pdf')
    if not pdf_div:
        raise ValueError("Could not find any PDF document links on the notices page.")
        
    link_tag = pdf_div.find('a')
    pdf_path = link_tag['href']
    pdf_title = link_tag.text.strip()
    
    download_url = base_url + pdf_path
    
    print(f"Downloading latest notice PDF: {pdf_title}")
    pdf_response = requests.get(download_url, headers=headers)
    pdf_response.raise_for_status()
    
    return pdf_title, io.BytesIO(pdf_response.content)

def extract_text_from_pdf(pdf_stream):
    print("Extracting text from PDF...")
    reader = PyPDF2.PdfReader(pdf_stream)
    text = ""
    for page in reader.pages:
        text += page.extract_text() + "\n"
    return text

def organize_with_gemini(raw_text):
    print("Organizing text with Gemini AI...")
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        print("Warning: GEMINI_API_KEY not set in environment. Returning raw text.")
        return {"Uncategorized": [raw_text]}
        
    genai.configure(api_key=api_key)
    # Using gemini-1.5-flash since we strictly need fast text processing
    model = genai.GenerativeModel('gemini-1.5-flash')
    
    prompt = f"""
    You are an AI assistant organizing high school daily notices.
    Read the following messy PDF text of daily notices and categorize it neatly into a JSON object.
    
    Structure the JSON exactly like this, adding or modifying categories as appropriate (e.g., General, Sports, Arts, Seniors, Juniors, Meetings):
    {{
        "Sports": ["Notice 1", "Notice 2"],
        "General": ["Notice 3"],
        "Meetings": ["Notice 4"]
    }}
    
    Do not output markdown code blocks (like ```json), just output the raw JSON brackets.
    Ensure all text is clean and legible.

    --- Notices Text Below ---
    {raw_text}
    """
    
    response = model.generate_content(prompt)
    
    try:
        # Strip potential markdown formatting if model ignores instructions
        response_text = response.text.strip()
        if response_text.startswith("```json"):
            response_text = response_text[7:]
        if response_text.endswith("```"):
            response_text = response_text[:-3]
            
        organized_data = json.loads(response_text)
        return organized_data
    except Exception as e:
        print(f"Error parsing Gemini JSON response: {e}")
        print("Raw response:", response.text)
        return {"Raw": [raw_text]}

def main():
    try:
        title, pdf_stream = fetch_latest_notices_pdf()
        raw_text = extract_text_from_pdf(pdf_stream)
        organized_json = organize_with_gemini(raw_text)
        
        final_data = {
            "title": title,
            "updated_at": datetime.now().isoformat(),
            "notices": organized_json
        }
        
        with open(DATA_FILE, 'w', encoding='utf-8') as f:
            json.dump(final_data, f, indent=4)
            
        print(f"Successfully updated daily notices at {DATA_FILE}")
        
    except Exception as e:
        print(f"Failed to fetch daily notices: {e}")

if __name__ == "__main__":
    main()
