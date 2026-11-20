import time
from fastapi.testclient import TestClient
from web_app import app
import sqlite3

client = TestClient(app)

def test_full_auth_multitenant_lifecycle():
    # 1. Login Admin
    res_login = client.post("/api/auth/login", json={"username": "admin", "password": "adminpassword"})
    assert res_login.status_code == 200
    admin_token = res_login.json()["access_token"]
    admin_headers = {"Authorization": f"Bearer {admin_token}"}

    # 2. Creazione utente SCOUT con assegnazione a singola squadra (team_id 1)
    res_teams = client.get("/api/admin/teams", headers=admin_headers)
    assert res_teams.status_code == 200
    teams = res_teams.json()
    assert len(teams) > 0
    assigned_team_id = teams[0]["id"]
    assigned_team_code = teams[0]["code"]

    unique_username = f"scout_e2e_{int(time.time() * 1000)}"
    res_cu = client.post("/api/admin/users", json={
        "username": unique_username,
        "password": "Password123!",
        "email": f"{unique_username}@volley.it",
        "role": "SCOUT",
        "team_ids": [assigned_team_id]
    }, headers=admin_headers)
    assert res_cu.status_code == 201
    created_user_id = res_cu.json()["id"]

    try:
        # 3. Login SCOUT
        res_scout_login = client.post("/api/auth/login", json={"username": unique_username, "password": "Password123!"})
        assert res_scout_login.status_code == 200
        scout_token = res_scout_login.json()["access_token"]
        scout_headers = {"Authorization": f"Bearer {scout_token}"}

        # 4. Verifica che SCOUT veda solo gare del suo team
        res_matches = client.get("/api/matches", headers=scout_headers)
        assert res_matches.status_code == 200
        for m in res_matches.json():
            assert m.get("home_team_id") == assigned_team_id or m.get("away_team_id") == assigned_team_id or m.get("home_code") == assigned_team_code or m.get("away_code") == assigned_team_code

        # 5. Verifica che SCOUT riceva 403 Forbidden su upload o audit file
        res_upload = client.post("/api/audit/file", json={"file_path": "dummy.dvw"}, headers=scout_headers)
        assert res_upload.status_code == 403

        # 6. Verifica audit log accessi in user_logins
        res_logins = client.get("/api/admin/logins", headers=admin_headers)
        assert res_logins.status_code == 200
        assert len(res_logins.json()) >= 2
        assert any(l["username"] == unique_username for l in res_logins.json())

        # 7. Verifica revalidate regole da admin
        res_reval = client.post("/api/admin/rules/revalidate", headers=admin_headers)
        assert res_reval.status_code == 200
        assert res_reval.json()["status"] == "SUCCESS"
    finally:
        # Cleanup
        client.delete(f"/api/admin/users/{created_user_id}", headers=admin_headers)
