import sqlite3
import os
from database.setup_db import create_database

def test_database_indices_and_columns(tmp_path):
    test_db = str(tmp_path / "test.db")
    create_database(test_db)
    conn = sqlite3.connect(test_db)
    cur = conn.cursor()
    
    # Verifica indici
    cur.execute("SELECT name FROM sqlite_master WHERE type='index'")
    indices = [r[0] for r in cur.fetchall()]
    assert any("idx_events_match" in idx for idx in indices)
    
    # Verifica colonne native in events
    cur.execute("PRAGMA table_info(events)")
    cols = [r[1] for r in cur.fetchall()]
    assert "home_pos1" in cols
    assert "away_pos1" in cols
    assert "home_setter_pos" in cols
    assert "away_setter_pos" in cols
    conn.close()

def test_matches_schema_has_summary_metrics(tmp_path):
    test_db = str(tmp_path / "test_schema.db")
    create_database(test_db)
    conn = sqlite3.connect(test_db)
    cur = conn.cursor()
    cur.execute("PRAGMA table_info(matches)")
    cols = {r[1] for r in cur.fetchall()}
    for expected_col in [
        "home_sets_won", "away_sets_won", "final_score",
        "set_scores", "sets_count", "events_count",
        "logs_count", "scout_author"
    ]:
        assert expected_col in cols, f"Missing column {expected_col} in matches table"
    conn.close()

