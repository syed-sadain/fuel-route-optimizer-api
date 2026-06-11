import logging
import time

from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status

from .serializers import RouteRequestSerializer
from .route_planner import plan_route

logger = logging.getLogger(__name__)


class RouteView(APIView):
    """
    POST /api/route/
    ─────────────────
    Plan a fuel-cost-optimised road trip route across the USA.

    Request body  (application/json):
    ┌──────────────────────────────────────────┐
    │  {                                       │
    │    "start": "Chicago, IL",               │
    │    "end":   "Denver, CO"                 │
    │  }                                       │
    └──────────────────────────────────────────┘

    Response fields:
      origin / destination   — geocoded coordinates + display name
      route_summary          — distance, duration, total cost, # stops
      fuel_stops[]           — ordered cheapest fuel stops along route
        • name, address, city, state
        • lat / lon
        • price_per_gallon
        • mile_marker         (distance from origin at refuel point)
        • segment_miles       (miles covered on this tank)
        • gallons_purchased
        • segment_cost_usd
        • detour_miles        (how far the station is off the route centre-line)
      map_links              — OpenStreetMap + Google Maps URLs
      route_geometry         — GeoJSON LineString for custom map rendering
    """

    def post(self, request):
        ser = RouteRequestSerializer(data=request.data)
        if not ser.is_valid():
            return Response(
                {"success": False, "errors": ser.errors},
                status=status.HTTP_400_BAD_REQUEST,
            )

        start = ser.validated_data["start"]
        end   = ser.validated_data["end"]

        t0 = time.perf_counter()
        try:
            result = plan_route(start, end)
        except ValueError as exc:
            logger.warning("plan_route validation error: %s", exc)
            return Response(
                {"success": False, "error": str(exc)},
                status=status.HTTP_422_UNPROCESSABLE_ENTITY,
            )
        except Exception:
            logger.exception("Unexpected error in plan_route")
            return Response(
                {"success": False, "error": "Internal server error. Please try again."},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        elapsed = round(time.perf_counter() - t0, 3)
        result["_meta"] = {
            "computation_time_seconds": elapsed,
            "geocoding":  "offline — bundled US-cities database (29 880 cities)",
            "routing":    "OSRM public demo server (1 API call)",
            "fuel_data":  "OPIS Truckstop Fuel Prices — 8 151 US stations",
        }

        return Response({"success": True, **result}, status=status.HTTP_200_OK)

    def get(self, request):
        """Usage guide (GET /api/route/)."""
        return Response({
            "service": "Fuel Route Optimizer API",
            "version": "1.0.0",
            "description": (
                "Plans the most cost-effective fuel stops for a US road trip. "
                "Assumes a vehicle with 500-mile range and 10 MPG."
            ),
            "endpoint": {
                "method":      "POST",
                "path":        "/api/route/",
                "content_type":"application/json",
                "body": {
                    "start": "Starting US location  (required)  e.g. 'New York, NY'",
                    "end":   "Destination US location (required) e.g. 'Los Angeles, CA'",
                },
            },
            "example_request": {
                "start": "Chicago, IL",
                "end":   "Denver, CO",
            },
            "vehicle_assumptions": {
                "max_range_miles": 500,
                "mpg":             10,
                "refuel_trigger":  "every 400 miles (80 % of range)",
            },
        })
