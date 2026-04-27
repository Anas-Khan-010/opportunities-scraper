import re
import os
import requests
from PyPDF2 import PdfReader
from io import BytesIO
from utils.logger import logger
from config.settings import config

class DocumentParser:
    """Utility class for parsing documents"""
    
    @staticmethod
    def download_pdf(url, filename=None):
        """Download PDF from URL"""
        try:
            response = requests.get(url, timeout=30)
            response.raise_for_status()
            
            if filename:
                filepath = os.path.join(config.DOWNLOADS_DIR, filename)
                with open(filepath, 'wb') as f:
                    f.write(response.content)
                return filepath
            
            return BytesIO(response.content)
            
        except Exception as e:
            logger.error(f"Error downloading PDF from {url}: {e}")
            return None
    
    @staticmethod
    def extract_text_from_pdf(pdf_source):
        """Extract text from PDF file or BytesIO object"""
        try:
            if isinstance(pdf_source, str):
                # File path
                reader = PdfReader(pdf_source)
            else:
                # BytesIO object
                reader = PdfReader(pdf_source)
            
            text = ""
            for page in reader.pages:
                text += page.extract_text() + "\n"
            
            return text.strip()
            
        except Exception as e:
            logger.error(f"Error extracting text from PDF: {e}")
            return None
    
    @staticmethod
    def extract_email(text):
        """Extract email addresses from text"""
        if not text:
            return []
        
        email_pattern = r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b'
        return re.findall(email_pattern, text)
    
    @staticmethod
    def extract_phone(text):
        """Extract phone numbers from text"""
        if not text:
            return []
        
        phone_pattern = r'\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}'
        return re.findall(phone_pattern, text)
    
    @staticmethod
    def extract_urls(text):
        """Extract URLs from text"""
        if not text:
            return []
        
        url_pattern = r'http[s]?://(?:[a-zA-Z]|[0-9]|[$-_@.&+]|[!*\\(\\),]|(?:%[0-9a-fA-F][0-9a-fA-F]))+'
        return re.findall(url_pattern, text)


class OpportunityEnricher:
    """Enrich opportunity data with additional information from PDFs."""

    _ELIGIBILITY_HEADERS = re.compile(
        r'(?:^|\n)\s*'
        r'(?:eligib(?:le|ility)\s*(?:requirements?|criteria)?'
        r'|who\s+(?:may|can|is\s+eligible\s+to)\s+apply'
        r'|qualified\s+applicants?'
        r'|applicant\s+(?:eligibility|requirements?|qualifications?)'
        r'|eligible\s+(?:entities|organizations|applicants?|respondents?)'
        r'|minimum\s+qualifications?'
        r'|vendor\s+(?:requirements?|qualifications?)'
        r'|contractor\s+qualifications?'
        r'|target\s+population'
        r'|mandatory\s+requirements?'
        r'|qualification\s+(?:requirements?|criteria)'
        r'|proposer\s+qualifications?'
        r'|respondent\s+qualifications?'
        r'|offeror\s+qualifications?'
        r'|evaluation\s+criteria'
        r'|selection\s+criteria'
        r'|statement\s+of\s+qualifications?'
        r'|required\s+qualifications?'
        r'|scope\s+of\s+work)'
        r'\s*[:\-—]?\s*',
        re.IGNORECASE,
    )

    _ELIGIBILITY_FALLBACK = re.compile(
        r'(?:must\s+be|shall\s+be|required\s+to|qualified\s+to|'
        r'applicants?\s+must|respondents?\s+must|offerors?\s+must|'
        r'bidders?\s+must|proposers?\s+must)',
        re.IGNORECASE,
    )

    _OPP_NUMBER_PATTERNS = re.compile(
        r'(?:'
        r'(?:RFP|RFA|RFQ|RFI|IFB|ITB)\s*[#:]\s*([\w\-\.\/]+)'
        r'|(?:NOFO|NOFA)\s*[#:\-]\s*([\w\-\.]+)'
        r'|(?:Solicitation|Contract|Grant|Bid)\s*(?:No\.?|Number|#)\s*[:\s]*([\w\-\.\/]+)'
        r'|(?:CFDA|ALN)\s*[#:\s]*(\d{2}\.\d{3})'
        r'|(?:Opportunity\s*(?:Number|ID|#))\s*[:\s]*([\w\-\.]+)'
        r'|(HHS-\d{4}-[\w\-]+)'
        r')',
        re.IGNORECASE,
    )

    @staticmethod
    def _extract_eligibility(text):
        """Pull the first eligibility-related paragraph from raw text."""
        if not text:
            return None
        m = OpportunityEnricher._ELIGIBILITY_HEADERS.search(text)
        if m:
            start = m.end()
            chunk = text[start:start + 1500]
            end_match = re.search(r'\n\s*\n|\n[A-Z][A-Za-z ]{3,}:', chunk)
            if end_match:
                chunk = chunk[:end_match.start()]
            chunk = chunk.strip()
            if chunk:
                return chunk[:1000]

        fb = OpportunityEnricher._ELIGIBILITY_FALLBACK.search(text[:5000])
        if fb:
            start = max(0, fb.start() - 20)
            raw = text[start:start + 800]
            line_start = raw.find('\n')
            if line_start >= 0 and line_start < 30:
                raw = raw[line_start + 1:]
            end_match = re.search(r'\n\s*\n', raw)
            if end_match:
                raw = raw[:end_match.start()]
            raw = raw.strip()
            if raw and len(raw) > 20:
                return raw[:1000]

        return None

    @staticmethod
    def _extract_opp_number(text):
        """Extract a government opportunity/solicitation number from text."""
        if not text:
            return None
        search_region = text[:3000]
        m = OpportunityEnricher._OPP_NUMBER_PATTERNS.search(search_region)
        if m:
            for g in m.groups():
                if g:
                    return g.strip().rstrip('.,;:')
        return None

    @staticmethod
    def enrich_with_documents(opportunity, document_urls=None):
        """Download PDFs and backfill empty description, eligibility, and funding_amount."""
        from utils.helpers import extract_funding_amount

        urls = document_urls or opportunity.get('document_urls') or []
        if not urls:
            return opportunity

        full_text = ""

        for url in urls[:3]:
            try:
                pdf_content = DocumentParser.download_pdf(url)
                if pdf_content:
                    text = DocumentParser.extract_text_from_pdf(pdf_content)
                    if text:
                        full_text += text + "\n\n"
            except Exception as e:
                logger.error(f"Error processing document {url}: {e}")
                continue

        if not full_text:
            return opportunity

        if not opportunity.get('description'):
            opportunity['description'] = full_text[:2000]

        if not opportunity.get('eligibility'):
            eligibility = OpportunityEnricher._extract_eligibility(full_text)
            if eligibility:
                opportunity['eligibility'] = eligibility

        if not opportunity.get('funding_amount'):
            amount = extract_funding_amount(full_text)
            if amount:
                opportunity['funding_amount'] = amount

        if not opportunity.get('opportunity_number'):
            opp_num = OpportunityEnricher._extract_opp_number(full_text)
            if opp_num:
                opportunity['opportunity_number'] = opp_num

        return opportunity
    
    @staticmethod
    def validate_opportunity(opportunity):
        """Validate opportunity data before insertion"""
        required_fields = ['title', 'source', 'source_url']
        
        for field in required_fields:
            if not opportunity.get(field):
                logger.warning(f"Missing required field: {field}")
                return False
        
        # Ensure title is not too long
        if len(opportunity['title']) > 500:
            opportunity['title'] = opportunity['title'][:500]
        
        # Ensure description is not too long
        if opportunity.get('description') and len(opportunity['description']) > 10000:
            opportunity['description'] = opportunity['description'][:10000]
        
        return True
