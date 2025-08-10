from pathlib import Path

import environ

# Build paths inside the project
BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
DATA_DIR.mkdir(exist_ok=True)

env = environ.Env()
environ.Env.read_env(BASE_DIR / ".env")

####################################################################################################
# Mandatory Settings (no defaults - must be set explicitly)                                        #
####################################################################################################

DEBUG = env.bool("DJANGO_DEBUG")
SECRET_KEY = env("DJANGO_SECRET_KEY")
ISCC_HUB_DB_NAME = env("ISCC_HUB_DB_NAME")
ISCC_HUB_DOMAIN = env("ISCC_HUB_DOMAIN")
ISCC_HUB_SECKEY = env("ISCC_HUB_SECKEY")
ISCC_HUB_ID = env.int("ISCC_HUB_ID")

ALLOWED_HOSTS = env.list("DJANGO_ALLOWED_HOSTS", default=(ISCC_HUB_DOMAIN,))

# Disable automatic trailing slash appending for clean URLs
APPEND_SLASH = False


INSTALLED_APPS = [
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


# Static files (CSS, JavaScript, Images)
# https://docs.djangoproject.com/en/5.2/howto/static-files/

STATIC_URL = "static/"
STATICFILES_DIRS = [
    BASE_DIR / "iscc_hub" / "static",
]

# ServeStatic configuration
SERVESTATIC_ROOT = BASE_DIR / "iscc_hub" / "static"
SERVESTATIC_INDEX_FILE = "index.html"

# Default primary key field type
# https://docs.djangoproject.com/en/5.2/ref/settings/#default-auto-field

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
