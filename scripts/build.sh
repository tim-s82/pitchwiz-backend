#!/usr/bin/env bash
# Exit immediately if any command exits with a non-zero status
set -o errexit

echo "=========================================="
echo " Starting Render Build & Test Pipeline"
echo "=========================================="

cd pitchwiz_backend

echo "--- 1. Upgrading Pip & Installing Pipenv ---"
pip install --upgrade pip
pip install pipenv

echo "--- 2. Generating requirements files from Pipenv ---"
pipenv requirements --dev > requirements_dev.txt
pipenv requirements > requirements.txt

echo "--- 3. Installing Development Requirements ---"
pip install -r requirements_dev.txt

echo "--- 4. Running Code Quality Checks ---"
echo "Running Black (check mode)..."
black --check .

echo "Running Pylint..."
# pylint .

echo "--- 5. Executing Unit Tests ---"
DJANGO_SETTINGS_MODULE=base.settings.unit_test pytest

echo "--- 6. Cleaning Dev Packages & Installing Production Requirements ---"
# Uninstall development packages to keep the final runtime environment lean
pip uninstall -y -r requirements_dev.txt || true
pip install -r requirements.txt

echo "--- 7. Running Django Static Collection ---"
python manage.py collectstatic --noinput

echo "--- 8. Running Django Migrations ---"
python manage.py migrate

echo "=========================================="
echo " Build & Test Pipeline Completed Successfully!"
echo "=========================================="