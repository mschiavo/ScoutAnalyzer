import pytest
from fastapi.testclient import TestClient
from web_app import app

client = TestClient(app)

def get_admin_headers():
    res = client.post("/api/auth/login", json={"username": "admin", "password": "adminpassword"})
    token = res.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}

def get_scout_headers():
    admin_h = get_admin_headers()
    # Crea scout di test
    client.post("/api/admin/users", json={
        "username": "scout_test_del",
        "password": "Password123!",
        "role": "SCOUT",
        "team_ids": []
    }, headers=admin_h)
    res = client.post("/api/auth/login", json={"username": "scout_test_del", "password": "Password123!"})
    token = res.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}

def test_admin_endpoints_require_admin():
    # Chiamata anonima -> 401
    res = client.get("/api/admin/users")
    assert res.status_code == 401

def test_admin_users_crud_and_teams():
    headers = get_admin_headers()

    # 1. Lista squadre per selettore
    res_teams = client.get("/api/admin/teams", headers=headers)
    assert res_teams.status_code == 200
    assert isinstance(res_teams.json(), list)

    # 2. Creazione utente
    new_user_payload = {
        "username": "new_scout_user",
        "password": "Password123!",
        "email": "new_scout@test.local",
        "role": "SCOUT",
        "team_ids": [1, 2]
    }
    res_create = client.post("/api/admin/users", json=new_user_payload, headers=headers)
    assert res_create.status_code in (200, 201)
    user_id = res_create.json()["id"]

    # 3. Lista utenti
    res_list = client.get("/api/admin/users", headers=headers)
    assert res_list.status_code == 200
    users = res_list.json()
    assert any(u["id"] == user_id for u in users)

    # 4. Modifica utente
    res_put = client.put(f"/api/admin/users/{user_id}", json={
        "email": "updated_scout@test.local",
        "role": "SCOUT",
        "team_ids": [1]
    }, headers=headers)
    assert res_put.status_code == 200
    assert res_put.json()["email"] == "updated_scout@test.local"

    # 5. Cancellazione utente
    res_del = client.delete(f"/api/admin/users/{user_id}", headers=headers)
    assert res_del.status_code == 200

def test_admin_logins_audit():
    headers = get_admin_headers()
    res = client.get("/api/admin/logins", headers=headers)
    assert res.status_code == 200
    assert isinstance(res.json(), list)

def test_admin_rules_config():
    headers = get_admin_headers()
    res = client.get("/api/admin/rules/terminal", headers=headers)
    assert res.status_code == 200
    rules = res.json()
    assert isinstance(rules, list)

def test_delete_match_and_clear_all():
    admin_h = get_admin_headers()
    scout_h = get_scout_headers()

    sample_content = b"""[3MATCH]
15/10/2026;20.30.00;2026/2027;Campionato;Andata;;1;1;TEST_DEL_1;1;Z;0;;;
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
    # 1. Carica una partita
    up_res = client.post(
        "/api/audit/upload",
        files={"file": ("test_del_1.dvw", sample_content, "text/plain")},
        headers=admin_h
    )
    assert up_res.status_code == 200
    match_id = up_res.json()["match_id"]

    # 2. Scout non puo' eliminare la partita (403)
    res_scout_del = client.delete(f"/api/matches/{match_id}", headers=scout_h)
    assert res_scout_del.status_code == 403

    # 3. Admin elimina la partita (200)
    res_admin_del = client.delete(f"/api/matches/{match_id}", headers=admin_h)
    assert res_admin_del.status_code == 200
    assert res_admin_del.json()["status"] == "SUCCESS"

    # 4. Verifica che non esista piu' (404)
    res_get = client.get(f"/api/matches/{match_id}", headers=admin_h)
    assert res_get.status_code == 404

    # 5. Carica due partite e prova lo svuotamento totale
    client.post("/api/audit/upload", files={"file": ("del_a.dvw", sample_content, "text/plain")}, headers=admin_h)
    client.post("/api/audit/upload", files={"file": ("del_b.dvw", sample_content, "text/plain")}, headers=admin_h)

    # Scout non puo' svuotare (403)
    res_scout_clear = client.delete("/api/admin/matches/clear", headers=scout_h)
    assert res_scout_clear.status_code == 403

    # Admin svuota tutto
    res_clear = client.delete("/api/admin/matches/clear", headers=admin_h)
    assert res_clear.status_code == 200
    assert res_clear.json()["status"] == "SUCCESS"

    # Verifica lista match vuota
    res_list = client.get("/api/matches", headers=admin_h)
    assert res_list.status_code == 200
    assert len(res_list.json()) == 0

def test_admin_revalidate_single_match():
    admin_h = get_admin_headers()
    scout_h = get_scout_headers()

    sample_content = b"""[3MATCH]
15/10/2026;20.30.00;2026/2027;Campionato;Andata;;1;1;TEST_REVAL;1;Z;0;;;
[3TEAMS]
TH;Home Team;0;;;;;
TV;Away Team;0;;;;;
[3SET]
True;8-5;16-10;21-15;25-20;22;
[3PLAYERS-H]
0;1;10;;;;;;;TEST;H;;;2;False;;;;;;
[3PLAYERS-V]
1;1;20;;;;;;;TEST;V;;;2;False;;;;;;
[3SCOUT]
*10SM#;;;;;;;;1;1;1;1;100;;10;11;12;13;14;15;20;21;22;23;24;25;
"""
    up_res = client.post(
        "/api/audit/upload",
        files={"file": ("test_reval_single.dvw", sample_content, "text/plain")},
        headers=admin_h
    )
    assert up_res.status_code == 200
    match_id = up_res.json()["match_id"]

    # Scout cannot revalidate (403)
    res_scout = client.post(f"/api/admin/matches/{match_id}/revalidate", headers=scout_h)
    assert res_scout.status_code == 403

    # Admin revalidates (200)
    res_admin = client.post(f"/api/admin/matches/{match_id}/revalidate", headers=admin_h)
    assert res_admin.status_code == 200
    data = res_admin.json()
    assert data["status"] == "SUCCESS"
    assert data["match_id"] == match_id
    assert "issues_count" in data
    assert "match" in data
    assert data["match"]["id"] == match_id

