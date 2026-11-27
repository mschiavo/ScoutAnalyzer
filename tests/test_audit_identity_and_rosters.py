from contextlib import closing
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from database.setup_db import create_database
from src.db import get_db_connection
from web_app import app


@pytest.fixture
def admin_client(tmp_path, monkeypatch):
    monkeypatch.setenv("SCOUT_DB_PATH", str(tmp_path / "test.db"))
    monkeypatch.setenv("STORAGE_DIR", str(tmp_path / "storage"))
    monkeypatch.setenv("STORAGE_BACKEND", "local")
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("SCOUT_NAS_MODE", raising=False)
    monkeypatch.delenv("SCOUT_ADMIN_PASSWORD", raising=False)
    create_database()
    with TestClient(app) as client:
        login = client.post("/api/auth/login", json={"username": "admin", "password": "adminpassword"})
        assert login.status_code == 200
        client.headers["Authorization"] = "Bearer " + login.json()["access_token"]
        yield client


def upload(client, filename, home="GPS26", away="VOL26", revision="", **data):
    content = f"""[3MATCH]
15/10/2026;20.30.00;2026/2027;Campionato;{revision};
[3TEAMS]
{home};Home Team;0;;;;;
{away};Away Team;0;;;;;
[3SET]
True;25-20;22;
""".encode()
    return client.post("/api/audit/upload", files={"file": (filename, content, "text/plain")}, data=data)


def test_confirm_replacement_preserves_match_id_and_reverse_order(admin_client):
    first = upload(admin_client, "&04_GPS-VOL_Delebio_b1fb_26_s.dvw", giornata="01")
    assert first.status_code == 200, first.text
    match_id = first.json()["match_id"]
    assert "/04/" in first.json()["storage_path"]
    assert admin_client.get("/api/matches").json()[0]["scout_author"] == "Delebio_b1fb_26_s"
    with closing(get_db_connection()) as db:
        db.execute("UPDATE matches SET audit_scope = NULL, giornata = NULL WHERE id = ?", (match_id,))
        db.commit()

    new_name = "&04_GPS-VOL_Rilevatore_b1fb_26_s.dvw"
    renamed = upload(admin_client, new_name)
    assert renamed.status_code == 409
    assert renamed.json()["detail"]["code"] == "identical_file"
    duplicate = upload(admin_client, new_name, revision="correzione")
    assert duplicate.status_code == 409
    assert duplicate.json()["detail"]["matches"][0]["id"] == match_id
    assert duplicate.json()["detail"]["incoming"]["giornata"] == 4
    assert duplicate.json()["detail"]["incoming"]["scout_author"] == "Rilevatore_b1fb_26_s"
    assert len(admin_client.get("/api/matches").json()) == 1

    reverse_name = "&04_VOL-GPS_Altro_b1fb_26_s.dvw"
    assert upload(admin_client, reverse_name, home="VOL26", away="GPS26").status_code == 409
    reverse = upload(admin_client, reverse_name, home="VOL26", away="GPS26", create_new=True)
    assert reverse.status_code == 200, reverse.text
    replacement = upload(admin_client, new_name, revision="correzione", replace_match_id=match_id)
    assert replacement.status_code == 200, replacement.text
    assert replacement.json()["match_id"] == match_id
    identical = upload(admin_client, new_name, revision="correzione", create_new=True)
    assert identical.status_code == 409
    assert identical.json()["detail"]["code"] == "identical_file"
    assert len(admin_client.get("/api/matches").json()) == 2


def test_new_import_keeps_both_files_even_when_names_match(admin_client, tmp_path):
    name = "&04_GPS-VOL_Rilevatore_b1fb_26_s.dvw"
    first = upload(admin_client, name).json()
    conflict = upload(admin_client, name, revision="seconda")
    assert conflict.status_code == 409
    second_response = upload(admin_client, name, revision="seconda", create_new=True)
    assert second_response.status_code == 200, second_response.text
    second = second_response.json()
    assert first["match_id"] != second["match_id"]
    assert first["storage_path"] != second["storage_path"]
    assert b"seconda" not in (tmp_path / "storage" / first["storage_path"]).read_bytes()
    assert b"seconda" in (tmp_path / "storage" / second["storage_path"]).read_bytes()
    assert {row["scout_author"] for row in admin_client.get("/api/matches").json()} == {"Rilevatore_b1fb_26_s"}


def test_roster_download_backup_soft_delete_and_reactivation(admin_client, tmp_path, monkeypatch):
    match = upload(admin_client, "&04_GPS-VOL_Delebio_b1fb_26_s.dvw").json()
    with closing(get_db_connection()) as db:
        db.execute("UPDATE teams SET roster_code = '1234' WHERE code = 'GPS26'")
        team_id = db.execute("SELECT id FROM teams WHERE code = 'GPS26'").fetchone()[0]
        db.commit()

    content = b"3\tP-1\tTest\t01/01/2000\t\t\t\t\tAda\t1\n"
    response = SimpleNamespace(content=content, raise_for_status=lambda: None)
    monkeypatch.setattr("src.roster_manager.requests.get", lambda *args, **kwargs: response)
    payload = {"team_code": "GPS26", "download": True}
    assert admin_client.post("/api/rosters/sync", json=payload).json()["results"][0]["status"] == "SUCCESS"
    assert not admin_client.post("/api/rosters/sync", json=payload).json()["results"][0]["backup_created"]
    response.content = content.replace(b"Ada", b"Anna")
    result = admin_client.post("/api/rosters/sync", json=payload).json()["results"][0]
    assert result["status"] == "SUCCESS" and result["backup_created"]

    roster_dir = tmp_path / "storage" / "rosters"
    assert next((roster_dir / "backups").glob("1234_*.sq")).read_bytes() == content
    assert admin_client.delete(f"/api/admin/rosters/{team_id}").status_code == 200
    assert team_id not in [team["id"] for team in admin_client.get("/api/admin/rosters").json()]
    assert (roster_dir / "current" / "1234.sq").read_bytes() == response.content
    assert len(admin_client.get("/api/matches").json()) == 1

    url = f"/api/admin/matches/{match['match_id']}/revalidate"
    blocked = admin_client.post(url)
    assert blocked.status_code == 409
    assert blocked.json()["detail"]["teams"][0]["id"] == team_id
    assert admin_client.post(url + "?reactivate_rosters=true").status_code == 200
    assert admin_client.get(f"/api/admin/rosters/{team_id}").json()[0]["first_name"] == "Anna"


def test_catalog_import_and_manual_roster_code(admin_client):
    url = "/api/admin/teams"
    assert admin_client.post(url, json={"code": "GPS26", "name": "GPS Volley Group Schio"}).status_code == 200
    first = admin_client.post(url + "/import-b1f-b").json()
    assert first == {"added": 13, "linked": 1, "conflicts": []}
    assert admin_client.post(url + "/import-b1f-b").json() == {"added": 0, "linked": 0, "conflicts": []}
    team = next(team for team in admin_client.get(url).json() if team["code"] == "GPS26")
    assert team["roster_code"] == "2771"
    assert admin_client.put(f"{url}/{team['id']}", json={**team, "roster_code": "2999"}).status_code == 200
    assert admin_client.post(url + "/import-b1f-b").json()["conflicts"] == [
        "GPS26: codice roster esistente 2999, catalogo 2771."
    ]


def test_admin_can_persist_substitution_limit(admin_client, tmp_path, monkeypatch):
    from src.state_engine import MatchStateEngine

    config_file = tmp_path / "config.json"
    config_file.write_text('{"validation":{"require_libero":true}}', encoding="utf-8")
    monkeypatch.setattr("src.api.admin_routes.DEFAULT_CONFIG_PATH", str(config_file))
    route = "/api/admin/rules/substitutions"
    assert admin_client.get(route, headers={"Authorization": ""}).status_code == 401
    assert admin_client.get(route).json() == {"max_substitutions_per_set": 8}
    assert admin_client.put(route, json={"max_substitutions_per_set": -1}).status_code == 422
    assert admin_client.put(route, json={"max_substitutions_per_set": 7}).status_code == 200
    assert admin_client.get(route).json() == {"max_substitutions_per_set": 7}
    engine = MatchStateEngine(match_id=1, config_path=str(config_file))
    assert engine.max_substitutions == 7
    assert engine.config["validation"]["require_libero"] is True


def upload_roster_fixture(client, filename, home_code, home_name, players, events="", **options):
    text = f"""[3MATCH]
15/10/2026;20.30.00;2026/2027;Campionato;{filename};
[3TEAMS]
{home_code};{home_name};0;;;;;
AWY26;Away Team;0;;;;;
[3PLAYERS-H]
"""
    text += "\n".join(";".join(["0", shirt, "", "", "", "", "", "", code, last, first, "", "", *role])
                      for shirt, code, last, first, *role in players)
    if events:
        text += "\n[3SCOUT]\n" + events
    return client.post("/api/audit/upload", files={"file": (filename, text.encode(), "text/plain")}, data=options)


def test_unknown_roster_requires_choice_and_can_be_skipped(admin_client):
    players = [("3", "P-1", "Rossi", "Anna")]
    args = ("&06_NEW-AWY_Rilevatore.dvw", "NEW26", "Nuova squadra", players)
    response = upload_roster_fixture(admin_client, *args)
    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "unknown_rosters"
    assert admin_client.get("/api/admin/teams").json() == []
    assert upload_roster_fixture(admin_client, *args, roster_policy="skip").status_code == 200
    team = next(team for team in admin_client.get("/api/admin/teams").json() if team["code"] == "NEW26")
    roster_url = f"/api/admin/rosters/{team['id']}"
    assert admin_client.get(roster_url).json() == []
    added = upload_roster_fixture(admin_client, "&07_NEW-AWY_Rilevatore.dvw", *args[1:], roster_policy="add")
    assert added.status_code == 200, added.text
    assert admin_client.get(roster_url).json()[0]["first_name"] == "Anna"


def test_roster_anomalies_keep_official_data_and_survive_revalidation(admin_client, tmp_path):
    team = {"code": "GPS26", "name": "GPS Volley Group Schio", "roster_code": "2771"}
    assert admin_client.post("/api/admin/teams", json=team).status_code == 200
    path = tmp_path / "storage" / "rosters" / "current" / "2771.sq"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("3\tP-1\tRossi\t01/01/2000\t\t\t\t\tAnna\t1\n"
                    "5\tP-2\tDe Luca\t01/01/2000\t\t\t\t\tMaria\t2\n", encoding="utf-8")
    assert admin_client.post("/api/rosters/sync", json={"team_code": "GPS26"}).json()["results"][0]["status"] == "SUCCESS"
    uploaded = upload_roster_fixture(admin_client, "&08_GPS-AWY_Rilevatore.dvw", "GPSX", team["name"],
                                    [("9", "P-1", "Rossi", "Ana"), ("5", "P-9", "De Luca", "Maria")])
    assert uploaded.status_code == 200, uploaded.text
    match = uploaded.json()
    assert len(match["roster_issues"]) == 4
    assert any("codice squadra nel DVW GPSX" in issue for issue in match["roster_issues"])
    assert any("numero di maglia ufficiale 3" in issue for issue in match["roster_issues"])
    assert any("codice atleta nel DVW P-9" in issue for issue in match["roster_issues"])
    assert any("nome e cognome ufficiali Rossi Anna" in issue for issue in match["roster_issues"])
    assert admin_client.post(f"/api/admin/matches/{match['match_id']}/revalidate").status_code == 200
    logs = admin_client.get(f"/api/matches/{match['match_id']}/logs").json()
    assert {entry["error_summary"] for entry in logs if entry["raw_code"] == "ROSTER"} == set(match["roster_issues"])
    teams = admin_client.get("/api/admin/teams").json()
    assert {entry["code"] for entry in teams} == {"GPS26", "AWY26"}
    team_id = next(entry["id"] for entry in teams if entry["code"] == "GPS26")
    detail = admin_client.get(f"/api/admin/rosters/{team_id}").json()
    assert [(entry["shirt_number"], entry["first_name"]) for entry in detail] == [(3, "Anna"), (5, "Maria")]


def test_match_role_overrides_official_libero_and_confirmed_changes_stay_notes(admin_client, tmp_path):
    team = {"code": "GPS26", "name": "GPS Volley Group Schio", "roster_code": "2771"}
    assert admin_client.post("/api/admin/teams", json=team).status_code == 200
    path = tmp_path / "storage" / "rosters" / "current" / "2771.sq"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("3\tP-1\tRossi\t01/01/2000\t\t\t\t\tAnna\t1\n", encoding="utf-8")
    assert admin_client.post("/api/rosters/sync", json={"team_code": "GPS26"}).json()["results"][0]["status"] == "SUCCESS"

    events = ("*09SM-;;;;;;;;1;1;1;1;100;;09;11;12;13;14;15;20;21;22;23;24;25;\n"
              "*09AM+;;;;;;;;1;1;1;1;105;;09;11;12;13;14;15;20;21;22;23;24;25;\n")
    response = upload_roster_fixture(admin_client, "&09_GPS-AWY_Rilevatore.dvw", "GPS26", team["name"],
                                     [("9", "P-1", "Rossi", "Anna", "2")], events=events)
    assert response.status_code == 200, response.text
    match = response.json()
    assert match["events_count"] == 2
    assert len(match["roster_variations"]) == 2
    assert match["state_issues_count"] == 0
    url = f"/api/admin/matches/{match['match_id']}"
    assert admin_client.post(url + "/confirm-roster-variations", params={"file_hash": match["file_hash"]}).json()["confirmed"] == 2

    with closing(get_db_connection()) as db:
        db.execute("DELETE FROM match_roster_players WHERE match_id = ?", (match["match_id"],))
        db.commit()
    assert admin_client.post(url + "/revalidate").json()["issues_count"] == 0
    match_view = f"/api/matches/{match['match_id']}"
    detail = admin_client.get(match_view).json()["players_home"][0]
    assert (detail["code"], detail["shirt_number"], detail["role_code"]) == ("P-1", 9, "S")
    logs = admin_client.get(match_view + "/logs").json()
    assert len(logs) == 2 and all(entry["parsed_status"] == "OK" for entry in logs)
    assert admin_client.get("/api/matches").json()[0]["logs_count"] == 0
