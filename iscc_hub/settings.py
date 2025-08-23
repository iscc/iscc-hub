from pathlib import Path

import environ
from django.conf.locale.en import formats as en_formats
from django.templatetags.static import static

# Build paths inside the project
BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
DATA_DIR.mkdir(exist_ok=True)

DEV = (BASE_DIR / "tests").exists()
if DEV:
    print("[DEV] Development mode detected (tests/ directory found)")
    print("[WARNING] Using INSECURE development defaults - DO NOT USE IN PRODUCTION!")
    print("[WARNING] These defaults are for local development only and are NOT secure.\n")


env = environ.Env()

####################################################################################################
# Mandatory Settings (no defaults - must be set explicitly)                                        #
####################################################################################################

DEBUG = env.bool("DJANGO_DEBUG", default=True if DEV else env.NOTSET)
SECRET_KEY = env("DJANGO_SECRET_KEY", default="test-secret-key-for-testing-only" if DEV else env.NOTSET)
ISCC_HUB_DOMAIN = env("ISCC_HUB_DOMAIN", default="localhost" if DEV else env.NOTSET)
ISCC_HUB_SECKEY = env(
    "ISCC_HUB_SECKEY", default="z3u2RDonZ81AFKiw8QCPKcsyg8Yy2MmYQNxfBn51SS2QmMiw" if DEV else env.NOTSET
)
ISCC_HUB_ID = env.int("ISCC_HUB_ID", default=0 if DEV else env.NOTSET)

####################################################################################################

# Build metadata from Docker image
BUILD_COMMIT = env("BUILD_COMMIT", default="unknown")
BUILD_TAG = env("BUILD_TAG", default="unknown")
BUILD_TIMESTAMP = env("BUILD_TIMESTAMP", default="unknown")

# Database file name - defaults based on DEBUG setting
# Development: iscc-hub-dev.db
# Production: iscc-hub-{ID}.db where ID is the hub ID
default_db_name = "iscc-hub-dev.db" if DEV else f"iscc-hub-{ISCC_HUB_ID:04d}.db"
ISCC_HUB_DB_NAME = env("ISCC_HUB_DB_NAME", default=default_db_name)

# Realm-0 (SUBTYPE="0000") for sanbdox hub network
# Realm-1 (SUBTYPE="0001") for operational network
ISCC_HUB_REALM = env.int("ISCC_HUB_REALM", default=0 if DEV else env.NOTSET)

ALLOWED_HOSTS = env.list("DJANGO_ALLOWED_HOSTS", default=(ISCC_HUB_DOMAIN,))

# CSRF settings for reverse proxy deployments
CSRF_TRUSTED_ORIGINS = env.list("DJANGO_CSRF_TRUSTED_ORIGINS", default=[f"https://{ISCC_HUB_DOMAIN}"])

# Disable automatic trailing slash appending for clean URLs
APPEND_SLASH = False


INSTALLED_APPS = [
    "unfold",
    "unfold.contrib.filters",
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "servestatic.runserver_nostatic",
    "iscc_hub",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "servestatic.middleware.ServeStaticMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "iscc_hub.middleware.ContentNegotiationMiddleware",  # Content negotiation must come early
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "iscc_hub.urls_views"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "iscc_hub.context.hub_context",
            ],
        },
    },
]

WSGI_APPLICATION = "iscc_hub.wsgi.application"


# Database
# https://docs.djangoproject.com/en/5.2/ref/settings/#databases

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": DATA_DIR / ISCC_HUB_DB_NAME,
        "OPTIONS": {
            "transaction_mode": "IMMEDIATE",  # Required for gapless sequences !!!
            "init_command": ("PRAGMA journal_mode=WAL;PRAGMA synchronous=FULL;PRAGMA busy_timeout=5000;"),
        },
        "TEST": {
            "NAME": DATA_DIR / "test_db.sqlite3",  # Use persisted file, not in-memory
            "SERIALIZE": True,  # Serialize database state for proper transaction testing
            # Explicitly set OPTIONS for test database to match production settings
            "OPTIONS": {
                "transaction_mode": "IMMEDIATE",  # Required for gapless sequences !!!
                "init_command": ("PRAGMA journal_mode=WAL;PRAGMA synchronous=FULL;PRAGMA busy_timeout=5000;"),
            },
        },
    }
}


ATOMIC_REQUESTS = False  # This is the default, but we better make sure with transaction mode IMMEDIATE

# Password validation
# https://docs.djangoproject.com/en/5.2/ref/settings/#auth-password-validators

AUTH_PASSWORD_VALIDATORS = [
    {
        "NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.CommonPasswordValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.NumericPasswordValidator",
    },
]


# Internationalization
# https://docs.djangoproject.com/en/5.2/topics/i18n/

LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True

# Override default datetime formats for microsecond precision in django admin
en_formats.DATETIME_FORMAT = "Y-m-d\\TH:i:s.u\\Z"
en_formats.SHORT_DATETIME_FORMAT = en_formats.DATETIME_FORMAT

SERIALIZATION_MODULES = {"json_micro": "iscc_hub.serializers"}

# Static files (CSS, JavaScript, Images)
# https://docs.djangoproject.com/en/5.2/howto/static-files/

STATIC_URL = "static/"
STATICFILES_DIRS = [
    BASE_DIR / "iscc_hub" / "static",
]

# ServeStatic configuration
SERVESTATIC_ROOT = BASE_DIR / "iscc_hub" / "static"
SERVESTATIC_INDEX_FILE = "index.html"
# Enable finders in production to serve static files without collectstatic
SERVESTATIC_USE_FINDERS = True
SERVESTATIC_USE_MANIFEST = False

# Default primary key field type
# https://docs.djangoproject.com/en/5.2/ref/settings/#default-auto-field

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# Django Unfold Configuration
UNFOLD = {
    "SITE_TITLE": f"ISCC-HUB / #{ISCC_HUB_ID:04d}",
    "SITE_HEADER": f"ISCC-HUB / #{ISCC_HUB_ID:04d}",
    "SITE_SUBHEADER": "ISCC Discovery Protocol",
    "SITE_SYMBOL": "orbit",
    "STYLES": [
        lambda request: static("css/admin_custom.css"),
    ],
}
