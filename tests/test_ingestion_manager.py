import sqlite3
from database.setup_db import create_database
from src.ingestion_manager import IngestionManager

def test_ingest_native_lineups(tmp_path):
    db_file = str(tmp_path / "test.db")
    create_database(db_file)

    ingester = IngestionManager()
    ingester.db_path = db_file

    mock_data = {
        "match_info": {"match_code": "TEST_01", "date": "2026-10-15"},
        "teams": {"home_code": "H_TEAM", "home_name": "Home", "away_code": "A_TEAM", "away_name": "Away"},
        "sets": [{"set_number": 1, "home_score": 25, "away_score": 20, "duration_minutes": 22, "winning_team": "*"}],
        "players_home": [{"number": "18", "name": "Player 18"}],
        "players_visiting": [{"number": "9", "name": "Player 9"}],
        "events": [{
            "event_index": 1, "set_number": 1, "team_code": "*", "shirt_number": 18,
            "skill": "S", "skill_type": "M", "evaluation": "-", "extended_code": "*18SM-~~~58B",
            "is_valid": 1, "home_setter_pos": 2, "away_setter_pos": 1,
            "home_lineup": [18, 15, 1, 5, 7, 4], "away_lineup": [9, 8, 2, 1, 11, 13],
            "video_frame": 398
        }]
    }

    res = ingester.ingest_dvw(mock_data)
    assert res["status"] == "SUCCESS"

    conn = sqlite3.connect(db_file)
    c = conn.cursor()
    c.execute("SELECT home_pos1, away_pos1, home_setter_pos, away_setter_pos, video_frame FROM events WHERE match_id = ?", (res["match_id"],))
    row = c.fetchone()
    assert row == (18, 9, 2, 1, 398)
    conn.close()


def test_reimport_replaces_removed_sets_and_preserves_current_syntax_logs(tmp_path):
    from src.state_engine import MatchStateEngine

    db_file = str(tmp_path / "reimport.db")
    create_database(db_file)
    ingester = IngestionManager()
    ingester.db_path = db_file
    parsed = {
        "match_info": {"match_code": "REIMPORT"},
        "sets": [
            {"set_number": 1, "home_score": 25, "away_score": 20},
            {"set_number": 2, "home_score": 20, "away_score": 25},
        ],
        "events": [
            {"event_index": 1, "set_number": 1, "is_valid": 0, "error_note": "Vecchio"},
        ],
    }
    match_id = ingester.ingest_dvw(parsed)["match_id"]

    parsed["sets"].pop()
    parsed["events"][0]["error_note"] = "Corrente"
    assert ingester.ingest_dvw(parsed)["match_id"] == match_id
    engine = MatchStateEngine(match_id)
    engine.db_path = db_file
    engine.process_match()

    with sqlite3.connect(db_file) as conn:
        assert conn.execute(
            "SELECT final_score, set_scores, sets_count, logs_count FROM matches WHERE id = ?",
            (match_id,),
        ).fetchone() == ("1 - 0", "25-20", 1, 1)
        assert conn.execute(
            "SELECT parsed_status, validation_source, error_summary FROM validation_logs WHERE match_id = ?",
            (match_id,),
        ).fetchall() == [("ERROR", "SYNTAX", "Corrente")]
