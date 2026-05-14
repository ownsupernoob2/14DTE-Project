import os
import json
import re
import requests
from bs4 import BeautifulSoup
import PyPDF2
from io import BytesIO
from google import genai

DATA_DIR = os.path.join(os.path.dirname(__file__), 'data')
OUT_FILE = os.path.join(DATA_DIR, 'daily_notices.json')
NOTICES_URL = "https://www.kingshigh.school.nz/whats-on/daily-notices/"

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8',
    'Accept-Language': 'en-US,en;q=0.9'
}

def fetch_latest_pdf_url():
    try:
        req = requests.get(NOTICES_URL, headers=HEADERS, timeout=10)
        req.raise_for_status()
        soup = BeautifulSoup(req.text, 'html.parser')
        
        # Find the first document pdf link
        pdf_div = soup.find('div', class_='document pdf')
        if not pdf_div:
            return None
        
        a_tag = pdf_div.find('a')
        if a_tag and 'href' in a_tag.attrs:
            return "https://www.kingshigh.school.nz" + a_tag['href']
    except Exception as e:
        print(f"Error fetching PDF URL: {e}")
        return None
    return None

def download_and_extract_text(pdf_url):
    try:
        req = requests.get(pdf_url, headers=HEADERS, timeout=15)
        req.raise_for_status()
        
        # Parse PDF
        pdf_file = BytesIO(req.content)
        reader = PyPDF2.PdfReader(pdf_file)
        
        text = ""
        for page in reader.pages:
            text += page.extract_text() + "\n"
            
        return text
    except Exception as e:
        print(f"Error downloading or extracting PDF: {e}")
        return None

def clean_messy_text(raw_text):
    # Fallback to handle messy text neatly
    lines = raw_text.split('\n')
    cleaned_lines = []
    
    for line in lines:
        line = line.strip()
        # Remove multiple spaces
        line = re.sub(r'\s{2,}', ' ', line)
        if line and len(line) > 2:  # Skip very short fragments
            cleaned_lines.append(line)
            
    notices = []
    current_category = "General"
    current_notice = []
    
    for line in cleaned_lines:
        # Ignore things that look like top-level general headers
        upper_line = line.upper()
        if "DAILY NOTICE" in upper_line:
            continue
            
        # Check for Category - Notice text
        # usually CAPITAL LETTERS - Text
        match = re.match(r'^([A-Z0-9\s/&,]+?)\s*[-–—]\s*(.+)$', line)
        if match:
            potential_category = match.group(1).strip()
            day_words = {'TODAY', 'MONDAY', 'TUESDAY', 'WEDNESDAY', 'THURSDAY', 'FRIDAY', 'SATURDAY', 'SUNDAY', 'EVERYDAY', 'TOMORROW'}
            
            if potential_category.upper() in day_words:
                # Treat as part of the current notice
                current_notice.append(f"{potential_category} - {match.group(2).strip()}")
            else:
                # Save the current notice before starting a new one
                if current_notice:
                    notices.append({
                        "category": current_category,
                        "notice": " ".join(current_notice)
                    })
                
                current_category = potential_category
                current_notice = [match.group(2).strip()]
        else:
            # If it looks like a generic standalone date string at the top of the file, let's ignore it
            # e.g., "Monday 12 May 2026"
            if len(line) < 40 and not current_notice and re.match(r'^(mon|tue|wed|thu|fri|sat|sun)\w*\s+\d+', line, re.I):
                continue
                
            current_notice.append(line)
            
    # Save the last accumulated notice
    if current_notice:
        notices.append({
            "category": current_category,
            "notice": " ".join(current_notice)
        })
            
    # If no notices matched, just wrap the whole thing or chunks
    if not notices and cleaned_lines:
        notices = [{"category": "General", "notice": " ".join(cleaned_lines)}]
        
    return notices

def process_with_gemini(text):
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        return None
        
    try:
        client = genai.Client(api_key=api_key)
        
        prompt = """
        Extract the following daily school notices into a neat JSON array.
        Each object should have "category" and "notice".
        Text:
        """ + text
        
        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=prompt,
        )
        response_text = response.text
        
        # Extract JSON from markdown if exists
        json_match = re.search(r'```(?:json)?\s*(.*?)\s*```', response_text, re.DOTALL)
        if json_match:
            response_text = json_match.group(1)
            
        notices = json.loads(response_text)
        return notices
    except Exception as e:
        print(f"Gemini API error: {e}")
        return None

def main():
    os.makedirs(DATA_DIR, exist_ok=True)
    
    print("Fetching latest notices PDF...")
    pdf_url = fetch_latest_pdf_url()
    
    text = ""
    if pdf_url:
        print(f"Found PDF URL: {pdf_url}")
        text = download_and_extract_text(pdf_url)
    
    if not text:
        # Check if local daily-notices.html exists (for dev/testing)
        local_html = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'daily-notices.html')
        if os.path.exists(local_html) and pdf_url is None:
            with open(local_html, 'r', encoding='utf-8') as f:
                soup = BeautifulSoup(f.read(), 'html.parser')
                a_tag = soup.find('div', class_='document pdf').find('a')
                if a_tag:
                    test_url = "https://www.kingshigh.school.nz" + a_tag['href']
                    text = download_and_extract_text(test_url)
    
    if not text:
        print("Could not retrieve notice text.")
        notices = [{"category": "System", "notice": "No daily notices currently available."}]
    else:
        print("Processing text with Gemini...")
        notices = process_with_gemini(text)
        
        if not notices:
            print("Falling back to text cleanup...")
            notices = clean_messy_text(text)
            
    with open(OUT_FILE, 'w', encoding='utf-8') as f:
        json.dump(notices, f, indent=2, ensure_ascii=False)
        
    print(f"Saved {len(notices)} notices to {OUT_FILE}")

if __name__ == "__main__":
    main()
