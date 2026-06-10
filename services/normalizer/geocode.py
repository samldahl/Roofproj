"""Census Geocoder client. Free, ~10-15% miss rate in MN suburbs."""
from __future__ import annotations

import os
from typing import Optional

import httpx

CENSUS_URL = os.getenv(
    "CENSUS_GEOCODER_URL",
    "https://geocoding.geo.census.gov/geocoder/locations/onelineaddress",
)


def geocode(address: str, *, city: str = "", state: str = "MN") -> Optional[list[float]]:
    """Return [lng, lat] or None."""
    query = address
    if city and city.lower() not in address.lower():
        query = f"{address}, {city}, {state}"

    try:
        r = httpx.get(
            CENSUS_URL,
            params={"address": query, "benchmark": "Public_AR_Current", "format": "json"},
            timeout=10.0,
        )
        r.raise_for_status()
        matches = r.json().get("result", {}).get("addressMatches", [])
        if not matches:
            return None
        coords = matches[0]["coordinates"]
        return [coords["x"], coords["y"]]
    except (httpx.HTTPError, KeyError, IndexError):
        return None
