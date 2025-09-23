from collections import OrderedDict
from pathlib import Path

import environ
from django.conf.locale.en import formats as en_formats
from django.templatetags.static import static
from django.urls import reverse_lazy

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

# Build metadata from Docker image
BUILD_COMMIT = env("BUILD_COMMIT", default="unknown")
BUILD_TAG = env("BUILD_TAG", default="unknown")
BUILD_TIMESTAMP = env("BUILD_TIMESTAMP", default="unknown")


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


# Database file name - defaults based on DEBUG setting
# Development: iscc-hub-dev.db
# Production: iscc-hub-{ID}.db where ID is the hub ID
default_db_name = "iscc-hub-dev.db" if DEV else f"iscc-hub-{ISCC_HUB_ID:04d}.db"
ISCC_HUB_DB_NAME = env("ISCC_HUB_DB_NAME", default=default_db_name)
ISCC_HUB_DB_PATH = DATA_DIR / ISCC_HUB_DB_NAME

# Realm-0 (SUBTYPE="0000") for sanbdox hub network
# Realm-1 (SUBTYPE="0001") for operational network
ISCC_HUB_REALM = env.int("ISCC_HUB_REALM", default=0 if DEV else env.NOTSET)

# List of RFC3161 Timestamping servers for checkpoint timestamping
# Ordered by performance (fastest first) based on testing with tsp-client
# Use `python scripts/timestamp.py test` to re-test TSA server performance
ISCC_HUB_TIMESTAMP_SERVERS = env.list(
    "ISCC_HUB_TIMESTAMP_SERVERS",
    default=[
        "http://tss.accv.es:8318/tsa",
        "http://ts.ssl.com",
        "http://timestamp.identrust.com",
        "http://timestamp.digicert.com",
        "http://timestamp.sectigo.com",
    ],
)

ISCC_HUB_SQLITE_SYNC_MODE = env.str("ISCC_HUB_SQLITE_SYNC_MODE", default="NORMAL")

# Hub list initial synchronization (used in Docker startup sequence)
ISCC_HUB_LIST_INITIAL_SYNC = env.bool("ISCC_HUB_LIST_INITIAL_SYNC", default=True)

ALLOWED_HOSTS = env.list("DJANGO_ALLOWED_HOSTS", default=(ISCC_HUB_DOMAIN,))

# CSRF settings for reverse proxy deployments
CSRF_TRUSTED_ORIGINS = env.list("DJANGO_CSRF_TRUSTED_ORIGINS", default=[f"https://{ISCC_HUB_DOMAIN}"])

# Disable automatic trailing slash appending for clean URLs
APPEND_SLASH = False


INSTALLED_APPS = [
    "unfold.contrib.constance",
    "constance",
    "constance.backends.database",
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
    "django_q",
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
        "NAME": ISCC_HUB_DB_PATH,
        "CONN_MAX_AGE": 600,
        "OPTIONS": {
            "transaction_mode": "IMMEDIATE",  # Required for gapless sequences !!!
            "init_command": (
                "PRAGMA journal_mode=WAL;"
                f"PRAGMA synchronous={ISCC_HUB_SQLITE_SYNC_MODE};"
                "PRAGMA busy_timeout=5000;"
                "PRAGMA cache_size=10000;"
            ),
        },
        "TEST": {
            "NAME": DATA_DIR / "test_db.sqlite3",  # Use persisted file, not in-memory
            "CONN_MAX_AGE": 600,
            "SERIALIZE": True,  # Serialize database state for proper transaction testing
            # Explicitly set OPTIONS for test database to match production settings
            "OPTIONS": {
                "transaction_mode": "IMMEDIATE",  # Required for gapless sequences !!!
                "init_command": (
                    "PRAGMA journal_mode=WAL;"
                    f"PRAGMA synchronous={ISCC_HUB_SQLITE_SYNC_MODE};"
                    "PRAGMA busy_timeout=5000;"
                    "PRAGMA cache_size=10000;"
                ),
            },
        },
    }
}


ATOMIC_REQUESTS = False  # This is the default, but we better make sure with transaction mode IMMEDIATE


# Shared memory cache used for django-constance configuration values
CACHES = {
    "default": {
        "BACKEND": "shared_memory_dict.caches.django.SharedMemoryCache",
        "LOCATION": "memory",
        "OPTIONS": {"MEMORY_BLOCK_SIZE": 1024 * 1024},  # 1MB instead of 1KB
    }
}

# Password validation
# https://docs.djangoproject.com/en/5.2/ref/settings/#auth-password-validators

AUTH_USER_MODEL = "iscc_hub.User"

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

# Set media root as subfolder under ServeStatic root
MEDIA_ROOT = SERVESTATIC_ROOT / "media"
MEDIA_URL = "media/"


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
    "COLORS": {
        "primary": {
            # ISCC Blue gradient from design.md
            "50": "240 248 255",  # Lightest blue
            "100": "219 234 254",  # Very light blue
            "200": "191 219 254",  # Light blue
            "300": "122 194 247",  # Light Cyan (#7ac2f7)
            "400": "69 150 245",  # Sky Blue (#4596f5)
            "500": "0 84 178",  # ISCC Blue (#0054b2) - Primary
            "600": "0 84 178",  # ISCC Blue (#0054b2) - Used for site icon
            "700": "14 43 79",  # Darker navy
            "800": "10 32 59",  # Even darker
            "900": "7 22 39",  # Very dark
            "950": "4 11 20",  # Almost black
        },
        "base": {
            # Neutral colors from design.md
            "50": "248 249 250",  # Off White (#f8f9fa)
            "100": "233 236 239",  # Light Gray (#e9ecef)
            "200": "222 226 230",  # Slightly darker
            "300": "206 212 218",  # Light-medium gray
            "400": "173 181 189",  # Medium-light gray
            "500": "108 117 125",  # Medium Gray (#6c757d)
            "600": "73 80 87",  # Medium-dark gray
            "700": "52 58 64",  # Dark Gray (#343a40)
            "800": "33 37 41",  # Near Black (#212529)
            "900": "23 26 29",  # Very dark
            "950": "12 14 16",  # Almost black
        },
    },
    "SIDEBAR": {
        "show_search": True,
        "command_search": True,
        "show_all_applications": False,  # Don't show all apps dropdown
        "navigation": [
            {
                "title": "ISCC-HUB",
                "collapsible": False,
                "items": [
                    {
                        "title": "Declarations",
                        "icon": "description",
                        "link": "/admin/iscc_hub/isccdeclaration/",
                    },
                    {
                        "title": "Events",
                        "icon": "history",
                        "link": "/admin/iscc_hub/event/",
                    },
                    {
                        "title": "Checkpoints",
                        "icon": "flag",
                        "link": "/admin/iscc_hub/checkpoint/",
                    },
                    {
                        "title": "Hubs",
                        "icon": "hub",
                        "link": "/admin/iscc_hub/hub/",
                    },
                    {
                        "title": "Configuration",
                        "icon": "settings",
                        "link": "/admin/constance/config/",
                    },
                ],
            },
            {
                "title": "Accounts",
                "collapsible": True,
                "items": [
                    {
                        "title": "Users",
                        "icon": "person",
                        "link": "/admin/iscc_hub/user/",
                    },
                    {
                        "title": "Pubkeys",
                        "icon": "key",
                        "link": "/admin/iscc_hub/pubkey/",
                    },
                    {
                        "title": "Groups",
                        "icon": "group",
                        "link": "/admin/auth/group/",
                    },
                ],
            },
            {
                "title": "Tasks",
                "collapsible": True,
                "items": [
                    {
                        "title": "Scheduled",
                        "icon": "schedule",
                        "link": "/admin/django_q/schedule/",
                    },
                    {
                        "title": "Queued",
                        "icon": "queue",
                        "link": "/admin/django_q/ormq/",
                    },
                    {
                        "title": "Success",
                        "icon": "check_circle",
                        "link": "/admin/django_q/success/",
                    },
                    {
                        "title": "Failed",
                        "icon": "error",
                        "link": "/admin/django_q/failure/",
                    },
                ],
            },
        ],
    },
    "SHOW_HISTORY": False,  # Disable history links for better performance
}

# Django-Q2 Configuration
Q_CLUSTER = {
    "name": "iscc-hub",
    "workers": 1,
    "timeout": 90,
    "retry": 120,
    "orm": "default",
    "poll": 3,
    "catch_up": False,
    "label": "Tasks",
}

# Constance Configuration for Dynamic Settings
UNFOLD_CONSTANCE_ADDITIONAL_FIELDS = {
    str: [
        "django.forms.CharField",
        {
            "widget": "unfold.widgets.UnfoldAdminTextInputWidget",
            "required": False,
        },
    ],
    "text_field": [
        "django.forms.CharField",
        {
            "widget": "unfold.widgets.UnfoldAdminTextareaWidget",
            "required": False,
        },
    ],
    int: [
        "django.forms.IntegerField",
        {
            "widget": "unfold.widgets.UnfoldAdminIntegerFieldWidget",
        },
    ],
    bool: [
        "django.forms.BooleanField",
        {
            "widget": "unfold.widgets.UnfoldBooleanSwitchWidget",
            "required": False,
        },
    ],
    "file_field": [
        "django.forms.fields.FileField",
        {
            "widget": "unfold.widgets.UnfoldAdminFileFieldWidget",
        },
    ],
    "image_field": [
        "django.forms.fields.ImageField",
        {
            "widget": "unfold.widgets.UnfoldAdminImageFieldWidget",
            "required": False,
        },
    ],
}

CONSTANCE_BACKEND = "constance.backends.database.DatabaseBackend"
CONSTANCE_DATABASE_PREFIX = "constance:iscc-hub:"
CONSTANCE_DATABASE_CACHE_BACKEND = "default"
CONSTANCE_ADDITIONAL_FIELDS = {**UNFOLD_CONSTANCE_ADDITIONAL_FIELDS}

CONSTANCE_CONFIG = OrderedDict(
    [
        # Organization Identity
        ("ORG_NAME", ("", "Organization Name", str)),
        ("ORG_LOGO", (None, "Organization Logo", "image_field")),
        ("ORG_URL", ("", "Organization URL", str)),
        ("ORG_TAGLINE", ("", "Organization Tagline (e.g., 'Digital Archives at Example University')", "text_field")),
        # Call to Action
        ("CTA_ENABLED", (False, "Enable Call-to-Action Section", bool)),
        ("CTA_TITLE", ("", "Call-to-Action Title (e.g., 'Integrate with Our Services')", str)),
        ("CTA_DESCRIPTION", ("", "Call-to-Action Description", "text_field")),
        ("CTA_BUTTON_TEXT", ("", "Call-to-Action Button Text (e.g., 'Explore Our Repository')", str)),
        ("CTA_BUTTON_URL", ("", "Call-to-Action Button URL", str)),
        # Access Control
        ("OPEN_ACCESS", (True, "Open Access", bool)),
    ]
)
