"""
Route Planner
=============
Orchestrates the full pipeline:

  1. Geocode start / end  → offline lookup  (0 external calls)
  2. Fetch route          → OSRM public API (1 external call)
  3. Sample waypoints every REFUEL_INTERVAL miles along the polyline
  4. For each waypoint pick the cheapest station within a search corridor
  5. Compute per-stop fuel cost and aggregate totals

External API budget: exactly 1 call (OSRM routing).
Geocoding is handled offline via the bundled US-cities CSV.
"""

import math
import time
import logging
import requests
from typing import Any

import numpy as np

from django.conf import settings

from .fuel_service import (
    get_stations,
    stations_within_radius,
    haversine_miles,
    geocode_offline,
    EARTH_RADIUS_MILES,
)

logger = logging.getLogger(__name__)

# ── Constants ──────────────────────────────────────────────────────────────
RANGE_MILES         = settings.VEHICLE_RANGE_MILES      # 500
MPG                 = settings.VEHICLE_MPG              # 10
REFUEL_INTERVAL     = int(RANGE_MILES * 0.80)           # 400 miles — refuel before empty
SEARCH_RADIUS       = 30                                # miles corridor around route
SEARCH_RADIUS_WIDE  = 60                                # fallback if nothing in 30 mi
OSRM_BASE_URL       = settings.OSRM_BASE_URL


# ── 1. Geocoding ──────────────────────────────────────────────────────────

def geocode(location: str) -> dict[str, Any]:
    """
    Resolve a location string to {lat, lon, display_name}.
    Uses the bundled offline city database — zero external calls.
    Optionally falls back to the Nominatim HTTP API if env allows it.
    """
    try:
        return geocode_offline(location)
    except ValueError:
        pass

    # Optional HTTP fallback (works when running locally with internet access)
    try:
        resp = requests.get(
            f"{settings.NOMINATIM_URL}/search",
            params={"q": location, "countrycodes": "us",
                    "format": "json", "limit": 1},
            headers={"User-Agent": "FuelRouteAPI/1.0"},
            timeout=8,
        )
        if resp.ok:
            results = resp.json()
            if results:
                r = results[0]
                return {
                    "lat": float(r["lat"]),
                    "lon": float(r["lon"]),
                    "display_name": r["display_name"],
                }
    except Exception as exc:
        logger.debug("Nominatim fallback failed: %s", exc)

    raise ValueError(
        f"Could not geocode '{location}'. "
        "Use 'City, ST' format, e.g. 'Chicago, IL' or 'Los Angeles, CA'."
    )


# ── 2. OSRM routing (1 API call) ──────────────────────────────────────────

def fetch_osrm_route(
    start_lat: float, start_lon: float,
    end_lat: float,   end_lon: float,
) -> dict[str, Any]:
    """
    Single call to OSRM public demo server.
    Returns distance_miles, duration_seconds, geometry [(lat,lon)...].
    """
    url = (
        f"{OSRM_BASE_URL}/route/v1/driving/"
        f"{start_lon},{start_lat};{end_lon},{end_lat}"
    )
    resp = requests.get(
        url,
        params={
            "overview":   "full",
            "geometries": "geojson",
            "steps":      "false",
            "annotations":"false",
        },
        timeout=30,
    )
    resp.raise_for_status()
    data = resp.json()

    if data.get("code") != "Ok" or not data.get("routes"):
        raise ValueError(
            f"OSRM returned no route. Code: {data.get('code')} — "
            f"{data.get('message', '')}"
        )

    route = data["routes"][0]
    coords_lonlat = route["geometry"]["coordinates"]   # [[lon,lat], ...]

    return {
        "distance_miles":    route["distance"] * 0.000621371,
        "duration_seconds":  route["duration"],
        "geometry":          [(c[1], c[0]) for c in coords_lonlat],  # → (lat,lon)
    }


def _straight_line_route(
    start_lat: float, start_lon: float,
    end_lat: float, end_lon: float,
) -> dict[str, Any]:
    """
    Fallback when OSRM is unreachable.
    Creates a 50-point interpolated great-circle path and estimates
    driving distance as 1.2× the straight-line distance.
    """
    n = 50
    geometry = [
        (
            start_lat + i / (n - 1) * (end_lat - start_lat),
            start_lon + i / (n - 1) * (end_lon - start_lon),
        )
        for i in range(n)
    ]
    straight = haversine_miles(start_lat, start_lon, end_lat, end_lon)
    est_miles = straight * 1.25          # road vs crow-flies factor
    est_secs  = est_miles / 60 * 3600    # assume avg 60 mph
    return {
        "distance_miles":   est_miles,
        "duration_seconds": est_secs,
        "geometry":         geometry,
        "_estimated":       True,
    }


# ── 3. Polyline helpers ───────────────────────────────────────────────────

def _cumulative_miles(geometry: list[tuple[float, float]]) -> list[float]:
    cum = [0.0]
    for i in range(1, len(geometry)):
        d = haversine_miles(
            geometry[i-1][0], geometry[i-1][1],
            geometry[i][0],   geometry[i][1],
        )
        cum.append(cum[-1] + d)
    return cum


def _interpolate_point(
    geometry: list[tuple[float, float]],
    cum: list[float],
    target_mile: float,
) -> tuple[float, float]:
    for i in range(1, len(cum)):
        if cum[i] >= target_mile:
            seg = cum[i] - cum[i-1]
            frac = (target_mile - cum[i-1]) / max(seg, 1e-9)
            lat = geometry[i-1][0] + frac * (geometry[i][0] - geometry[i-1][0])
            lon = geometry[i-1][1] + frac * (geometry[i][1] - geometry[i-1][1])
            return lat, lon
    return geometry[-1]


def sample_waypoints(
    geometry: list[tuple[float, float]],
    total_miles: float,
    interval: float,
) -> list[dict]:
    """Return list of {lat, lon, mile_marker} at every `interval` miles."""
    cum = _cumulative_miles(geometry)
    waypoints = []
    target = interval
    while target < total_miles:
        lat, lon = _interpolate_point(geometry, cum, target)
        waypoints.append({"lat": lat, "lon": lon, "mile_marker": round(target, 1)})
        target += interval
    return waypoints


# ── 4. Station picker ─────────────────────────────────────────────────────

def _cheapest_near(
    lat: float, lon: float, radius: float,
    df, coords_rad,
) -> dict | None:
    nearby = stations_within_radius(lat, lon, radius, df, coords_rad)
    if nearby.empty:
        return None
    best = nearby.sort_values("Retail Price").iloc[0]
    return {
        "truckstop_id":    int(best["OPIS Truckstop ID"]),
        "name":            str(best["Truckstop Name"]),
        "address":         str(best["Address"]),
        "city":            str(best["City"]),
        "state":           str(best["State"]),
        "lat":             round(float(best["lat"]), 6),
        "lon":             round(float(best["lon"]), 6),
        "price_per_gallon":round(float(best["Retail Price"]), 3),
        "detour_miles":    round(float(best["_dist_miles"]), 1),
    }


# ── 5. Main entry point ───────────────────────────────────────────────────

def plan_route(start: str, end: str) -> dict[str, Any]:
    """
    Full pipeline.  Returns a dict ready for JSON serialisation.
    """
    # ── Geocode (offline, 0 external calls) ────────────────────────────────
    origin      = geocode(start)
    destination = geocode(end)

    # ── Fetch route (1 external call — OSRM) ──────────────────────────────
    route_estimated = False
    try:
        route_data = fetch_osrm_route(
            origin["lat"],      origin["lon"],
            destination["lat"], destination["lon"],
        )
    except Exception as exc:
        logger.warning("OSRM unavailable (%s) — using straight-line estimate.", exc)
        route_data = _straight_line_route(
            origin["lat"],      origin["lon"],
            destination["lat"], destination["lon"],
        )
        route_estimated = True

    total_miles = route_data["distance_miles"]
    geometry    = route_data["geometry"]

    # ── Load station index (in-memory, built once at startup) ─────────────
    df, coords_rad = get_stations()

    # ── Sample refuel waypoints ────────────────────────────────────────────
    waypoints = sample_waypoints(geometry, total_miles, REFUEL_INTERVAL)

    # ── Pick cheapest station at each waypoint ─────────────────────────────
    fuel_stops: list[dict] = []
    seen_ids:   set[int]   = set()

    for wp in waypoints:
        station = (
            _cheapest_near(wp["lat"], wp["lon"], SEARCH_RADIUS,      df, coords_rad)
            or _cheapest_near(wp["lat"], wp["lon"], SEARCH_RADIUS_WIDE, df, coords_rad)
        )
        if station and station["truckstop_id"] not in seen_ids:
            station["mile_marker"] = wp["mile_marker"]
            fuel_stops.append(station)
            seen_ids.add(station["truckstop_id"])

    # ── Cost calculation ───────────────────────────────────────────────────
    # Segment boundaries: 0 → stop1 → stop2 → … → total_miles
    segment_bounds = [0.0] + [s["mile_marker"] for s in fuel_stops] + [total_miles]
    total_cost = 0.0

    for i, stop in enumerate(fuel_stops):
        seg_miles = segment_bounds[i + 1] - segment_bounds[i]
        gallons   = seg_miles / MPG
        cost      = gallons * stop["price_per_gallon"]
        stop["segment_miles"]      = round(seg_miles, 1)
        stop["gallons_purchased"]  = round(gallons, 3)
        stop["segment_cost_usd"]   = round(cost, 2)
        total_cost += cost

    total_gallons = total_miles / MPG

    # ── Map links ─────────────────────────────────────────────────────────
    map_links = _build_map_links(origin, destination, fuel_stops)

    return {
        "origin": {
            "input":        start,
            "display_name": origin["display_name"],
            "lat":          origin["lat"],
            "lon":          origin["lon"],
        },
        "destination": {
            "input":        end,
            "display_name": destination["display_name"],
            "lat":          destination["lat"],
            "lon":          destination["lon"],
        },
        "route_summary": {
            "total_distance_miles":   round(total_miles, 1),
            "estimated_duration_hrs": round(route_data["duration_seconds"] / 3600, 2),
            "total_gallons_needed":   round(total_gallons, 2),
            "total_fuel_cost_usd":    round(total_cost, 2),
            "num_fuel_stops":         len(fuel_stops),
            "vehicle_range_miles":    RANGE_MILES,
            "vehicle_mpg":            MPG,
            "route_estimated":        route_estimated,
        },
        "fuel_stops": fuel_stops,
        "map_links":  map_links,
        "route_geometry": {
            "type":        "LineString",
            "coordinates": [[lon, lat] for lat, lon in geometry],
        },
    }


# ── Map link builder ──────────────────────────────────────────────────────

def _build_map_links(origin, destination, fuel_stops) -> dict:
    osm = (
        f"https://www.openstreetmap.org/directions?"
        f"from={origin['lat']},{origin['lon']}"
        f"&to={destination['lat']},{destination['lon']}"
        f"&engine=osrm_car"
    )

    waypoints_str = "/".join(
        f"{s['lat']},{s['lon']}" for s in fuel_stops
    )
    sep = "/" if waypoints_str else ""
    gmaps = (
        f"https://www.google.com/maps/dir/"
        f"{origin['lat']},{origin['lon']}"
        f"{sep}{waypoints_str}"
        f"/{destination['lat']},{destination['lon']}"
    )

    return {
        "openstreetmap": osm,
        "google_maps":   gmaps,
        "note": (
            "Embed the route_geometry GeoJSON LineString with Leaflet.js "
            "or Mapbox GL for a fully interactive map."
        ),
    }
