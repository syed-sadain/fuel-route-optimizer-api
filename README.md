## 🚛 Fuel Route Optimizer API

A production-ready Django REST API that calculates the most cost-effective fuel stops for road trips across the United States.

The API analyzes a route between two locations, identifies the lowest-priced fuel stations within a route corridor, estimates total fuel consumption and trip cost, and generates shareable navigation links for Google Maps and OpenStreetMap.

---

## ✨ Key Features

* 🛣️ Route optimization between any two US locations
* ⛽ Intelligent fuel-stop selection based on fuel prices
* 📍 Cheapest station within a 30-mile route corridor
* 🚚 Vehicle range-aware planning (500-mile tank range)
* 💰 Detailed fuel cost estimation and breakdown 
* 🗺️ GeoJSON route geometry for frontend map rendering
* 🔗 Google Maps and OpenStreetMap route generation
* ⚡ High-performance vectorized geospatial search using NumPy
* 🌎 Offline geocoding with bundled US city database
* 🔄 Consistent REST API responses and error handling
* ✅ Automated test coverage

---

## 🏗️ System Architecture

```text
User Request
      │
      ▼
Offline Geocoder
(US Cities Database)
      │
      ▼
OSRM Routing Engine
(1 External API Call)
      │
      ▼
Waypoint Sampling
(Every 400 Miles)
      │
      ▼
Fuel Station Search
(Vectorized NumPy Haversine)
      │
      ▼
Cheapest Station Selection
      │
      ▼
Cost Calculation + Route Output
```

---

## 🚀 Quick Start

### 1. Clone Repository

```bash
git clone https://github.com/syed-sadain/fuel-route-optimizer-api.git
cd fuel-route-optimizer-api
```

### 2. Create Virtual Environment

```bash
python -m venv venv
```

### Windows

```bash
venv\Scripts\activate
```

### Linux / macOS

```bash
source venv/bin/activate
```

### 3. Install Dependencies

```bash
pip install -r requirements.txt
```

### 4. Apply Database Migrations

```bash
python manage.py migrate
```

### 5. Run Development Server

```bash
python manage.py runserver
```

API Endpoint:

```text
http://127.0.0.1:8000/api/route/
```

---

## 📡 API Endpoints

### GET /api/route/

Returns API documentation and serves as a health-check endpoint.

---

### POST /api/route/

Generate a fuel-optimized route.

#### Request

```json
{
  "start": "Chicago, IL",
  "end": "Los Angeles, CA"
}
```

#### Example Response

```json
{
  "success": true,
  "route_summary": {
    "total_distance_miles": 2017.4,
    "estimated_duration_hrs": 29.8,
    "total_fuel_cost_usd": 624.18,
    "num_fuel_stops": 4
  }
}
```

---

## 📊 Response Highlights

The API returns:

* Origin & destination details
* Route distance and travel duration
* Estimated fuel consumption
* Total fuel cost
* Recommended fuel stops
* Cost per stop
* Google Maps navigation link
* OpenStreetMap route link
* GeoJSON LineString geometry
* Performance metadata

---

## ⚠️ Error Handling

| Status Code | Description                      |
| ----------- | -------------------------------- |
| 400         | Missing required fields          |
| 422         | Invalid or unrecognized location |
| 500         | Internal server error            |

Example:

```json
{
  "success": false,
  "error": "Location could not be geocoded"
}
```

---

## 📂 Project Structure

```text
fuel_route_api/
│
├── manage.py
├── requirements.txt
├── README.md
│
├── config/
│   ├── settings.py
│   ├── urls.py
│   ├── asgi.py
│   └── wsgi.py
│
└── routes/
    ├── fuel_service.py
    ├── route_planner.py
    ├── serializers.py
    ├── views.py
    ├── exceptions.py
    ├── tests.py
    ├── fuel_prices.csv
    └── uscities_lite.csv
```

---

## ⚡ Performance

| Metric                    | Value       |
| ------------------------- | ----------- |
| Fuel Stations             | 8,151       |
| US Cities                 | 29,880      |
| External API Calls        | 1           |
| Station Search Complexity | O(N)        |
| Spatial Search Time       | < 5 ms      |
| Typical Request Time      | 1–2 seconds |

---

## 🧪 Running Tests

```bash
python manage.py test routes --verbosity=2
```

Test coverage includes:

* API validation
* Offline geocoding
* Route generation
* Fuel-stop selection
* Cost calculations
* Vehicle range constraints
* GeoJSON validation

---

## 🚀 Production Deployment

Run using Gunicorn:

```bash
gunicorn config.wsgi:application --workers 4 --bind 0.0.0.0:8000
```

Environment variables:

```env
DJANGO_SECRET_KEY=your-secret-key
DJANGO_DEBUG=False
DJANGO_ALLOWED_HOSTS=your-domain.com
```

---

## 📚 Data Sources

| Source                 | Purpose           |
| ---------------------- | ----------------- |
| OPIS Truckstop Dataset | Fuel pricing data |
| US Cities Database     | Offline geocoding |
| OSRM Routing Engine    | Route generation  |

---

## 🎯 Design Decisions

### Why Offline Geocoding?

* No API costs
* Faster lookups
* No rate limits
* Works without external geocoding services

### Why Vectorized Search?

* Searches all stations simultaneously
* Significantly faster than iterative distance calculations
* Scales efficiently with larger datasets

### Why OSRM?

* Open-source routing engine
* Reliable road network routing
* Requires only one external request per route

---

## 👨‍💻 Author

**Syed Sadain**

Backend Engineer | Django Developer | Data Analyst

Assessment Project: Fuel Route Optimizer API
