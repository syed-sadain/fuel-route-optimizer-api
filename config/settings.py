from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
SECRET_KEY = 'django-insecure-fuel-route-api-secret-key-change-in-production'
DEBUG = True
ALLOWED_HOSTS = ['*']

INSTALLED_APPS = [
    'django.contrib.contenttypes',
    'django.contrib.auth',          # required by DRF
    'django.contrib.staticfiles',
    'rest_framework',
    'routes.apps.RoutesConfig',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'django.middleware.common.CommonMiddleware',
]

ROOT_URLCONF = 'config.urls'
WSGI_APPLICATION = 'config.wsgi.application'

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': BASE_DIR / 'db.sqlite3',
    }
}

REST_FRAMEWORK = {
    'DEFAULT_RENDERER_CLASSES': [
        'rest_framework.renderers.JSONRenderer',
    ],
    'DEFAULT_PARSER_CLASSES': [
        'rest_framework.parsers.JSONParser',
    ],
    'DEFAULT_AUTHENTICATION_CLASSES': [],   # no auth needed for this API
    'DEFAULT_PERMISSION_CLASSES': [],       # open API
    'EXCEPTION_HANDLER': 'routes.exceptions.custom_exception_handler',
}

STATIC_URL = '/static/'
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# ── App constants ────────────────────────────────────────────────────────
VEHICLE_RANGE_MILES = 500
VEHICLE_MPG         = 10
FUEL_CSV_PATH       = BASE_DIR / 'routes' / 'fuel_prices.csv'
CITIES_CSV_PATH     = BASE_DIR / 'routes' / 'uscities_lite.csv'
OSRM_BASE_URL       = 'http://router.project-osrm.org'
NOMINATIM_URL       = 'https://nominatim.openstreetmap.org'

LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {'simple': {'format': '[%(asctime)s] %(levelname)s %(name)s: %(message)s'}},
    'handlers': {'console': {'class': 'logging.StreamHandler', 'formatter': 'simple'}},
    'root': {'handlers': ['console'], 'level': 'INFO'},
}
