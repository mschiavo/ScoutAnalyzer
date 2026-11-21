import os
from fastapi.testclient import TestClient
from web_app import app

client = TestClient(app)

def test_static_files_exist_and_structure():
    assert os.path.exists("static/index.html")
    assert os.path.exists("static/style.css")
    assert os.path.exists("static/app.js")

    with open("static/index.html", "r", encoding="utf-8") as f:
        html = f.read()

    assert "court-container" in html
    assert "events-table" in html
    assert "court-svg" in html
    assert "ScoutAnalyzer 3000" in html

def test_serve_frontend_root():
    response = client.get("/")
    assert response.status_code == 200
    assert "ScoutAnalyzer" in response.text

def test_upload_modal_hierarchy_inputs():
    with open("static/index.html", "r", encoding="utf-8") as f:
        html = f.read()

    assert 'id="upload-campionato"' in html
    assert 'id="upload-categoria"' in html
    assert 'id="upload-girone"' in html
    assert 'id="upload-giornata"' in html

    with open("static/app.js", "r", encoding="utf-8") as f:
        js = f.read()

    assert "autoDetectMatchHierarchy" in js

def test_admin_matches_management_modal_and_quick_delete():
    with open("static/index.html", "r", encoding="utf-8") as f:
        html = f.read()

    assert 'id="btn-open-matches-modal"' in html
    assert 'id="admin-matches-modal"' in html
    assert 'id="btn-quick-delete-match"' in html
    assert 'id="btn-clear-all-matches"' in html
    assert 'id="btn-admin-dropdown"' in html
    assert 'id="admin-dropdown-menu"' in html

    with open("static/app.js", "r", encoding="utf-8") as f:
        js = f.read()

    assert "deleteMatch" in js
    assert "clearAllMatches" in js
    assert "btnAdminDropdown" in js

def test_match_select_dropdown_clean_formatting():
    with open("static/app.js", "r", encoding="utf-8") as f:
        js = f.read()

    assert "populateMatchSelect" in js
    # Non deve comparire match_code o ID tecnico nelle opzioni della tendina
    func_body = js[js.find("function populateMatchSelect()"):js.find("function resetMatchDisplay()")]
    assert "${m.match_code}" not in func_body
    assert "opt.textContent = `${home} - ${away}`;" in func_body

def test_admin_matches_full_page_view():
    with open("static/index.html", "r", encoding="utf-8") as f:
        html = f.read()

    assert 'id="view-dashboard"' in html
    assert 'id="view-admin-matches"' in html
    assert 'id="btn-back-to-dashboard"' in html
    assert 'id="admin-matches-full-tbody"' in html

    with open("static/app.js", "r", encoding="utf-8") as f:
        js = f.read()

    assert "switchView" in js
    assert "openMatchInDashboard" in js

def test_admin_matches_page_validation_buttons():
    with open("static/index.html", "r", encoding="utf-8") as f:
        html = f.read()
    with open("static/app.js", "r", encoding="utf-8") as f:
        js = f.read()

    assert "btn-admin-revalidate-all" in html
    assert "revalidateMatchFromAdmin" in js
    assert "handleAdminRevalidateAllMatches" in js
    assert "30" in js  # Threshold alert for > 30 matches

def test_dashboard_anomaly_filter_robustness():
    with open("static/app.js", "r", encoding="utf-8") as f:
        js = f.read()

    # Must check boolean false/0 and error_note without relying strictly on === 1
    func_body = js[js.find("function renderEventsTable()"):js.find("function showEventOnCourt")]
    assert "ev.is_valid === 1" not in func_body
    assert "ev.is_valid === 0 || ev.is_valid === false" in func_body
    assert "filterErrorsOnly.checked" in js


