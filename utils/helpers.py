import re
from datetime import datetime
from dateutil import parser
import hashlib

def clean_text(text):
    """Clean and normalize text"""
    if not text:
        return None
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

def extract_funding_amount(text):
    """Extract funding amount from text"""
    if not text:
        return None
    
    # Look for patterns like $1,000,000 or $1M
    patterns = [
        r'\$[\d,]+(?:\.\d{2})?',
        r'\$\d+(?:\.\d+)?[KMB]'
    ]
    
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            return match.group(0)
    
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
