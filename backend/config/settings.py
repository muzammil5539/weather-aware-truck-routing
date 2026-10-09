"""Django settings for the weather-aware truck routing API."""
from pathlib import Path

import dj_database_url
from dotenv import load_dotenv
import os

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")


def env_bool(name: str, default: bool = False) -> bool:
    return os.getenv(name, str(default)).strip().lower() in {"1", "true", "yes", "on"}


def env_list(name: str, default: str = "") -> list[str]:
    return [item.strip() for item in os.getenv(name, default).split(",") if item.strip()]


SECRET_KEY = os.getenv("DJANGO_SECRET_KEY", "dev-insecure-key-do-not-use-in-production")
DEBUG = env_bool("DJANGO_DEBUG", True)
ALLOWED_HOSTS = env_list("DJANGO_ALLOWED_HOSTS", "localhost,127.0.0.1")
CSRF_TRUSTED_ORIGINS = env_list("DJANGO_CSRF_TRUSTED_ORIGINS")

INSTALLED_APPS = [
    "django.contrib.contenttypes",
    "django.contrib.auth",
    "django.contrib.staticfiles",
    "corsheaders",
    "rest_framework",
    "routing",
]

MIDDLEWARE = [
    "corsheaders.middleware.CorsMiddleware",
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.middleware.common.CommonMiddleware",
    # DRF views are csrf_exempt unless SessionAuthentication is in use, which it
    # is not here, so this guards any non-DRF view added later without
    # affecting the API.
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

X_FRAME_OPTIONS = "DENY"

ROOT_URLCONF = "config.urls"
WSGI_APPLICATION = "config.wsgi.application"
TEMPLATES = [{"BACKEND": "django.template.backends.django.DjangoTemplates", "APP_DIRS": True, "DIRS": []}]

DATABASES = {
    "default": dj_database_url.config(
        default=os.getenv("DATABASE_URL", f"sqlite:///{BASE_DIR / 'db.sqlite3'}"),
        conn_max_age=600,
    )
}

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage"},
}

# The assessment app has no accounts; the API is open and read/write by anyone.
# See docs/ASSUMPTIONS.md.
REST_FRAMEWORK = {
    "DEFAULT_PERMISSION_CLASSES": ["rest_framework.permissions.AllowAny"],
    "DEFAULT_AUTHENTICATION_CLASSES": [],
    "DEFAULT_RENDERER_CLASSES": ["rest_framework.renderers.JSONRenderer"],
    "EXCEPTION_HANDLER": "routing.exceptions.api_exception_handler",
}
if DEBUG:
    REST_FRAMEWORK["DEFAULT_RENDERER_CLASSES"].append(
        "rest_framework.renderers.BrowsableAPIRenderer"
    )

CORS_ALLOWED_ORIGINS = env_list(
    "CORS_ALLOWED_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173"
)
CORS_ALLOW_ALL_ORIGINS = env_bool("CORS_ALLOW_ALL_ORIGINS", False)

# --- Upstream providers (all free, no API key) -------------------------------
# Each service lists its providers in preference order and falls through to the
# next only on a rate limit, a timeout or a server fault. All are free and
# key-less, so a demo keeps working when one of them throttles a shared cloud IP.
OSRM_BASE_URLS = env_list(
    "OSRM_BASE_URLS",
    "https://router.project-osrm.org,https://routing.openstreetmap.de/routed-car",
)
OSRM_BASE_URL = OSRM_BASE_URLS[0]

NOMINATIM_BASE_URL = os.getenv("NOMINATIM_BASE_URL", "https://nominatim.openstreetmap.org")
PHOTON_BASE_URL = os.getenv("PHOTON_BASE_URL", "https://photon.komoot.io")

OPEN_METEO_BASE_URL = os.getenv("OPEN_METEO_BASE_URL", "https://api.open-meteo.com/v1/forecast")
MET_NO_BASE_URL = os.getenv(
    "MET_NO_BASE_URL", "https://api.met.no/weatherapi/locationforecast/2.0/compact"
)
# MET Norway serves one coordinate per request, so a fallback trip fans out.
# Their terms ask for a identifying User-Agent and modest concurrency.
MET_NO_MAX_CONCURRENCY = int(os.getenv("MET_NO_MAX_CONCURRENCY", "5"))
GEOCODER_USER_AGENT = os.getenv("GEOCODER_USER_AGENT", "weather-aware-truck-routing/1.0")
UPSTREAM_TIMEOUT_SECONDS = float(os.getenv("UPSTREAM_TIMEOUT_SECONDS", "20"))

# HTTPS hardening, off in development and switched on by the deployment env.
SECURE_SSL_REDIRECT = env_bool("DJANGO_SECURE_SSL_REDIRECT", False)
SECURE_HSTS_SECONDS = int(os.getenv("DJANGO_SECURE_HSTS_SECONDS", "0"))
SECURE_HSTS_INCLUDE_SUBDOMAINS = SECURE_HSTS_SECONDS > 0
SECURE_HSTS_PRELOAD = SECURE_HSTS_SECONDS > 0
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
SESSION_COOKIE_SECURE = not DEBUG
CSRF_COOKIE_SECURE = not DEBUG

# Forecasts are cached so a repeated trip costs the rate-limited free tier
# nothing. In-process by default; set REDIS_URL to share it across workers.
CACHES = {
    "default": (
        {"BACKEND": "django.core.cache.backends.redis.RedisCache", "LOCATION": os.getenv("REDIS_URL")}
        if os.getenv("REDIS_URL")
        else {
            "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
            "LOCATION": "truck-routing",
            "OPTIONS": {"MAX_ENTRIES": 5000},
        }
    )
}

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "handlers": {"console": {"class": "logging.StreamHandler"}},
    "root": {"handlers": ["console"], "level": os.getenv("DJANGO_LOG_LEVEL", "INFO")},
}
