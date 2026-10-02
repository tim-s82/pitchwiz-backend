from base.settings.local import *

# Override the database to use a fast, temporary in-memory SQLite database
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": ":memory:",
    }
}

PASSWORD_HASHERS = [
    "django.contrib.auth.hashers.MD5PasswordHasher",
]

# --- Email (test) ---
EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"
EMAIL_ENABLED = False  # tests explicitly enable per test case as needed
