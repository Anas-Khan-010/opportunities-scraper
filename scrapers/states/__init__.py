"""
State-level scrapers — one module per official government source.
Full 50-state coverage (some states may have network-dependent accessibility).
"""

from scrapers.states.alabama import get_alabama_scrapers
from scrapers.states.alaska import get_alaska_scrapers
from scrapers.states.arizona import get_arizona_scrapers
from scrapers.states.arkansas import get_arkansas_scrapers
from scrapers.states.california import get_california_scrapers
from scrapers.states.colorado import get_colorado_scrapers
from scrapers.states.connecticut import get_connecticut_scrapers
from scrapers.states.delaware import get_delaware_scrapers
from scrapers.states.florida import get_florida_scrapers
from scrapers.states.georgia import get_georgia_scrapers
from scrapers.states.hawaii import get_hawaii_scrapers
from scrapers.states.idaho import get_idaho_scrapers
from scrapers.states.illinois import get_illinois_scrapers
from scrapers.states.indiana import get_indiana_scrapers
from scrapers.states.iowa import get_iowa_scrapers
from scrapers.states.kansas import get_kansas_scrapers
from scrapers.states.kentucky import get_kentucky_scrapers
from scrapers.states.louisiana import get_louisiana_scrapers
from scrapers.states.maine import get_maine_scrapers
from scrapers.states.maryland import get_maryland_scrapers
from scrapers.states.massachusetts import get_massachusetts_scrapers
from scrapers.states.michigan import get_michigan_scrapers
from scrapers.states.minnesota import get_minnesota_scrapers
from scrapers.states.mississippi import get_mississippi_scrapers
from scrapers.states.missouri import get_missouri_scrapers
from scrapers.states.montana import get_montana_scrapers
from scrapers.states.nebraska import get_nebraska_scrapers
from scrapers.states.nevada import get_nevada_scrapers
from scrapers.states.new_hampshire import get_new_hampshire_scrapers
from scrapers.states.new_jersey import get_new_jersey_scrapers
from scrapers.states.new_mexico import get_new_mexico_scrapers
from scrapers.states.new_york import get_ny_grants_scrapers
from scrapers.states.north_carolina import get_nc_evp_scrapers
from scrapers.states.north_dakota import get_north_dakota_scrapers
from scrapers.states.ohio import get_ohio_scrapers
from scrapers.states.oklahoma import get_oklahoma_scrapers
from scrapers.states.oregon import get_oregon_scrapers
from scrapers.states.pennsylvania import get_pennsylvania_scrapers
from scrapers.states.rhode_island import get_rhode_island_scrapers
from scrapers.states.south_carolina import get_south_carolina_scrapers
from scrapers.states.south_dakota import get_south_dakota_scrapers
from scrapers.states.tennessee import get_tennessee_scrapers
from scrapers.states.texas import get_texas_esbd_scrapers
from scrapers.states.utah import get_utah_scrapers
from scrapers.states.vermont import get_vermont_scrapers
from scrapers.states.virginia import get_virginia_scrapers
from scrapers.states.washington import get_washington_scrapers
from scrapers.states.west_virginia import get_west_virginia_scrapers
from scrapers.states.wisconsin import get_wisconsin_scrapers
from scrapers.states.wyoming import get_wyoming_scrapers


def get_all_state_scrapers():
    """Return all state scraper instances (50-state coverage)."""
    scrapers = []
    scrapers.extend(get_alabama_scrapers())
    scrapers.extend(get_alaska_scrapers())
    scrapers.extend(get_arizona_scrapers())
    scrapers.extend(get_arkansas_scrapers())
    scrapers.extend(get_california_scrapers())
    scrapers.extend(get_colorado_scrapers())
    scrapers.extend(get_connecticut_scrapers())
    scrapers.extend(get_delaware_scrapers())
    scrapers.extend(get_florida_scrapers())
    scrapers.extend(get_georgia_scrapers())
    scrapers.extend(get_hawaii_scrapers())
    scrapers.extend(get_idaho_scrapers())
    scrapers.extend(get_illinois_scrapers())
    scrapers.extend(get_indiana_scrapers())
    scrapers.extend(get_iowa_scrapers())
    scrapers.extend(get_kansas_scrapers())
    scrapers.extend(get_kentucky_scrapers())
    scrapers.extend(get_louisiana_scrapers())
    scrapers.extend(get_maine_scrapers())
    scrapers.extend(get_maryland_scrapers())
    scrapers.extend(get_massachusetts_scrapers())
    scrapers.extend(get_michigan_scrapers())
    scrapers.extend(get_minnesota_scrapers())
    scrapers.extend(get_mississippi_scrapers())
    scrapers.extend(get_missouri_scrapers())
    scrapers.extend(get_montana_scrapers())
    scrapers.extend(get_nebraska_scrapers())
    scrapers.extend(get_nevada_scrapers())
    scrapers.extend(get_new_hampshire_scrapers())
    scrapers.extend(get_new_jersey_scrapers())
    scrapers.extend(get_new_mexico_scrapers())
    scrapers.extend(get_ny_grants_scrapers())
    scrapers.extend(get_nc_evp_scrapers())
    scrapers.extend(get_north_dakota_scrapers())
    scrapers.extend(get_ohio_scrapers())
    scrapers.extend(get_oklahoma_scrapers())
    scrapers.extend(get_oregon_scrapers())
    scrapers.extend(get_pennsylvania_scrapers())
    scrapers.extend(get_rhode_island_scrapers())
    scrapers.extend(get_south_carolina_scrapers())
    scrapers.extend(get_south_dakota_scrapers())
    scrapers.extend(get_tennessee_scrapers())
    scrapers.extend(get_texas_esbd_scrapers())
    scrapers.extend(get_utah_scrapers())
    scrapers.extend(get_vermont_scrapers())
    scrapers.extend(get_virginia_scrapers())
    scrapers.extend(get_washington_scrapers())
    scrapers.extend(get_west_virginia_scrapers())
    scrapers.extend(get_wisconsin_scrapers())
    scrapers.extend(get_wyoming_scrapers())
    return scrapers
