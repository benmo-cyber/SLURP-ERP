"""
Django settings for wwi_erp project.
"""

from pathlib import Path
import os

from corsheaders.defaults import default_headers

# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent


def _load_dotenv(path: Path) -> None:
    """Load KEY=VALUE pairs from a local .env into os.environ (does not override existing)."""
    if not path.is_file():
        return
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, val = line.partition("=")
        key = key.strip()
        if not key or key in os.environ:
            continue
        val = val.strip()
        if (val.startswith('"') and val.endswith('"')) or (val.startswith("'") and val.endswith("'")):
            val = val[1:-1]
        os.environ[key] = val


_load_dotenv(BASE_DIR / ".env")

# SECURITY WARNING: keep the secret key used in production secret!
SECRET_KEY = 'django-insecure-dev-key-change-in-production'

# SECURITY WARNING: don't run with debug turned on in production!
DEBUG = True

ALLOWED_HOSTS = ['*']

# Application definition
INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'rest_framework',
    'corsheaders',
    'erp_core.apps.ErpCoreConfig',
    'slurp_ui.apps.SlurpUiConfig',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'corsheaders.middleware.CorsMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'wwi_erp.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
                'slurp_ui.context_processors.slurp_ui',
            ],
            'builtins': [
                'slurp_ui.templatetags.slurp_format',
            ],
        },
    },
]

LOGIN_URL = 'slurp_ui:login'
LOGIN_REDIRECT_URL = 'slurp_ui:inventory'
LOGOUT_REDIRECT_URL = 'slurp_ui:login'

WSGI_APPLICATION = 'wwi_erp.wsgi.application'

# Database
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': BASE_DIR.parent / 'wwi_erp.db',
    }
}

# Password validation
AUTH_PASSWORD_VALIDATORS = [
    {
        'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator',
    },
]

# Internationalization
LANGUAGE_CODE = 'en-us'
# US Central with real DST (spring forward / fall back). IANA id — not a fixed UTC offset.
# Winter: CST (UTC-6). Summer: CDT (UTC-5). Same zone the frontend uses (see appDateFormat.ts).
BUSINESS_TIME_ZONE = 'America/Chicago'
TIME_ZONE = BUSINESS_TIME_ZONE
USE_I18N = True
USE_TZ = True

# Static files (CSS, JavaScript, Images)
STATIC_URL = 'static/'
STATICFILES_DIRS = []

# Media files (user uploads)
MEDIA_URL = '/media/'
MEDIA_ROOT = BASE_DIR / 'media'

# Default primary key field type
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# REST Framework
REST_FRAMEWORK = {
    'DEFAULT_PERMISSION_CLASSES': [
        'rest_framework.permissions.IsAuthenticated',
    ],
    'DEFAULT_AUTHENTICATION_CLASSES': [
        'rest_framework.authentication.SessionAuthentication',
    ],
    'DEFAULT_PAGINATION_CLASS': 'rest_framework.pagination.PageNumberPagination',
    'PAGE_SIZE': 100
}

# HTML→PDF (xhtml2pdf): in-process is much faster on Windows (no subprocess spawn per PDF).
# Set env HTML_PDF_USE_SUBPROCESS=1 if a template hangs the worker and you need a killable child process.
HTML_PDF_USE_SUBPROCESS = os.environ.get('HTML_PDF_USE_SUBPROCESS', '').lower() in ('1', 'true', 'yes')

# Address autocomplete (vendor facility address): Mapbox Geocoding API is used when set; otherwise OSM Nominatim.
# https://account.mapbox.com/ — create a token with Geocoding scope; keep server-side only.
MAPBOX_ACCESS_TOKEN = (os.environ.get('MAPBOX_ACCESS_TOKEN') or '').strip()

# CORS settings
CORS_ALLOWED_ORIGINS = [
    "http://localhost:5173",
    "http://127.0.0.1:5173",
]

# Allow CSRF when requests come from the frontend (different port)
CSRF_TRUSTED_ORIGINS = [
    "http://localhost:5173",
    "http://127.0.0.1:5173",
    "http://localhost:5174",
    "http://127.0.0.1:5174",
    "http://localhost:5175",
    "http://127.0.0.1:5175",
    "http://localhost:3000",
    "http://127.0.0.1:3000",
    "http://localhost:4173",
    "http://127.0.0.1:4173",
]

CORS_ALLOW_ALL_ORIGINS = True  # For development only
CORS_ALLOW_CREDENTIALS = True  # Required for session cookie auth
# Custom headers on API requests (e.g. checkout ship idempotency) must be listed or preflight fails.
CORS_ALLOW_HEADERS = list(default_headers) + [
    'x-idempotency-key',
]

# Email configuration — set values in backend_django/.env (not in this file).
# After leaving GoDaddy, use your new Microsoft 365 mailbox password or app password.
EMAIL_BACKEND = "django.core.mail.backends.smtp.EmailBackend"
EMAIL_HOST = os.environ.get("EMAIL_HOST", "smtp.office365.com")
EMAIL_PORT = int(os.environ.get("EMAIL_PORT", "587"))
EMAIL_USE_TLS = os.environ.get("EMAIL_USE_TLS", "true").lower() in ("1", "true", "yes")
EMAIL_HOST_USER = (os.environ.get("EMAIL_HOST_USER") or "").strip()
EMAIL_HOST_PASSWORD = os.environ.get("EMAIL_HOST_PASSWORD") or ""
DEFAULT_FROM_EMAIL = (os.environ.get("DEFAULT_FROM_EMAIL") or EMAIL_HOST_USER).strip()
EMAIL_REPLY_TO = (os.environ.get("EMAIL_REPLY_TO") or DEFAULT_FROM_EMAIL).strip()

# Frontend URL for password reset links in email
FRONTEND_URL = os.environ.get('FRONTEND_URL', 'http://localhost:5173')