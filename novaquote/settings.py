"""
Django settings for NovaQuote project.

Environment variables (production — see DEPLOYMENT.md):
  DJANGO_SECRET_KEY       — required when DEBUG=0
  DJANGO_DEBUG            — 0/false/no for production
  DJANGO_ALLOWED_HOSTS    — comma-separated hostnames
  DJANGO_SECURE_SSL_REDIRECT, DJANGO_SESSION_COOKIE_SECURE, DJANGO_CSRF_COOKIE_SECURE
  DJANGO_DATABASE         — set to "postgres" to use PostgreSQL (+ PG* vars)
"""

import os
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent.parent


def _env_bool(name: str, default: bool = False) -> bool:
    v = (os.environ.get(name, "") or "").strip().lower()
    if v in ("1", "true", "yes", "on"):
        return True
    if v in ("0", "false", "no", "off"):
        return False
    return default


# -----------------------------------------------------------------------------
# Core security
# -----------------------------------------------------------------------------

SECRET_KEY = os.environ.get(
    "DJANGO_SECRET_KEY",
    "django-insecure-(-oro-fs1tmt4s%jp24#zb^nx(^4v_&r36%va(49^xnu8vup)p",
)

DEBUG = _env_bool("DJANGO_DEBUG", True)

_allowed_raw = (os.environ.get("DJANGO_ALLOWED_HOSTS", "") or "").strip()
if _allowed_raw:
    ALLOWED_HOSTS = [h.strip() for h in _allowed_raw.split(",") if h.strip()]
elif DEBUG:
    ALLOWED_HOSTS = ["127.0.0.1", "localhost", "[::1]"]
else:
    ALLOWED_HOSTS = []

# -----------------------------------------------------------------------------
# HTTPS / cookies (enable behind TLS in production)
# -----------------------------------------------------------------------------

if not DEBUG:
    SECURE_SSL_REDIRECT = _env_bool("DJANGO_SECURE_SSL_REDIRECT", False)
    SESSION_COOKIE_SECURE = _env_bool("DJANGO_SESSION_COOKIE_SECURE", True)
    CSRF_COOKIE_SECURE = _env_bool("DJANGO_CSRF_COOKIE_SECURE", True)
    SECURE_HSTS_SECONDS = int(os.environ.get("DJANGO_SECURE_HSTS_SECONDS", "0"))
    if SECURE_HSTS_SECONDS > 0:
        SECURE_HSTS_INCLUDE_SUBDOMAINS = _env_bool("DJANGO_SECURE_HSTS_INCLUDE_SUBDOMAINS", False)
        SECURE_HSTS_PRELOAD = _env_bool("DJANGO_SECURE_HSTS_PRELOAD", False)
    # SECURE_BROWSER_XSS_FILTER was removed in Django 4.0; use Content-Type nosniff (default in Django).
    SECURE_CONTENT_TYPE_NOSNIFF = True
    X_FRAME_OPTIONS = "DENY"

# -----------------------------------------------------------------------------
# Application
# -----------------------------------------------------------------------------

INSTALLED_APPS = [
    "pricelist",
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.locale.LocaleMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "pricelist.middleware.LoginRequiredMiddleware",
    "pricelist.middleware.LanguageFromSettingsMiddleware",
]

ROOT_URLCONF = "novaquote.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.template.context_processors.i18n",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "pricelist.context_processors.nav_categories",
                "pricelist.context_processors.general_settings",
            ],
        },
    },
]

WSGI_APPLICATION = "novaquote.wsgi.application"

# -----------------------------------------------------------------------------
# Database
# -----------------------------------------------------------------------------

if (os.environ.get("DJANGO_DATABASE", "") or "").strip().lower() in ("postgres", "postgresql"):
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.postgresql",
            "NAME": os.environ.get("PGDATABASE", "novaquote"),
            "USER": os.environ.get("PGUSER", "novaquote"),
            "PASSWORD": os.environ.get("PGPASSWORD", ""),
            "HOST": os.environ.get("PGHOST", "localhost"),
            "PORT": os.environ.get("PGPORT", "5432"),
        }
    }
else:
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": BASE_DIR / "db.sqlite3",
        }
    }

# -----------------------------------------------------------------------------
# Auth URLs (frontend login)
# -----------------------------------------------------------------------------

LOGIN_URL = "/accounts/login/"
LOGIN_REDIRECT_URL = "/"
LOGOUT_REDIRECT_URL = "/accounts/login/"

# -----------------------------------------------------------------------------
# Password validation
# -----------------------------------------------------------------------------

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

# -----------------------------------------------------------------------------
# Internationalization
# -----------------------------------------------------------------------------

TIME_ZONE = "UTC"
USE_TZ = True
LANGUAGE_CODE = "en"
LANGUAGES = [
    ("en", "English"),
    ("nl", "Nederlands"),
]
LOCALE_PATHS = [BASE_DIR / "locale"]
USE_I18N = True

# -----------------------------------------------------------------------------
# Static / media
# -----------------------------------------------------------------------------

STATIC_URL = "/static/"
MEDIA_URL = "/media/"
MEDIA_ROOT = BASE_DIR

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
