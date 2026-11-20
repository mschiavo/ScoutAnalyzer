import pytest
import sqlite3
from fastapi.testclient import TestClient
from database.setup_db import create_database
from src.api.auth import hash_password
from web_app import app

client = TestClient(app)

def test_login_tracking_and_multitenant_matches(tmp_path):
    # 1. Login fallito -> 401 e log FAILED
    res_fail = client.post("/api/auth/login", json={"username": "admin", "password": "wrong_password"})
    assert res_fail.status_code == 401

    # 2. Login admin con successo -> 200 e token
    res_ok = client.post("/api/auth/login", json={"username": "admin", "password": "adminpassword"})
    assert res_ok.status_code == 200
    data = res_ok.json()
    assert "access_token" in data
    admin_token = data["access_token"]
    assert data["user"]["role"] == "ADMIN"

    admin_headers = {"Authorization": f"Bearer {admin_token}"}

    # 3. GET /api/auth/me per admin
    res_me = client.get("/api/auth/me", headers=admin_headers)
    assert res_me.status_code == 200
    assert res_me.json()["username"] == "admin"

    # 4. Creazione manuale a DB di un utente SCOUT associato solo a team 1
    conn = sqlite3.connect("scoutanalyzer.db")
    c = conn.cursor()
    scout_pwd = hash_password("scoutpass123")
    c.execute("INSERT OR IGNORE INTO users (username, password_hash, email, role, is_active) VALUES (?, ?, ?, 'SCOUT', 1)",
              ("scout_test", scout_pwd, "scout_test@test.local"))
    c.execute("SELECT id FROM users WHERE username = 'scout_test'")
    scout_id = c.fetchone()[0]

    # Assegna team_id 1
    c.execute("INSERT OR IGNORE INTO user_teams (user_id, team_id) VALUES (?, 1)", (scout_id,))
    conn.commit()
    conn.close()

    # 5. Login utente SCOUT
    res_scout = client.post("/api/auth/login", json={"username": "scout_test", "password": "scoutpass123"})
    assert res_scout.status_code == 200
    scout_token = res_scout.json()["access_token"]
    scout_headers = {"Authorization": f"Bearer {scout_token}"}

    # 6. Verifica filtro /api/matches: scout vede solo partite con team 1
    res_scout_matches = client.get("/api/matches", headers=scout_headers)
    assert res_scout_matches.status_code == 200
    scout_matches = res_scout_matches.json()
    for m in scout_matches:
        # Match deve includere team 1
        assert m.get("home_team_id") == 1 or m.get("away_team_id") == 1 or m.get("home_code") == "ADU23" or m.get("away_code") == "ADU23"

    # 7. Scout non può effettuare upload (403 Forbidden)
    res_upload = client.post("/api/audit/file", json={"file_path": "dummy.dvw"}, headers=scout_headers)
    assert res_upload.status_code == 403
