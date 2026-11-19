import os
import sqlite3
import pytest
from src.dvw_parser import DVWParser
from src.ingestion_manager import IngestionManager
from src.state_engine import MatchStateEngine

def test_real_match_audit_end_to_end():
    sample_file = r"D:\Volley\B1FB\giornata_01\&01_COR-VOL_Vicenza_b1fb_26_s.dvw"
    if not os.path.exists(sample_file):
        pytest.skip(f"File di test reale non presente sul path locale: {sample_file}")

    # 1. Parsing
    parser = DVWParser(sample_file)
    parsed = parser.parse()
    assert len(parsed["events"]) > 1000
    assert parsed["teams"]["home_code"] != ""
    assert parsed["teams"]["away_code"] != ""

    # 2. Ingestione
    ingester = IngestionManager()
    res = ingester.ingest_dvw(parsed)
    assert res["status"] == "SUCCESS"
    assert res["events_count"] > 1000
    match_id = res["match_id"]

    # Verifica persistenza delle formazioni native a DB
    conn = sqlite3.connect(ingester.db_path)
    cur = conn.cursor()
    cur.execute("""
        SELECT COUNT(*) FROM events 
        WHERE match_id = ? AND home_pos1 IS NOT NULL AND away_pos1 IS NOT NULL
    """, (match_id,))
    events_with_native_lineups = cur.fetchone()[0]
    conn.close()

    assert events_with_native_lineups > 1000

    # 3. State Engine & Validazione Semantica
    engine = MatchStateEngine(match_id=match_id)
    s_res = engine.process_match()
    assert s_res["status"] == "SUCCESS"
    assert s_res["actions_created"] > 0
    assert s_res["rotations_created"] > 0
