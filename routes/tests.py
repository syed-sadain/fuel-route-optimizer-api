"""
Test suite for the Fuel Route Optimizer API.
Run with:  python manage.py test routes
"""

import json
from unittest.mock import patch, MagicMock

from django.test import TestCase, override_settings
from rest_framework.test import APIClient


# ── Sample OSRM response (Chicago → Denver-ish straight line simplified) ──
MOCK_OSRM = {
    "code": "Ok",
    "routes": [{
        "distance": 1_609_344,        # ~1000 miles in metres
        "duration": 54_000,           # 15 hours in seconds
        "geometry": {
            "type": "LineString",
            "coordinates": [
                [-87.6298, 41.8781],   # Chicago (lon, lat)
                [-93.0,    41.5],
                [-96.0,    40.5],
                [-100.0,   39.8],
                [-104.9847, 39.7392],  # Denver
            ],
        },
        "legs": [{"distance": 1_609_344, "duration": 54_000, "steps": []}],
    }],
}


def _make_mock_osrm_response():
    m = MagicMock()
    m.ok = True
    m.raise_for_status = MagicMock()
    m.json.return_value = MOCK_OSRM
    return m


class GeocodingTests(TestCase):
    def test_city_state_format(self):
        from routes.fuel_service import geocode_offline
        result = geocode_offline("Chicago, IL")
        self.assertIn("lat", result)
        self.assertIn("lon", result)
        self.assertAlmostEqual(result["lat"], 41.85, delta=1.0)
        self.assertAlmostEqual(result["lon"], -87.65, delta=1.0)

    def test_city_abbreviation_no_comma(self):
        from routes.fuel_service import geocode_offline
        result = geocode_offline("Denver CO")
        self.assertIn("lat", result)

    def test_invalid_location_raises(self):
        from routes.fuel_service import geocode_offline
        with self.assertRaises(ValueError):
            geocode_offline("XYZZY_NONEXISTENT_PLACE")

    def test_state_name_full(self):
        from routes.fuel_service import geocode_offline
        result = geocode_offline("Chicago Illinois")
        self.assertIn("lat", result)


class FuelServiceTests(TestCase):
    def test_stations_load(self):
        from routes.fuel_service import get_stations
        df, coords = get_stations()
        self.assertGreater(len(df), 5_000)
        self.assertEqual(df.shape[0], coords.shape[0])
        self.assertIn("Retail Price", df.columns)
        self.assertIn("lat", df.columns)

    def test_spatial_search(self):
        from routes.fuel_service import get_stations, stations_within_radius
        df, coords = get_stations()
        nearby = stations_within_radius(41.88, -87.63, 50, df, coords)
        self.assertGreater(len(nearby), 0)
        self.assertIn("_dist_miles", nearby.columns)
        self.assertTrue((nearby["_dist_miles"] <= 50).all())

    def test_spatial_search_empty_when_ocean(self):
        from routes.fuel_service import get_stations, stations_within_radius
        df, coords = get_stations()
        # Middle of Pacific Ocean — no stations
        nearby = stations_within_radius(25.0, -160.0, 10, df, coords)
        self.assertEqual(len(nearby), 0)


class RouteAPITests(TestCase):
    def setUp(self):
        self.client = APIClient()

    def test_get_usage(self):
        resp = self.client.get("/api/route/")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["service"], "Fuel Route Optimizer API")

    @patch("routes.route_planner.requests.get")
    def test_post_valid_route(self, mock_get):
        mock_get.return_value = _make_mock_osrm_response()
        resp = self.client.post(
            "/api/route/",
            data=json.dumps({"start": "Chicago, IL", "end": "Denver, CO"}),
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertTrue(data["success"])
        self.assertIn("route_summary", data)
        self.assertIn("fuel_stops", data)
        self.assertIn("route_geometry", data)
        self.assertIn("map_links", data)
        self.assertGreater(data["route_summary"]["total_distance_miles"], 0)
        self.assertGreater(data["route_summary"]["total_fuel_cost_usd"], 0)

    @patch("routes.route_planner.requests.get")
    def test_fuel_stops_within_range(self, mock_get):
        mock_get.return_value = _make_mock_osrm_response()
        resp = self.client.post(
            "/api/route/",
            data=json.dumps({"start": "Chicago, IL", "end": "Denver, CO"}),
            content_type="application/json",
        )
        data = resp.json()
        stops = data["fuel_stops"]
        # Each stop must be ≤ 500 miles apart
        mile_markers = [0] + [s["mile_marker"] for s in stops]
        for i in range(1, len(mile_markers)):
            gap = mile_markers[i] - mile_markers[i - 1]
            self.assertLessEqual(gap, 500, f"Gap {gap} > 500 miles between stops {i-1} and {i}")

    def test_missing_start(self):
        resp = self.client.post(
            "/api/route/",
            data=json.dumps({"end": "Denver, CO"}),
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 400)
        self.assertFalse(resp.json()["success"])

    def test_missing_end(self):
        resp = self.client.post(
            "/api/route/",
            data=json.dumps({"start": "Chicago, IL"}),
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 400)

    def test_blank_start(self):
        resp = self.client.post(
            "/api/route/",
            data=json.dumps({"start": "  ", "end": "Denver, CO"}),
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 400)

    def test_invalid_location(self):
        resp = self.client.post(
            "/api/route/",
            data=json.dumps({"start": "NOWHERE_LAND_XYZ", "end": "Denver, CO"}),
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 422)
        self.assertFalse(resp.json()["success"])

    @patch("routes.route_planner.requests.get")
    def test_cost_calculation(self, mock_get):
        mock_get.return_value = _make_mock_osrm_response()
        resp = self.client.post(
            "/api/route/",
            data=json.dumps({"start": "Chicago, IL", "end": "Denver, CO"}),
            content_type="application/json",
        )
        data = resp.json()
        summary = data["route_summary"]
        # total_gallons should equal total_miles / 10
        expected_gallons = summary["total_distance_miles"] / 10
        self.assertAlmostEqual(summary["total_gallons_needed"], expected_gallons, places=1)

    @patch("routes.route_planner.requests.get")
    def test_stops_have_required_fields(self, mock_get):
        mock_get.return_value = _make_mock_osrm_response()
        resp = self.client.post(
            "/api/route/",
            data=json.dumps({"start": "Chicago, IL", "end": "Denver, CO"}),
            content_type="application/json",
        )
        required = {
            "name", "address", "city", "state", "lat", "lon",
            "price_per_gallon", "mile_marker",
            "gallons_purchased", "segment_cost_usd", "detour_miles",
        }
        for stop in resp.json()["fuel_stops"]:
            for field in required:
                self.assertIn(field, stop, f"Missing field '{field}' in stop")

    @patch("routes.route_planner.requests.get")
    def test_geometry_is_geojson(self, mock_get):
        mock_get.return_value = _make_mock_osrm_response()
        resp = self.client.post(
            "/api/route/",
            data=json.dumps({"start": "Chicago, IL", "end": "Denver, CO"}),
            content_type="application/json",
        )
        geom = resp.json()["route_geometry"]
        self.assertEqual(geom["type"], "LineString")
        self.assertIsInstance(geom["coordinates"], list)
        self.assertGreater(len(geom["coordinates"]), 1)
        for coord in geom["coordinates"]:
            self.assertEqual(len(coord), 2)   # [lon, lat]
