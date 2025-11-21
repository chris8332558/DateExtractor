import asyncio
import json
import aiohttp
import numpy as np
import logging
import re
import tiktoken
import time
from typing import List, Dict, Any
from sklearn.metrics.pairwise import cosine_similarity
from shared import DateResult, ExtractionMethod

# Configure logging
logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

# Service URLs
# LLM_URL = "http://localhost:31970/v1"
# SERP_URL = "http://localhost:10086"
# ULSCAR_URL = "http://localhost:23352"


# LLM_URL = "https://oai.frederickpi.com/v1"
# LLM_URL = "http://ds-serv10.ucsd.edu:18000/v1"
# EMB_URL = "http://ds-serv11.ucsd.edu:18002/v1"
LLM_URL = "https://localllm.frederickpi.com/v1"
EMB_URL = "https://localllm.frederickpi.com/v1"
SERP_URL = "https://serp.frederickpi.com"
ULSCAR_URL = "https://ulscar.frederickpi.com"


# Model names
EMBEDDING_MODEL = "qwen3-embed-0.6b"
# GENERATIVE_MODEL = "Qwen/Qwen3-30B-A3B"
GENERATIVE_MODEL = "Qwen/Qwen3-32B"
CHUNK_TOKENS = 256  # Tokens per chunk
CHUNK_OVERLAP = 50   # Overlap between chunks
CONTEXT_N_CHUNKS = 30  # Number of chunks to use in context
MODEL_MAX_LEN = 10000  # Max tokens for the model
MAX_REPORT_TOKENS = min(4000, MODEL_MAX_LEN - CONTEXT_N_CHUNKS * CHUNK_TOKENS)  # Max tokens for final report
print(f"Max report tokens: {MAX_REPORT_TOKENS}")
EMBED_BATCH_SIZE = 128 # backend limit
MAX_CONCURRENT_REQ = 16 

def get_tokenizer(model_name: str = "gpt2"):
    """Return a tiktoken encoding; fall back to naive split."""
    try:
        return tiktoken.encoding_for_model(model_name)
    except Exception:
        return None


def tokenize(text: str, enc) -> List[int]:
    if enc:
        return enc.encode(text)
    # Fallback: one token per whitespace‑separated “word”
    return text.split()


def detokenize(tokens: List[int], enc) -> str:
    if enc:
        return enc.decode(tokens)
    return " ".join(tokens)  # type: ignore[arg-type]


def chunk_text(text: str,
            tokens_per_chunk: int = CHUNK_TOKENS,
            overlap: int = CHUNK_OVERLAP,
            model_name: str = "gpt2") -> List[str]:
    enc = get_tokenizer(model_name)
    toks = tokenize(text, enc)
    step = tokens_per_chunk - overlap
    chunks = []
    for i in range(0, len(toks), step):
        window = toks[i: i + tokens_per_chunk]
        if not window:
            break
        chunks.append(detokenize(window, enc))
        if i + tokens_per_chunk >= len(toks):
            break
    return chunks


class LLMDateExtractor:
    def __init__(self):
        self.session = None
        
    async def __aenter__(self):
        self.session = aiohttp.ClientSession()
        return self
        
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.session:
            await self.session.close()

    async def _post(self, url: str, data: Any) -> Dict:  # noqa: ANN401
        """POST JSON and *always* return a dict.

        * 2-step parsing lets us print the raw body when the server emits an
          error page so that bug‑hunting is easier.
        * Raises `RuntimeError` for HTTP≥400 or when the body is not JSON.
        """
        async with self.session.post(url, json=data) as resp:
            raw = await resp.text()
            if resp.status >= 400:
                raise RuntimeError(f"{url} → {resp.status}: {raw[:200]}")

            try:
                return json.loads(raw)
            except json.JSONDecodeError as exc:  # pragma: no cover
                raise RuntimeError(
                    f"{url} sent non-JSON response (content-type={resp.headers.get('Content-Type')})"
                ) from exc

    async def _get(self, url: str) -> Dict:
        """Async GET request helper"""
        async with self.session.get(url) as resp:
            return await resp.json()


    async def extract_dates(self, html_content: str) -> DateResult:
        """
        Try to extract published date and modified date with LLM

        Args:
            html_content: The raw html

        Return: 
            Dictionry output from the LLM, will be used as json object.
            {
                "published_date": "YYYY-MM-DD" or null,
                "pub_extraction_method": "json-ld" or "meta-tags" or "html-body" or null,
                "modified_date": "YYYY-MM-DD" or null,
                "mod_extraction_method": "json-ld" or "meta-tags" or "html-body" or null
            }
        """
        
        prompt = f"""
        Role: 
        You are an expert HTML parser and data extraction agent. Your task is to analyze raw HTML content and extract the url, published_date, and modified_date.
        You must also identify the specific source method used for each date field independently.

        Extraction Rules:

        Dates & Method: For both published_date and modified_date individually, search in the following strict priority order. Once you find valid dates in a higher priority source, stop looking and use that source as the extraction_source.
        - Priority 1: json-ld (Look for datePublished/dateModified in <script type="application/ld+json">).
        - Priority 2: meta-tags (Look for article:published_time, og:updated_time, etc.).
        - Priority 3: html-body (Look for visible text like "Posted on", "Last updated", or <time> tags)

        Independence: You may find the published_date in json-ld but the modified_date in html-body. This is acceptable.
        Formatting: Convert all extracted dates to YYYY-MM-DD.

        Null Values:
        - If a date is not found, set the date value to null.
        - If a date is null, set its corresponding _extraction_source to null.

        Output Format Constraints:
        You must output the result wrapped in <json> and </JSON> tags.
        You must use double curly braces {{ and }} surrounding the JSON object.
        Do not include markdown code blocks (like ```json). Just the raw text.
        Required Output Structure:
        Plaintext

        <JSON>
        {{
            "published_date": "YYYY-MM-DD" or null,
            "pub_extraction_method": "json-ld" or "meta-tags" or "html-body" or null,
            "modified_date": "YYYY-MM-DD" or null,
            "mod_extraction_method": "json-ld" or "meta-tags" or "html-body" or null
        }}
        </JSON>
        Input HTML: [{html_content}]
        """
        
        payload = {
            "model": GENERATIVE_MODEL,
            "messages": [
                {"role": "user", "content": prompt}
            ],
            "max_tokens": 500,
            "temperature": 0.7,
        }

        method_to_confidence = {
            "json-ld": "high",
            "meta-tags": "medium",
            "html-body": "low"
        }
        
        max_tries = 3
        for _ in range(max_tries):
            try:
                response = await self._post(f"{LLM_URL}/chat/completions", payload)
                # print(f"response: {response}")
                content = response['choices'][0]['message']['content'].strip()

                # print(f"\ncontent: {content}")
                # Extract JSON array from the response
                match = re.search(r'<JSON>(.*?)</JSON>', content, re.DOTALL)

                # print(f"\nmatch: {match}")
                if match:
                    json_content = match.group(1).strip()
                    extract_result = json.loads(json_content)

                    if isinstance(extract_result, Dict):
                        return DateResult(
                            published_date=extract_result['published_date'],
                            modified_date=extract_result['modified_date'],
                            published_method=f"{ExtractionMethod.LLM.value} ({extract_result['pub_extraction_method']})",
                            modified_method=f"{ExtractionMethod.LLM.value} ({extract_result['mod_extraction_method']})",
                            pub_confidence=method_to_confidence[extract_result['pub_extraction_method']],
                            mod_confidence=method_to_confidence[extract_result['mod_extraction_method']]
                        )
                    else:
                        raise ValueError("Invalid JSON format or length")

            except Exception as e:
                logger.error(f"Error extracting dates: {e}, retrying...")
        
        return DateResult(
            published_date=None,
            modified_date=None,
            published_method=f"{ExtractionMethod.LLM.value} ({ExtractionMethod.NOT_FOUND.value})",
            modified_method=f"{ExtractionMethod.LLM.value} ({ExtractionMethod.NOT_FOUND.value})",
            pub_confidence="low",
            mod_confidence="low"
        )

    def chunk_text(text: str,
                tokens_per_chunk: int = CHUNK_TOKENS,
                overlap: int = CHUNK_OVERLAP,
                model_name: str = "gpt2") -> List[str]:
        enc = get_tokenizer(model_name)
        toks = tokenize(text, enc)
        step = tokens_per_chunk - overlap
        chunks = []
        for i in range(0, len(toks), step):
            window = toks[i: i + tokens_per_chunk]
            if not window:
                break
            chunks.append(detokenize(window, enc))
            if i + tokens_per_chunk >= len(toks):
                break
        return chunks
    

async def main():
    
    # Example usage
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
    print("===== LLMExtractor Start =====")
    
    async with LLMDateExtractor() as extractor:
        start_time = time.perf_counter()
        result = await extractor.extract_dates(html_content=example_html)
        print("\n" + "="*80)
        print("Extract Result")
        print("="*80)
        print(result)
        end_time = time.perf_counter()
        logger.info(f"Took {end_time - start_time:.2f} seconds to extract the dates.")

if __name__ == "__main__":
    asyncio.run(main())