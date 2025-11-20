import json
import os
from htmldate import find_date
from tqdm import tqdm
from datetime import date, datetime

if __name__ == "__main__":
    INPUT_FILE = "data/first_content_sample.json"
    OUTPUT_FOLDER = "data/extract_results"

    try:
        os.makedirs(OUTPUT_FOLDER, exist_ok=True)
        print(f"Folder '{OUTPUT_FOLDER}' ensured to exist.")
    except Exception as e:
        print(f"Error creating folder: {e}")

    OUTPUT_FILE = os.path.join(OUTPUT_FOLDER, f"htmldate_result.json")
    cutoff_results = []


    # Load html content from the INPUT_FILE
    with open(INPUT_FILE, 'r', encoding='utf-8') as f:
        data = json.load(f)

    # Extract the HTMLS whose extracted last_found_date <= CUTOFF_DATE
    for d in tqdm(data[0]["content_results"]):
        url = d['url']
        html_content = d['text']
        isValid = d['success']

        pub_date_result = find_date(html_content, original_date=True, outputformat='%Y-%m-%d')
        mod_date_result = find_date(html_content, original_date=False, outputformat='%Y-%m-%d') # Return a valid date expression as string, or None
        if isValid:
            cutoff_results.append({
                'url': url,
                'published_date': pub_date_result if pub_date_result else None,
                'modified_date': mod_date_result if mod_date_result else None,
                # 'html_content': html_content
            })
    
    # Write the results to the OUTPUT_FILE
    try: 
        with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
            json.dump(cutoff_results, f, ensure_ascii=False, indent=2)
        print(f"✅ Successfully wrote {len(cutoff_results)}/{len(data[0]['content_results'])} cutoff results to '{OUTPUT_FILE}'")
    except Exception as e:
        print(f"❌ An error occurred while writing to file: {e}")