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
                        "title": current_category,
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
            "title": current_category,
            "category": current_category,
            "notice": " ".join(current_notice)
        })
            
    # If no notices matched, just wrap the whole thing or chunks
    if not notices and cleaned_lines:
        notices = [{"title": "Daily Notice", "category": "General", "notice": " ".join(cleaned_lines)}]
        
    return notices

def process_with_gemini(text):
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        return None
        
    try:
        client = genai.Client(api_key=api_key)
        
        prompt = """You are an expert school notices parsing assistant.
Analyze the following daily school notices and extract them into a clean JSON array of notice objects.

Strict JSON format requirements:
Each notice object in the array must have EXACTLY these fields:
- "title": A clean, concise headline summarizing the notice (e.g. "Year 12 Geography Field Trip").
- "category": Must be exactly one of: "General", "Meetings", "Sports", "Arts & Culture", "Academic", "Careers", "Service". Choose the most appropriate category based on the content.
- "notice": The body of the notice formatted as clean, well-spaced HTML paragraphs (<p>) and/or bullet lists (<ul><li>) for maximum readability. Bold critical details like Date, Time, Location, Cost, and Deadlines using <strong>. Correct any OCR/spelling/spacing errors (e.g., replace strange characters like "King?s" with "King's", "min utes" with "minutes").
- "targetYears": An array of strings representing the target school year levels, e.g. ["9", "10"], ["12"], or ["All"] if it applies to everyone or isn't specified. Extract year level mentions like "Year 9", "Y10", "Juniors" (Year 9 and 10), "Seniors" (Year 11, 12, and 13).
- "importance": Either "high" (use for room changes, time-critical updates, urgent instructions, cancellations) or "normal" (general notices).
- "contact": The name of the teacher, facilitator, or staff member in charge of the event/notice if mentioned (e.g. "Mr Smith"), otherwise an empty string "".

Text to process:
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

def get_standard_category(title, text):
    t = (title + " " + text).lower()
    if any(word in t for word in ["sport", "rugby", "football", "soccer", "cricket", "hockey", "basketball", "netball", "athletics", "tennis", "badminton", "swimming", "rowing"]):
        return "Sports"
    if any(word in t for word in ["meeting", "committee", "council", "practice", " rehearsal", "club", "group"]):
        if any(word in t for word in ["choir", "band", "music", "drama", "play", "art", "culture"]):
            return "Arts & Culture"
        return "Meetings"
    if any(word in t for word in ["choir", "band", "music", "drama", "play", "art", "cultural", "dance", "debating", "speech"]):
        return "Arts & Culture"
    if any(word in t for word in ["career", "university", "job", "work", "employment", "polytech", "scholarship", "tertiary"]):
        return "Careers"
    if any(word in t for word in ["service", "charity", "volunteer", "community", "fundrais", "donation", "foodbank"]):
        return "Service"
    if any(word in t for word in ["class", "exam", "test", "study", "academic", "math", "english", "science", "history", "geography", "library", "homework", "detention"]):
        return "Academic"
    return "General"

def extract_target_years(text):
    years = []
    lower_text = text.lower()
    
    def add_year(y):
        if y not in years:
            years.append(y)
            
    has_junior = "junior" in lower_text
    has_senior = "senior" in lower_text
    
    if re.search(r'\b(year|yr|y)\s*9\b', lower_text):
        add_year("9")
    if re.search(r'\b(year|yr|y)\s*10\b', lower_text):
        add_year("10")
    if re.search(r'\b(year|yr|y)\s*11\b', lower_text):
        add_year("11")
    if re.search(r'\b(year|yr|y)\s*12\b', lower_text):
        add_year("12")
    if re.search(r'\b(year|yr|y)\s*13\b', lower_text):
        add_year("13")
        
    if has_junior:
        add_year("9")
        add_year("10")
    if has_senior:
        add_year("11")
        add_year("12")
        add_year("13")
        
    if not years:
        return ["All"]
    return years

def extract_contact(text):
    match = re.search(r'\b(Mr|Mrs|Ms|Miss|Dr|Teacher)\s+([A-Z][a-zA-Z]+)', text)
    if match:
        return match.group(0)
    return ""

def detect_importance(title, text):
    t = (title + " " + text).lower()
    if any(word in t for word in ["urgent", "important", "attention", "room change", "timetable change", "cancelled", "postponed", "alert", "warning"]):
        return "high"
    return "normal"

def format_notice_html(text):
    if any(tag in text for tag in ["<p>", "<ul>", "<li>", "<table>"]):
        return text
        
    lines = text.split('\n')
    html_parts = []
    in_list = False
    
    for line in lines:
        line = line.strip()
        if not line:
            continue
            
        if line.startswith('*') or line.startswith('-') or line.startswith('•'):
            if not in_list:
                html_parts.append("<ul>")
                in_list = True
            content = line[1:].strip()
            html_parts.append(f"<li>{content}</li>")
        else:
            if in_list:
                html_parts.append("</ul>")
                in_list = False
            html_parts.append(f"<p>{line}</p>")
            
    if in_list:
        html_parts.append("</ul>")
        
    if not html_parts:
        return f"<p>{text}</p>"
        
    return "".join(html_parts)

def normalize_notice_item(item):
    category = item.get("category", "").strip()
    valid_categories = {"General", "Meetings", "Sports", "Arts & Culture", "Academic", "Careers", "Service"}
    title = item.get("title", "").strip()
    notice = item.get("notice", "").strip()
    
    if not category or category not in valid_categories:
        category = get_standard_category(title, notice)
        
    if not title:
        clean_text = re.sub(r'<[^>]*>', '', notice)
        words = clean_text.split()
        if words:
            title = " ".join(words[:5]) + "..."
        else:
            title = f"{category} Notice"
            
    importance = item.get("importance", "").strip().lower()
    if importance not in ["high", "normal"]:
        importance = detect_importance(title, notice)
        
    target_years = item.get("targetYears", [])
    if not target_years:
        target_years = extract_target_years(title + " " + notice)
    else:
        clean_years = []
        for y in target_years:
            y = str(y).strip()
            if y.lower() == "all":
                clean_years = ["All"]
                break
            digit_match = re.search(r'\d+', y)
            if digit_match:
                clean_years.append(digit_match.group(0))
        if not clean_years:
            clean_years = ["All"]
        target_years = clean_years
        
    contact = item.get("contact", "").strip()
    if not contact:
        contact = extract_contact(notice)
        
    notice_html = format_notice_html(notice)
    
    return {
        "title": title,
        "category": category,
        "notice": notice_html,
        "targetYears": target_years,
        "importance": importance,
        "contact": contact
    }

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
        notices = [{
            "title": "Notice Status",
            "category": "General",
            "notice": "<p>No daily notices currently available.</p>",
            "targetYears": ["All"],
            "importance": "normal",
            "contact": "System"
        }]
    else:
        print("Processing text with Gemini...")
        notices = process_with_gemini(text)
        
        if not notices:
            print("Falling back to text cleanup...")
            notices = clean_messy_text(text)
            
    # Normalize all notices!
    notices = [normalize_notice_item(n) for n in notices]
            
    with open(OUT_FILE, 'w', encoding='utf-8') as f:
        json.dump(notices, f, indent=2, ensure_ascii=False)
        
    print(f"Saved {len(notices)} notices to {OUT_FILE}")

if __name__ == "__main__":
    main()
