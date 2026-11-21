import json
import logging
import os
from pathlib import Path
from flask import Flask, jsonify, redirect, request, url_for

app = Flask(__name__)
logging.basicConfig(level=logging.INFO)

BASE_DIR = Path(__file__).resolve().parent
MOCK_DATA_DIR = BASE_DIR / "mock_data" / "play_cricket"

# Scenario definitions and file mappings
SCENARIOS = {
    "initial": MOCK_DATA_DIR / "fixtures_initial.json",
    "refresh_changes": MOCK_DATA_DIR / "fixtures_refresh_changes.json",
    "venue_clash": MOCK_DATA_DIR / "fixtures_venue_clash.json",
    "fuzzy_names": MOCK_DATA_DIR / "fixtures_fuzzy_names.json",
}

# Current active scenario in memory
ACTIVE_SCENARIO = os.environ.get("MOCK_PC_SCENARIO", "initial")
if ACTIVE_SCENARIO not in SCENARIOS:
    ACTIVE_SCENARIO = "initial"


def load_fixtures_for_scenario(scenario_name):
    """Loads fixtures dictionary from the corresponding JSON file."""
    filepath = SCENARIOS.get(scenario_name)
    if not filepath or not filepath.exists():
        logging.warning("Scenario file '%s' not found, falling back to initial", filepath)
        filepath = SCENARIOS["initial"]

    try:
        with open(filepath, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        logging.error("Failed to load scenario %s from %s: %s", scenario_name, filepath, e)
        return {"2026": []}


@app.route("/", methods=["GET"])
def dashboard():
    """Simple HTML dashboard to view and toggle the active scenario."""
    current_fixtures = load_fixtures_for_scenario(ACTIVE_SCENARIO)
    matches_2026 = current_fixtures.get("2026", [])

    scenario_buttons = "".join(
        f'<a href="/set-scenario/{name}" style="display:inline-block; margin:6px; padding:10px 16px; '
        f'background-color:{"#059669" if name == ACTIVE_SCENARIO else "#334155"}; color:white; '
        f'border-radius:8px; text-decoration:none; font-weight:bold; font-size:13px;">'
        f'{"✓ " if name == ACTIVE_SCENARIO else ""}{name.replace("_", " ").title()}</a>'
        for name in SCENARIOS.keys()
    )

    rows = "".join(
        f"<tr><td style='padding:8px;border-bottom:1px solid #334155;'>{m.get('id')}</td>"
        f"<td style='padding:8px;border-bottom:1px solid #334155;'><b>{m.get('home_team_name')}</b> vs {m.get('away_team_name')}</td>"
        f"<td style='padding:8px;border-bottom:1px solid #334155;'>{m.get('match_date')} ({m.get('match_time')})</td>"
        f"<td style='padding:8px;border-bottom:1px solid #334155;'>{m.get('ground_name')}</td></tr>"
        for m in matches_2026
    )

    html = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <title>PitchWiz Mock Play-Cricket Server</title>
        <style>
            body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; background:#0f172a; color:#f8fafc; padding:32px; }}
            .container {{ max-width:900px; margin:0 auto; background:#1e293b; padding:24px; border-radius:16px; box-shadow:0 10px 25px rgba(0,0,0,0.5); }}
            h1 {{ margin-top:0; color:#34d399; font-size:24px; }}
            table {{ width:100%; border-collapse:collapse; margin-top:16px; font-size:14px; text-align:left; }}
            th {{ background:#0f172a; padding:10px; color:#94a3b8; }}
        </style>
    </head>
    <body>
        <div class="container">
            <h1>🏏 Mock ECB Play-Cricket Server</h1>
            <p>Active Scenario: <b style="color:#34d399; font-size:16px;">{ACTIVE_SCENARIO}</b> ({len(matches_2026)} fixtures loaded for season 2026)</p>
            <div style="margin:20px 0;">
                <p style="margin-bottom:8px; color:#94a3b8; font-size:13px; font-weight:600;">SWITCH SCENARIO:</p>
                {scenario_buttons}
            </div>
            <h3>Current Fixture Data (Season 2026):</h3>
            <table>
                <thead>
                    <tr><th>ID</th><th>Match</th><th>Date & Time</th><th>Ground</th></tr>
                </thead>
                <tbody>{rows}</tbody>
            </table>
        </div>
    </body>
    </html>
    """
    return html


@app.route("/set-scenario/<scenario_name>", methods=["GET", "POST"])
def set_scenario(scenario_name):
    """Endpoint to switch the active scenario."""
    global ACTIVE_SCENARIO
    if scenario_name in SCENARIOS:
        ACTIVE_SCENARIO = scenario_name
        logging.info("Active mock Play-Cricket scenario switched to '%s'", scenario_name)
        if request.headers.get("Accept", "").find("application/json") != -1 or request.is_json:
            return jsonify({"status": "success", "active_scenario": ACTIVE_SCENARIO}), 200
        return redirect("/")
    return jsonify({"error": f"Unknown scenario: {scenario_name}. Available: {list(SCENARIOS.keys())}"}), 400


@app.route("/api/v2/matches.json", methods=["GET"])
def get_matches():
    api_token = request.args.get("api_token")
    site_id = request.args.get("site_id")
    season_raw = request.args.get("season", "2026")
    override_scenario = request.args.get("scenario")

    scenario_to_use = override_scenario if (override_scenario in SCENARIOS) else ACTIVE_SCENARIO

    logging.info(
        "[Mock Play-Cricket API] Request received - site_id: %s, season: %s, scenario: %s",
        site_id,
        season_raw,
        scenario_to_use,
    )

    if not api_token:
        return jsonify({"error": "Unauthorized. Missing api_token parameter."}), 401

    try:
        season = int(season_raw)
    except ValueError:
        return jsonify({"error": "Invalid season parameter format."}), 400

    fixtures_data = load_fixtures_for_scenario(scenario_to_use)
    # Return requested season, or fallback to season 2026
    matches = fixtures_data.get(str(season), fixtures_data.get(2026, fixtures_data.get("2026", [])))

    return jsonify({"matches": matches, "scenario": scenario_to_use}), 200


if __name__ == "__main__":
    print(f"\n🏏 Mock Play-Cricket Server running on http://127.0.0.1:8001")
    print(f"   Active Scenario: {ACTIVE_SCENARIO}\n")
    app.run(host="127.0.0.1", port=8001, debug=True)
