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
