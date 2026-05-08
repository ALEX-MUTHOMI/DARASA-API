from __future__ import annotations

import os
import sys
from datetime import timedelta
from pathlib import Path
from typing import Any
from urllib.parse import quote_plus

import environ
from cryptography.fernet import Fernet
from django.core.exceptions import ImproperlyConfigured


BASE_DIR = Path(__file__).resolve().parent.parent

env = environ.Env(
    DEBUG=(bool, False),
    TESTING=(bool, False),
    SECRET_KEY=(str, ""),
    DATABASE_URL=(str, ""),
    DB_HOST=(str, ""),
    DB_PORT=(int, 5432),
    DB_NAME=(str, ""),
    DB_USER=(str, ""),
    DB_PASS=(str, ""),
    REDIS_URL=(str, ""),
    CELERY_BROKER_URL=(str, ""),
    CELERY_RESULT_BACKEND=(str, ""),
    JWT_SIGNING_KEY=(str, ""),
    FERNET_ENCRYPTION_KEY=(str, ""),
    DJANGO_LOG_LEVEL=(str, "INFO"),
    ALLOWED_HOSTS=(list, ["localhost", "127.0.0.1"]),
    CORS_ALLOWED_ORIGINS=(list, []),
    CSRF_TRUSTED_ORIGINS=(list, []),
    DEFAULT_FROM_EMAIL=(str, "Darasa <no-reply@darasa.ac.ke>"),
    SERVER_EMAIL=(str, "server@darasa.ac.ke"),
    TENANT_PUBLIC_SCHEMA_NAME=(str, "public"),
    PG_EXTRA_SEARCH_PATHS=(list, []),
)

environ.Env.read_env(BASE_DIR / ".env")


def _detect_test_mode() -> bool:
    if env.bool("TESTING", default=False):
        return True
    if os.environ.get("PYTEST_CURRENT_TEST"):
        return True
    argv = [str(arg).lower() for arg in sys.argv]
    return any(
        arg in {"test", "pytest"}
        or arg.endswith(("/pytest", "\\pytest", "/pytest.exe", "\\pytest.exe"))
        or arg.endswith(("/pytest/__main__.py", "\\pytest\\__main__.py"))
        or "/pytest/" in arg
        or "\\pytest\\" in arg
        for arg in argv
    )


TESTING = _detect_test_mode()


def _build_database_url() -> str:
    database_url = env("DATABASE_URL", default="")
    if database_url:
        return database_url

    db_name = env("DB_NAME", default="")
    db_user = env("DB_USER", default="")
    db_pass = env("DB_PASS", default="")
    db_host = env("DB_HOST", default="")
    db_port = env.int("DB_PORT", default=5432)

    if all([db_name, db_user, db_pass, db_host]):
        return (
            f"postgres://{quote_plus(db_user)}:{quote_plus(db_pass)}"
            f"@{db_host}:{db_port}/{db_name}"
        )

    if TESTING:
        return f"sqlite:///{(BASE_DIR / 'test_db.sqlite3').as_posix()}"

    raise ImproperlyConfigured(
        "Database configuration is missing. Set DATABASE_URL or "
        "DB_HOST/DB_PORT/DB_NAME/DB_USER/DB_PASS."
    )


DATABASE_URL = _build_database_url()

if not TESTING:
    required_env = {
        "SECRET_KEY": env("SECRET_KEY", default=""),
        "JWT_SIGNING_KEY": env("JWT_SIGNING_KEY", default=""),
        "FERNET_ENCRYPTION_KEY": env("FERNET_ENCRYPTION_KEY", default=""),
        "DATABASE_URL": DATABASE_URL,
    }
    missing = [name for name, value in required_env.items() if not value]
    if missing:
        raise ImproperlyConfigured(
            f"CRITICAL: Required environment variables are unset: {missing}."
        )


SECRET_KEY = env("SECRET_KEY", default="insecure-dev-key-change-me")
DEBUG = env.bool("DEBUG", default=False)
ALLOWED_HOSTS = env.list("ALLOWED_HOSTS", default=["localhost", "127.0.0.1"])
CSRF_TRUSTED_ORIGINS = env.list("CSRF_TRUSTED_ORIGINS", default=[])
CORS_ALLOWED_ORIGINS = env.list("CORS_ALLOWED_ORIGINS", default=[])
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
AUTH_USER_MODEL = "core.CustomUser"

TENANT_MODEL = "tenant.School"
TENANT_DOMAIN_MODEL = "tenant.Domain"
PUBLIC_SCHEMA_NAME = env("TENANT_PUBLIC_SCHEMA_NAME", default="public").strip()
PUBLIC_SCHEMA_NAME = PUBLIC_SCHEMA_NAME or "public"
PUBLIC_SCHEMA_URLCONF = "darasa_project.urls"


def _build_pg_extra_search_paths(public_schema_name: str) -> list[str]:
    forbidden_schema_names = {"public", public_schema_name.lower()}
    configured_paths = env.list("PG_EXTRA_SEARCH_PATHS", default=[])
    safe_paths: list[str] = []

    for path in configured_paths:
        normalized_path = str(path).strip()
        if not normalized_path:
            continue
        if normalized_path.lower() in forbidden_schema_names:
            continue
        if normalized_path not in safe_paths:
            safe_paths.append(normalized_path)

    return safe_paths


PG_EXTRA_SEARCH_PATHS = _build_pg_extra_search_paths(PUBLIC_SCHEMA_NAME)
SHOW_PUBLIC_IF_NO_TENANT_FOUND = False

SHARED_APPS = [
    "django_tenants",
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django.contrib.sites",
    "corsheaders",
    "rest_framework",
    "rest_framework.authtoken",
    "rest_framework_simplejwt.token_blacklist",
    "django_celery_beat",
    "django_celery_results",
    "drf_spectacular",
    "tenant",
    "core",
    "academics",
]

TENANT_APPS = [
    "django.contrib.contenttypes",
    "grading",
    "curriculum",
    "disciplinary",
    "portals",
    "bus",
]

INSTALLED_APPS = SHARED_APPS + [
    app_name for app_name in TENANT_APPS if app_name not in SHARED_APPS
]

MIDDLEWARE = [
    "django_tenants.middleware.main.TenantMainMiddleware",
    "django.middleware.security.SecurityMiddleware",
    "corsheaders.middleware.CorsMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "darasa_project.urls"
WSGI_APPLICATION = "darasa_project.wsgi.application"
ASGI_APPLICATION = "darasa_project.asgi.application"
SITE_ID = 1

TEMPLATES: list[dict[str, Any]] = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    }
]

DATABASES = {"default": env.db("DATABASE_URL", default=DATABASE_URL)}
if DATABASES["default"]["ENGINE"] != "django.db.backends.sqlite3":
    DATABASES["default"]["ENGINE"] = "django_tenants.postgresql_backend"
    DATABASES["default"]["CONN_MAX_AGE"] = 0 if TESTING else 60
    DATABASES["default"].setdefault("OPTIONS", {})
    DATABASES["default"]["OPTIONS"].update(
        {
            "options": "-c timezone=UTC",
            "keepalives": 1,
            "keepalives_idle": 30,
            "keepalives_interval": 5,
            "keepalives_count": 5,
        }
    )
DATABASE_ROUTERS = ["django_tenants.routers.TenantSyncRouter"]

AUTH_PASSWORD_VALIDATORS = [
    {
        "NAME": (
            "django.contrib.auth.password_validation."
            "UserAttributeSimilarityValidator"
        )
    },
    {
        "NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
        "OPTIONS": {"min_length": 12},
    },
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

PASSWORD_HASHERS = [
    "django.contrib.auth.hashers.Argon2PasswordHasher",
    "django.contrib.auth.hashers.PBKDF2PasswordHasher",
    "django.contrib.auth.hashers.PBKDF2SHA1PasswordHasher",
    "django.contrib.auth.hashers.BCryptSHA256PasswordHasher",
]

LANGUAGE_CODE = "en-us"
TIME_ZONE = "Africa/Nairobi"
USE_I18N = True
USE_TZ = True

STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "static_root"
STATICFILES_DIRS = [BASE_DIR / "static"] if (BASE_DIR / "static").exists() else []
MEDIA_URL = "/media/"
MEDIA_ROOT = BASE_DIR / "media_root"

DATA_UPLOAD_MAX_MEMORY_SIZE = 5 * 1024 * 1024
FILE_UPLOAD_MAX_MEMORY_SIZE = 2 * 1024 * 1024

REDIS_URL = env("REDIS_URL", default=env("CELERY_BROKER_URL", default=""))
if REDIS_URL and not TESTING:
    CACHES = {
        "default": {
            "BACKEND": "django.core.cache.backends.redis.RedisCache",
            "LOCATION": REDIS_URL,
            "OPTIONS": {
                "socket_connect_timeout": 5,
                "socket_timeout": 5,
            },
        }
    }
else:
    CACHES = {"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}}

REST_FRAMEWORK: dict[str, Any] = {
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
    "DEFAULT_AUTHENTICATION_CLASSES": (
        "rest_framework_simplejwt.authentication.JWTAuthentication",
    ),
    "DEFAULT_PERMISSION_CLASSES": (
        "rest_framework.permissions.IsAuthenticated",
    ),
    "DEFAULT_RENDERER_CLASSES": ["rest_framework.renderers.JSONRenderer"],
}
if DEBUG:
    REST_FRAMEWORK["DEFAULT_RENDERER_CLASSES"].append(
        "rest_framework.renderers.BrowsableAPIRenderer"
    )

SIMPLE_JWT = {
    "ACCESS_TOKEN_LIFETIME": timedelta(minutes=15),
    "REFRESH_TOKEN_LIFETIME": timedelta(days=7),
    "ROTATE_REFRESH_TOKENS": True,
    "BLACKLIST_AFTER_ROTATION": True,
    "UPDATE_LAST_LOGIN": True,
    "ALGORITHM": "HS256",
    "AUTH_HEADER_TYPES": ("Bearer",),
    "SIGNING_KEY": env("JWT_SIGNING_KEY", default=SECRET_KEY),
    "USER_ID_FIELD": "id",
    "USER_ID_CLAIM": "user_id",
}

SPECTACULAR_SETTINGS = {
    "TITLE": "Darasa-Core API",
    "DESCRIPTION": "Schema-per-tenant educational ERP API",
    "VERSION": "0.1.0",
    "SERVE_INCLUDE_SCHEMA": False,
}

CELERY_BROKER_URL = env("CELERY_BROKER_URL", default="redis://redis:6379/0")
CELERY_RESULT_BACKEND = env("CELERY_RESULT_BACKEND", default=CELERY_BROKER_URL)
CELERY_ACCEPT_CONTENT = ["json"]
CELERY_TASK_SERIALIZER = "json"
CELERY_RESULT_SERIALIZER = "json"
CELERY_TIMEZONE = "UTC"
CELERY_ENABLE_UTC = True
CELERY_TASK_DEFAULT_QUEUE = "bus"
CELERY_TASK_ROUTES = {
    "bus.tasks.*": {"queue": "bus"},
    "academics.tasks.*": {"queue": "academics"},
    "grading.tasks.*": {"queue": "grading"},
    "curriculum.tasks.*": {"queue": "curriculum"},
    "disciplinary.tasks.*": {"queue": "disciplinary"},
    "portals.tasks.*": {"queue": "portals"},
}
CELERY_TASK_SOFT_TIME_LIMIT = 300
CELERY_TASK_TIME_LIMIT = 600
CELERY_BEAT_SCHEDULER = "django_celery_beat.schedulers:DatabaseScheduler"


def _get_fernet_encryption_key() -> str:
    key = env("FERNET_ENCRYPTION_KEY", default="").strip()
    if not key:
        if TESTING:
            return ""
        raise ImproperlyConfigured("FERNET_ENCRYPTION_KEY is required.")

    try:
        Fernet(key)
    except (TypeError, ValueError) as exc:
        raise ImproperlyConfigured(
            "FERNET_ENCRYPTION_KEY must be a valid 32-byte url-safe "
            "base64-encoded Fernet key."
        ) from exc

    return key


FERNET_ENCRYPTION_KEY = _get_fernet_encryption_key()

DEFAULT_FROM_EMAIL = env(
    "DEFAULT_FROM_EMAIL",
    default="Darasa <no-reply@darasa.ac.ke>",
)
SERVER_EMAIL = env("SERVER_EMAIL", default="server@darasa.ac.ke")
EMAIL_BACKEND = env(
    "EMAIL_BACKEND",
    default="django.core.mail.backends.console.EmailBackend",
)
EMAIL_HOST = env("EMAIL_HOST", default="smtp.sendgrid.net")
EMAIL_PORT = env.int("EMAIL_PORT", default=587)
EMAIL_HOST_USER = env("EMAIL_HOST_USER", default="")
EMAIL_HOST_PASSWORD = env("EMAIL_HOST_PASSWORD", default="")
EMAIL_USE_TLS = True
EMAIL_USE_SSL = False

LOGGING: dict[str, Any] = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "standard": {
            "format": "[{asctime}] {levelname} {name} schema={schema_name} {message}",
            "style": "{",
            "defaults": {"schema_name": "public"},
        }
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "standard",
            "level": env("DJANGO_LOG_LEVEL", default="INFO"),
        }
    },
    "loggers": {
        "django": {
            "handlers": ["console"],
            "level": env("DJANGO_LOG_LEVEL", default="INFO"),
            "propagate": False,
        },
        "django.security": {
            "handlers": ["console"],
            "level": "WARNING",
            "propagate": False,
        },
        "core": {"handlers": ["console"], "level": "INFO", "propagate": False},
        "tenant": {"handlers": ["console"], "level": "INFO", "propagate": False},
        "bus": {"handlers": ["console"], "level": "INFO", "propagate": False},
    },
}

SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_REFERRER_POLICY = "strict-origin-when-cross-origin"
X_FRAME_OPTIONS = "DENY"
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Lax"
CSRF_COOKIE_HTTPONLY = True
CSRF_COOKIE_SAMESITE = "Strict"
SECURE_CROSS_ORIGIN_OPENER_POLICY = "same-origin"

if not DEBUG:
    SECURE_SSL_REDIRECT = True
    SECURE_HSTS_SECONDS = 31_536_000
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True
    SECURE_HSTS_PRELOAD = True
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
else:
    SECURE_SSL_REDIRECT = False
    SESSION_COOKIE_SECURE = False
    CSRF_COOKIE_SECURE = False

if TESTING:
    ALLOWED_HOSTS = list(dict.fromkeys(ALLOWED_HOSTS + ["testserver", "localhost"]))
    CELERY_BROKER_URL = "memory://"
    CELERY_RESULT_BACKEND = "cache+memory://"
    CELERY_TASK_ALWAYS_EAGER = True
    CELERY_TASK_EAGER_PROPAGATES = True
    PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]
    EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"
    if DATABASES["default"]["ENGINE"] == "django.db.backends.sqlite3":
        DATABASE_ROUTERS = []
