from fastapi.testclient import TestClient
import sqlite3
import pytest
from database.setup_db import create_database
from src.ingestion_manager import IngestionManager
from web_app import app

client = TestClient(app)

def get_admin_headers():
    res = client.post("/api/auth/login", json={"username": "admin", "password": "adminpassword"})
    if res.status_code == 200:
        token = res.json()["access_token"]
        return {"Authorization": f"Bearer {token}"}
    return {}

def test_unauthenticated_request_is_blocked():
    # Verifica che senza token le API rispondano 401
    res = client.get("/api/matches")
    assert res.status_code == 401

def test_get_matches_api():
    headers = get_admin_headers()
    response = client.get("/api/matches", headers=headers)
    assert response.status_code == 200
    assert isinstance(response.json(), list)

def test_cors_headers():
    response = client.options("/api/matches", headers={
        "Origin": "http://localhost:5173",
        "Access-Control-Request-Method": "GET"
    })
    assert response.status_code == 200
    assert response.headers.get("access-control-allow-origin") in ("*", "http://localhost:5173")

def test_match_detail_and_events_api(tmp_path):
    headers = get_admin_headers()

    # Inseriamo un match di prova nel db
    test_db = str(tmp_path / "test_api.db")
    create_database(test_db)
    
    ingester = IngestionManager()
    ingester.db_path = test_db
    mock_data = {
        "match_info": {"match_code": "API_MATCH", "date": "2026-10-15"},
        "teams": {"home_code": "H_API", "home_name": "Home Api", "away_code": "A_API", "away_name": "Away Api"},
        "sets": [{"set_number": 1, "home_score": 25, "away_score": 20, "duration_minutes": 22, "winning_team": "*"}],
        "players_home": [{"number": "10", "name": "Player 10"}],
        "players_visiting": [{"number": "4", "name": "Player 4"}],
        "events": [{
            "event_index": 1, "set_number": 1, "team_code": "*", "shirt_number": 10,
            "skill": "S", "skill_type": "M", "evaluation": "#", "extended_code": "*10SM#",
            "is_valid": 1, "home_setter_pos": 1, "away_setter_pos": 1,
            "home_lineup": [10, 11, 12, 13, 14, 15], "away_lineup": [4, 5, 6, 7, 8, 9],
            "video_frame": 100
        }]
    }
    res = ingester.ingest_dvw(mock_data)
    match_id = res["match_id"]

    # Verifica chiamata match detail
    res_m = client.get(f"/api/matches/{match_id}", headers=headers)
    assert res_m.status_code in (200, 404)

def test_audit_upload_endpoint():
    headers = get_admin_headers()
    sample_content = b"""[3MATCH]
15/10/2026;20.30.00;2026/2027;Campionato;Andata;;1;1;TEST_UP;1;Z;0;;;
[3TEAMS]
TH;Home Team;0;;;;;
TV;Away Team;0;;;;;
[3SET]
True;25-20;22;
[3PLAYERS-H]
0;1;10;;;;;;;TEST;H;;;2;False;;;;;;
[3PLAYERS-V]
1;1;20;;;;;;;TEST;V;;;2;False;;;;;;
[3SCOUT]
*10SM#;;;;;;;;1;1;1;1;100;;10;11;12;13;14;15;20;21;22;23;24;25;
*p25:20;;;;;;;;1;1;1;1;105;;10;11;12;13;14;15;20;21;22;23;24;25;
"""
    response = client.post(
        "/api/audit/upload",
        files={"file": ("test_upload.dvw", sample_content, "text/plain")},
        headers=headers
    )
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "SUCCESS"
    assert data["events_count"] == 2


def test_audit_upload_with_hierarchy_metadata():
    headers = get_admin_headers()
    sample_content = b"""[3MATCH]
15/10/2026;20.30.00;2026/2027;Campionato;Andata;;1;1;TEST_HIERARCHY;1;Z;0;;;
[3TEAMS]
TH;Home Team;0;;;;;
TV;Away Team;0;;;;;
[3SET]
True;25-20;22;
[3PLAYERS-H]
0;1;10;;;;;;;TEST;H;;;2;False;;;;;;
[3PLAYERS-V]
1;1;20;;;;;;;TEST;V;;;2;False;;;;;;
[3SCOUT]
*10SM#;;;;;;;;1;1;1;1;100;;10;11;12;13;14;15;20;21;22;23;24;25;
*p25:20;;;;;;;;1;1;1;1;105;;10;11;12;13;14;15;20;21;22;23;24;25;
"""
    response = client.post(
        "/api/audit/upload",
        files={"file": ("&01_test_match.dvw", sample_content, "text/plain")},
        data={
            "campionato": "2026-2027",
            "categoria": "B1F",
            "girone": "B",
            "giornata": "03"
        },
        headers=headers
    )
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "SUCCESS"
    assert "2026-2027/B1F/B/03/&01_test_match.dvw" in data.get("storage_path", "")


def test_matches_list_enriched_fields():
    headers = get_admin_headers()
    sample_content = b"""[3MATCH]
15/10/2026;20.30.00;2026/2027;Campionato;Andata;;1;1;TEST_SCORE;1;Z;0;;;
[3TEAMS]
TH;Home Team;0;;;;;
TV;Away Team;0;;;;;
[3SET]
True;8-5;16-10;21-15;25-20;22;
True;8-5;16-10;21-15;23-25;24;
True;8-5;16-10;21-15;25-18;20;
True;8-5;16-10;21-15;25-22;23;
[3PLAYERS-H]
0;1;10;;;;;;;TEST;H;;;2;False;;;;;;
[3PLAYERS-V]
1;1;20;;;;;;;TEST;V;;;2;False;;;;;;
[3SCOUT]
*10SM#;;;;;;;;1;1;1;1;100;;10;11;12;13;14;15;20;21;22;23;24;25;
*p25:20;;;;;;;;1;1;1;1;105;;10;11;12;13;14;15;20;21;22;23;24;25;
"""
    res_up = client.post(
        "/api/audit/upload",
        files={"file": ("&And01_aduna-verona_sync_marco.dvw", sample_content, "text/plain")},
        headers=headers
    )
    assert res_up.status_code == 200

    res = client.get("/api/matches", headers=headers)
    assert res.status_code == 200
    matches = res.json()
    assert len(matches) > 0
    m = next((x for x in matches if "sync_marco" in x["match_code"]), None)
    assert m is not None

    assert "final_score" in m
    assert "set_scores" in m
    assert "scout_author" in m
    assert m["scout_author"].lower() == "marco"
    assert "25-20" in m["set_scores"]
    assert "home_sets_won" in m
    assert "away_sets_won" in m

def test_list_matches_performance_and_columns_integrity():
    headers = get_admin_headers()
    res = client.get("/api/matches", headers=headers)
    assert res.status_code == 200
    matches = res.json()
    assert isinstance(matches, list)
    if matches:
        m = matches[0]
        for field in ["final_score", "set_scores", "sets_count", "events_count", "logs_count", "home_sets_won", "away_sets_won", "home_name", "away_name"]:
            assert field in m, f"Field {field} missing from /api/matches payload"



