"""
Property valuation via Realtor.com API (RapidAPI).

Uses the "Realty in US" API:
1. Auto-complete endpoint to find property ID by address
2. Detail endpoint to get estimates, tax history, and property details
"""

import json
import logging
import urllib.error
import urllib.parse
import urllib.request
from typing import Optional

from app.config import settings

log = logging.getLogger(__name__)

RAPIDAPI_HOST = "realty-in-us.p.rapidapi.com"


def get_property_estimate(address: str) -> Optional[dict]:
    """Look up property value via Realtor.com API.

    Returns dict with estimate, details, and tax history — or None on failure.
    """
    if not settings.rapidapi_key:
        log.debug("RapidAPI key not configured; skipping Realtor.com lookup")
        return None

    headers = {
        "X-RapidAPI-Key": settings.rapidapi_key,
        "X-RapidAPI-Host": RAPIDAPI_HOST,
    }

    # Step 1: Find property ID via auto-complete
    property_id = _find_property_id(address, headers)
    if not property_id:
        return None

    # Step 2: Get detailed property data
    return _get_property_detail(property_id, headers)


def _find_property_id(address: str, headers: dict) -> Optional[str]:
    """Use the auto-complete endpoint to find a property's mpr_id."""
    try:
        encoded = urllib.parse.quote(address)
        url = f"https://{RAPIDAPI_HOST}/locations/v2/auto-complete?input={encoded}&limit=5"
        req = urllib.request.Request(url, headers=headers)
        resp = urllib.request.urlopen(req, timeout=15)
        data = json.loads(resp.read().decode("utf-8"))

        for result in data.get("autocomplete", []):
            if result.get("area_type") == "address":
                mpr_id = result.get("mpr_id")
                if mpr_id:
                    log.info("Found property mpr_id=%s for: %s", mpr_id, address)
                    return mpr_id

        log.info("No address match in auto-complete for: %s", address)
        return None

    except Exception as exc:
        log.warning("Auto-complete error for '%s': %s", address, exc)
        return None


def _get_property_detail(property_id: str, headers: dict) -> Optional[dict]:
    """Fetch property detail including estimates and tax history."""
    try:
        url = (
            f"https://{RAPIDAPI_HOST}/properties/v3/detail"
            f"?property_id={urllib.parse.quote(property_id)}"
        )
        req = urllib.request.Request(url, headers=headers)
        resp = urllib.request.urlopen(req, timeout=15)
        data = json.loads(resp.read().decode("utf-8"))
        home = data.get("data", {}).get("home", {})

        # Extract estimates
        estimates_data = home.get("estimates", {})
        current_values = estimates_data.get("current_values", [])

        # Pick the best estimate (average of available sources)
        estimate_values = [cv.get("estimate") for cv in current_values if cv.get("estimate")]
        if not estimate_values:
            log.info("No estimates available for property_id=%s", property_id)
            return None

        avg_estimate = int(sum(estimate_values) / len(estimate_values))

        # Collect estimate sources
        sources = []
        for cv in current_values:
            if cv.get("estimate"):
                sources.append({
                    "name": cv.get("source", {}).get("name", "Unknown"),
                    "estimate": cv["estimate"],
                    "low": cv.get("estimate_low"),
                    "high": cv.get("estimate_high"),
                    "date": cv.get("date"),
                })

        # Property details
        desc = home.get("description", {})
        addr = home.get("location", {}).get("address", {})
        details = {
            "address": f"{addr.get('line', '')}, {addr.get('city', '')}, {addr.get('state_code', '')} {addr.get('postal_code', '')}",
            "beds": desc.get("beds"),
            "baths": desc.get("baths"),
            "sqft": desc.get("sqft"),
            "year_built": desc.get("year_built"),
            "lot_sqft": desc.get("lot_sqft"),
            "last_sold_price": home.get("last_sold_price"),
            "last_sold_date": home.get("last_sold_date"),
        }

        # Tax assessment history
        tax_history = []
        for t in (home.get("tax_history") or []):
            assessment = t.get("assessment", {})
            if t.get("year") and assessment.get("total"):
                tax_history.append({
                    "year": t["year"],
                    "tax": t.get("tax"),
                    "assessed_value": assessment["total"],
                })

        result = {
            "estimate": avg_estimate,
            "source": "Realtor.com",
            "property_id": property_id,
            "sources": sources,
            "details": details,
            "tax_history": tax_history,
        }

        log.info("Realtor.com estimate for property_id=%s: $%s (%d sources)",
                 property_id, f"{avg_estimate:,}", len(sources))
        return result

    except Exception as exc:
        log.warning("Property detail error for %s: %s", property_id, exc)
        return None
