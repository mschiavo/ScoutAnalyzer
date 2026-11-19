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
