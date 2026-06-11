"""
Fuel Station Service
====================
Loads all 8 151 fuel stations from the OPIS CSV once at process start,
attaches coordinates via the bundled US-cities lookup, and exposes a
vectorised haversine search so the route planner can find the cheapest
station near any point in O(N) time without any external calls.
"""

import math
import threading
from functools import lru_cache
from pathlib import Path

import numpy as np
import pandas as pd
from django.conf import settings

# ── Module-level singleton ─────────────────────────────────────────────────
_lock = threading.Lock()
_stations_df: pd.DataFrame | None = None
_coords_rad:  np.ndarray   | None = None   # shape (N, 2) radians


# ── Public entry point ─────────────────────────────────────────────────────

def get_stations() -> tuple[pd.DataFrame, np.ndarray]:
    """Return (df, coords_radians) — loaded once, cached for lifetime of process."""
    global _stations_df, _coords_rad
    if _stations_df is None:
        with _lock:
            if _stations_df is None:
                _stations_df, _coords_rad = _load_stations()
    return _stations_df, _coords_rad


# ── Internal loading ───────────────────────────────────────────────────────

def _load_stations() -> tuple[pd.DataFrame, np.ndarray]:
    df = pd.read_csv(settings.FUEL_CSV_PATH)
    df.columns = [c.strip() for c in df.columns]
    df = df.dropna(subset=["Retail Price"])
    df = df[df["Retail Price"] > 0].copy()
    df = _attach_coords(df)
    df = df.dropna(subset=["lat", "lon"]).reset_index(drop=True)
    coords = np.deg2rad(df[["lat", "lon"]].values.astype(float))
    return df, coords


def _attach_coords(df: pd.DataFrame) -> pd.DataFrame:
    lookup = _city_lookup()
    lats, lons = [], []
    for _, row in df.iterrows():
        city  = str(row.get("City",  "")).strip().upper()
        state = str(row.get("State", "")).strip().upper()
        coord = lookup.get((city, state)) or _STATE_CENTROIDS.get(state)
        if coord:
            lats.append(coord[0])
            lons.append(coord[1])
        else:
            lats.append(None)
            lons.append(None)
    df = df.copy()
    df["lat"] = lats
    df["lon"] = lons
    return df


@lru_cache(maxsize=1)
def _city_lookup() -> dict[tuple[str, str], tuple[float, float]]:
    path: Path = settings.CITIES_CSV_PATH
    if not path.exists():
        return {}
    cities = pd.read_csv(path, usecols=["city", "state_id", "lat", "lng"])
    result: dict[tuple[str, str], tuple[float, float]] = {}
    for _, r in cities.iterrows():
        key = (str(r["city"]).strip().upper(), str(r["state_id"]).strip().upper())
        result[key] = (float(r["lat"]), float(r["lng"]))
    return result


# ── Haversine helpers ──────────────────────────────────────────────────────

EARTH_RADIUS_MILES = 3_958.8


def haversine_miles(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    φ1, λ1, φ2, λ2 = map(math.radians, [lat1, lon1, lat2, lon2])
    a = (math.sin((φ2 - φ1) / 2) ** 2
         + math.cos(φ1) * math.cos(φ2) * math.sin((λ2 - λ1) / 2) ** 2)
    return 2 * EARTH_RADIUS_MILES * math.asin(math.sqrt(a))


def stations_within_radius(
    lat: float, lon: float, radius_miles: float,
    df: pd.DataFrame, coords_rad: np.ndarray,
) -> pd.DataFrame:
    """Vectorised — returns subset of df with '_dist_miles' column added."""
    φ0, λ0 = math.radians(lat), math.radians(lon)
    φ, λ = coords_rad[:, 0], coords_rad[:, 1]
    a = (np.sin((φ - φ0) / 2) ** 2
         + np.cos(φ0) * np.cos(φ) * np.sin((λ - λ0) / 2) ** 2)
    dist = 2 * EARTH_RADIUS_MILES * np.arcsin(np.sqrt(np.clip(a, 0, 1)))
    mask = dist <= radius_miles
    result = df[mask].copy()
    result["_dist_miles"] = dist[mask]
    return result


# ── Offline geocoder ───────────────────────────────────────────────────────

def geocode_offline(location: str) -> dict:
    """
    Parse  'City, State'  or  'City State'  strings against the bundled
    cities CSV.  Returns {lat, lon, display_name} or raises ValueError.

    Examples that work:
        "Chicago, IL"  |  "chicago illinois"  |  "New York City, NY"
        "Los Angeles"  |  "Denver"
    """
    lookup   = _city_lookup()
    abbr_map = _state_abbr_map()

    raw = location.strip()

    # ── strategy 1: "City, ST" ─────────────────────────────────────────────
    if "," in raw:
        parts = [p.strip() for p in raw.split(",", 1)]
        city_q  = parts[0].upper()
        state_q = parts[1].strip().upper()
        # resolve full state name → abbreviation
        if len(state_q) > 2:
            state_q = abbr_map.get(state_q, state_q)
        coord = lookup.get((city_q, state_q))
        if coord:
            return {"lat": coord[0], "lon": coord[1],
                    "display_name": f"{parts[0].title()}, {state_q}"}

    # ── strategy 2: last word is a 2-letter state abbreviation ────────────
    words = raw.split()
    if len(words) >= 2:
        maybe_state = words[-1].upper()
        if len(maybe_state) == 2 and maybe_state in _STATE_CENTROIDS:
            city_q = " ".join(words[:-1]).upper()
            coord  = lookup.get((city_q, maybe_state))
            if coord:
                return {"lat": coord[0], "lon": coord[1],
                        "display_name": f"{city_q.title()}, {maybe_state}"}

    # ── strategy 3: last word(s) is a full state name ─────────────────────
    for n in (2, 1):
        if len(words) > n:
            state_name = " ".join(words[-n:]).upper()
            abbr = abbr_map.get(state_name)
            if abbr:
                city_q = " ".join(words[:-n]).upper()
                coord  = lookup.get((city_q, abbr))
                if coord:
                    return {"lat": coord[0], "lon": coord[1],
                            "display_name": f"{city_q.title()}, {abbr}"}

    # ── strategy 4: city-only search (first match) ────────────────────────
    city_q = raw.upper()
    for (c, s), coord in lookup.items():
        if c == city_q:
            return {"lat": coord[0], "lon": coord[1],
                    "display_name": f"{c.title()}, {s}"}

    # ── strategy 5: state centroid ────────────────────────────────────────
    abbr = abbr_map.get(raw.upper())
    if abbr and abbr in _STATE_CENTROIDS:
        coord = _STATE_CENTROIDS[abbr]
        return {"lat": coord[0], "lon": coord[1], "display_name": raw.title()}

    raise ValueError(
        f"Could not geocode '{location}'. "
        "Please use 'City, ST' format, e.g. 'Chicago, IL'."
    )


@lru_cache(maxsize=1)
def _state_abbr_map() -> dict[str, str]:
    return {
        "ALABAMA": "AL", "ALASKA": "AK", "ARIZONA": "AZ", "ARKANSAS": "AR",
        "CALIFORNIA": "CA", "COLORADO": "CO", "CONNECTICUT": "CT",
        "DELAWARE": "DE", "FLORIDA": "FL", "GEORGIA": "GA", "HAWAII": "HI",
        "IDAHO": "ID", "ILLINOIS": "IL", "INDIANA": "IN", "IOWA": "IA",
        "KANSAS": "KS", "KENTUCKY": "KY", "LOUISIANA": "LA", "MAINE": "ME",
        "MARYLAND": "MD", "MASSACHUSETTS": "MA", "MICHIGAN": "MI",
        "MINNESOTA": "MN", "MISSISSIPPI": "MS", "MISSOURI": "MO",
        "MONTANA": "MT", "NEBRASKA": "NE", "NEVADA": "NV",
        "NEW HAMPSHIRE": "NH", "NEW JERSEY": "NJ", "NEW MEXICO": "NM",
        "NEW YORK": "NY", "NORTH CAROLINA": "NC", "NORTH DAKOTA": "ND",
        "OHIO": "OH", "OKLAHOMA": "OK", "OREGON": "OR", "PENNSYLVANIA": "PA",
        "RHODE ISLAND": "RI", "SOUTH CAROLINA": "SC", "SOUTH DAKOTA": "SD",
        "TENNESSEE": "TN", "TEXAS": "TX", "UTAH": "UT", "VERMONT": "VT",
        "VIRGINIA": "VA", "WASHINGTON": "WA", "WEST VIRGINIA": "WV",
        "WISCONSIN": "WI", "WYOMING": "WY", "DISTRICT OF COLUMBIA": "DC",
        # abbreviation → itself
        "AL":"AL","AK":"AK","AZ":"AZ","AR":"AR","CA":"CA","CO":"CO",
        "CT":"CT","DE":"DE","FL":"FL","GA":"GA","HI":"HI","ID":"ID",
        "IL":"IL","IN":"IN","IA":"IA","KS":"KS","KY":"KY","LA":"LA",
        "ME":"ME","MD":"MD","MA":"MA","MI":"MI","MN":"MN","MS":"MS",
        "MO":"MO","MT":"MT","NE":"NE","NV":"NV","NH":"NH","NJ":"NJ",
        "NM":"NM","NY":"NY","NC":"NC","ND":"ND","OH":"OH","OK":"OK",
        "OR":"OR","PA":"PA","RI":"RI","SC":"SC","SD":"SD","TN":"TN",
        "TX":"TX","UT":"UT","VT":"VT","VA":"VA","WA":"WA","WV":"WV",
        "WI":"WI","WY":"WY","DC":"DC",
    }


_STATE_CENTROIDS: dict[str, tuple[float, float]] = {
    "AL": (32.806671,-86.791130), "AK": (61.370716,-152.404419),
    "AZ": (33.729759,-111.431221),"AR": (34.969704,-92.373123),
    "CA": (36.116203,-119.681564),"CO": (39.059811,-105.311104),
    "CT": (41.597782,-72.755371), "DE": (39.318523,-75.507141),
    "FL": (27.766279,-81.686783), "GA": (33.040619,-83.643074),
    "HI": (21.094318,-157.498337),"ID": (44.240459,-114.478828),
    "IL": (40.349457,-88.986137), "IN": (39.849426,-86.258278),
    "IA": (42.011539,-93.210526), "KS": (38.526600,-96.726486),
    "KY": (37.668140,-84.670067), "LA": (31.169960,-91.867805),
    "ME": (44.693947,-69.381927), "MD": (39.063946,-76.802101),
    "MA": (42.230171,-71.530106), "MI": (43.326618,-84.536095),
    "MN": (45.694454,-93.900192), "MS": (32.741646,-89.678696),
    "MO": (38.456085,-92.288368), "MT": (46.921925,-110.454353),
    "NE": (41.125370,-98.268082), "NV": (38.313515,-117.055374),
    "NH": (43.452492,-71.563896), "NJ": (40.298904,-74.521011),
    "NM": (34.840515,-106.248482),"NY": (42.165726,-74.948051),
    "NC": (35.630066,-79.806419), "ND": (47.528912,-99.784012),
    "OH": (40.388783,-82.764915), "OK": (35.565342,-96.928917),
    "OR": (44.572021,-122.070938),"PA": (40.590752,-77.209755),
    "RI": (41.680893,-71.511780), "SC": (33.856892,-80.945007),
    "SD": (44.299782,-99.438828), "TN": (35.747845,-86.692345),
    "TX": (31.054487,-97.563461), "UT": (40.150032,-111.862434),
    "VT": (44.045876,-72.710686), "VA": (37.769337,-78.169968),
    "WA": (47.400902,-121.490494),"WV": (38.491226,-80.954453),
    "WI": (44.268543,-89.616508), "WY": (42.755966,-107.302490),
    "DC": (38.897438,-77.026817),
}
