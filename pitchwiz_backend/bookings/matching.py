import re


def normalize_text(text):
    if not text:
        return ""
    s = str(text).lower()
    s = re.sub(r"\bfirst\b", "1st", s)
    s = re.sub(r"\bsecond\b", "2nd", s)
    s = re.sub(r"\bthird\b", "3rd", s)
    s = re.sub(r"\bfourth\b", "4th", s)
    return re.sub(r"[^\w\s]", " ", s)


def find_best_team_match(imported_name, teams_qs):
    norm_imported = normalize_text(imported_name)
    imported_tokens = set(norm_imported.split())

    matches = []
    for team in teams_qs:
        norm_team = normalize_text(team.name)
        team_tokens = set(norm_team.split())

        if norm_team == norm_imported:
            matches.append({"team": team, "score": 100})
            continue

        intersection_count = sum(1 for token in imported_tokens if token in team_tokens)
        if intersection_count == len(imported_tokens) and len(imported_tokens) > 0:
            matches.append({"team": team, "score": 80 + intersection_count})
        elif intersection_count > 0:
            matches.append({"team": team, "score": intersection_count * 10})

    matches.sort(key=lambda x: x["score"], reverse=True)

    first_team = teams_qs.first()
    if not matches:
        return {"team_id": first_team.id if first_team else None, "ambiguous": False}

    top_score = matches[0]["score"]
    top_candidates = [m for m in matches if m["score"] == top_score]
    is_ambiguous = len(top_candidates) > 1 or (
        len(matches) > 1 and matches[0]["score"] - matches[1]["score"] < 5
    )

    return {
        "team_id": matches[0]["team"].id,
        "ambiguous": is_ambiguous,
    }


def find_best_pitch_match(pitch_pref, pitches_qs, venues_qs):
    if not pitch_pref:
        first_pitch = pitches_qs.first()
        return first_pitch.id if first_pitch else None

    norm_imported = normalize_text(pitch_pref)
    imported_tokens = set(norm_imported.split())

    best_pitch_id = None
    max_score = -1

    for pitch in pitches_qs:
        venue_obj = venues_qs.filter(id=pitch.venue_id).first()
        venue_name = venue_obj.name if venue_obj else ""
        full_str = f"{venue_name} {pitch.name}"
        norm_full = normalize_text(full_str)

        score = sum(15 for token in imported_tokens if token in norm_full)
        if norm_full in norm_imported or norm_imported in norm_full:
            score += 50

        if score > max_score:
            max_score = score
            best_pitch_id = pitch.id

    first_pitch = pitches_qs.first()
    return best_pitch_id or (first_pitch.id if first_pitch else None)
