import sys, os, json

sys.path.insert(0, ".")
sys.path.insert(0, "pitchwiz_backend")
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "base.settings.unit_test")
import django

django.setup()
from django.core.management import call_command

call_command("migrate", verbosity=0)

import mock_play_cricket
from rest_framework.test import APIRequestFactory, force_authenticate
from bookings.views import preview_play_cricket_fixtures_view, commit_fixtures_import_view
from bookings.models import Venue, Pitch, Team, Fixture, PitchBooking
from django.contrib.auth import get_user_model
from unittest.mock import patch, MagicMock

User = get_user_model()
user = User.objects.create_user(
    username="sec_test", password="password", roles=["FIXTURE_SECRETARY"]
)

v1 = Venue.objects.create(name="The Leaze", is_default=True)
p1 = Pitch.objects.create(venue=v1, name="Pitch 1", pitch_type="GRASS", entity_type="MAIN")
p2 = Pitch.objects.create(venue=v1, name="Pitch 2", pitch_type="GRASS", entity_type="MAIN")

v2 = Venue.objects.create(name="Colehill", is_default=False)
p3 = Pitch.objects.create(venue=v2, name="Main Pitch", pitch_type="GRASS", entity_type="MAIN")

v3 = Venue.objects.create(name="Dumpton School", is_default=False)
p4 = Pitch.objects.create(venue=v3, name="Dumpton Pitch", pitch_type="GRASS", entity_type="MAIN")

t1 = Team.objects.create(name="Wimborne CC 1st XI")
t2 = Team.objects.create(name="Wimborne CC 2nd XI")
t3 = Team.objects.create(name="Wimborne Girls U13 Warriors")
t4 = Team.objects.create(name="Wimborne U11 Wildcats")
t5 = Team.objects.create(name="Wimborne Girls U11 Warriors")

factory = APIRequestFactory()

# Phase A: Initial import simulation
initial_data = mock_play_cricket.load_fixtures_for_scenario("initial")
with patch("bookings.views.requests.get") as mock_get:
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"matches": initial_data["2026"]}
    mock_get.return_value = mock_resp

    with django.test.override_settings(
        PLAY_CRICKET_SITE_ID="123", PLAY_CRICKET_API_KEY="abc", HOME_CLUB_NAME=""
    ):
        req = factory.post("/api/fixtures/preview-play-cricket", {"season": 2026}, format="json")
        force_authenticate(req, user=user)
        res = preview_play_cricket_fixtures_view(req)
        assert res.status_code == 200, f"Status {res.status_code}"
        print(
            "Initial preview succeeded. Detected teams:",
            len(res.data["detected_teams"]),
            "Rows:",
            len(res.data["rows"]),
        )

        # Commit all initial rows
        req_commit = factory.post(
            "/api/fixtures/commit-import", {"rows": res.data["rows"]}, format="json"
        )
        force_authenticate(req_commit, user=user)
        commit_res = commit_fixtures_import_view(req_commit)
        assert commit_res.status_code == 200
        print("Initial commit succeeded. Synced:", commit_res.data["synced_count"])

initial_fixture_count = Fixture.objects.count()
print(f"DB Fixture count after initial: {initial_fixture_count}")

# Phase B: Refresh simulation with refresh_changes scenario
refresh_data = mock_play_cricket.load_fixtures_for_scenario("refresh_changes")
with patch("bookings.views.requests.get") as mock_get:
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"matches": refresh_data["2026"]}
    mock_get.return_value = mock_resp

    with django.test.override_settings(
        PLAY_CRICKET_SITE_ID="123", PLAY_CRICKET_API_KEY="abc", HOME_CLUB_NAME=""
    ):
        req = factory.post("/api/fixtures/preview-play-cricket", {"season": 2026}, format="json")
        force_authenticate(req, user=user)
        res = preview_play_cricket_fixtures_view(req)
        assert res.status_code == 200
        rows = res.data["rows"]

        actions = [r.get("action") for r in rows]
        print("Refresh preview actions:", {a: actions.count(a) for a in set(actions)})

        # Verify 5001 is UNCHANGED and pitch preserved
        r_5001 = next(r for r in rows if r.get("playCricketId") == "5001")
        assert r_5001["action"] == "UNCHANGED", f"Expected UNCHANGED, got {r_5001['action']}"
        assert r_5001["pitchPreserved"] is True, "Expected pitchPreserved True"

        # Verify 5007 is RESCHEDULED
        r_5007 = next(r for r in rows if r.get("playCricketId") == "5007")
        assert r_5007["action"] == "RESCHEDULED", f"Expected RESCHEDULED, got {r_5007['action']}"
        assert r_5007["oldDate"] == "2026-05-23"
        assert r_5007["date"] == "2026-05-30"

        # Verify 5003 is REMOVED and unchecked
        r_5003 = next(r for r in rows if r.get("playCricketId") == "5003")
        assert r_5003["action"] == "REMOVED", f"Expected REMOVED, got {r_5003['action']}"
        assert r_5003["selected"] is False, "Expected REMOVED to be unchecked"

        # Verify 5008 is NEW
        r_5008 = next(r for r in rows if r.get("playCricketId") == "5008")
        assert r_5008["action"] == "NEW", f"Expected NEW, got {r_5008['action']}"

        # Now simulate user approving removal of 5003 and committing
        r_5003["selected"] = True
        rows_to_commit = [r for r in rows if r["selected"]]
        req_commit = factory.post(
            "/api/fixtures/commit-import", {"rows": rows_to_commit}, format="json"
        )
        force_authenticate(req_commit, user=user)
        commit_res = commit_fixtures_import_view(req_commit)
        assert commit_res.status_code == 200
        print("Refresh commit succeeded:", commit_res.data)

        # Verify DB state
        assert not Fixture.objects.filter(play_cricket_id="5003").exists(), "5003 should be deleted"
        assert Fixture.objects.filter(play_cricket_id="5008").exists(), "5008 should exist"
        f_5007 = Fixture.objects.get(play_cricket_id="5007")
        assert str(f_5007.start_date) == "2026-05-30", "5007 should have new date"

# Phase C: Spreadsheet import & refresh simulation
import csv
from bookings.views import preview_spreadsheet_fixtures_view

# Clear fixtures to start fresh spreadsheet test
Fixture.objects.all().delete()
PitchBooking.objects.all().delete()

with open("mock_data/spreadsheets/spreadsheet_initial.csv", "r") as f:
    csv_initial_rows = list(csv.DictReader(f))

req_csv_init = factory.post(
    "/api/fixtures/preview-spreadsheet", {"rows": csv_initial_rows}, format="json"
)
force_authenticate(req_csv_init, user=user)
res_csv_init = preview_spreadsheet_fixtures_view(req_csv_init)
assert res_csv_init.status_code == 200
assert len(res_csv_init.data["rows"]) == 5
print(
    "Spreadsheet initial preview succeeded. Detected teams:",
    len(res_csv_init.data["detected_teams"]),
)

req_csv_commit = factory.post(
    "/api/fixtures/commit-import", {"rows": res_csv_init.data["rows"]}, format="json"
)
force_authenticate(req_csv_commit, user=user)
res_csv_commit = commit_fixtures_import_view(req_csv_commit)
assert res_csv_commit.status_code == 200
assert Fixture.objects.count() == 5
print("Spreadsheet initial commit succeeded. Fixtures in DB:", Fixture.objects.count())

# Refresh spreadsheet
with open("mock_data/spreadsheets/spreadsheet_refresh.csv", "r") as f:
    csv_refresh_rows = list(csv.DictReader(f))

req_csv_ref = factory.post(
    "/api/fixtures/preview-spreadsheet", {"rows": csv_refresh_rows}, format="json"
)
force_authenticate(req_csv_ref, user=user)
res_csv_ref = preview_spreadsheet_fixtures_view(req_csv_ref)
assert res_csv_ref.status_code == 200

csv_actions = [r["action"] for r in res_csv_ref.data["rows"]]
print("Spreadsheet refresh preview actions:", {a: csv_actions.count(a) for a in set(csv_actions)})

# U13 fixture missing in spreadsheet refresh -> REMOVED
u13_removed = next(
    r
    for r in res_csv_ref.data["rows"]
    if "U13" in r.get("teamNameRaw", "") or r.get("opponent") == "Parley Girls U13"
)
assert u13_removed["action"] == "REMOVED"
assert u13_removed["selected"] is False

# 1st XI Poole Town rescheduled
poole_resched = next(r for r in res_csv_ref.data["rows"] if "Poole Town" in r.get("opponent", ""))
assert poole_resched["action"] == "RESCHEDULED"
assert poole_resched["date"] == "2026-05-30"

# Broadstone new
broadstone_new = next(r for r in res_csv_ref.data["rows"] if "Broadstone" in r.get("opponent", ""))
assert broadstone_new["action"] == "NEW"

# Approve removal and commit
u13_removed["selected"] = True
csv_rows_to_commit = [r for r in res_csv_ref.data["rows"] if r["selected"]]
req_csv_ref_commit = factory.post(
    "/api/fixtures/commit-import", {"rows": csv_rows_to_commit}, format="json"
)
force_authenticate(req_csv_ref_commit, user=user)
res_csv_ref_commit = commit_fixtures_import_view(req_csv_ref_commit)
assert res_csv_ref_commit.status_code == 200
print("Spreadsheet refresh commit succeeded:", res_csv_ref_commit.data)

assert not Fixture.objects.filter(opponent="Parley Girls U13").exists(), "Parley should be deleted"
assert Fixture.objects.filter(opponent="Broadstone CC 1st XI").exists(), "Broadstone should exist"

print("ALL END-TO-END VERIFICATION CHECKS PASSED!")
