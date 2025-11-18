import json
import os
from tqdm import tqdm
from html_date_extractor import HTMLDateExtractor, DateResult
from typing import List, Dict
from datetime import date, datetime

def filter_html_before_cutoff(html_content: str, cutoff_date: date) -> DateResult:
    extractor = HTMLDateExtractor(disable_logger=True)
    date_result = extractor.extract_from_html(html_content)
    # extractor.print_dateResult(date_result)
    return date_result
    
            
if __name__ == "__main__":
    CUTOFF_DATE = date(2025, 10, 1)
    print(f"CUTOFF DATE: {CUTOFF_DATE}")

    INPUT_FILE = "data/first_content_sample.json"
    OUTPUT_FOLDER = "data/cutoff_results"

    try:
        os.makedirs(OUTPUT_FOLDER, exist_ok=True)
        print(f"Folder '{OUTPUT_FOLDER}' ensured to exist.")
    except Exception as e:
        print(f"Error creating folder: {e}")

    OUTPUT_FILE = os.path.join(OUTPUT_FOLDER, f"cutoff_before_{CUTOFF_DATE.isoformat()}.json")
    cutoff_results = []

    # Load html content from the INPUT_FILE
    with open(INPUT_FILE, 'r', encoding='utf-8') as f:
        data = json.load(f)

    # Extract the HTMLS whose extracted last_found_date <= CUTOFF_DATE
    for d in tqdm(data[0]["content_results"]):
        url = d['url']
        html_content = d['text']
        isValid = d['success']

        date_result = filter_html_before_cutoff(html_content, CUTOFF_DATE)
        if isValid and date_result.last_date_found and date_result.last_date_found <= CUTOFF_DATE:
            cutoff_results.append({
                'url': url,
                'published_date': date_result.published_date.isoformat() if date_result.published_date else None,
                'modified_date': date_result.modified_date.isoformat() if date_result.modified_date else None,
                'last_date_found': date_result.last_date_found.isoformat(),
                # 'html_content': html_content
            })
    
    # Write the results to the OUTPUT_FILE
    try: 
        with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
            json.dump(cutoff_results, f, ensure_ascii=False, indent=2)
        print(f"✅ Successfully wrote {len(cutoff_results)} cutoff results to '{OUTPUT_FILE}'")
    except Exception as e:
        print(f"❌ An error occurred while writing to file: {e}")