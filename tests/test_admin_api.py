import pytest
from fastapi.testclient import TestClient
from web_app import app

client = TestClient(app)

def get_admin_headers():
    res = client.post("/api/auth/login", json={"username": "admin", "password": "adminpassword"})
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
    if res.json():
        first = res.json()[0]
        assert "ip_address" in first
        assert "username" in first
        assert "login_status" in first

def test_admin_rules_crud():
    headers = get_admin_headers()
    
    # 1. Lettura regole
    res_rules = client.get("/api/admin/rules/terminal", headers=headers)
    assert res_rules.status_code == 200
    initial_count = len(res_rules.json())

    # 2. Aggiunta regola di test
    new_rule = {
        "description": "Regola di test dinamica",
        "terminal_skill": "A",
        "terminal_eval": "#",
        "followup_skills": ["D"],
        "followup_evals": ["="],
        "must_be_opponent": True
    }
    res_add = client.post("/api/admin/rules/terminal", json=new_rule, headers=headers)
    assert res_add.status_code == 200
    rules_after_add = res_add.json()
    assert len(rules_after_add) == initial_count + 1

    # 3. Rimozione della regola di test appena aggiunta
    rule_idx = len(rules_after_add) - 1
    res_del = client.delete(f"/api/admin/rules/terminal/{rule_idx}", headers=headers)
    assert res_del.status_code == 200
    assert len(res_del.json()) == initial_count
