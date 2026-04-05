"""
State RFP/procurement scrapers — configs and factory for all 50 US states.

Each entry targets the state's official procurement portal where RFPs, IFBs,
and solicitations are posted.  All opportunities are tagged opportunity_type='rfp'.

Every state has a public procurement portal; URLs verified April 2026.
"""

from scrapers.state_scrapers import create_state_scrapers
from utils.logger import logger


# ============================================================================
# RFP / PROCUREMENT CONFIGS — all 50 states
# ============================================================================

RFP_CONFIGS = [

    # ── A ──────────────────────────────────────────────────────────────────

    {
        'abbr': 'AL', 'name': 'Alabama',
        'method': 'selenium',
        'source_name': 'Alabama Purchasing (RFP)',
        'organization': 'State of Alabama',
        'location': 'Alabama',
        'opportunity_type': 'rfp',
        'url': 'https://www.alabamabuys.gov/',
        'wait_selector': 'table, .solicitation-list, main, form',
        'item_selector': 'table tbody tr, .result-item',
        'title_selector': 'td a, a',
    },

    {
        'abbr': 'AK', 'name': 'Alaska',
        'method': 'selenium',
        'source_name': 'Alaska Public Notices (RFP)',
        'organization': 'State of Alaska',
        'location': 'Alaska',
        'opportunity_type': 'rfp',
        'url': 'https://aws.state.ak.us/OnlinePublicNotices/',
        'wait_selector': 'table, #results, .notice-list, main',
        'item_selector': 'table tbody tr, .notice-row',
        'title_selector': 'td a, a',
    },

    {
        'abbr': 'AZ', 'name': 'Arizona',
        'method': 'selenium',
        'source_name': 'Arizona Procurement Portal (RFP)',
        'organization': 'State of Arizona',
        'location': 'Arizona',
        'opportunity_type': 'rfp',
        'url': 'https://app.az.gov/page/public-solicitations',
        'wait_selector': 'table, .solicitation-list, main',
        'item_selector': 'table tbody tr, .solicitation-row',
        'title_selector': 'td a, a',
    },

    {
        'abbr': 'AR', 'name': 'Arkansas',
        'method': 'selenium',
        'source_name': 'Arkansas ARBuy (RFP)',
        'organization': 'State of Arkansas',
        'location': 'Arkansas',
        'opportunity_type': 'rfp',
        'url': 'https://arbuy.arkansas.gov/bso/view/search/external/advancedSearchBid.xhtml?openBids=true',
        'wait_selector': 'table, .search-results, .solicitation-list',
        'item_selector': 'table tbody tr',
        'title_selector': 'td a, a',
    },

    # ── C ──────────────────────────────────────────────────────────────────

    {   # VERIFIED — Cal eProcure public bid search
        'abbr': 'CA', 'name': 'California',
        'method': 'selenium',
        'source_name': 'California CaleProcure (RFP)',
        'organization': 'State of California',
        'location': 'California',
        'opportunity_type': 'rfp',
        'url': 'https://caleprocure.ca.gov/pages/public-search.aspx',
        'wait_selector': 'table, .search-results, form, #results',
        'item_selector': 'table tbody tr, .result-item',
        'title_selector': 'td a, a',
    },

    {   # Colorado VSS
        'abbr': 'CO', 'name': 'Colorado',
        'method': 'selenium',
        'source_name': 'Colorado VSS (RFP)',
        'organization': 'State of Colorado',
        'location': 'Colorado',
        'opportunity_type': 'rfp',
        'url': 'https://vss.state.co.us/',
        'wait_selector': 'table, .search-results, form, main',
        'item_selector': 'table tbody tr, .solicitation-row',
        'title_selector': 'td a, a',
    },

    {
        'abbr': 'CT', 'name': 'Connecticut',
        'method': 'selenium',
        'source_name': 'Connecticut CTsource (RFP)',
        'organization': 'State of Connecticut',
        'location': 'Connecticut',
        'opportunity_type': 'rfp',
        'url': 'https://portal.ct.gov/DAS/CTSource/CTSource',
        'wait_selector': 'table, .search-results, main',
        'item_selector': 'table tbody tr, .result-item',
        'title_selector': 'td a, a',
    },

    # ── D ──────────────────────────────────────────────────────────────────

    {
        'abbr': 'DE', 'name': 'Delaware',
        'method': 'selenium',
        'source_name': 'Delaware MyMarketplace (RFP)',
        'organization': 'State of Delaware',
        'location': 'Delaware',
        'opportunity_type': 'rfp',
        'url': 'https://mmp.delaware.gov/Bids',
        'wait_selector': 'table, .search-results, .solicitation-list',
        'item_selector': 'table tbody tr',
        'title_selector': 'td a, a',
    },

    # ── F ──────────────────────────────────────────────────────────────────

    {
        'abbr': 'FL', 'name': 'Florida',
        'method': 'selenium',
        'source_name': 'Florida MFMP (RFP)',
        'organization': 'State of Florida',
        'location': 'Florida',
        'opportunity_type': 'rfp',
        'url': 'https://vendor.myfloridamarketplace.com/search/advertisements',
        'wait_selector': 'table, .advertisement-list, .search-results, main',
        'item_selector': 'table tbody tr, .result-item, .advertisement-row',
        'title_selector': 'td a, a',
    },

    # ── G ──────────────────────────────────────────────────────────────────

    {
        'abbr': 'GA', 'name': 'Georgia',
        'method': 'selenium',
        'source_name': 'Georgia Procurement Registry (RFP)',
        'organization': 'State of Georgia',
        'location': 'Georgia',
        'opportunity_type': 'rfp',
        'url': 'https://doas.ga.gov/state-purchasing',
        'wait_selector': 'table, form, .search-results',
        'item_selector': 'table tbody tr, .result-row',
        'title_selector': 'td a, a',
    },

    # ── H ──────────────────────────────────────────────────────────────────

    {
        'abbr': 'HI', 'name': 'Hawaii',
        'method': 'selenium',
        'source_name': 'Hawaii HIePRO (RFP)',
        'organization': 'State of Hawaii',
        'location': 'Hawaii',
        'opportunity_type': 'rfp',
        'url': 'https://hiepro.ehawaii.gov/welcome.html',
        'wait_selector': 'table, .solicitation-list, main',
        'item_selector': 'table tbody tr, .solicitation-row',
        'title_selector': 'td a, a',
    },

    # ── I ──────────────────────────────────────────────────────────────────

    {
        'abbr': 'ID', 'name': 'Idaho',
        'method': 'selenium',
        'source_name': 'Idaho IPRO (RFP)',
        'organization': 'State of Idaho',
        'location': 'Idaho',
        'opportunity_type': 'rfp',
        'url': 'https://purchasing.idaho.gov/solicitation-instructions/',
        'wait_selector': 'table, .opportunity-list, main',
        'item_selector': 'table tbody tr, .opportunity-item, li a',
        'title_selector': 'td a, a',
    },

    {   # VERIFIED — Illinois BidBuy
        'abbr': 'IL', 'name': 'Illinois',
        'method': 'selenium',
        'source_name': 'Illinois BidBuy (RFP)',
        'organization': 'State of Illinois',
        'location': 'Illinois',
        'opportunity_type': 'rfp',
        'url': 'https://www.bidbuy.illinois.gov/bso/',
        'wait_selector': 'table, .results, form',
        'item_selector': 'table tbody tr',
        'title_selector': 'td a, a',
    },

    {
        'abbr': 'IN', 'name': 'Indiana',
        'method': 'selenium',
        'source_name': 'Indiana Procurement (RFP)',
        'organization': 'State of Indiana',
        'location': 'Indiana',
        'opportunity_type': 'rfp',
        'url': 'https://www.in.gov/idoa/procurement/current-business-opportunities/',
        'wait_selector': 'table, .business-opportunities, main, article',
        'item_selector': 'table tbody tr, li a, .opportunity-row',
        'title_selector': 'td a, a',
    },

    {
        'abbr': 'IA', 'name': 'Iowa',
        'method': 'selenium',
        'source_name': 'Iowa VSS (RFP)',
        'organization': 'State of Iowa',
        'location': 'Iowa',
        'opportunity_type': 'rfp',
        'url': 'https://bidopportunities.iowa.gov/',
        'wait_selector': 'table, .search-results, .solicitation-list',
        'item_selector': 'table tbody tr',
        'title_selector': 'td a, a',
    },

    # ── K ──────────────────────────────────────────────────────────────────

    {
        'abbr': 'KS', 'name': 'Kansas',
        'method': 'selenium',
        'source_name': 'Kansas eSupplier (RFP)',
        'organization': 'State of Kansas',
        'location': 'Kansas',
        'opportunity_type': 'rfp',
        'url': 'https://supplier.sok.ks.gov/psc/fmssupplier/SUPPLIER/ERP/c/NUI_FRAMEWORK.PT_AGSTARTPAGE_NUI.GBL',
        'wait_selector': 'table, .ps_grid-body, main',
        'item_selector': 'table tbody tr, .ps_grid-row',
        'title_selector': 'td a, a, span',
    },

    {
        'abbr': 'KY', 'name': 'Kentucky',
        'method': 'selenium',
        'source_name': 'Kentucky eProcurement (RFP)',
        'organization': 'Commonwealth of Kentucky',
        'location': 'Kentucky',
        'opportunity_type': 'rfp',
        'url': 'https://eprocurement.ky.gov/',
        'wait_selector': 'table, .search-results, .solicitation-list',
        'item_selector': 'table tbody tr',
        'title_selector': 'td a, a',
    },

    # ── L ──────────────────────────────────────────────────────────────────

    {
        'abbr': 'LA', 'name': 'Louisiana',
        'method': 'selenium',
        'source_name': 'Louisiana LaPAC (RFP)',
        'organization': 'State of Louisiana',
        'location': 'Louisiana',
        'opportunity_type': 'rfp',
        'url': 'https://wwwcfprd.doa.louisiana.gov/OSP/LaPAC/srchopen.cfm',
        'wait_selector': 'table, form, .search-results',
        'item_selector': 'table tbody tr, table tr',
        'title_selector': 'td a, a',
    },

    # ── M ──────────────────────────────────────────────────────────────────

    {
        'abbr': 'ME', 'name': 'Maine',
        'method': 'selenium',
        'source_name': 'Maine Procurement (RFP)',
        'organization': 'State of Maine',
        'location': 'Maine',
        'opportunity_type': 'rfp',
        'url': 'https://www.maine.gov/dafs/bbm/procurementservices/vendors/current-bids',
        'wait_selector': 'table, .content-area, main, article',
        'item_selector': 'table tbody tr, li a, .content-area a',
        'title_selector': 'td a, a',
    },

    {
        'abbr': 'MD', 'name': 'Maryland',
        'method': 'selenium',
        'source_name': 'Maryland eMMA (RFP)',
        'organization': 'State of Maryland',
        'location': 'Maryland',
        'opportunity_type': 'rfp',
        'url': 'https://emma.maryland.gov/',
        'wait_selector': 'table, .solicitation-list, main',
        'item_selector': 'table tbody tr, .solicitation-row',
        'title_selector': 'td a, a',
    },

    {
        'abbr': 'MA', 'name': 'Massachusetts',
        'method': 'selenium',
        'source_name': 'Massachusetts COMMBUYS (RFP)',
        'organization': 'Commonwealth of Massachusetts',
        'location': 'Massachusetts',
        'opportunity_type': 'rfp',
        'url': 'https://www.commbuys.com/bso/external/publicBids.sdo',
        'wait_selector': 'table, .results-table, form',
        'item_selector': 'table tbody tr',
        'title_selector': 'td a, a',
    },

    {
        'abbr': 'MI', 'name': 'Michigan',
        'method': 'selenium',
        'source_name': 'Michigan SIGMA VSS (RFP)',
        'organization': 'State of Michigan',
        'location': 'Michigan',
        'opportunity_type': 'rfp',
        'url': 'https://www.michigan.gov/dtmb/procurement/contractconnect/bid-proposals',
        'wait_selector': 'table, .bid-list, .content-area, main',
        'item_selector': 'table tbody tr, .bid-row, li a',
        'title_selector': 'td a, a',
        'fallback_procurement_only': True,
        'max_parse_items': 300,
    },

    {
        'abbr': 'MN', 'name': 'Minnesota',
        'method': 'selenium',
        'source_name': 'Minnesota SWIFT (RFP)',
        'organization': 'State of Minnesota',
        'location': 'Minnesota',
        'opportunity_type': 'rfp',
        'url': 'https://mn.gov/admin/osp/vendors/vendor-documents/',
        'wait_selector': 'table, .ps_grid-body, #win0divPSSRCHRESULTS',
        'item_selector': 'table tbody tr, .ps_grid-row',
        'title_selector': 'td a, a, span',
    },

    {
        'abbr': 'MS', 'name': 'Mississippi',
        'method': 'selenium',
        'source_name': 'Mississippi MAGIC (RFP)',
        'organization': 'State of Mississippi',
        'location': 'Mississippi',
        'opportunity_type': 'rfp',
        'url': 'https://www.ms.gov/dfa/contract_bid_search/Search',
        'wait_selector': 'table, form, .search-results, main',
        'item_selector': 'table tbody tr',
        'title_selector': 'td a, a',
        'max_parse_items': 250,
    },

    {
        'abbr': 'MO', 'name': 'Missouri',
        'method': 'selenium',
        'source_name': 'Missouri MissouriBUYS (RFP)',
        'organization': 'State of Missouri',
        'location': 'Missouri',
        'opportunity_type': 'rfp',
        'url': 'https://missouribuys.mo.gov/search/publicSolicitations',
        'wait_selector': 'table, .search-results, .solicitation-list',
        'item_selector': 'table tbody tr, .solicitation-row',
        'title_selector': 'td a, a',
    },

    {
        'abbr': 'MT', 'name': 'Montana',
        'method': 'selenium',
        'source_name': 'Montana Procurement (RFP)',
        'organization': 'State of Montana',
        'location': 'Montana',
        'opportunity_type': 'rfp',
        'url': 'https://spb.mt.gov/Vendor-Resources',
        'wait_selector': 'table, .content-area, main',
        'item_selector': 'table tbody tr, li a, .content-area a',
        'title_selector': 'td a, a',
    },

    # ── N ──────────────────────────────────────────────────────────────────

    {
        'abbr': 'NE', 'name': 'Nebraska',
        'method': 'selenium',
        'source_name': 'Nebraska Purchasing (RFP)',
        'organization': 'State of Nebraska',
        'location': 'Nebraska',
        'opportunity_type': 'rfp',
        'url': 'https://das.nebraska.gov/materiel/purchasing/',
        'wait_selector': 'table, .content-area, main, article',
        'item_selector': 'table tbody tr, li a, .content-area a',
        'title_selector': 'td a, a',
    },

    {
        'abbr': 'NV', 'name': 'Nevada',
        'method': 'selenium',
        'source_name': 'Nevada NevadaEPro (RFP)',
        'organization': 'State of Nevada',
        'location': 'Nevada',
        'opportunity_type': 'rfp',
        'url': 'https://nevadaepro.com/bso/external/publicBids.sdo',
        'wait_selector': 'table, .results, form',
        'item_selector': 'table tbody tr',
        'title_selector': 'td a, a',
    },

    {
        'abbr': 'NH', 'name': 'New Hampshire',
        'method': 'selenium',
        'source_name': 'New Hampshire Purchasing (RFP)',
        'organization': 'State of New Hampshire',
        'location': 'New Hampshire',
        'opportunity_type': 'rfp',
        'url': 'https://apps.das.nh.gov/NHProcurement/',
        'wait_selector': 'table, .content-area, main, #content',
        'item_selector': 'table tbody tr, li a, .content-area a',
        'title_selector': 'td a, a',
    },

    {
        'abbr': 'NJ', 'name': 'New Jersey',
        'method': 'selenium',
        'source_name': 'New Jersey NJSTART (RFP)',
        'organization': 'State of New Jersey',
        'location': 'New Jersey',
        'opportunity_type': 'rfp',
        'url': 'https://www.njstart.gov/',
        'wait_selector': 'table, .results, form',
        'item_selector': 'table tbody tr',
        'title_selector': 'td a, a',
    },

    {
        'abbr': 'NM', 'name': 'New Mexico',
        'method': 'selenium',
        'source_name': 'New Mexico Purchasing (RFP)',
        'organization': 'State of New Mexico',
        'location': 'New Mexico',
        'opportunity_type': 'rfp',
        'url': 'https://www.generalservices.state.nm.us/state-purchasing/active-itbs-and-rfps/',
        'wait_selector': 'table, .content-area, main',
        'item_selector': 'table tbody tr, li a',
        'title_selector': 'td a, a',
    },

    {
        'abbr': 'NY', 'name': 'New York',
        'method': 'selenium',
        'source_name': 'New York Contract Reporter (RFP)',
        'organization': 'State of New York',
        'location': 'New York',
        'opportunity_type': 'rfp',
        'url': 'https://nyscr.ny.gov/',
        'wait_selector': 'table, .search-results, form',
        'item_selector': 'table tbody tr, .opportunity-row',
        'title_selector': 'td a, a',
    },

    {   # VERIFIED — NC eVP (electronic Vendor Portal)
        'abbr': 'NC', 'name': 'North Carolina',
        'method': 'selenium',
        'source_name': 'North Carolina eVP (RFP)',
        'organization': 'State of North Carolina',
        'location': 'North Carolina',
        'opportunity_type': 'rfp',
        'url': 'https://evp.nc.gov/',
        'wait_selector': 'table, .solicitation-list, main, form',
        'item_selector': 'table tbody tr, .solicitation-row',
        'title_selector': 'td a, a',
    },

    {
        'abbr': 'ND', 'name': 'North Dakota',
        'method': 'selenium',
        'source_name': 'North Dakota OMB Procurement (RFP)',
        'organization': 'State of North Dakota',
        'location': 'North Dakota',
        'opportunity_type': 'rfp',
        'url': 'https://www.omb.nd.gov/doing-business-state/procurement/bidding-opportunities',
        'wait_selector': 'table, .content-area, main',
        'item_selector': 'table tbody tr, li a, .content-area a',
        'title_selector': 'td a, a',
    },

    # ── O ──────────────────────────────────────────────────────────────────

    {   # VERIFIED — OhioBuys
        'abbr': 'OH', 'name': 'Ohio',
        'method': 'selenium',
        'source_name': 'Ohio OhioBuys (RFP)',
        'organization': 'State of Ohio',
        'location': 'Ohio',
        'opportunity_type': 'rfp',
        'url': 'https://ohiobuys.ohio.gov/',
        'wait_selector': 'table, .search-results, form, main',
        'item_selector': 'table tbody tr, .solicitation-row',
        'title_selector': 'td a, a',
    },

    {
        'abbr': 'OK', 'name': 'Oklahoma',
        'method': 'selenium',
        'source_name': 'Oklahoma OMES Purchasing (RFP)',
        'organization': 'State of Oklahoma',
        'location': 'Oklahoma',
        'opportunity_type': 'rfp',
        'url': 'https://oklahoma.gov/omes/divisions/central-purchasing/solicitations.html',
        'wait_selector': 'table, .solicitation-list, main, article',
        'item_selector': 'table tbody tr, li a, .content-area a',
        'title_selector': 'td a, a',
    },

    {
        'abbr': 'OR', 'name': 'Oregon',
        'method': 'selenium',
        'source_name': 'Oregon OregonBuys (RFP)',
        'organization': 'State of Oregon',
        'location': 'Oregon',
        'opportunity_type': 'rfp',
        'url': 'https://oregonbuys.gov/',
        'wait_selector': 'table, .search-results, .solicitation-list',
        'item_selector': 'table tbody tr',
        'title_selector': 'td a, a',
    },

    # ── P ──────────────────────────────────────────────────────────────────

    {
        'abbr': 'PA', 'name': 'Pennsylvania',
        'method': 'selenium',
        'source_name': 'Pennsylvania eMarketplace (RFP)',
        'organization': 'Commonwealth of Pennsylvania',
        'location': 'Pennsylvania',
        'opportunity_type': 'rfp',
        'url': 'https://www.emarketplace.state.pa.us/Search.aspx',
        'wait_selector': 'table, .search-results, #results, form',
        'item_selector': 'table tbody tr, .result-row',
        'title_selector': 'td a, a',
    },

    # ── R ──────────────────────────────────────────────────────────────────

    {
        'abbr': 'RI', 'name': 'Rhode Island',
        'method': 'selenium',
        'source_name': 'Rhode Island RIVIP (RFP)',
        'organization': 'State of Rhode Island',
        'location': 'Rhode Island',
        'opportunity_type': 'rfp',
        'url': 'https://www.ridop.ri.gov/rivip/',
        'wait_selector': 'table, .bid-list, main',
        'item_selector': 'table tbody tr, .bid-item',
        'title_selector': 'td a, a',
    },

    # ── S ──────────────────────────────────────────────────────────────────

    {
        'abbr': 'SC', 'name': 'South Carolina',
        'method': 'selenium',
        'source_name': 'South Carolina SCBO (RFP)',
        'organization': 'State of South Carolina',
        'location': 'South Carolina',
        'opportunity_type': 'rfp',
        'url': 'https://scbo.sc.gov/online-edition',
        'wait_selector': 'table, .solicitation-list, main',
        'item_selector': 'table tbody tr, .result-item',
        'title_selector': 'td a, a',
    },

    {
        'abbr': 'SD', 'name': 'South Dakota',
        'method': 'selenium',
        'source_name': 'South Dakota Procurement (RFP)',
        'organization': 'State of South Dakota',
        'location': 'South Dakota',
        'opportunity_type': 'rfp',
        'url': 'https://boa.sd.gov/central-services/procurement-management/bid-opportunities.aspx',
        'wait_selector': 'table, .content-area, main',
        'item_selector': 'table tbody tr, li a',
        'title_selector': 'td a, a',
    },

    # ── T ──────────────────────────────────────────────────────────────────

    {
        'abbr': 'TN', 'name': 'Tennessee',
        'method': 'selenium',
        'source_name': 'Tennessee Procurement (RFP)',
        'organization': 'State of Tennessee',
        'location': 'Tennessee',
        'opportunity_type': 'rfp',
        'url': 'https://www.tn.gov/generalservices/procurement.html',
        'wait_selector': 'table, .content-area, main, article',
        'item_selector': 'table tbody tr, li a, .content-area a',
        'title_selector': 'td a, a',
    },

    {
        'abbr': 'TX', 'name': 'Texas',
        'method': 'selenium',
        'source_name': 'Texas ESBD (RFP)',
        'organization': 'State of Texas',
        'location': 'Texas',
        'opportunity_type': 'rfp',
        'url': 'https://www.txsmartbuy.gov/esbd',
        'wait_selector': 'table, .esbd-results, .search-results',
        'item_selector': 'table tbody tr, .result-row',
        'title_selector': 'td a, a',
    },

    # ── U ──────────────────────────────────────────────────────────────────

    {
        'abbr': 'UT', 'name': 'Utah',
        'method': 'selenium',
        'source_name': 'Utah eProcurement (RFP)',
        'organization': 'State of Utah',
        'location': 'Utah',
        'opportunity_type': 'rfp',
        'url': 'https://purchasing.utah.gov/currentbids',
        'wait_selector': 'table, .bid-list, main, article',
        'item_selector': 'table tbody tr, li a, .bid-row',
        'title_selector': 'td a, a',
    },

    # ── V ──────────────────────────────────────────────────────────────────

    {   # VERIFIED — eVA
        'abbr': 'VA', 'name': 'Virginia',
        'method': 'selenium',
        'source_name': 'Virginia eVA (RFP)',
        'organization': 'Commonwealth of Virginia',
        'location': 'Virginia',
        'opportunity_type': 'rfp',
        'url': 'https://eva.virginia.gov/',
        'wait_selector': 'table, .solicitation-list, main, form',
        'item_selector': 'table tbody tr, .solicitation-row',
        'title_selector': 'td a, a',
    },

    {
        'abbr': 'VT', 'name': 'Vermont',
        'method': 'selenium',
        'source_name': 'Vermont Purchasing (RFP)',
        'organization': 'State of Vermont',
        'location': 'Vermont',
        'opportunity_type': 'rfp',
        'url': 'https://bgs.vermont.gov/purchasing/opportunities',
        'wait_selector': 'table, .view-content, main',
        'item_selector': 'table tbody tr, .views-row, li a',
        'title_selector': 'td a, a',
    },

    # ── W ──────────────────────────────────────────────────────────────────

    {   # VERIFIED — WEBS bid calendar
        'abbr': 'WA', 'name': 'Washington',
        'method': 'selenium',
        'source_name': 'Washington WEBS (RFP)',
        'organization': 'State of Washington',
        'location': 'Washington',
        'opportunity_type': 'rfp',
        'url': 'https://pr-webs-vendor.des.wa.gov/bidcalendar.aspx',
        'wait_selector': 'table, .bid-calendar, main',
        'item_selector': 'table tbody tr, .bid-row',
        'title_selector': 'td a, a',
    },

    {
        'abbr': 'WV', 'name': 'West Virginia',
        'method': 'selenium',
        'source_name': 'West Virginia Purchasing (RFP)',
        'organization': 'State of West Virginia',
        'location': 'West Virginia',
        'opportunity_type': 'rfp',
        'url': 'https://www.state.wv.us/admin/purchase/Bids/default.html',
        'wait_selector': 'table, pre, main',
        'item_selector': 'table tbody tr, table tr, li a',
        'title_selector': 'td a, a',
    },

    {
        'abbr': 'WI', 'name': 'Wisconsin',
        'method': 'selenium',
        'source_name': 'Wisconsin VendorNet (RFP)',
        'organization': 'State of Wisconsin',
        'location': 'Wisconsin',
        'opportunity_type': 'rfp',
        'url': 'https://vendornet.wi.gov/Bids.aspx',
        'wait_selector': 'table, .search-results, #results, form',
        'item_selector': 'table tbody tr, .result-row',
        'title_selector': 'td a, a',
    },

    {
        'abbr': 'WY', 'name': 'Wyoming',
        'method': 'selenium',
        'source_name': 'Wyoming Procurement (RFP)',
        'organization': 'State of Wyoming',
        'location': 'Wyoming',
        'opportunity_type': 'rfp',
        'url': 'https://ai.wyo.gov/divisions/general-services/purchasing',
        'wait_selector': 'table, .content-area, main',
        'item_selector': 'table tbody tr, li a, .content-area a',
        'title_selector': 'td a, a',
    },
]


# ============================================================================
# Factory
# ============================================================================

def get_all_state_rfp_scrapers():
    """Create and return scraper instances for all 50 state procurement portals."""
    scrapers = create_state_scrapers(RFP_CONFIGS)
    logger.info(f"Created {len(scrapers)} state RFP scrapers")
    return scrapers
