from .common import *

# SECURITY WARNING: keep the secret key used in production secret!
SECRET_KEY = "django-insecure-qurch#-+_$5_b^fwcvxcm^tplr@l6bm1t8ew^bj7*7b!yd&_gz"

# SECURITY WARNING: don't run with debug turned on in production!
DEBUG = True

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": BASE_DIR / "db.sqlite3",
    }
}
