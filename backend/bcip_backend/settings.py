"""
Django settings for the BCIP backend.

Every environment-specific value is read from the environment (NFR-5.2); see
backend/.env.example for the full list. Nothing here should need editing to move
between development and deployment.
"""

import os
from datetime import timedelta
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent.parent


def env_bool(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {'1', 'true', 'yes', 'on'}


def env_list(name: str, default: str = '') -> list[str]:
    return [item.strip() for item in os.getenv(name, default).split(',') if item.strip()]


# ─── Core ────────────────────────────────────────────────────────────────────

SECRET_KEY = os.getenv('SECRET_KEY', 'django-insecure-dev-only-do-not-deploy')
DEBUG = env_bool('DEBUG', False)
ALLOWED_HOSTS = env_list('ALLOWED_HOSTS', 'localhost,127.0.0.1,backend')

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',

    # Third party
    'rest_framework',
    'rest_framework_simplejwt',
    'rest_framework_simplejwt.token_blacklist',
    'django_q',
    'corsheaders',

    # Local
    'accounts',
    'certificates',
    'blockchain',
    'notifications',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'corsheaders.middleware.CorsMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'bcip_backend.urls'
WSGI_APPLICATION = 'bcip_backend.wsgi.application'
AUTH_USER_MODEL = 'accounts.Organization'
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

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
            ],
        },
    },
]

# ─── Database ────────────────────────────────────────────────────────────────

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.postgresql',
        'NAME': os.getenv('DB_NAME', 'bcip'),
        'USER': os.getenv('DB_USER', 'postgres'),
        'PASSWORD': os.getenv('DB_PASSWORD', 'postgres'),
        'HOST': os.getenv('DB_HOST', 'localhost'),
        'PORT': os.getenv('DB_PORT', '5432'),
        'OPTIONS': {
            # Managed Postgres (Neon) refuses plaintext connections, so every
            # deployment sets this to "require". The default stays "prefer" —
            # psycopg2's own default — because the docker-compose `db` service
            # runs without TLS and "require" would make it unreachable.
            'sslmode': os.getenv('DB_SSLMODE', 'prefer'),
        },
    }
}

# ─── Cache (NFR-1.10) ────────────────────────────────────────────────────────
#
# Deliberately database-backed, not LocMemCache.
#
# LocMemCache is per-process. Rate-limit counters and lockout state stored in it
# would be silently divided by the number of gunicorn workers: with 4 workers, a
# "5 attempts" limit becomes an effective 20, because each worker keeps its own
# tally. A DatabaseCache is shared by every process and by the django-q2 worker,
# so the thresholds in SRS 3.1.4 mean what they say.
#
# SRS 2.4 rules out running Redis for this project, and the same table also
# backs the FR-5.9 on-chain read cache used by public verification.
#
# The table is created by `python manage.py createcachetable`, which the
# docker-compose backend command runs on start. It is idempotent.

CACHE_TABLE_NAME = 'cache_entries'

CACHES = {
    'default': {
        'BACKEND': 'django.core.cache.backends.db.DatabaseCache',
        'LOCATION': CACHE_TABLE_NAME,
        'TIMEOUT': 300,
        'OPTIONS': {
            'MAX_ENTRIES': 10000,
            'CULL_FREQUENCY': 3,
        },
    }
}

# django-ratelimit reads this to pick a cache. Naming it explicitly rather than
# relying on the default is what keeps the guarantee above from silently
# regressing if someone adds a second cache alias later.
RATELIMIT_USE_CACHE = 'default'
RATELIMIT_FAIL_OPEN = False

# ─── Password policy (SRS 3.1.5) ─────────────────────────────────────────────

AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {
        'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator',
        'OPTIONS': {'min_length': 10},
    },
    # Django ships a static list of ~20,000 common passwords; this is the
    # "static common-password list" the SRS calls for.
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]

PASSWORD_HASHERS = [
    'django.contrib.auth.hashers.Argon2PasswordHasher',
    'django.contrib.auth.hashers.PBKDF2PasswordHasher',
]

# ─── DRF ─────────────────────────────────────────────────────────────────────

REST_FRAMEWORK = {
    'DEFAULT_AUTHENTICATION_CLASSES': (
        'rest_framework_simplejwt.authentication.JWTAuthentication',
    ),
    # Closed by default (NFR-1.3). Public endpoints opt out explicitly with
    # permission_classes = [AllowAny].
    'DEFAULT_PERMISSION_CLASSES': (
        'rest_framework.permissions.IsAuthenticated',
    ),
    'DEFAULT_PAGINATION_CLASS': 'rest_framework.pagination.PageNumberPagination',
    'PAGE_SIZE': 25,  # NFR-2.2
    'EXCEPTION_HANDLER': 'bcip_backend.exceptions.bcip_exception_handler',
}

SIMPLE_JWT = {
    'ACCESS_TOKEN_LIFETIME': timedelta(minutes=15),   # SRS 3.1.2
    'REFRESH_TOKEN_LIFETIME': timedelta(days=7),
    'ROTATE_REFRESH_TOKENS': True,
    'BLACKLIST_AFTER_ROTATION': True,
    'UPDATE_LAST_LOGIN': False,
    'ALGORITHM': 'HS256',
    'SIGNING_KEY': SECRET_KEY,
    'AUTH_HEADER_TYPES': ('Bearer',),
    'USER_ID_FIELD': 'id',
    'USER_ID_CLAIM': 'user_id',
}

# Refresh token travels as an httpOnly cookie (FR-1.3), never in the JSON body.
REFRESH_COOKIE_NAME = 'refresh_token'
REFRESH_COOKIE_SAMESITE = os.getenv('REFRESH_COOKIE_SAMESITE', 'Lax')

# ─── Authentication policy (SRS 3.1.4, FR-1.6) ───────────────────────────────

# Lockout: 5 failures for one account, or 20 from one IP, within the window.
ACCOUNT_LOCKOUT_THRESHOLD = int(os.getenv('ACCOUNT_LOCKOUT_THRESHOLD', '5'))
IP_LOCKOUT_THRESHOLD = int(os.getenv('IP_LOCKOUT_THRESHOLD', '20'))
LOCKOUT_WINDOW_MINUTES = int(os.getenv('LOCKOUT_WINDOW_MINUTES', '15'))
LOCKOUT_COOLDOWN_MINUTES = int(os.getenv('LOCKOUT_COOLDOWN_MINUTES', '30'))

# NFR-1.11 — client IP resolution.
#
# This deployment terminates TLS at the application host with no reverse proxy
# in front of it, so REMOTE_ADDR is the real client address and X-Forwarded-For
# is entirely attacker-controlled. Trusting it here would let anyone defeat both
# IP lockout and rate limiting by sending a random header per request.
#
# Set TRUST_X_FORWARDED_FOR=1 *only* when running behind a proxy you control
# that overwrites the header; see accounts.ip.get_client_ip for how the value is
# then read.
TRUST_X_FORWARDED_FOR = env_bool('TRUST_X_FORWARDED_FOR', False)

# ─── Rate limits (SRS 3.1.4) ─────────────────────────────────────────────────
# Format is django-ratelimit's 'count/period'.
RATELIMITS = {
    'register': '5/h',
    'login': '10/m',
    'verify_email': '10/h',
    'resend_verification': '3/h',
    'request_password_reset': '3/h',
    'verify_password_reset': '10/h',
    'reset_password': '5/h',
    'public_verify': '30/m',  # FR-5.8, NFR-1.7
}

# ─── Certificates ────────────────────────────────────────────────────────────

MEDIA_URL = '/media/'
MEDIA_ROOT = Path(os.getenv('MEDIA_ROOT', BASE_DIR / 'media'))
STATIC_URL = 'static/'
STATIC_ROOT = BASE_DIR / 'staticfiles'

# A PENDING certificate older than this is treated as stale and retryable
# (FR-2.9).
STALE_PENDING_MINUTES = int(os.getenv('STALE_PENDING_MINUTES', '10'))

# Field limits enforced on create (FR-2.1.1).
CERTIFICATE_NAME_MAX_LENGTH = 200
CERTIFICATE_TITLE_MAX_LENGTH = 200
CERTIFICATE_EMAIL_MAX_LENGTH = 254

# ─── Blockchain ──────────────────────────────────────────────────────────────

BLOCKCHAIN_RPC_URL = os.getenv('BLOCKCHAIN_RPC_URL', '')
BLOCKCHAIN_CONTRACT_ADDRESS = os.getenv('BLOCKCHAIN_CONTRACT_ADDRESS', '')
# NFR-1.2: server-side only. Never serialised into any response.
BLOCKCHAIN_ISSUER_PRIVATE_KEY = os.getenv('BLOCKCHAIN_ISSUER_PRIVATE_KEY', '')
BLOCKCHAIN_TX_TIMEOUT = int(os.getenv('BLOCKCHAIN_TX_TIMEOUT', '180'))
BLOCKCHAIN_EXPLORER_URL = os.getenv(
    'BLOCKCHAIN_EXPLORER_URL', 'https://amoy.polygonscan.com'
)

# Public verification cache TTLs (FR-5.9).
# certHash and issuedAt are immutable once anchored, so they are cached for a
# long time; `revoked` can change, so it is cached briefly and invalidated
# explicitly when our own revocation transaction confirms.
ONCHAIN_IMMUTABLE_CACHE_TTL = int(os.getenv('ONCHAIN_IMMUTABLE_CACHE_TTL', str(60 * 60 * 24 * 30)))
ONCHAIN_REVOKED_CACHE_TTL = int(os.getenv('ONCHAIN_REVOKED_CACHE_TTL', '60'))

# ─── Background tasks ────────────────────────────────────────────────────────
#
# workers=1 is deliberate and load-bearing, not a default left unchanged.
#
# Every on-chain write is signed by one hot wallet. Two workers signing
# concurrently would both read the same nonce; one transaction would be dropped
# or silently replaced, and the certificate would sit PENDING forever. Making
# the cluster single-worker serialises all writes through one process, which
# removes the race by construction.
#
# The cost is throughput: issuances queue behind one another at roughly one
# Amoy confirmation each. That is an accepted trade-off at this project's scale
# (SRS 11) — not a bug to be "optimised" by raising this number.
Q_CLUSTER = {
    'name': 'bcip',
    'workers': 1,
    'recycle': 500,
    'timeout': 600,
    'retry': 900,
    'queue_limit': 50,
    'bulk': 1,
    'orm': 'default',
    'max_attempts': 1,
    'catch_up': False,
    'save_limit': 250,
}

# ─── Email ───────────────────────────────────────────────────────────────────

EMAIL_BACKEND = os.getenv(
    'EMAIL_BACKEND', 'django.core.mail.backends.console.EmailBackend'
)
EMAIL_HOST = os.getenv('EMAIL_HOST', 'smtp.gmail.com')
EMAIL_PORT = int(os.getenv('EMAIL_PORT', '587'))
EMAIL_USE_TLS = env_bool('EMAIL_USE_TLS', True)
EMAIL_HOST_USER = os.getenv('EMAIL_HOST_USER', '')
EMAIL_HOST_PASSWORD = os.getenv('EMAIL_HOST_PASSWORD', '')
DEFAULT_FROM_EMAIL = os.getenv('DEFAULT_FROM_EMAIL', 'noreply@bcip.local')
EMAIL_TIMEOUT = int(os.getenv('EMAIL_TIMEOUT', '20'))

# Render's free instances block outbound SMTP (25/465/587), so production
# points EMAIL_BACKEND at notifications.email_backends.ResendAPIBackend,
# which reaches Resend over HTTPS instead.
RESEND_API_KEY = os.getenv('RESEND_API_KEY', '')
# Brevo is the alternative when BCIP has no verified domain: it sends to any
# recipient once a single sender address is confirmed. See
# notifications/email_backends.py for the trade-off between the two.
BREVO_API_KEY = os.getenv('BREVO_API_KEY', '')

# ─── Frontend / CORS ─────────────────────────────────────────────────────────

FRONTEND_URL = os.getenv('FRONTEND_URL', 'http://localhost:5173').rstrip('/')
CORS_ALLOWED_ORIGINS = env_list(
    'CORS_ALLOWED_ORIGINS', 'http://localhost:5173,http://127.0.0.1:5173'
)
# Required for the httpOnly refresh cookie to be sent cross-origin.
CORS_ALLOW_CREDENTIALS = True
CSRF_TRUSTED_ORIGINS = CORS_ALLOWED_ORIGINS

# Any header the SPA sends that is not on this list causes the browser to fail
# the CORS preflight and never send the real request — the failure looks like a
# generic network error in the UI, with nothing in the server log but an OPTIONS.
# Idempotency-Key is a custom header (FR-2.2.1), so it has to be named here.
from corsheaders.defaults import default_headers  # noqa: E402

CORS_ALLOW_HEADERS = (*default_headers, 'idempotency-key')

# ─── Admin exposure (NFR-1.12) ───────────────────────────────────────────────
# /admin/ is only routed when this is explicitly enabled, so a deployment that
# forgets to think about it does not silently publish the admin site.
ENABLE_ADMIN = env_bool('ENABLE_ADMIN', False)

# ─── Security posture ────────────────────────────────────────────────────────

SESSION_COOKIE_HTTPONLY = True
CSRF_COOKIE_HTTPONLY = False  # the SPA must read it to echo the header back
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_REFERRER_POLICY = 'same-origin'
X_FRAME_OPTIONS = 'DENY'

if not DEBUG:
    SECURE_SSL_REDIRECT = env_bool('SECURE_SSL_REDIRECT', True)
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    SECURE_HSTS_SECONDS = int(os.getenv('SECURE_HSTS_SECONDS', '31536000'))
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True
    SECURE_HSTS_PRELOAD = True
    SECURE_PROXY_SSL_HEADER = (
        ('HTTP_X_FORWARDED_PROTO', 'https') if TRUST_X_FORWARDED_FOR else None
    )

# ─── i18n ────────────────────────────────────────────────────────────────────

LANGUAGE_CODE = 'en-us'
TIME_ZONE = 'UTC'
USE_I18N = True
USE_TZ = True

# ─── Logging ─────────────────────────────────────────────────────────────────

LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'standard': {'format': '[{asctime}] {levelname} {name}: {message}', 'style': '{'},
    },
    'handlers': {
        'console': {'class': 'logging.StreamHandler', 'formatter': 'standard'},
    },
    'root': {'handlers': ['console'], 'level': os.getenv('LOG_LEVEL', 'INFO')},
    'loggers': {
        'blockchain': {'level': 'INFO', 'propagate': True},
        'certificates': {'level': 'INFO', 'propagate': True},
        'accounts': {'level': 'INFO', 'propagate': True},
        'notifications': {'level': 'INFO', 'propagate': True},
        'django.db.backends': {'level': 'WARNING', 'propagate': True},
    },
}
