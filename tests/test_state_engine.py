import sqlite3
from database.setup_db import create_database
from src.ingestion_manager import IngestionManager
from src.state_engine import MatchStateEngine

def test_native_lineup_serving_check(tmp_path):
    db_file = str(tmp_path / "test.db")
    create_database(db_file)

    ingester = IngestionManager()
    ingester.db_path = db_file
    mock_data = {
        "match_info": {"match_code": "VB_TEST1", "date": "2026-10-15"},
        "teams": {"home_code": "H", "home_name": "Home", "away_code": "A", "away_name": "Away"},
        "sets": [{"set_number": 1, "home_score": 25, "away_score": 20, "duration_minutes": 25, "winning_team": "*"}],
        "players_home": [{"number": "18", "name": "H18"}, {"number": "15", "name": "H15"}],
        "players_visiting": [{"number": "9", "name": "A9"}],
        "events": [
            {
                "event_index": 1, "set_number": 1, "team_code": "*", "shirt_number": 18,
                "skill": "S", "skill_type": "M", "evaluation": "+", "extended_code": "*18SM+~~~58B",
                "is_valid": 1, "home_setter_pos": 2, "away_setter_pos": 1,
                "home_lineup": [18, 15, 1, 5, 7, 4], "away_lineup": [9, 8, 2, 1, 11, 13]
            }
        ]
    }
    res = ingester.ingest_dvw(mock_data)

    engine = MatchStateEngine(match_id=res["match_id"])
    engine.db_path = db_file
    status = engine.process_match()
    assert status["issues_found"] == 0

def test_libero_serving_rule(tmp_path):
    db_file = str(tmp_path / "test.db")
    create_database(db_file)

    # Inseriamo un'atleta con ruolo Libero (role_id 1 o special L)
    ingester = IngestionManager()
    ingester.db_path = db_file
    mock_data = {
        "match_info": {"match_code": "VB_TEST_LIBERO", "date": "2026-10-15"},
        "teams": {"home_code": "H", "home_name": "Home", "away_code": "A", "away_name": "Away"},
        "sets": [{"set_number": 1, "home_score": 25, "away_score": 20, "duration_minutes": 25, "winning_team": "*"}],
        "players_home": [{"number": "1", "name": "Libero Player", "role_code": "1"}],
        "players_visiting": [{"number": "9", "name": "A9"}],
        "events": [
            {
                "event_index": 1, "set_number": 1, "team_code": "*", "shirt_number": 1,
                "skill": "S", "skill_type": "M", "evaluation": "-", "extended_code": "*01SM-",
                "is_valid": 1, "home_setter_pos": 1, "away_setter_pos": 1,
                "home_lineup": [1, 2, 3, 4, 5, 6], "away_lineup": [9, 8, 2, 1, 11, 13]
            }
        ]
    }
    res = ingester.ingest_dvw(mock_data)

    engine = MatchStateEngine(match_id=res["match_id"])
    engine.db_path = db_file
    status = engine.process_match()
    assert status["issues_found"] >= 1

    conn = sqlite3.connect(db_file)
    cur = conn.cursor()
    cur.execute("SELECT error_summary FROM validation_logs WHERE match_id = ?", (res["match_id"],))
    errors = [r[0] for r in cur.fetchall()]
    conn.close()
    assert any("Libero" in err for err in errors)

def test_max_substitutions_rule(tmp_path):
    db_file = str(tmp_path / "test.db")
    create_database(db_file)

    ingester = IngestionManager()
    ingester.db_path = db_file
    # Generiamo 7 sostituzioni per la squadra di casa nel set 1
    events = []
    idx = 1
    for i in range(1, 8):
        events.append({
            "event_index": idx, "set_number": 1, "team_code": "*", "shirt_number": None,
            "skill": None, "skill_type": None, "evaluation": None, "extended_code": f"*c0{i}:1{i}",
            "is_valid": 1, "home_lineup": [1, 2, 3, 4, 5, 6], "away_lineup": [9, 8, 7, 10, 11, 12]
        })
        idx += 1

    mock_data = {
        "match_info": {"match_code": "VB_TEST_SUBST", "date": "2026-10-15"},
        "teams": {"home_code": "H", "home_name": "Home", "away_code": "A", "away_name": "Away"},
        "sets": [{"set_number": 1, "home_score": 25, "away_score": 20, "duration_minutes": 25, "winning_team": "*"}],
        "players_home": [], "players_visiting": [],
        "events": events
    }
    res = ingester.ingest_dvw(mock_data)

    engine = MatchStateEngine(match_id=res["match_id"])
    engine.db_path = db_file
    status = engine.process_match()
    assert status["issues_found"] >= 1

    conn = sqlite3.connect(db_file)
    cur = conn.cursor()
    cur.execute("SELECT error_summary FROM validation_logs WHERE match_id = ?", (res["match_id"],))
    errors = [r[0] for r in cur.fetchall()]
    conn.close()
    assert any("sostituzion" in err.lower() for err in errors)

def test_set_score_margin_rule(tmp_path):
    db_file = str(tmp_path / "test.db")
    create_database(db_file)

    ingester = IngestionManager()
    ingester.db_path = db_file
    mock_data = {
        "match_info": {"match_code": "VB_TEST_SET_MARGIN", "date": "2026-10-15"},
        "teams": {"home_code": "H", "home_name": "Home", "away_code": "A", "away_name": "Away"},
        # Set 1 con soli 24-23 (scarto < 2 e vincente < 25)
        "sets": [{"set_number": 1, "home_score": 24, "away_score": 23, "duration_minutes": 25, "winning_team": "*"}],
        "players_home": [], "players_visiting": [],
        "events": []
    }
    res = ingester.ingest_dvw(mock_data)

    engine = MatchStateEngine(match_id=res["match_id"])
    engine.db_path = db_file
    status = engine.process_match()
    assert status["issues_found"] >= 1

    conn = sqlite3.connect(db_file)
    cur = conn.cursor()
    cur.execute("SELECT error_summary FROM validation_logs WHERE match_id = ?", (res["match_id"],))
    errors = [r[0] for r in cur.fetchall()]
    conn.close()
    assert any("Punteggio finale anomalo" in err for err in errors)
