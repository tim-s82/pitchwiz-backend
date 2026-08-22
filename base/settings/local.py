from .common import *

# SECURITY WARNING: keep the secret key used in production secret!
SECRET_KEY = "local-secret-key"

# SECURITY WARNING: don't run with debug turned on in production!
DEBUG = True

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": BASE_DIR / "db.sqlite3",
    }
}

print(f"SQLite DB: {BASE_DIR / 'db.sqlite3'}")

CORS_ALLOWED_ORIGINS = [
    "http://localhost:5173",
    "http://localhost:3000",
    "http://127.0.0.1:5173",
    "http://127.0.0.1:3000",
]
