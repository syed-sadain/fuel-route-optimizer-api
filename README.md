# Fuel Route Optimizer API

A production-grade Django REST API that plans the most **cost-effective fuel stops** for any US road trip.

---

## Features

| Feature | Detail |
|---|---|
| **Optimal fuel stops** | Cheapest station within 30-mile corridor of your route |
| **Multi-stop routes** | Automatic refuelling every 400 miles (80% of 500-mile range) |
| **Cost breakdown** | Per-stop cost + total trip fuel spend |
| **Route geometry** | Full GeoJSON LineString for map rendering |
| **Map links** | Direct OpenStreetMap + Google Maps URLs with waypoints |
| **Fast** | Stations pre-loaded at startup; all lookups are vectorised numpy |
| **Minimal API calls** | 1 external call (OSRM routing); geocoding is fully offline |

---

## Quick Start

```bash
# 1. Clone / unzip the project
cd fuel_route_api

# 2. Create virtual environment
python -m venv venv
venv\Scripts\activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. Apply migrations
python manage.py migrate

# 5. Run the development server
python manage.py runserver
```

The API is now available at **http://127.0.0.1:8000/api/route/**

---

## API Reference

### `POST /api/route/`

Plan a fuel-optimal road trip.

**Request**

```json
{
  "start": "Chicago, IL",
  "end":   "Los Angeles, CA"
}
```

**Response**

```json
{
  "success": true,
  "origin": {
    "input": "Chicago, IL",
    "display_name": "Chicago, IL",
    "lat": 41.85,
    "lon": -87.65
  },
  "destination": { ... },
  "route_summary": {
    "total_distance_miles": 2017.4,
    "estimated_duration_hrs": 29.8,
    "total_gallons_needed": 201.7,
    "total_fuel_cost_usd": 624.18,
    "num_fuel_stops": 4,
    "vehicle_range_miles": 500,
    "vehicle_mpg": 10
  },
  "fuel_stops": [
    {
      "truckstop_id": 1234,
      "name": "PILOT TRAVEL CENTER #42",
      "address": "I-80, EXIT 145",
      "city": "Iowa City",
      "state": "IA",
      "lat": 41.66,
      "lon": -91.53,
      "price_per_gallon": 3.099,
      "mile_marker": 400.0,
      "segment_miles": 400.0,
      "gallons_purchased": 40.0,
      "segment_cost_usd": 123.96,
      "detour_miles": 4.2
    }
  ],
  "map_links": {
    "openstreetmap": "https://www.openstreetmap.org/directions?...",
    "google_maps":   "https://www.google.com/maps/dir/..."
  },
  "route_geometry": {
    "type": "LineString",
    "coordinates": [[-87.65, 41.85], ...]
  },
  "_meta": {
    "computation_time_seconds": 1.243,
    "geocoding": "offline — bundled US-cities database (29 880 cities)",
    "routing":   "OSRM public demo server (1 API call)",
    "fuel_data": "OPIS Truckstop Fuel Prices — 8 151 US stations"
  }
}
```

### `GET /api/route/`

Returns usage documentation. Useful as a health-check endpoint.

---

## Error Responses

| Status | Meaning |
|---|---|
| `400 Bad Request` | Missing or blank `start` / `end` field |
| `422 Unprocessable Entity` | Location could not be geocoded — use `City, ST` format |
| `500 Internal Server Error` | Unexpected server-side error |

All errors follow:

```json
{
  "success": false,
  "error": "Human-readable message"
}
```

---

## Location Format

The API accepts any of these formats:

```
"Chicago, IL"          ✅ preferred
"Chicago Illinois"     ✅
"chicago il"           ✅ (case-insensitive)
"Los Angeles"          ✅ (city-only, first match)
"California"           ✅ (state centroid)
```

---

## Architecture

```
config/
  settings.py       — Django + DRF configuration; all tunable constants here
  urls.py           — URL root: /api/ → routes app

routes/
  fuel_service.py   — Loads OPIS CSV, attaches lat/lon, builds numpy spatial index
  route_planner.py  — Geocoding + OSRM call + waypoint sampling + station picker
  serializers.py    — Input validation (RouteRequestSerializer)
  views.py          — RouteView (GET: docs, POST: plan route)
  exceptions.py     — Consistent JSON error responses
  tests.py          — 17 unit + integration tests
  fuel_prices.csv   — OPIS Truckstop dataset (8 151 stations)
  uscities_lite.csv — US cities→lat/lon lookup (29 880 cities, offline)
```

### Performance characteristics

- Station data loaded **once** at server startup (~0.3 s)
- Every request: 1 OSRM HTTP call (~0.5–1 s depending on network)
- Station nearest-neighbour search: vectorised numpy haversine, O(N), < 5 ms for 7 500 stations
- Typical end-to-end latency: **1–2 seconds** (dominated by OSRM network round-trip)

---

## Running Tests

```bash
python manage.py test routes --verbosity=2
```

17 tests covering geocoding, spatial search, API endpoints, cost calculation, and geometry validation.

---

## Production Deployment

```bash
# Install gunicorn (already in requirements.txt)
gunicorn config.wsgi:application --workers 4 --bind 0.0.0.0:8000
```

Set these environment variables for production:

```
DJANGO_SECRET_KEY=<long-random-string>
DJANGO_DEBUG=False
DJANGO_ALLOWED_HOSTS=yourdomain.com
```
---
## Project Structure

fuel_route_api/
├── manage.py
├── requirements.txt
├── README.md
├── config/
│   ├── settings.py      — All constants (range, MPG, API URLs)
│   ├── urls.py          — /api/ → routes app
│   ├── wsgi.py / asgi.py
└── routes/
    ├── fuel_service.py  — CSV loader + offline geocoder + vectorised search
    ├── route_planner.py — OSRM call + waypoint sampling + stop picker
    ├── serializers.py   — Input validation
    ├── views.py         — GET (docs) + POST (plan route)
    ├── exceptions.py    — Consistent JSON error format
    ├── tests.py         — 17 tests
    ├── fuel_prices.csv  — OPIS dataset (bundled)
    └── uscities_lite.csv— 29 880 US cities (offline geocoding)
---

## Data Sources

| Source | License | Notes |
|---|---|---|
| OPIS Truckstop Fuel Prices | Provided for assessment | 8 151 US truck-stop prices |
| US Cities Database (kelvins/US-Cities-Database) | Public domain | 29 880 cities with lat/lon |
| OSRM Demo Server | Free, no key | `router.project-osrm.org` |

> **Note:** For production use, replace the OSRM demo server with a self-hosted OSRM instance or a commercial routing API. The demo server has rate limits and no SLA.
----
Username: admin
Email: admin@example.com
Password: admin123