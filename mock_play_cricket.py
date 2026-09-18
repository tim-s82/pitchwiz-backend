import logging
from flask import Flask, jsonify, request

app = Flask(__name__)
logging.basicConfig(level=logging.INFO)

# Sample fixture database keyed by season year
MOCK_FIXTURES = {
    2026: [
        {
            "id": 5001,
            "home_team_name": "Wimborne CC 1st XI",
            "away_team_name": "Dorchester CC 1st XI",
            "match_date": "16/05/2026",
            "match_time": "13:30",
            "ground_name": "The Leaze",
            "ground_id": "101",
        },
        {
            "id": 5002,
            "home_team_name": "Swanage CC 2nd XI",
            "away_team_name": "Wimborne Second XI",
            "match_date": "23/05/2026",
            "match_time": "14:00",
            # Away match, so ground shouldn't match Wimborne's local grounds
            "ground_name": "Swanage Rec Ground",
            "ground_id": "102",
        },
        {
            "id": 5003,
            "home_team_name": "Wimborne Girls U13 Warriors",
            "away_team_name": "Parley Girls U13",
            "match_date": "30/05/2026",
            "match_time": "10:00",
            "ground_name": "Dumpton School",
            "ground_id": "103",
        },
        {
            "id": 5004,
            "home_team_name": "Wimborne U11 Wildcats",
            "away_team_name": "Poole Town U11",
            "match_date": "06/06/2026",
            "match_time": "09:30",
            "ground_name": "Colehill",
            "ground_id": "104",
        },
    ]
}


@app.route("/api/v2/matches.json", methods=["GET"])
def get_matches():
    api_token = request.args.get("api_token")
    site_id = request.args.get("site_id")
    season_raw = request.args.get("season", "2026")

    logging.info(
        f"[Mock Play-Cricket API] Received request - site_id: {site_id}, season: {season_raw}, api_token: {api_token}"
    )

    # Basic API Token Validation Simulation
    if not api_token:
        return jsonify({"error": "Unauthorized. Missing api_token parameter."}), 401

    try:
        season = int(season_raw)
    except ValueError:
        return jsonify({"error": "Invalid season parameter format."}), 400

    # Retrieve fixtures for requested season, defaulting to 2026 fixture set if season not found
    matches = MOCK_FIXTURES.get(season, MOCK_FIXTURES[2026])

    return jsonify({"matches": matches}), 200


if __name__ == "__main__":
    print("\n🏏 Mock Play-Cricket Server running on http://127.0.0.1:8001\n")
    app.run(host="127.0.0.1", port=8001, debug=True)
