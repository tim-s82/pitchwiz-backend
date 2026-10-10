import os

import dj_database_url

from .common import *

# SECURITY WARNING: keep the secret key used in production secret!
SECRET_KEY = "local-secret-key"

# SECURITY WARNING: don't run with debug turned on in production!
DEBUG = True

DATABASES = {
    "default": dj_database_url.config(
        default=os.environ.get("DATABASE_URL"),
        conn_max_age=600,
        conn_health_checks=True,
    )
}

RENDER_EXTERNAL_HOSTNAME = os.environ.get("RENDER_EXTERNAL_HOSTNAME")
if RENDER_EXTERNAL_HOSTNAME:
    ALLOWED_HOSTS.append(RENDER_EXTERNAL_HOSTNAME)

CORS_ALLOWED_ORIGINS = [
    "https://pitchwiz-backend-dev.onrender.com",
    "http://localhost:5173",
    "http://127.0.0.1:5173",
]

PLAY_CRICKET_URL = "http://127.0.0.1:8001"
PLAY_CRICKET_SITE_ID = "12345"
PLAY_CRICKET_API_KEY = "mock-dev-token-xyz"

# --- Email (Resend via django-anymail) ---
ANYMAIL = {
    "RESEND_API_KEY": os.environ.get("RESEND_API_KEY"),
}
EMAIL_BACKEND = "anymail.backends.resend.EmailBackend"
DEFAULT_FROM_EMAIL = os.environ.get(
    "DEFAULT_FROM_EMAIL", "pitchwiz-dev.wimbornecc@onresend.com"
)
# EMAIL_ENABLED defaults True (from common.py env var); set EMAIL_ENABLED=False in Render to pause sending
