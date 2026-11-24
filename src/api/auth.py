import os
import sqlite3
import jwt
import bcrypt
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, Optional, List
from fastapi import Depends, HTTPException, status, Request
from fastapi.security import OAuth2PasswordBearer
from pydantic import BaseModel
from src.db import get_db_connection

JWT_SECRET = os.environ.get("JWT_SECRET", "scoutanalyzer3000-jwt-secret-volleyball-key-2026")
if os.environ.get("SCOUT_NAS_MODE") == "1" and len(os.environ.get("JWT_SECRET", "")) < 32:
    raise RuntimeError("Imposta JWT_SECRET con almeno 32 caratteri per il deploy NAS.")
JWT_ALGORITHM = "HS256"

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login", auto_error=False)

class User(BaseModel):
    id: int
    username: str
    email: Optional[str] = None
    role: str
    team_ids: List[int] = []

def hash_password(plain_password: str) -> str:
    pwd_bytes = plain_password.encode("utf-8")
    salt = bcrypt.gensalt()
    return bcrypt.hashpw(pwd_bytes, salt).decode("utf-8")

def verify_password(plain_password: str, hashed_password: str) -> bool:
    try:
        return bcrypt.checkpw(plain_password.encode("utf-8"), hashed_password.encode("utf-8"))
    except Exception:
        return False

def create_access_token(user_id: int, username: str, role: str, is_local: bool = False, expires_minutes: Optional[int] = None) -> str:
    now = datetime.now(timezone.utc)
    if role == "ADMIN" or is_local:
        # Perenne per admin / locale (30 giorni rinnovabili)
        expire = now + timedelta(days=30)
    else:
        # Sliding session di inattività (default 60 minuti)
        duration = expires_minutes if expires_minutes is not None else 60
        expire = now + timedelta(minutes=duration)

    payload = {
        "sub": str(user_id),
        "username": username,
        "role": role,
        "iat": now,
        "exp": expire
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)

def verify_access_token(token: str) -> Dict[str, Any]:
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        return payload
    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Sessione scaduta. Effettua nuovamente il login."
        )
    except jwt.PyJWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token di autenticazione non valido."
        )

def get_current_user(request: Request, token: Optional[str] = Depends(oauth2_scheme)) -> User:
    # Prova header Authorization, altrimenti cookie scout_token o query token
    auth_token = token
    if not auth_token:
        auth_token = request.cookies.get("scout_token")
    if not auth_token:
        # Supporta header Authorization grezzo
        auth_header = request.headers.get("Authorization")
        if auth_header and auth_header.startswith("Bearer "):
            auth_token = auth_header[7:].strip()

    if not auth_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Autenticazione richiesta. Effettua il login per accedere."
        )

    payload = verify_access_token(auth_token)
    user_id = int(payload.get("sub", 0))

    conn = get_db_connection()
    c = conn.cursor()
    c.execute("SELECT id, username, email, role, is_active FROM users WHERE id = ?", (user_id,))
    row = c.fetchone()
    if not row:
        conn.close()
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Utente disabilitato o inesistente."
        )

    is_act = row[4] if isinstance(row, (tuple, list)) else row["is_active"]
    if not is_act:
        conn.close()
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Utente disabilitato o inesistente."
        )

    # Carica team_ids associati
    c.execute("SELECT team_id FROM user_teams WHERE user_id = ?", (user_id,))
    team_ids = [r[0] if isinstance(r, (tuple, list)) else r["team_id"] for r in c.fetchall()]
    conn.close()

    u_id = row[0] if isinstance(row, (tuple, list)) else row["id"]
    u_name = row[1] if isinstance(row, (tuple, list)) else row["username"]
    u_email = row[2] if isinstance(row, (tuple, list)) else row["email"]
    u_role = row[3] if isinstance(row, (tuple, list)) else row["role"]

    return User(
        id=u_id,
        username=u_name,
        email=u_email,
        role=u_role,
        team_ids=team_ids
    )

def require_admin(current_user: User = Depends(get_current_user)) -> User:
    if current_user.role != "ADMIN":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Operazione riservata esclusivamente agli amministratori."
        )
    return current_user
