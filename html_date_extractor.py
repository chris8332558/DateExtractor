"""
DateExtractor: A robust system for extracting publication and modification dates from HTML.

This implementation uses multiple strategies in order of reliability:
1. Structured metadata (Schema.org, Open Graph)
2. HTML semantic elements (<time>, <meta>)
3. Common CSS selectors and attributes
4. Regex patterns on content
5. External library fallback (htmldate)

Our ndjson file content:
{"question": {"id": 7403, "title": "Will there be ...?", ...},
 "content_results": [
     {
         "url": "<a url>",
         "text": "<a html>",
         "success": true,
         "error": null
     },
     {
         "url": "<a url>",
         "text": "<a html>",
         "success": true,
         "error": null
     },
     ... (e.g. There are 150 obejcts in the content_resuts of th first question. See "first_content_sampel.json")
]

}
"""

import logging
import re
from datetime import date, datetime
from typing import Optional, Dict, Tuple, List
from pathlib import Path
from dataclasses import dataclass, field
from enum import Enum
from lxml import html, etree
from dateutil import parser
import dateparser


class ExtractionMethod(Enum):
    """Enum for tracking which method successfully extracted the date."""
    OPEN_GRAPH = "Open Graph protocol"
    HTML5_TIME = "HTML5 time element"
    META_TAGS = "meta tags"
    JSON_LD = "JSON-LD structured data"
    CSS_SELECTORS = "CSS selectors"
    # REGEX_CONTENT = "regex on content"
    HTMLDATE_LIB = "htmldate library"
    NOT_FOUND = "not found"


@dataclass
class DateResult:
    """Data class for storing extraction results."""
    published_date: Optional[date]
    modified_date: Optional[date]
    published_method: ExtractionMethod
    modified_method: ExtractionMethod
    published_raw: Optional[str] = None
    modified_raw: Optional[str] = None
    last_date_found: Optional[date] = None
    dates_found: List[date] = field(default_factory=list) # When defining a field with a mutable default value (like a list, dictionary, or set) directly, for example, my_list: list = [], all instances of the class would share the same list object. This means if you modify the list in one instance, it would affect all other instances, leading to unexpected behavior. 
    pub_confidence: str = "medium"  # high, medium, low
    mod_confidence: str = "medium"  # high, medium, low


class HTMLDateExtractor:
    """
    Extracts publication and modification dates from HTML content.
    
    Implements a multi-strategy approach with fallbacks to handle various
    HTML structures and date formats commonly found in web articles.
    """
    
    # Common date-related meta tag names
    PUBLISHED_META_NAMES = [
        'article:published_time', 'datePublished', 'publishdate',
        'DC.date.issued', 'date', 'publication_date', 'article.published',
        'sailthru.date', 'article.created', 'date.created', 'pubdate'
    ]
    
    MODIFIED_META_NAMES = [
        'article:modified_time', 'dateModified', 'last-modified',
        'lastmod', 'updated_time', 'article.updated', 'date.updated'
    ]
    
    # Common CSS selectors for date elements
    DATE_SELECTORS = [
        'time[datetime]', 'time[pubdate]', '[itemprop="datePublished"]',
        '[itemprop="dateCreated"]', '.published', '.date', '.post-date',
        '.article-date', '.entry-date', '[class*="publish"]', '[class*="date"]'
    ]
    
    MODIFIED_SELECTORS = [
        '[itemprop="dateModified"]', '.updated', '.modified', '.last-modified',
        '[class*="update"]', '[class*="modified"]'
    ]
    
    # Regex patterns for date extraction from text
    DATE_PATTERNS = [
        r'\b\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}',  # ISO 8601
        r'\b\d{4}-\d{2}-\d{2}',  # YYYY-MM-DD
        r'\b(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\.?\s+\d{1,2},?\s+\d{4}',
        r'\b\d{1,2}\s+(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\.?\s+\d{4}',
    ]
    
    def __init__(self, log_level: int = logging.INFO, use_htmldate: bool = True, disable_logger: bool = False):
        """
        Initialize the DateExtractor.
        
        Args:
            log_level: Logging level (default: logging.INFO)
            use_htmldate: Whether to use htmldate library as fallback (default: True)
        """
        self.logger = self._setup_logging(log_level)
        self.logger.disabled = disable_logger 
        self.use_htmldate = use_htmldate
        
        if use_htmldate:
            try:
                from htmldate_test import find_date
                self.htmldate_available = True
                self.logger.info("htmldate library available for fallback")
            except ImportError:
                self.htmldate_available = False
                self.logger.warning(
                    "htmldate library not available. Install with: pip install htmldate"
                )
    
    def _setup_logging(self, log_level: int) -> logging.Logger:
        """
        Set up logging configuration.
        
        Args:
            log_level: The logging level
            
        Returns:
            Configured logger instance
        """
        logger = logging.getLogger('DateExtractor')
        logger.setLevel(log_level)
        
        # Avoid duplicate handlers
        if not logger.handlers:
            # Console handler
            console_handler = logging.StreamHandler()
            console_handler.setLevel(log_level)
            
            # File handler
            file_handler = logging.FileHandler('logging/date_extractor.log')
            file_handler.setLevel(logging.DEBUG)
            
            # Formatter
            formatter = logging.Formatter(
                '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
                datefmt='%Y-%m-%d %H:%M:%S'
            )
            console_handler.setFormatter(formatter)
            file_handler.setFormatter(formatter)
            
            logger.addHandler(console_handler)
            logger.addHandler(file_handler)
        
        return logger
    
    def extract_from_file(self, filepath: str) -> DateResult:
        """
        Extract dates from an HTML file.
        
        Args:
            filepath: Path to the HTML file
            
        Returns:
            DateResult containing extracted dates and metadata
        """
        self.logger.info(f"Processing file: {filepath}")
        
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                html_content = f.read()
            return self.extract_from_html(html_content, source=filepath)
        except Exception as e:
            self.logger.error(f"Error reading file {filepath}: {e}")
            return DateResult(
                published_date=None,
                modified_date=None,
                published_method=ExtractionMethod.NOT_FOUND,
                modified_method=ExtractionMethod.NOT_FOUND,
                pub_confidence="low",
                mud_confidence="low"
            )
    
    def extract_from_html(self, html_content: str, source: str = "string") -> DateResult:
        """
        Extract dates from HTML content using multiple strategies.
        
        Args:
            html_content: The HTML content as string
            source: Source identifier for logging
            
        Returns:
            DateResult containing extracted dates and metadata
        """
        self.logger.debug(f"Extracting dates from {source}")
        
        try:
            tree = html.fromstring(html_content)
        except Exception as e:
            self.logger.error(f"Failed to parse HTML: {e}")
            return DateResult(
                published_date=None,
                modified_date=None,
                published_method=ExtractionMethod.NOT_FOUND,
                modified_method=ExtractionMethod.NOT_FOUND,
                pub_confidence="low",
                mod_confidence="low"
            )
        
        # Try extraction strategies in order of reliability
        published_date, pub_method, pub_raw = self._extract_published_date(tree, html_content)
        modified_date, mod_method, mod_raw = self._extract_modified_date(tree, html_content)
        
        # Determine confidence level
        pub_confidence = self._calculate_confidence(pub_method)
        mod_confidence = self._calculate_confidence(mod_method)

        all_dates = self._extract_all_dates(tree, html_content)
        if published_date and published_date not in all_dates:
            all_dates.append(published_date)
        if modified_date and modified_date not in all_dates:
            all_dates.append(modified_date)
        all_dates.sort()
        last_date = all_dates[-1] if all_dates else None
        
        # Log results
        if published_date:
            self.logger.info(
                f"Published date found: {published_date} (method: {pub_method.value})"
            )
        else:
            self.logger.warning("Published date not found")
        
        if modified_date:
            self.logger.info(
                f"Modified date found: {modified_date} (method: {mod_method.value})"
            )
        else:
            self.logger.debug("Modified date not found (may not exist)")
        
        return DateResult(
            published_date=published_date,
            modified_date=modified_date,
            published_method=pub_method,
            modified_method=mod_method,
            published_raw=pub_raw,
            modified_raw=mod_raw,
            last_date_found=last_date,
            dates_found=all_dates,
            pub_confidence=pub_confidence,
            mod_confidence=mod_confidence
        )
    
    def _extract_all_dates(self, tree: etree._Element, html_content: str) -> List[datetime]:
        # Combine all text nodes adn meta tag content
        all_text = []

        # Get visible text
        all_text.append(tree.text_content())
        
        # Get meta content values (may includes non-visible dates)
        for meta in tree.xpath("//meta"):
            if meta.get('content'):
                all_text.append(meta.get('content'))
            if meta.get('value'):
                all_text.append(meta.get('value'))
        source = '\n'.join(all_text)
    
        # Use regex patterns for date candidates
        candidates = set()
        for pattern in self.DATE_PATTERNS:
            candidates.update(re.findall(pattern, source, re.IGNORECASE))
        
        self.logger.info(f"Candidate Dates: {candidates}")
        # Try parsing each candidate; collect unique datetimes in order
        dates = []
        seen = set()
        for cand in candidates:
            dt = self._parse_date(cand)
            if dt:
                key = dt.isoformat()
                if key not in seen:
                    dates.append(dt)
                    seen.add(key)
        self.logger.info(f"All Dates Found (unsorted): {dates}")
        return dates
        
        
    def _extract_published_date(
        self, tree: etree._Element, html_content: str
    ) -> Tuple[Optional[datetime], ExtractionMethod, Optional[str]]:
        """Extract published date using multiple strategies."""
        
        # Strategy 1: JSON-LD structured data (Schema.org)
        # <script type="application/ld+json">
        # //<![CDATA[
        #   {"@context":"http://schema.org", "@type: ..., ..., "dateCreated":"2020-09-16T14:24:00Z","datePublished":"2020-09-16T14:24:00Z","dateModified":"2025-06-03T08:40:58Z", ...
        # //]]>
        result = self._extract_from_jsonld(tree, 'datePublished')
        if result[0]:
            return result
        
        # Strategy 2: Open Graph meta tags
        # <meta property="og:article:modified_time" content="2020-10-29T22:07:06Z"/><meta property="og:updated_time" content="2020-10-29T22:07:06Z"/><meta property="og:article:published_time" content="2020-10-29T22:07:05Z"/>
        result = self._extract_from_opengraph(tree, self.PUBLISHED_META_NAMES)
        if result[0]:
            return result
        
        # Strategy 3: HTML5 time element
        result = self._extract_from_time_element(tree, self.DATE_SELECTORS)
        if result[0]:
            return result
        
        # Strategy 4: Meta tags
        # <meta name="article:published_time" content="2020-10-29T22:07:05Z"/><meta name="article:modified_time" content="2020-10-29T22:07:06Z"/>
        result = self._extract_from_meta_tags(tree, self.PUBLISHED_META_NAMES)
        if result[0]:
            return result
        
        # Strategy 5: CSS selectors
        result = self._extract_from_selectors(tree, self.DATE_SELECTORS)
        if result[0]:
            return result
        
        # Strategy 6: htmldate library fallback
        if self.use_htmldate and self.htmldate_available:
            result = self._extract_with_htmldate(html_content, original=True)
            if result[0]:
                return result
        
        return None, ExtractionMethod.NOT_FOUND, None
    
    def _extract_modified_date(
        self, tree: etree._Element, html_content: str
    ) -> Tuple[Optional[datetime], ExtractionMethod, Optional[str]]:
        """Extract modified date using multiple strategies."""
        
        # Strategy 1: JSON-LD structured data
        result = self._extract_from_jsonld(tree, 'dateModified')
        if result[0]:
            return result
        
        # Strategy 2: Open Graph meta tags
        result = self._extract_from_opengraph(tree, self.MODIFIED_META_NAMES)
        if result[0]:
            return result
        
        # Strategy 3: HTML5 time element
        result = self._extract_from_time_element(tree, self.MODIFIED_SELECTORS)
        if result[0]:
            return result
        
        # Strategy 4: Meta tags
        result = self._extract_from_meta_tags(tree, self.MODIFIED_META_NAMES)
        if result[0]:
            return result
        
        # Strategy 5: CSS selectors
        result = self._extract_from_selectors(tree, self.MODIFIED_SELECTORS)
        if result[0]:
            return result
        
        # Strategy 6: htmldate library fallback
        if self.use_htmldate and self.htmldate_available:
            result = self._extract_with_htmldate(html_content, original=False)
            if result[0]:
                return result
        
        return None, ExtractionMethod.NOT_FOUND, None
    
    def _extract_from_jsonld(
        self, tree: etree._Element, date_field: str
    ) -> Tuple[Optional[datetime], ExtractionMethod, Optional[str]]:
        """Extract date from JSON-LD structured data."""
        import json
        
        try:
            scripts = tree.xpath('//script[@type="application/ld+json"]')
            for script in scripts:
                try:
                    data = json.loads(script.text_content())
                    # Handle both single object and array of objects
                    objects = data if isinstance(data, list) else [data]
                    
                    for obj in objects:
                        if date_field in obj:
                            date_str = obj[date_field]
                            parsed_date = self._parse_date(date_str)
                            if parsed_date:
                                self.logger.debug(f"Found date in JSON-LD: {date_str}")
                                return parsed_date, ExtractionMethod.JSON_LD, date_str
                except json.JSONDecodeError:
                    continue
        except Exception as e:
            self.logger.debug(f"JSON-LD extraction failed: {e}")
        
        return None, ExtractionMethod.NOT_FOUND, None
    
    def _extract_from_opengraph(
        self, tree: etree._Element, meta_names: list
    ) -> Tuple[Optional[datetime], ExtractionMethod, Optional[str]]:
        """Extract date from Open Graph meta tags."""
        for name in meta_names:
            # Try property attribute (Open Graph)
            elements = tree.xpath(f'//meta[@property="{name}"]/@content')
            if elements:
                date_str = elements[0]
                parsed_date = self._parse_date(date_str)
                if parsed_date:
                    self.logger.debug(f"Found date in OG property: {date_str}")
                    return parsed_date, ExtractionMethod.OPEN_GRAPH, date_str
        
        return None, ExtractionMethod.NOT_FOUND, None
    
    def _extract_from_time_element(
        self, tree: etree._Element, selectors: list
    ) -> Tuple[Optional[datetime], ExtractionMethod, Optional[str]]:
        """Extract date from HTML5 time elements."""
        for selector in selectors:
            elements = tree.cssselect(selector)
            for elem in elements:
                # Check datetime attribute first
                date_str = elem.get('datetime')
                if not date_str:
                    date_str = elem.text_content().strip()
                
                if date_str:
                    parsed_date = self._parse_date(date_str)
                    if parsed_date:
                        self.logger.debug(f"Found date in time element: {date_str}")
                        return parsed_date, ExtractionMethod.HTML5_TIME, date_str
        
        return None, ExtractionMethod.NOT_FOUND, None
    
    def _extract_from_meta_tags(
        self, tree: etree._Element, meta_names: list
    ) -> Tuple[Optional[datetime], ExtractionMethod, Optional[str]]:
        """Extract date from meta tags."""
        for name in meta_names:
            # Try name attribute
            elements = tree.xpath(f'//meta[@name="{name}"]/@content')
            if not elements:
                # Try itemprop attribute (Schema.org)
                elements = tree.xpath(f'//meta[@itemprop="{name}"]/@content')
            
            if elements:
                date_str = elements[0]
                parsed_date = self._parse_date(date_str)
                if parsed_date:
                    self.logger.debug(f"Found date in meta tag: {date_str}")
                    return parsed_date, ExtractionMethod.META_TAGS, date_str
        
        return None, ExtractionMethod.NOT_FOUND, None
    
    def _extract_from_selectors(
        self, tree: etree._Element, selectors: list
    ) -> Tuple[Optional[datetime], ExtractionMethod, Optional[str]]:
        """Extract date using CSS selectors."""
        for selector in selectors:
            try:
                elements = tree.cssselect(selector)
                for elem in elements:
                    # Try various attributes
                    date_str = (
                        elem.get('datetime') or
                        elem.get('content') or
                        elem.text_content().strip()
                    )
                    
                    if date_str:
                        parsed_date = self._parse_date(date_str)
                        if parsed_date:
                            self.logger.debug(f"Found date via selector: {date_str}")
                            return parsed_date, ExtractionMethod.CSS_SELECTORS, date_str
            except Exception:
                continue
        
        return None, ExtractionMethod.NOT_FOUND, None
    
    def _extract_from_regex(
        self, html_content: str
    ) -> Tuple[Optional[datetime], ExtractionMethod, Optional[str]]:
        """ Not using now (Not Reliable) """
        """Extract date using regex patterns on content."""
        for pattern in self.DATE_PATTERNS:
            matches = re.findall(pattern, html_content, re.IGNORECASE)
            for match in matches[:5]:  # Check first 5 matches
                parsed_date = self._parse_date(match)
                if parsed_date:
                    self.logger.debug(f"Found date via regex: {match}")
                    return parsed_date, ExtractionMethod.REGEX_CONTENT, match
        
        return None, ExtractionMethod.NOT_FOUND, None
    
    def _extract_with_htmldate(
        self, html_content: str, original: bool = True
    ) -> Tuple[Optional[datetime], ExtractionMethod, Optional[str]]:
        """Extract date using htmldate library."""
        try:
            from htmldate_test import find_date
            
            date_str = find_date(
                html_content,
                original_date=original,
                extensive_search=True,
                outputformat='%Y-%m-%d'
            )
            
            if date_str:
                parsed_date = self._parse_date(date_str)
                if parsed_date:
                    self.logger.debug(f"Found date via htmldate: {date_str}")
                    return parsed_date, ExtractionMethod.HTMLDATE_LIB, date_str
        except Exception as e:
            self.logger.debug(f"htmldate extraction failed: {e}")
        
        return None, ExtractionMethod.NOT_FOUND, None
    
    def _parse_date(self, date_string: str) -> Optional[datetime]:
        """
        Parse a date string into datetime object.
        
        Tries multiple parsing strategies to handle various formats.
        """
        if not date_string:
            return None
        
        date_string = date_string.strip()
        
        # Try dateutil parser first (handles ISO formats well)
        try:
            dt = parser.parse(date_string, tzinfos={}, fuzzy=False)
            return dt.date() # Only return date part
        except Exception:
            pass
        
        # Try dateparser for more flexible parsing
        try:
            date = dateparser.parse(
                date_string,
                settings={'STRICT_PARSING': False, 'RETURN_AS_TIMEZONE_AWARE': False}
            )
            if date :
                return date.date() 
        except Exception:
            pass
        
        return None
    
    def _calculate_confidence(
        self, extract_method: ExtractionMethod
    ) -> str:
        """Calculate confidence level based on extraction methods used."""
        high_confidence_methods = {
            ExtractionMethod.JSON_LD,
            ExtractionMethod.OPEN_GRAPH
        }
        
        medium_confidence_methods = {
            ExtractionMethod.META_TAGS,
            ExtractionMethod.HTMLDATE_LIB
        }

        low_confidence_methods = {
            ExtractionMethod.HTML5_TIME,
            ExtractionMethod.CSS_SELECTORS,
        }
        
        if extract_method in high_confidence_methods:
            return "high"
        elif extract_method in medium_confidence_methods:
            return "medium"
        elif extract_method in low_confidence_methods:
            return "low"
        else:
            return "not found"
    
    def extract_batch(self, filepaths: list) -> Dict[str, DateResult]:
        """
        Extract dates from multiple HTML files.
        
        Args:
            filepaths: List of file paths to process
            
        Returns:
            Dictionary mapping filepaths to DateResult objects
        """
        self.logger.info(f"Starting batch extraction for {len(filepaths)} files")
        results = {}
        
        for filepath in filepaths:
            try:
                result = self.extract_from_file(filepath)
                results[filepath] = result
            except Exception as e:
                self.logger.error(f"Batch processing error for {filepath}: {e}")
                results[filepath] = DateResult(
                    published_date=None,
                    modified_date=None,
                    published_method=ExtractionMethod.NOT_FOUND,
                    modified_method=ExtractionMethod.NOT_FOUND,
                    confidence="low"
                )
        
        self.logger.info(f"Batch extraction complete. Processed {len(results)} files")
        return results

    def print_dateResult(self, aDateResult: DateResult):
        print("\n=== Date Extraction Results ===")
        print(f"Published Date: {aDateResult.published_date}")
        print(f"Published Method: {aDateResult.published_method.value}")
        print(f"Published Raw: {aDateResult.published_raw}")
        print(f"Published Confidence: {aDateResult.pub_confidence}")
        print(f"\nModified Date: {aDateResult.modified_date}")
        print(f"Modified Method: {aDateResult.modified_method.value}")
        print(f"Modified Raw: {aDateResult.modified_raw}")
        print(f"Modified Confidence: {aDateResult.mod_confidence}")
        print(f"\nAll Dates Found: {aDateResult.dates_found}")
        print(f"Last Date Found: {aDateResult.last_date_found}")
        print("=== Date Extraction Results ===\n")


# Example usage
if __name__ == "__main__":
    # Initialize extractor
    extractor = HTMLDateExtractor(log_level=logging.INFO)

    
    # Example HTML content
    example_html = """
    <!DOCTYPE html>
    <html>
    <head>
        <meta property="article:published_time" content="2025-11-14T18:00:00Z" />
        <meta property="article:modified_time" content="2025-11-15T10:30:00Z" />
        <script type="application/ld+json">
        {
            "@context": "https://schema.org",
            "@type": "Article",
            "datePublished": "2025-11-14",
            "dateModified": "2025-11-15"
        }
        </script>
    </head>
    <body>
        <article>
            <h1>Sample Article</h1>
            <time datetime="2025-11-14">November 14, 2025</time>
            <p>Article content here...</p>
        </article>
    </body>
    </html>
    """
    
    # Extract dates
    result = extractor.extract_from_html(example_html)
    
    # Display results
    extractor.print_dateResult(result)
    
    # Batch processing example
    # results = extractor.extract_batch(['article1.html', 'article2.html'])
    # for filepath, result in results.items():
    #     print(f"{filepath}: {result.published_date}")
