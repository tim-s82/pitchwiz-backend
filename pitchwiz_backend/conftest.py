# pitchwiz-backend/conftest.py
import os
import django
from django.conf import settings
from django.core.management import call_command


def pytest_configure():
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "base.settings.unit_test")
    django.setup()

    # Run migrations against the in-memory database
    print("Applying Django migrations to in-memory test database...")
    call_command("migrate", verbosity=0)
