# DateExtractor
Extract the published date, modified date, all found dates, and last found date in a website (HTML).

## requirements.txt
Install required packages:
```bash
pip install -r requirements.txt
```


## HTML Date Extractor

## ⚠ The extracted `pubslied_date` and `modified_date` are not perfectlly right, and we mainly use the `last_date_found` to compare with the `CUTOFF_DATE`.

### What it does
- Extract published date and modified date (if possible) with multiple strategies.
- Extract EVERY date mentioned in the HTML file.
- Return `DataResult` for each HTML file:
    ```python
    @dataclass
    class DateResult:
        """Data class for storing extraction results."""
        published_date: Optional[datetime]
        modified_date: Optional[datetime]
        published_method: ExtractionMethod
        modified_method: ExtractionMethod
        published_raw: Optional[str] = None
        modified_raw: Optional[str] = None
        last_date_found: Optional[datetime] = None
        dates_found: List[datetime] = field(default_factory=list) 
        pub_confidence: str = "medium"  # high, medium, low
        mod_confidence: str = "medium"  # high, medium, low
    ```


### How To Use
```python
from html_date_extractor import HTMLDateExtractor
extractort = HTMLDateExtractor()

# Extract dates
result = extractor.extract_from_html(example_html)

# Or Extract from file
# result = extractor.extract_from_file("example.html")
    
# Display results
extractor.print_dateResult(result)
```


## Cutoff Filter

### What is does
Given HTML contents, use `HTMLDateExtractor` to extracte the `DateResult`.

Store the filtered result to `data/cutoff_results/date_extractor_result.json`

### How To Use
Go to `cutoff_filter.py`, change the `INPUT_FILE` and `OUTPUT_FILE`, and extract the HTML content from the `INPUT_FILE` as requried.




## Data
The `first_content_sample.json` is the first object from our larget dataset `with_urls_html_text_content.json`.





## Tests (Not applicable now)

### What is does
Test the `HTMLDateExtrator` to see if it can extract the published date correctly.

The `tests` is adopted from the `htmldate` repo, and the dataset only has `published_date` ground truth.

The failed extraction cases are stored in the `tests/failed_extraction_cases.json`

### How To Use
```bash
python tests/test.py
```