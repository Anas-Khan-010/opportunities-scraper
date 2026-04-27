"""
Alaska DCRA Grants scraper — Division of Community and Regional Affairs

Scrapes Alaska state grant records from the ArcGIS Feature Service that
backs the official DCRA Grants Database portal.  Returns ~24,000 grant
records with rich metadata including award amounts, grant status, dates,
recipients, and administrators.

Source:  https://experience.arcgis.com/experience/d7158093678a4339a6c16357ae544b91
API:     https://services2.arcgis.com/0DjevcWawQ1dy3il/arcgis/rest/services/DCRAGrants_Hosted/FeatureServer/0
"""

from datetime import datetime, timezone

from scrapers.base_scraper import BaseScraper
from config.settings import config
from utils.logger import logger
from utils.helpers import clean_text, categorize_opportunity


class AlaskaDCRAGrantsScraper(BaseScraper):
    """Scrapes Alaska DCRA grants from the ArcGIS Feature Service REST API."""

    QUERY_URL = (
        "https://services2.arcgis.com/0DjevcWawQ1dy3il"
        "/arcgis/rest/services/DCRAGrants_Hosted/FeatureServer/0/query"
    )
    PAGE_SIZE = 200
    OUT_FIELDS = (
        "ObjectID,CommunityName,GrantRecipient,ProjectName,GrantNumber,"
        "AwardYear,GrantStatus,GrantType,GrantAdministrator,AwardAmount,"
        "AmendedAmount,GrantAmount,ApprovedReimbursements,RemainingAmount,"
        "StartDate,EndDate,LapseDate,CloseOutDate,AsOfDate,"
        "HasAuditCFSDocument,HasBudgetDocument,"
        "LegislativeBill,HouseDistrict,SenateDistrict"
    )
    PORTAL_URL = (
        "https://experience.arcgis.com/experience/"
        "d7158093678a4339a6c16357ae544b91"
    )

    def __init__(self):
        super().__init__("Alaska DCRA Grants")
        self.max_pages = getattr(config, "AK_DCRA_MAX_PAGES", 200)

    def scrape(self):
        logger.info(f"Starting {self.source_name} scraper (ArcGIS API)...")
        self._fetch_total()
        self._scrape_pages()
        self.log_summary()
        return self.opportunities

    def _fetch_total(self):
        """Log the total record count so we know what to expect."""
        try:
            resp = self.fetch_page(self.QUERY_URL, params={
                "where": "1=1",
                "returnCountOnly": "true",
                "f": "json",
            })
            if resp:
                total = resp.json().get("count", "?")
                logger.info(f"Alaska DCRA: {total} total records in API")
        except Exception:
            pass

    def _scrape_pages(self):
        offset = 0
        page = 0

        while page < self.max_pages:
            params = {
                "where": "1=1",
                "outFields": self.OUT_FIELDS,
                "resultOffset": str(offset),
                "resultRecordCount": str(self.PAGE_SIZE),
                "orderByFields": "ObjectID ASC",
                "f": "json",
            }
            try:
                resp = self.fetch_page(self.QUERY_URL, params=params)
                if not resp:
                    break

                data = resp.json()
                features = data.get("features", [])
                if not features:
                    break

                for feat in features:
                    opp = self.parse_opportunity(feat)
                    if opp:
                        self.add_opportunity(opp)
                    if self.reached_limit():
                        break

                exceeded = data.get("exceededTransferLimit", False)
                logger.info(
                    f"  Page {page + 1}: fetched {len(features)} records "
                    f"(offset {offset}), running total: {len(self.opportunities)}"
                )

                if self.reached_limit() or not exceeded:
                    break

                offset += self.PAGE_SIZE
                page += 1

            except Exception as e:
                logger.error(f"Error at offset {offset}: {e}")
                break

    GRANT_TYPE_ELIGIBILITY = {
        'ELEA': 'Eligible Local Entity Award — local governments, boroughs, and tribal entities in Alaska',
        'Legislative': 'Legislative grant — eligible Alaska municipalities, nonprofits, and community organizations as designated by the Legislature',
        'Matching': 'Matching grant — eligible Alaska communities and organizations that provide matching funds',
        'Competitive': 'Competitive grant — open to eligible Alaska entities via competitive application process',
        'Direct': 'Direct award — designated Alaska entities as specified by the awarding authority',
    }

    def parse_opportunity(self, feature):
        try:
            attrs = feature.get("attributes", {})

            title = clean_text(attrs.get("ProjectName", ""))
            if not title:
                return None

            grant_number = (attrs.get("GrantNumber") or "").strip()
            object_id = attrs.get("ObjectID", "")
            unique_key = grant_number or str(object_id)
            source_url = f"{self.PORTAL_URL}#grant={unique_key}" if unique_key else self.PORTAL_URL

            recipient = clean_text(attrs.get("GrantRecipient", ""))
            community = clean_text(attrs.get("CommunityName", ""))
            grant_type = clean_text(attrs.get("GrantType", ""))
            status = clean_text(attrs.get("GrantStatus", ""))
            administrator = clean_text(attrs.get("GrantAdministrator", ""))
            leg_bill = clean_text(attrs.get("LegislativeBill", ""))

            description_parts = []
            if recipient:
                description_parts.append(f"Recipient: {recipient}")
            if grant_type:
                description_parts.append(f"Type: {grant_type}")
            if status:
                description_parts.append(f"Status: {status}")
            if administrator:
                description_parts.append(f"Administrator: {administrator}")
            if leg_bill:
                description_parts.append(f"Legislative Bill: {leg_bill}")

            award_amount = attrs.get("AwardAmount")
            remaining = attrs.get("RemainingAmount")
            if remaining and award_amount:
                description_parts.append(
                    f"Remaining: ${remaining:,.2f} of ${award_amount:,.2f}"
                )

            has_audit = attrs.get("HasAuditCFSDocument")
            has_budget = attrs.get("HasBudgetDocument")
            if has_audit:
                description_parts.append("Audit/CFS document on file")
            if has_budget:
                description_parts.append("Budget document on file")

            description = "; ".join(description_parts) if description_parts else None

            funding_str = None
            if award_amount is not None:
                funding_str = f"${award_amount:,.2f}"

            eligibility = self.GRANT_TYPE_ELIGIBILITY.get(grant_type)
            if not eligibility and grant_type:
                eligibility = f"{grant_type} grant — eligible Alaska entities"

            start_date = self._epoch_to_datetime(attrs.get("StartDate"))
            end_date = self._epoch_to_datetime(attrs.get("EndDate"))

            doc_urls = [source_url] if unique_key else []

            location = f"Alaska - {community}" if community else "Alaska"
            category = categorize_opportunity(title, description or "")

            return {
                "title": title,
                "organization": "Alaska DCRA" + (f" - {recipient}" if recipient else ""),
                "description": description,
                "eligibility": eligibility,
                "funding_amount": funding_str,
                "deadline": end_date,
                "category": category,
                "location": location,
                "source": self.source_name,
                "source_url": source_url,
                "opportunity_number": grant_number or None,
                "posted_date": start_date,
                "document_urls": doc_urls,
                "opportunity_type": "grant",
            }
        except Exception as e:
            logger.error(f"Error parsing Alaska DCRA record: {e}")
            return None

    @staticmethod
    def _epoch_to_datetime(epoch_ms):
        if not epoch_ms:
            return None
        try:
            return datetime.fromtimestamp(epoch_ms / 1000, tz=timezone.utc)
        except (ValueError, OSError, OverflowError):
            return None


def get_alaska_scrapers():
    """Create scraper instances for Alaska DCRA Grants."""
    return [AlaskaDCRAGrantsScraper()]
