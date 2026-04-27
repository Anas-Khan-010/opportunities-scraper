import re
from datetime import datetime
from dateutil import parser
import hashlib

def clean_text(text, preserve_newlines=False):
    """Clean and normalize text"""
    if not text:
        return None
        
    if preserve_newlines:
        # Strip horizontal whitespace (spaces, tabs) but keep newlines
        text = re.sub(r'[^\S\n]+', ' ', text)
        # Clean up multiple consecutive newlines
        text = re.sub(r'\n\s*\n', '\n', text)
    else:
        # Strip all whitespace including newlines
        text = re.sub(r'\s+', ' ', text)
        
    return text.strip()

def parse_date(date_string):
    """Parse various date formats into datetime object"""
    if not date_string:
        return None
    
    try:
        # Try parsing with dateutil
        return parser.parse(date_string)
    except:
        return None

def extract_funding_amount(text, require_keyword=False):
    """Extract funding amount from text.
    
    Args:
        text (str): The text to search.
        require_keyword (bool): If True, only return amount if preceded by a budget-related keyword.
                              If False, return amount if >= $1,000 OR if preceded by a keyword.
    """
    if not text:
        return None

    # 1. Keyword-based patterns (Highly reliable)
    keyword_patterns = [
        r'(?:not\s+to\s+exceed|NTE|maximum\s+(?:contract\s+)?value|'
        r'estimated\s+budget|total\s+(?:available\s+)?funding|'
        r'award\s+(?:amount|value)|budget\s+(?:amount|ceiling)|'
        r'funding\s+(?:amount|available|level))\s*[:\s]*'
        r'(\$[\d,]+(?:\.\d{2})?)',
    ]
    for pattern in keyword_patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            return match.group(1).rstrip(',.')

    if require_keyword:
        return None

    # 2. General pattern (Fallback for large amounts only)
    patterns = [
        r'\$[\d,]{5,}(?:\.\d{2})?',  # e.g. $10,000 (minimum 5 digits including comma)
        r'\$\d{4,}(?:\.\d{2})?',    # e.g $1000
        r'\$\d+(?:\.\d+)?[KMB]',     # e.g $10K
    ]
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            # Final verification: ignore amounts < 1000 if no keyword
            val = match.group(0).rstrip(',.')
            clean_val = re.sub(r'[^\d.]', '', val)
            try:
                # Handle K/M/B suffixes
                multiplier = 1
                if 'k' in val.lower(): multiplier = 1000
                elif 'm' in val.lower(): multiplier = 1000000
                elif 'b' in val.lower(): multiplier = 1000000000
                
                if float(clean_val) * multiplier >= 1000:
                    return val
            except:
                pass

    return None


def generate_hash(url):
    """Generate unique hash for URL"""
    return hashlib.md5(url.encode()).hexdigest()

def categorize_opportunity(title, description):
    """Auto-categorize opportunity based on keywords"""
    text = f"{title} {description}".lower()
    
    categories = {
        'Research': ['research', 'study', 'investigation', 'science'],
        'Education': ['education', 'school', 'student', 'learning', 'training'],
        'Healthcare': ['health', 'medical', 'hospital', 'patient', 'care'],
        'Technology': ['technology', 'software', 'IT', 'digital', 'cyber'],
        'Infrastructure': ['infrastructure', 'construction', 'building', 'facility'],
        'Environment': ['environment', 'climate', 'energy', 'sustainability', 'green'],
        'Community': ['community', 'social', 'nonprofit', 'outreach'],
        'Arts': ['arts', 'culture', 'museum', 'heritage']
    }
    
    for category, keywords in categories.items():
        if any(keyword in text for keyword in keywords):
            return category
    
    return 'General'
