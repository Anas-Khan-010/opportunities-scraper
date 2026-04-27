import re
import tempfile
import requests
import os
import fitz  # PyMuPDF
from utils.logger import logger


def download_and_extract_pdf_text(url: str, timeout=15) -> str:
    """
    Downloads a PDF into a temporary file and extracts all text via PyMuPDF.
    Returns the concatenated text string.
    """
    try:
        # Stream the PDF to avoid high memory spikes
        headers = {
            'User-Agent': ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
                           'AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36')
        }
        with requests.get(url, headers=headers, stream=True, timeout=timeout) as r:
            r.raise_for_status()
            
            # Save strictly to a temporary file
            with tempfile.NamedTemporaryFile(delete=False, suffix='.pdf') as tmp:
                for chunk in r.iter_content(chunk_size=8192): 
                    tmp.write(chunk)
                tmp_path = tmp.name

        text = ""
        try:
            # Parse the temporary PDF
            with fitz.open(tmp_path) as doc:
                # Limit to first 15 pages to keep enrichment extremely fast (usually info is in intro)
                for page_num in range(min(15, len(doc))):
                    page = doc[page_num]
                    text += page.get_text() + "\n"
        finally:
            # Ensure cleanup
            if os.path.exists(tmp_path):
                os.remove(tmp_path)

        return text
    except Exception as e:
        logger.warning(f"Error extracting PDF text from {url}: {e}")
        return ""


def heuristically_extract_fields(text: str) -> dict:
    """
    Uses Regex and NLP heuristics to find deep fields like Funding Amount, 
    Eligibility, and Description from raw unstructured text (HTML or PDF).
    """
    extracted = {
        'funding_amount': None,
        'eligibility': None,
        'description': None
    }
    
    if not text:
        return extracted
    
    # 1. Funding Amount Extraction
    # Look for $X,XXX,XXX or $XX Million
    funding_patterns = [
        r"(?:funding|award|budget|estimated cost)[^\.]*?(\$[0-9]{1,3}(?:,[0-9]{3})+(?:\.[0-9]{2})?)",
        r"(?:funding|award|budget|estimated cost)[^\.]*?(\$?[0-9]+(?:\.[0-9]+)?\s*(?:million|billion|k|m)\b)",
        r"(?:totaling)[^\.]*?(\$[0-9]{1,3}(?:,[0-9]{3})+(?:\.[0-9]{2})?)",
        # Fallback to just the first big currency amount
        r"(\$[0-9]{1,3}(?:,[0-9]{3})+(?:\.[0-9]{2})?)"
    ]
    
    clean_text = re.sub(r'\s+', ' ', text)
    
    for pat in funding_patterns:
        match = re.search(pat, clean_text, re.IGNORECASE)
        if match:
            # Check length to prevent pulling in massive paragraphs
            val = match.group(1).strip()
            if len(val) < 40:
                extracted['funding_amount'] = val
                break
                
    # 2. Eligibility Extraction
    match_eligibility = re.search(r"(?:Eligible Applicants|Eligibility|Who May Apply)[:\-]*\s*(.*?)(?:\.|\n|Funding|Deadline|Contact)", clean_text, re.IGNORECASE)
    if match_eligibility:
        elig = match_eligibility.group(1).strip()
        if 5 < len(elig) < 250:
            extracted['eligibility'] = elig
            
    # 3. Description Extraction (First substantial paragraph after abstract/summary)
    match_desc = re.search(r"(?:Summary|Description|Abstract|Background|Objective|Purpose)[:\-]*\s*(.{50,500}?)(?:\n|Eligibility|Funding|\Z)", clean_text, re.IGNORECASE)
    if match_desc:
        extracted['description'] = match_desc.group(1).strip()
    else:
        # Fallback: Just grab the first ~250 chars of the text
        if len(clean_text) > 50:
            extracted['description'] = clean_text[:247] + "..."

    return extracted
