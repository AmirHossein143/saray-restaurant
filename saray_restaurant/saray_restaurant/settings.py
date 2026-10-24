"""
Django settings for the Saray restaurant website.

Everything that differs between a developer laptop and the production server is
read from environment variables (see ``env``/``env_bool``/``env_list`` below).
Local development needs no configuration at all: DEBUG defaults to on and a
throw-away secret key is used.

Production checklist (set these in the server environment)::

    DJANGO_DEBUG=0
    DJANGO_SECRET_KEY=<long random string>
    DJANGO_ALLOWED_HOSTS=saray.example,www.saray.example
    DJANGO_CSRF_TRUSTED_ORIGINS=https://saray.example,https://www.saray.example
    DJANGO_TRUSTED_PROXY_COUNT=1   # when behind nginx/Caddy/a PaaS router
    python manage.py migrate && python manage.py collectstatic --noinput
"""

import os
import sys
import warnings
from pathlib import Path

from django.core.exceptions import ImproperlyConfigured

BASE_DIR = Path(__file__).resolve().parent.parent


def env(name, default=None):
    """Return a stripped environment variable, or ``default`` when unset/empty."""
    value = os.environ.get(name, '').strip()
    return value if value else default


def env_bool(name, default=False):
    value = env(name)
    if value is None:
        return default
    return value.lower() in {'1', 'true', 'yes', 'on'}


def env_int(name, default=0):
    value = env(name)
    try:
        return int(value) if value is not None else default
    except ValueError as exc:
        raise ImproperlyConfigured(f'{name} must be an integer.') from exc


def env_list(name, default=()):
    value = env(name)
    if value is None:
        return list(default)
    return [item.strip() for item in value.split(',') if item.strip()]


TESTING = len(sys.argv) > 1 and sys.argv[1] == 'test'

# --------------------------------------------------------------------------
# Core
# --------------------------------------------------------------------------

DEBUG = env_bool('DJANGO_DEBUG', True)

_DEV_SECRET_KEY = 'django-insecure-local-dev-only-saray-change-me-in-production'
SECRET_KEY = env('DJANGO_SECRET_KEY', _DEV_SECRET_KEY)
if not DEBUG and not TESTING and SECRET_KEY == _DEV_SECRET_KEY:
    raise ImproperlyConfigured('Set DJANGO_SECRET_KEY when DJANGO_DEBUG is off.')
if DEBUG and env('DJANGO_ALLOWED_HOSTS') and SECRET_KEY == _DEV_SECRET_KEY:
    # Real host names but development defaults: almost certainly a server that
    # forgot DJANGO_DEBUG=0 / DJANGO_SECRET_KEY.
    warnings.warn(
        'DJANGO_ALLOWED_HOSTS is set but DEBUG is on and the development secret key '
        'is in use. Set DJANGO_DEBUG=0 and DJANGO_SECRET_KEY on a public server.',
        RuntimeWarning, stacklevel=1,
    )

ALLOWED_HOSTS = env_list(
    'DJANGO_ALLOWED_HOSTS', ['localhost', '127.0.0.1', '[::1]', 'testserver']
)
CSRF_TRUSTED_ORIGINS = env_list('DJANGO_CSRF_TRUSTED_ORIGINS')

INSTALLED_APPS = [
    # saray_menu comes before django.contrib.admin so that its
    # templates/admin/* overrides (branding, dashboard) win.
    'saray_menu.apps.SarayMenuConfig',
    'reservations.apps.ReservationsConfig',
    'studio.apps.StudioConfig',
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'django.contrib.sitemaps',
    'django.contrib.humanize',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    # WhiteNoise is inserted here when DEBUG is off (see below).
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'saray_restaurant.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        # Optional project-level overrides; app templates live in each app.
        'DIRS': [BASE_DIR / 'templates'],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
                'saray_menu.context_processors.site',
            ],
        },
    },
]

WSGI_APPLICATION = 'saray_restaurant.wsgi.application'

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': env('DJANGO_SQLITE_PATH', BASE_DIR / 'db.sqlite3'),
    }
}

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

CACHES = {
    'default': {
        'BACKEND': 'django.core.cache.backends.locmem.LocMemCache',
        'LOCATION': 'saray',
    }
}

AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]

# --------------------------------------------------------------------------
# Internationalization — the whole site and admin are Persian (RTL).
# --------------------------------------------------------------------------

LANGUAGE_CODE = 'fa'
LANGUAGES = [('fa', 'فارسی')]
TIME_ZONE = 'Asia/Tehran'
USE_I18N = True
# Project overrides for Django strings missing from its Persian catalog.
LOCALE_PATHS = [BASE_DIR / 'locale']
USE_TZ = True

# --------------------------------------------------------------------------
# Static & media
# --------------------------------------------------------------------------

STATIC_URL = '/static/'
STATIC_ROOT = Path(env('DJANGO_STATIC_ROOT', BASE_DIR / 'staticfiles'))
MEDIA_URL = '/media/'
MEDIA_ROOT = Path(env('DJANGO_MEDIA_ROOT', BASE_DIR / 'media'))
# Serve uploads through Django even when DEBUG is off (small single-server
# deployments without a separate web server for /media/).
SERVE_MEDIA = env_bool('DJANGO_SERVE_MEDIA', DEBUG)

USE_WHITENOISE = not DEBUG and not TESTING
STORAGES = {
    'default': {'BACKEND': 'django.core.files.storage.FileSystemStorage'},
    'staticfiles': {
        'BACKEND': (
            'saray_restaurant.storage.LenientManifestStaticFilesStorage'
            if USE_WHITENOISE
            else 'django.contrib.staticfiles.storage.StaticFilesStorage'
        ),
    },
}
if USE_WHITENOISE:
    MIDDLEWARE.insert(1, 'whitenoise.middleware.WhiteNoiseMiddleware')
    WHITENOISE_MAX_AGE = 60 * 60 * 24 * 30

FILE_UPLOAD_MAX_MEMORY_SIZE = 5 * 1024 * 1024
DATA_UPLOAD_MAX_MEMORY_SIZE = 5 * 1024 * 1024

# --------------------------------------------------------------------------
# Security
# --------------------------------------------------------------------------

X_FRAME_OPTIONS = 'DENY'
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_REFERRER_POLICY = 'same-origin'
SESSION_COOKIE_HTTPONLY = True

if not DEBUG:
    # Behind a TLS-terminating proxy (nginx, Caddy, a PaaS router).
    SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')
    _secure_cookies = env_bool('DJANGO_SECURE_COOKIES', True)
    SESSION_COOKIE_SECURE = _secure_cookies
    CSRF_COOKIE_SECURE = _secure_cookies
    SECURE_SSL_REDIRECT = env_bool('DJANGO_SECURE_SSL_REDIRECT', False)
    # HSTS is opt-in: only enable once HTTPS is confirmed working everywhere.
    SECURE_HSTS_SECONDS = env_int('DJANGO_HSTS_SECONDS', 0)
    SECURE_HSTS_INCLUDE_SUBDOMAINS = env_bool('DJANGO_HSTS_INCLUDE_SUBDOMAINS', False)
    SECURE_HSTS_PRELOAD = env_bool('DJANGO_HSTS_PRELOAD', False)

# Number of reverse proxies in front of Django that append to X-Forwarded-For
# (e.g. 1 for nginx using $proxy_add_x_forwarded_for). Used to find the real
# visitor IP for reservation rate limiting. 0 = use REMOTE_ADDR directly.
# DJANGO_TRUST_X_FORWARDED_FOR=1 is accepted as an alias for one proxy.
TRUSTED_PROXY_COUNT = env_int(
    'DJANGO_TRUSTED_PROXY_COUNT', 1 if env_bool('DJANGO_TRUST_X_FORWARDED_FOR', False) else 0
)

# --------------------------------------------------------------------------
# Email & reservations
# --------------------------------------------------------------------------

EMAIL_BACKEND = env(
    'DJANGO_EMAIL_BACKEND',
    'django.core.mail.backends.console.EmailBackend'
    if DEBUG
    else 'django.core.mail.backends.smtp.EmailBackend',
)
EMAIL_HOST = env('DJANGO_EMAIL_HOST', 'localhost')
EMAIL_PORT = env_int('DJANGO_EMAIL_PORT', 25)
EMAIL_HOST_USER = env('DJANGO_EMAIL_HOST_USER', '')
EMAIL_HOST_PASSWORD = env('DJANGO_EMAIL_HOST_PASSWORD', '')
EMAIL_USE_TLS = env_bool('DJANGO_EMAIL_USE_TLS', False)
EMAIL_TIMEOUT = env_int('DJANGO_EMAIL_TIMEOUT', 10)
DEFAULT_FROM_EMAIL = env('DJANGO_DEFAULT_FROM_EMAIL', 'webmaster@localhost')
SERVER_EMAIL = DEFAULT_FROM_EMAIL

# When set, every new reservation sends a short notification to this address.
RESERVATION_NOTIFY_EMAIL = env('RESERVATION_NOTIFY_EMAIL', '')
# Max successful reservations per IP address per hour.
RESERVATION_RATE_LIMIT = env_int('RESERVATION_RATE_LIMIT', 5)

# --------------------------------------------------------------------------
# Logging — everything to the console (captured by systemd/docker/PaaS).
# --------------------------------------------------------------------------

LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'simple': {'format': '{asctime} {levelname} {name}: {message}', 'style': '{'},
    },
    'handlers': {
        'console': {'class': 'logging.StreamHandler', 'formatter': 'simple'},
    },
    'root': {'handlers': ['console'], 'level': env('DJANGO_LOG_LEVEL', 'INFO')},
    'loggers': {
        'django': {'handlers': ['console'], 'level': 'INFO', 'propagate': False},
        # 4xx noise from bots is not interesting; real errors still log.
        'django.request': {'handlers': ['console'], 'level': 'ERROR', 'propagate': False},
        'django.security.DisallowedHost': {'handlers': [], 'propagate': False},
    },
}
