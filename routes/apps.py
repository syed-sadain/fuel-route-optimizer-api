import logging
from django.apps import AppConfig

logger = logging.getLogger(__name__)


class RoutesConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "routes"

    def ready(self):
        import os
        # Only pre-load in the main runserver process, not in migrations etc.
        if os.environ.get("RUN_MAIN") != "true" and not os.environ.get("PRELOAD_STATIONS"):
            return
        try:
            from .fuel_service import get_stations
            df, _ = get_stations()
            logger.info("FuelRouteAPI: %d fuel stations loaded into memory.", len(df))
        except Exception as exc:
            logger.warning("FuelRouteAPI: could not pre-load stations: %s", exc)
