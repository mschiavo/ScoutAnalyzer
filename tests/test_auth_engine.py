import pytest
from datetime import datetime, timezone, timedelta
from fastapi import HTTPException
from src.api.auth import (
    hash_password,
    verify_password,
    create_access_token,
    verify_access_token
)

def test_password_hashing():
    pw = "SuperSecret123!"
    h = hash_password(pw)
    assert h != pw
    assert verify_password(pw, h) is True
    assert verify_password("WrongPassword", h) is False

def test_jwt_token_generation_and_verification():
    # Admin / local token -> 30 days
    token_admin = create_access_token(user_id=1, username="admin", role="ADMIN", is_local=True)
    payload_admin = verify_access_token(token_admin)
    assert payload_admin["sub"] == "1"
    assert payload_admin["username"] == "admin"
    assert payload_admin["role"] == "ADMIN"
    
    # Scout token -> 60 minutes
    token_scout = create_access_token(user_id=2, username="scout_user", role="SCOUT", is_local=False)
    payload_scout = verify_access_token(token_scout)
    assert payload_scout["sub"] == "2"
    assert payload_scout["username"] == "scout_user"
    assert payload_scout["role"] == "SCOUT"

def test_invalid_jwt_token():
    with pytest.raises(HTTPException) as exc_info:
        verify_access_token("invalid.token.here")
    assert exc_info.value.status_code == 401

def test_require_admin():
    from src.api.auth import User, require_admin
    admin_user = User(id=1, username="admin", role="ADMIN")
    assert require_admin(admin_user) == admin_user

    scout_user = User(id=2, username="scout", role="SCOUT")
    with pytest.raises(HTTPException) as exc_info:
        require_admin(scout_user)
    assert exc_info.value.status_code == 403
