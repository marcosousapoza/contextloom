from pathlib import Path

import environ

from contextloom import __version__

env = environ.Env(
    CONTEXTLOOM_DEBUG=(bool, False),
    CONTEXTLOOM_REGISTRATION_ENABLED=(bool, False),
    CONTEXTLOOM_SECURE_COOKIES=(bool, False),
)
BASE_DIR = Path(env("CONTEXTLOOM_BASE_DIR", default=Path.cwd()))
PACKAGE_DIR = Path(__file__).resolve().parents[1]

SECRET_KEY = env("CONTEXTLOOM_SECRET_KEY")
DEBUG = env.bool("CONTEXTLOOM_DEBUG")
ALLOWED_HOSTS = env.list("CONTEXTLOOM_ALLOWED_HOSTS", default=["localhost", "127.0.0.1"])
CSRF_TRUSTED_ORIGINS = env.list("CONTEXTLOOM_CSRF_TRUSTED_ORIGINS", default=[])
CONTEXTLOOM_PUBLIC_URL = env("CONTEXTLOOM_PUBLIC_URL", default="http://localhost:8000").rstrip("/")

INSTALLED_APPS = [
    "contextloom.accounts.apps.AccountsConfig",
    "contextloom.knowledge.apps.KnowledgeConfig",
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "contextloom.accounts.middleware.PasswordChangeRequiredMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "contextloom.config.urls"
TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [PACKAGE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "contextloom.accounts.context_processors.application_settings",
            ]
        },
    }
]
WSGI_APPLICATION = "contextloom.config.wsgi.application"
ASGI_APPLICATION = "contextloom.config.asgi.application"

DATABASES = {"default": env.db("CONTEXTLOOM_DATABASE_URL")}
DATABASES["default"]["CONN_MAX_AGE"] = 60
DATABASES["default"]["CONN_HEALTH_CHECKS"] = True

AUTH_USER_MODEL = "accounts.User"
AUTHENTICATION_BACKENDS = ["contextloom.accounts.backends.UsernameOrEmailBackend"]
PASSWORD_HASHERS = [
    "django.contrib.auth.hashers.Argon2PasswordHasher",
    "django.contrib.auth.hashers.PBKDF2PasswordHasher",
]
AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True
STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "var" / "static"
STATICFILES_DIRS = [PACKAGE_DIR / "static"]
STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "whitenoise.storage.CompressedStaticFilesStorage"},
}
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

LOGIN_URL = "accounts:login"
LOGIN_REDIRECT_URL = "knowledge:home"
LOGOUT_REDIRECT_URL = "accounts:login"
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Lax"
SESSION_COOKIE_SECURE = env.bool("CONTEXTLOOM_SECURE_COOKIES")
CSRF_COOKIE_SECURE = env.bool("CONTEXTLOOM_SECURE_COOKIES")
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
SECURE_CONTENT_TYPE_NOSNIFF = True
X_FRAME_OPTIONS = "DENY"
DATA_UPLOAD_MAX_MEMORY_SIZE = 12 * 1024 * 1024
FILE_UPLOAD_MAX_MEMORY_SIZE = 2 * 1024 * 1024

CONTEXTLOOM_VERSION = __version__
CONTEXTLOOM_REGISTRATION_ENABLED = env.bool("CONTEXTLOOM_REGISTRATION_ENABLED")
CONTEXTLOOM_LOGIN_ATTEMPTS = env.int("CONTEXTLOOM_LOGIN_ATTEMPTS", default=5)
CONTEXTLOOM_LOGIN_WINDOW_SECONDS = env.int("CONTEXTLOOM_LOGIN_WINDOW_SECONDS", default=300)
CONTEXTLOOM_MCP_ALLOWED_HOSTS = env.list(
    "CONTEXTLOOM_MCP_ALLOWED_HOSTS",
    default=["localhost", "localhost:*", "127.0.0.1", "127.0.0.1:*"],
)
CONTEXTLOOM_MCP_ALLOWED_ORIGINS = env.list(
    "CONTEXTLOOM_MCP_ALLOWED_ORIGINS", default=["http://localhost:*", "http://127.0.0.1:*"]
)
CONTEXTLOOM_EXPORT_SPOOL_LIMIT = env.int("CONTEXTLOOM_EXPORT_SPOOL_LIMIT", default=2_000_000)
CONTEXTLOOM_IMPORT_MAX_BYTES = env.int("CONTEXTLOOM_IMPORT_MAX_BYTES", default=10_000_000)
CONTEXTLOOM_IMPORT_MAX_EXPANDED_BYTES = env.int(
    "CONTEXTLOOM_IMPORT_MAX_EXPANDED_BYTES", default=25_000_000
)
CONTEXTLOOM_IMPORT_MAX_ROWS = env.int("CONTEXTLOOM_IMPORT_MAX_ROWS", default=50_000)
CONTEXTLOOM_IMPORT_MAX_FIELD_LENGTH = env.int(
    "CONTEXTLOOM_IMPORT_MAX_FIELD_LENGTH", default=1_000_000
)
CONTEXTLOOM_IMPORT_MAX_DEPTH = env.int("CONTEXTLOOM_IMPORT_MAX_DEPTH", default=50)

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "handlers": {"console": {"class": "logging.StreamHandler"}},
    "root": {"handlers": ["console"], "level": env("CONTEXTLOOM_LOG_LEVEL", default="INFO")},
}
