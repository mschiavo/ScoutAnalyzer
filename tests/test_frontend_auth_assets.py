import os
import pytest

def test_frontend_auth_elements_exist():
    with open("static/index.html", "r", encoding="utf-8") as f:
        html = f.read()

    assert "login-overlay" in html
    assert "login-form" in html
    assert "user-badge" in html
    assert "btn-logout" in html
    assert "admin-users-modal" in html
    assert "admin-rules-modal" in html
    assert "admin-logins-modal" in html

def test_frontend_auth_css_classes():
    with open("static/style.css", "r", encoding="utf-8") as f:
        css = f.read()

    assert ".login-overlay" in css
    assert ".user-badge" in css

def test_frontend_auth_js_logic():
    with open("static/app.js", "r", encoding="utf-8") as f:
        js = f.read()

    assert "handleLogin" in js
    assert "handleLogout" in js
    assert "checkAuth" in js
