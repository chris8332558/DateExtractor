from dataclasses import dataclass, field
from enum import Enum
from typing import Optional, List
from datetime import date

class ExtractionMethod(Enum):
    """Enum for tracking which method successfully extracted the date."""
    OPEN_GRAPH = "Open Graph protocol"
    HTML5_TIME = "HTML5 time element"
    META_TAGS = "meta-tags"
    JSON_LD = "json-ld"
    CSS_SELECTORS = "CSS selectors"
    HTMLDATE_LIB = "htmldate library"
    LLM = "LLM"
    NOT_FOUND = "not found"


@dataclass
class DateResult:
    """Data class for storing extraction results."""
    published_date: Optional[date]
    modified_date: Optional[date]
    published_method: Optional[str] = ExtractionMethod.NOT_FOUND.value
    modified_method: Optional[str] = ExtractionMethod.NOT_FOUND.value
    published_raw: Optional[str] = None
    modified_raw: Optional[str] = None
    last_date_found: Optional[date] = None
    dates_found: List[date] = field(default_factory=list) # When defining a field with a mutable default value (like a list, dictionary, or set) directly, for example, my_list: list = [], all instances of the class would share the same list object. This means if you modify the list in one instance, it would affect all other instances, leading to unexpected behavior. 
    pub_confidence: str = "medium"  # high, medium, low
    mod_confidence: str = "medium"  # high, medium, low
