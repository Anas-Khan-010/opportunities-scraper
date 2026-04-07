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
    """Enrich opportunity data with additional information"""
    
    @staticmethod
    def enrich_with_documents(opportunity, document_urls):
        """Download and extract text from opportunity documents"""
        if not document_urls:
            return opportunity
        
        full_text = ""
        
        for url in document_urls[:3]:  # Limit to first 3 documents
            try:
                pdf_content = DocumentParser.download_pdf(url)
                if pdf_content:
                    text = DocumentParser.extract_text_from_pdf(pdf_content)
                    if text:
                        full_text += text + "\n\n"
            except Exception as e:
                logger.error(f"Error processing document {url}: {e}")
                continue
        
        if full_text:
            if not opportunity.get('description'):
                opportunity['description'] = full_text[:2000]
        
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
