import re
from collections import Counter
from datetime import date as dt_date
from datetime import datetime


def normalize_text(text):
    if not text:
        return ""
    s = str(text).lower()
    s = re.sub(r"\bfirst\b", "1st", s)
    s = re.sub(r"\bsecond\b", "2nd", s)
    s = re.sub(r"\bthird\b", "3rd", s)
    s = re.sub(r"\bfourth\b", "4th", s)
    return re.sub(r"[^\w\s]", " ", s)


def normalize_opponent(text):
    if not text:
        return ""
    s = normalize_text(text)
    # Convert roman numerals at word boundaries e.g. " ii" -> " 2nd"
    s = re.sub(r"\biii\b", "3rd", s)
    s = re.sub(r"\bii\b", "2nd", s)
    s = re.sub(r"\bi\b", "1st", s)
    # Strip common club / organization words
    s = re.sub(r"\b(cc|cricket club|town|club|xi)\b", " ", s)
    # Normalize spaces
    return " ".join(s.split())


def infer_season_year(dates):
    years = []
    for d in dates or []:
        if not d:
            continue
        d_str = str(d).strip()
        if "-" in d_str:
            parts = d_str.split("-")
            if len(parts) >= 1 and len(parts[0]) == 4 and parts[0].isdigit():
                years.append(int(parts[0]))
        elif "/" in d_str:
            parts = d_str.split("/")
            if len(parts) >= 3 and len(parts[2]) == 4 and parts[2].isdigit():
                years.append(int(parts[2]))
    if years:
        return Counter(years).most_common(1)[0][0]
    return datetime.now().year


def find_best_venue_match(ground_name, venues_qs):
    venues_list = list(venues_qs) if venues_qs else []
    if not venues_list:
        return None

    default_venue = next(
        (v for v in venues_list if getattr(v, "is_default", False)), venues_list[0]
    )

    if not ground_name:
        return default_venue

    norm_ground = normalize_text(ground_name)
    ground_tokens = set(norm_ground.split())

    best_venue = None
    max_score = -1

    for venue in venues_list:
        norm_v = normalize_text(venue.name)
        v_tokens = set(norm_v.split())

        if norm_v == norm_ground:
            return venue

        score = sum(20 for t in ground_tokens if t in v_tokens)
        if norm_v in norm_ground or norm_ground in norm_v:
            score += 50

        if score > max_score and score > 0:
            max_score = score
            best_venue = venue

    return best_venue or default_venue


def find_best_team_match(imported_name, teams_qs):
    norm_imported = normalize_text(imported_name)
    imported_tokens = set(norm_imported.split())

    teams_list = list(teams_qs) if teams_qs else []

    matches = []
    for team in teams_list:
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

    first_team = teams_list[0] if teams_list else None
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


def find_best_pitch_match(pitch_pref, pitches_qs, venues_qs, team_id=None, teams_qs=None):
    pitches_list = [
        p for p in (pitches_qs or []) if getattr(p, "entity_type", "MAIN") in ["MAIN", "YOUTH"]
    ]
    venues_list = list(venues_qs) if venues_qs else []

    if not pitch_pref:
        first_pitch = pitches_list[0] if pitches_list else None
        return first_pitch.id if first_pitch else None

    norm_imported = normalize_text(pitch_pref)
    imported_tokens = set(norm_imported.split())

    required_length = None
    if team_id and teams_qs is not None:
        teams_list = list(teams_qs)
        team = next((t for t in teams_list if t.id == team_id), None)
        if team and getattr(team, "required_length", None):
            required_length = team.required_length

    best_pitch_id = None
    max_score = -1

    for pitch in pitches_list:
        venue_id = getattr(pitch, "venue_id", getattr(pitch, "venue", None))
        venue_obj = next((v for v in venues_list if v.id == venue_id), None)

        venue_name = venue_obj.name if venue_obj else ""
        full_str = f"{venue_name} {pitch.name}"
        norm_full = normalize_text(full_str)

        score = sum(15 for token in imported_tokens if token in norm_full)
        if norm_full in norm_imported or norm_imported in norm_full:
            score += 50

        if required_length and score > 0:
            if (
                hasattr(pitch.supported_lengths, "all")
                and required_length in pitch.supported_lengths.all()
            ):
                score += 100

        if score > max_score:
            max_score = score
            best_pitch_id = pitch.id

    first_pitch = pitches_list[0] if pitches_list else None
    return best_pitch_id or (first_pitch.id if first_pitch else None)


def match_fixtures_for_refresh(team_id, incoming_rows, existing_fixtures_qs, is_play_cricket=False):
    """
    Matches incoming rows for a team against existing DB fixtures.
    Categorizes changes into NEW, RESCHEDULED, UNCHANGED, REMOVED.
    """
    existing_list = list(existing_fixtures_qs) if existing_fixtures_qs else []
    results = []

    if is_play_cricket:
        db_by_pcid = {str(f.play_cricket_id): f for f in existing_list if f.play_cricket_id}
        matched_db_ids = set()

        for idx, row in enumerate(incoming_rows):
            row_copy = dict(row)
            pcid = str(row_copy.get("playCricketId", "")).strip()

            if pcid and pcid in db_by_pcid:
                existing_f = db_by_pcid[pcid]
                matched_db_ids.add(existing_f.id)
                old_date = (
                    existing_f.start_date.isoformat()
                    if hasattr(existing_f.start_date, "isoformat")
                    else str(existing_f.start_date)
                )
                new_date = str(row_copy.get("date", "")).strip()

                is_date_moved = old_date != new_date
                action = "RESCHEDULED" if is_date_moved else "UNCHANGED"

                row_copy.update(
                    {
                        "id": row_copy.get("id", f"row_{idx}"),
                        "action": action,
                        "existing_fixture_id": existing_f.id,
                        "teamId": team_id,
                        "date": new_date,
                        "oldDate": old_date if is_date_moved else None,
                        "selected": not bool(row_copy.get("clashReason")),
                    }
                )
                results.append(row_copy)
            else:
                row_copy.update(
                    {
                        "id": row_copy.get("id", f"row_{idx}"),
                        "action": "NEW",
                        "existing_fixture_id": None,
                        "teamId": team_id,
                        "selected": not bool(row_copy.get("clashReason")),
                    }
                )
                results.append(row_copy)

        # Surfaced removals for Play-Cricket:
        # Only existing fixtures that HAVE a play_cricket_id and were NOT in the incoming data
        for f in existing_list:
            if f.play_cricket_id and f.id not in matched_db_ids:
                f_date = (
                    f.start_date.isoformat()
                    if hasattr(f.start_date, "isoformat")
                    else str(f.start_date)
                )
                booking = getattr(f, "pitchbooking", None)
                results.append(
                    {
                        "id": f"rem_{f.id}",
                        "action": "REMOVED",
                        "existing_fixture_id": f.id,
                        "existing_booking_id": booking.id if booking else None,
                        "playCricketId": f.play_cricket_id,
                        "teamId": team_id,
                        "opponent": f.opponent,
                        "date": f_date,
                        "timeSlot": booking.time_slot if booking else "AFTERNOON",
                        "pitchId": booking.pitch_id if booking else None,
                        "selected": False,  # Unchecked by default
                    }
                )

        return results

    # SPREADSHEET HEURISTIC MATCHING
    def parse_dt(d_str):
        try:
            return dt_date.fromisoformat(str(d_str))
        except Exception:
            return None

    # Group DB fixtures by normalized opponent
    db_by_opp = {}
    for f in existing_list:
        norm_opp = normalize_opponent(f.opponent)
        db_by_opp.setdefault(norm_opp, []).append(f)

    # Helper to find matching opponent group in DB
    def match_opp_group(opp_name, existing_groups):
        if opp_name in existing_groups:
            return opp_name
        tokens = set(opp_name.split())
        best_match = None
        best_score = 0
        for grp in existing_groups:
            grp_tokens = set(grp.split())
            intersection = sum(1 for t in tokens if t in grp_tokens)
            if intersection > 0:
                score = intersection * 10
                if opp_name in grp or grp in opp_name:
                    score += 30
                if score > best_score:
                    best_score = score
                    best_match = grp
        if best_score >= 30:
            return best_match
        return opp_name

    # Group incoming rows by matching DB opponent group or own normalized opponent
    incoming_by_opp = {}
    for idx, row in enumerate(incoming_rows):
        row_dict = dict(row)
        row_dict.setdefault("id", f"row_{idx}")
        row_dict.setdefault("teamId", team_id)
        raw_norm_opp = normalize_opponent(row_dict.get("opponent", ""))
        matched_opp = match_opp_group(raw_norm_opp, db_by_opp.keys())
        incoming_by_opp.setdefault(matched_opp, []).append(row_dict)

    all_opps = set(db_by_opp.keys()) | set(incoming_by_opp.keys())

    for opp in all_opps:
        db_fixtures = list(db_by_opp.get(opp, []))
        inc_rows = list(incoming_by_opp.get(opp, []))

        # Pass 1: Match Exact Dates
        unmatched_db = []
        unmatched_inc = list(inc_rows)
        matched_pairs = []

        for f in db_fixtures:
            f_date_str = (
                f.start_date.isoformat()
                if hasattr(f.start_date, "isoformat")
                else str(f.start_date)
            )
            inc_match = next(
                (r for r in unmatched_inc if str(r.get("date", "")).strip() == f_date_str), None
            )
            if inc_match:
                unmatched_inc.remove(inc_match)
                matched_pairs.append((f, inc_match, False))
            else:
                unmatched_db.append(f)

        # Pass 2 & 3: Match remaining unmatched DB and incoming
        if len(unmatched_db) == 1 and len(unmatched_inc) == 1:
            matched_pairs.append((unmatched_db[0], unmatched_inc[0], True))
            unmatched_db = []
            unmatched_inc = []
        elif len(unmatched_db) > 0 and len(unmatched_inc) > 0:
            while unmatched_db and unmatched_inc:
                best_pair = None
                min_diff = None
                for f in unmatched_db:
                    f_d = parse_dt(f.start_date)
                    for r in unmatched_inc:
                        r_d = parse_dt(r.get("date"))
                        if f_d and r_d:
                            diff = abs((f_d - r_d).days)
                        else:
                            diff = 9999
                        if min_diff is None or diff < min_diff:
                            min_diff = diff
                            best_pair = (f, r)

                if best_pair:
                    f_best, r_best = best_pair
                    unmatched_db.remove(f_best)
                    unmatched_inc.remove(r_best)
                    matched_pairs.append((f_best, r_best, True))
                else:
                    break

        for f, r, date_moved in matched_pairs:
            f_date_str = (
                f.start_date.isoformat()
                if hasattr(f.start_date, "isoformat")
                else str(f.start_date)
            )
            r["existing_fixture_id"] = f.id
            r["action"] = "RESCHEDULED" if date_moved else "UNCHANGED"
            if date_moved:
                r["oldDate"] = f_date_str
            r["selected"] = not bool(r.get("clashReason"))
            results.append(r)

        for r in unmatched_inc:
            r["action"] = "NEW"
            r["existing_fixture_id"] = None
            r["selected"] = not bool(r.get("clashReason"))
            results.append(r)

        for f in unmatched_db:
            f_date_str = (
                f.start_date.isoformat()
                if hasattr(f.start_date, "isoformat")
                else str(f.start_date)
            )
            booking = getattr(f, "pitchbooking", None)
            results.append(
                {
                    "id": f"rem_{f.id}",
                    "action": "REMOVED",
                    "existing_fixture_id": f.id,
                    "existing_booking_id": booking.id if booking else None,
                    "teamId": team_id,
                    "opponent": f.opponent,
                    "date": f_date_str,
                    "timeSlot": booking.time_slot if booking else "AFTERNOON",
                    "pitchId": booking.pitch_id if booking else None,
                    "selected": False,
                }
            )

    return results


def allocate_pitches_for_matches(records, venues_qs, pitches_qs, existing_bookings_qs, team_obj):
    """
    Assigns pitches to matched records according to business rules:
    1. Preserves existing assigned pitch on exact matches (same date & venue).
    2. Searches for vacant pitches on multi-pitch venues (considering pitch length and blocks_pitches).
    3. Handles batch collisions across rows on the same date/slot.
    4. Detects venue full clashes and suggests alternative venues.
    """
    venues_list = list(venues_qs) if venues_qs else []
    pitches_list = list(pitches_qs) if pitches_qs else []
    bookings_list = list(existing_bookings_qs) if existing_bookings_qs else []

    allocated_in_batch = []  # List of tuples: (date_str, time_slot, pitch_id)

    # Pre-sort venues: default venue first, then alphabetical
    def venue_sort_key(v):
        return (0 if getattr(v, "is_default", False) else 1, getattr(v, "name", ""))

    sorted_venues = sorted(venues_list, key=venue_sort_key)

    def is_slot_clashing(slot1, slot2):
        if slot1 == "ALL_DAY" or slot2 == "ALL_DAY":
            return True
        return slot1 == slot2

    def is_pitch_available(pitch, target_date_str, target_slot, ignore_fixture_id=None):
        # 1. Direct booking clash in DB
        for b in bookings_list:
            if getattr(b, "status", "APPROVED") in ["PENDING", "APPROVED"]:
                # Ignore self if rescheduling existing fixture
                if ignore_fixture_id and getattr(b, "fixture_id", None) == ignore_fixture_id:
                    continue

                b_start = (
                    b.start_date.isoformat()
                    if hasattr(b.start_date, "isoformat")
                    else str(b.start_date)
                )
                b_end = (
                    b.end_date.isoformat() if hasattr(b.end_date, "isoformat") else str(b.end_date)
                )
                if b_start <= target_date_str <= b_end:
                    if is_slot_clashing(b.time_slot, target_slot):
                        # Direct clash on this pitch
                        if b.pitch_id == pitch.id:
                            return False

                        # Blocking clash: b.pitch blocks pitch or pitch blocks b.pitch
                        b_pitch = next((p for p in pitches_list if p.id == b.pitch_id), None)
                        if b_pitch:
                            # If b_pitch blocks pitch
                            if hasattr(b_pitch.blocks_pitches, "all"):
                                if pitch in b_pitch.blocks_pitches.all():
                                    return False
                            # If pitch blocks b_pitch
                            if hasattr(pitch.blocks_pitches, "all"):
                                if b_pitch in pitch.blocks_pitches.all():
                                    return False

        # 2. Check collisions with other allocations in this import batch
        for b_date, b_slot, b_pid in allocated_in_batch:
            if b_date == target_date_str and is_slot_clashing(b_slot, target_slot):
                if b_pid == pitch.id:
                    return False
                b_pitch = next((p for p in pitches_list if p.id == b_pid), None)
                if b_pitch:
                    if (
                        hasattr(b_pitch.blocks_pitches, "all")
                        and pitch in b_pitch.blocks_pitches.all()
                    ):
                        return False
                    if (
                        hasattr(pitch.blocks_pitches, "all")
                        and b_pitch in pitch.blocks_pitches.all()
                    ):
                        return False

        return True

    for record in records:
        if record.get("action") == "REMOVED":
            record.setdefault("pitchPreserved", False)
            record.setdefault("venueClash", False)
            continue

        target_date_str = str(record.get("date", "")).strip()
        target_slot = record.get("timeSlot", "AFTERNOON")
        pitch_pref = (
            record.get("pitchPref")
            or record.get("pitchPreference")
            or record.get("ground_name")
            or ""
        )
        existing_f_id = record.get("existing_fixture_id")

        # Step 1: Exact match preservation
        if existing_f_id:
            existing_b = next(
                (b for b in bookings_list if getattr(b, "fixture_id", None) == existing_f_id), None
            )
            if existing_b and existing_b.pitch:
                b_date = (
                    existing_b.start_date.isoformat()
                    if hasattr(existing_b.start_date, "isoformat")
                    else str(existing_b.start_date)
                )
                target_venue = find_best_venue_match(pitch_pref, venues_list)
                # If date matches and venue matches
                if b_date == target_date_str and (
                    not target_venue or existing_b.pitch.venue_id == target_venue.id
                ):
                    record["pitchId"] = existing_b.pitch_id
                    record["pitchPreserved"] = True
                    record["venueClash"] = False
                    allocated_in_batch.append((target_date_str, target_slot, existing_b.pitch_id))
                    continue

        # Step 2: Target Venue Resolution
        target_venue = find_best_venue_match(pitch_pref, venues_list)
        required_length = getattr(team_obj, "required_length", None) if team_obj else None

        def get_compatible_pitches(venue):
            venue_pitches = [
                p
                for p in pitches_list
                if p.venue_id == venue.id
                and getattr(p, "is_active", True)
                and getattr(p, "entity_type", "MAIN") in ["MAIN", "YOUTH"]
            ]
            if required_length:
                venue_pitches = [
                    p
                    for p in venue_pitches
                    if hasattr(p.supported_lengths, "all")
                    and required_length in p.supported_lengths.all()
                ]
            return venue_pitches

        assigned_pitch = None
        if target_venue:
            candidate_pitches = get_compatible_pitches(target_venue)
            for p in candidate_pitches:
                if is_pitch_available(
                    p, target_date_str, target_slot, ignore_fixture_id=existing_f_id
                ):
                    assigned_pitch = p
                    break

        if assigned_pitch:
            record["pitchId"] = assigned_pitch.id
            record["pitchPreserved"] = False
            record["venueClash"] = False
            allocated_in_batch.append((target_date_str, target_slot, assigned_pitch.id))
            continue

        # Step 3: Venue Full / Clash Handling -> Search Alternative Venues
        record["venueClash"] = True
        record["pitchPreserved"] = False
        record["pitchId"] = None

        alt_pitch = None
        alt_venues = [v for v in sorted_venues if not target_venue or v.id != target_venue.id]

        for v in alt_venues:
            alt_candidates = get_compatible_pitches(v)
            for p in alt_candidates:
                if is_pitch_available(
                    p, target_date_str, target_slot, ignore_fixture_id=existing_f_id
                ):
                    alt_pitch = p
                    break
            if alt_pitch:
                break

        if alt_pitch:
            alt_venue_name = getattr(alt_pitch.venue, "name", "Alternative Venue")
            record["suggestedPitchId"] = alt_pitch.id
            record["suggestedPitchName"] = f"{alt_venue_name} - {alt_pitch.name}"
            target_vname = target_venue.name if target_venue else "Target venue"
            record["clashReason"] = (
                f"Venue full: all pitches at {target_vname} are occupied or blocked. "
                f"Suggested: {record['suggestedPitchName']}"
            )
        else:
            record["suggestedPitchId"] = None
            record["clashReason"] = (
                f"No pitches available across any venue on {target_date_str} ({target_slot})"
            )
            record["selected"] = False

    return records
