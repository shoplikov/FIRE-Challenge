import asyncio
import logging
import time

from geopy.adapters import AioHTTPAdapter
from geopy.distance import geodesic
from geopy.exc import GeocoderTimedOut, GeocoderServiceError
from geopy.geocoders import Nominatim
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.business_unit import BusinessUnit
from app.models.ticket import Ticket

logger = logging.getLogger(__name__)

_MAX_RETRIES = 3
_RETRY_BASE_DELAY = 2.0
_MIN_REQUEST_INTERVAL = 1.1  # Nominatim policy: max 1 req/s

_lock = asyncio.Lock()
_last_request_time: float = 0.0


async def _throttled_geocode(address: str) -> tuple[float, float] | None:
    """Geocode with rate-limiting: ensures >=1.1 s between Nominatim calls."""
    global _last_request_time
    async with _lock:
        now = time.monotonic()
        wait = _MIN_REQUEST_INTERVAL - (now - _last_request_time)
        if wait > 0:
            await asyncio.sleep(wait)
        _last_request_time = time.monotonic()

        async with Nominatim(
            user_agent=settings.geocoder_user_agent,
            adapter_factory=AioHTTPAdapter,
        ) as geolocator:
            location = await geolocator.geocode(address, timeout=10)
            if location:
                return (location.latitude, location.longitude)
    return None


async def _geocode_address(
    *addresses: str,
) -> tuple[float, float] | None:
    """Try each address variant in order, with retries on transient errors."""
    for address in addresses:
        for attempt in range(_MAX_RETRIES + 1):
            try:
                result = await _throttled_geocode(address)
                if result:
                    return result
                break  # got None (not found) – try next address variant
            except (GeocoderTimedOut, GeocoderServiceError) as exc:
                delay = _RETRY_BASE_DELAY * (2 ** attempt)
                if attempt < _MAX_RETRIES:
                    logger.debug(
                        "Geocoding %s (attempt %d/%d): %s – retrying in %.1fs",
                        address, attempt + 1, _MAX_RETRIES + 1, exc, delay,
                    )
                    await asyncio.sleep(delay)
                else:
                    logger.warning("Geocoding retries exhausted for: %s", address)
            except Exception:
                logger.exception("Geocoding failed for: %s", address)
                break
    return None


def _build_office_addresses(bu: BusinessUnit) -> list[str]:
    """Return address variants from most to least specific."""
    return [
        f"{bu.address}, {bu.name}, Казахстан",
        f"{bu.name}, Казахстан",
    ]


def _build_ticket_addresses(ticket: Ticket) -> list[str]:
    """Return address variants from most to least specific."""
    parts = []
    if ticket.street:
        parts.append(ticket.street)
    if ticket.house:
        parts.append(ticket.house)
    if ticket.city:
        parts.append(ticket.city)
    if ticket.region:
        parts.append(ticket.region)
    if ticket.country:
        parts.append(ticket.country)

    variants = []
    if parts:
        variants.append(", ".join(parts))
    city_parts = [p for p in [ticket.city, ticket.region, ticket.country] if p]
    if city_parts and city_parts != parts:
        variants.append(", ".join(city_parts))
    return variants


async def geocode_business_units(
    session: AsyncSession, units: list[BusinessUnit]
) -> None:
    to_geocode = [bu for bu in units if bu.latitude is None]
    if not to_geocode:
        return

    logger.info("Geocoding %d business units...", len(to_geocode))

    async def _process(bu: BusinessUnit) -> None:
        addresses = _build_office_addresses(bu)
        coords = await _geocode_address(*addresses)
        if coords:
            bu.latitude, bu.longitude = coords
            logger.info("Geocoded office '%s': %s", bu.name, coords)
        else:
            logger.warning("Could not geocode office '%s'", bu.name)

    await asyncio.gather(*[_process(bu) for bu in to_geocode])
    await session.flush()


async def geocode_tickets(session: AsyncSession, tickets: list[Ticket]) -> None:
    to_geocode = [t for t in tickets if t.latitude is None and t.city]
    if not to_geocode:
        return

    logger.info("Geocoding %d ticket addresses...", len(to_geocode))

    async def _process(ticket: Ticket) -> None:
        addresses = _build_ticket_addresses(ticket)
        if not addresses:
            return
        coords = await _geocode_address(*addresses)
        if coords:
            ticket.latitude, ticket.longitude = coords

    await asyncio.gather(*[_process(t) for t in to_geocode])
    await session.flush()
    geocoded = sum(1 for t in to_geocode if t.latitude is not None)
    logger.info("Geocoded %d / %d ticket addresses", geocoded, len(to_geocode))


def find_nearest_office(
    lat: float, lon: float, offices: list[BusinessUnit]
) -> BusinessUnit | None:
    geocoded = [bu for bu in offices if bu.latitude is not None]
    if not geocoded:
        return None
    return min(geocoded, key=lambda bu: geodesic((lat, lon), (bu.latitude, bu.longitude)).km)


def get_distance_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    return geodesic((lat1, lon1), (lat2, lon2)).km
