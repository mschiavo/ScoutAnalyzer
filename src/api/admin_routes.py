import os
import json
import sqlite3
from typing import Dict, Any, List, Optional
from fastapi import APIRouter, HTTPException, Depends, Body, Query, status
from pydantic import BaseModel

from src.api.auth import User, require_admin, hash_password
from src.state_engine import MatchStateEngine

admin_router = APIRouter(
    prefix="/api/admin",
    tags=["Admin Management"],
    dependencies=[Depends(require_admin)]
)

DEFAULT_CONFIG_PATH = "config/config.json"
SPECS_PATH = "config/datavalley_specs.json"

def get_db_path() -> str:
    env_path = os.environ.get("SCOUT_DB_PATH")
    if env_path:
        return env_path
    if os.path.exists(DEFAULT_CONFIG_PATH):
        try:
            with open(DEFAULT_CONFIG_PATH, "r", encoding="utf-8") as f:
                cfg = json.load(f)
                p = cfg.get("db_path", "scoutanalyzer.db")
                if os.path.exists(p):
                    return p
        except Exception:
            pass
    root_candidate = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "scoutanalyzer.db")
    if os.path.exists(root_candidate):
        return root_candidate
    return "scoutanalyzer.db"

def get_db_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(get_db_path())
    conn.execute("PRAGMA foreign_keys = ON;")
    conn.row_factory = sqlite3.Row
    return conn

# --- PYDANTIC SCHEMAS ---
class CreateUserRequest(BaseModel):
    username: str
    password: str
    email: Optional[str] = None
    role: str = "SCOUT"
    team_ids: List[int] = []

class UpdateUserRequest(BaseModel):
    email: Optional[str] = None
    role: Optional[str] = None
    is_active: Optional[int] = None
    password: Optional[str] = None
    team_ids: Optional[List[int]] = None

class TerminalRuleSchema(BaseModel):
    description: str
    terminal_skill: str
    terminal_eval: str
    followup_skills: List[str]
    followup_evals: List[str]
    must_be_opponent: bool = True

# --- 1. SQUADRE PER ASSEGNAZIONE ---
@admin_router.get("/teams")
def list_teams_for_admin():
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("SELECT id, code, name, homestadium FROM teams ORDER BY name ASC")
    teams = [dict(r) for r in c.fetchall()]
    conn.close()
    return teams

# --- 2. GESTIONE UTENTI CRUD ---
@admin_router.get("/users")
def list_users():
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("""
        SELECT u.id, u.username, u.email, u.role, u.is_active, u.created_at
        FROM users u
        ORDER BY u.id ASC
    """)
    users = []
    for r in c.fetchall():
        u = dict(r)
        c.execute("""
            SELECT t.id, t.code, t.name
            FROM user_teams ut
            JOIN teams t ON ut.team_id = t.id
            WHERE ut.user_id = ?
        """, (u["id"],))
        teams = [dict(tr) for tr in c.fetchall()]
        u["team_ids"] = [t["id"] for t in teams]
        u["teams"] = teams
        users.append(u)
    conn.close()
    return users

@admin_router.post("/users", status_code=status.HTTP_201_CREATED)
def create_user(payload: CreateUserRequest):
    conn = get_db_connection()
    c = conn.cursor()

    c.execute("SELECT id FROM users WHERE username = ?", (payload.username,))
    if c.fetchone():
        conn.close()
        raise HTTPException(status_code=400, detail="Username già in uso.")

    pwd_hash = hash_password(payload.password)
    try:
        c.execute("""
            INSERT INTO users (username, password_hash, email, role, is_active)
            VALUES (?, ?, ?, ?, 1)
        """, (payload.username, pwd_hash, payload.email, payload.role))
        user_id = c.lastrowid

        if payload.team_ids:
            records = [(user_id, t_id) for t_id in payload.team_ids]
            c.executemany("INSERT OR IGNORE INTO user_teams (user_id, team_id) VALUES (?, ?)", records)

        conn.commit()
    except Exception as e:
        conn.rollback()
        conn.close()
        raise HTTPException(status_code=500, detail=f"Errore creazione utente: {str(e)}")

    conn.close()
    return {
        "id": user_id,
        "username": payload.username,
        "email": payload.email,
        "role": payload.role,
        "team_ids": payload.team_ids
    }

@admin_router.put("/users/{user_id}")
def update_user(user_id: int, payload: UpdateUserRequest):
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("SELECT id, username, email, role, is_active FROM users WHERE id = ?", (user_id,))
    row = c.fetchone()
    if not row:
        conn.close()
        raise HTTPException(status_code=404, detail="Utente non trovato.")

    updates = []
    params = []

    if payload.email is not None:
        updates.append("email = ?")
        params.append(payload.email)
    if payload.role is not None:
        updates.append("role = ?")
        params.append(payload.role)
    if payload.is_active is not None:
        updates.append("is_active = ?")
        params.append(payload.is_active)
    if payload.password:
        updates.append("password_hash = ?")
        params.append(hash_password(payload.password))

    if updates:
        params.append(user_id)
        c.execute(f"UPDATE users SET {', '.join(updates)}, updated_at = CURRENT_TIMESTAMP WHERE id = ?", params)

    if payload.team_ids is not None:
        c.execute("DELETE FROM user_teams WHERE user_id = ?", (user_id,))
        if payload.team_ids:
            records = [(user_id, t_id) for t_id in payload.team_ids]
            c.executemany("INSERT OR IGNORE INTO user_teams (user_id, team_id) VALUES (?, ?)", records)

    conn.commit()

    # Ricarica
    c.execute("SELECT id, username, email, role, is_active FROM users WHERE id = ?", (user_id,))
    updated_user = dict(c.fetchone())
    c.execute("SELECT team_id FROM user_teams WHERE user_id = ?", (user_id,))
    updated_user["team_ids"] = [r["team_id"] for r in c.fetchall()]

    conn.close()
    return updated_user

@admin_router.delete("/users/{user_id}")
def delete_user(user_id: int, current_user: User = Depends(require_admin)):
    if user_id == current_user.id:
        raise HTTPException(status_code=400, detail="Non puoi eliminare la tua stessa utenza attiva.")

    conn = get_db_connection()
    c = conn.cursor()

    # Verifica che non sia l'ultimo admin
    c.execute("SELECT role FROM users WHERE id = ?", (user_id,))
    target = c.fetchone()
    if not target:
        conn.close()
        raise HTTPException(status_code=404, detail="Utente non trovato.")

    if target["role"] == "ADMIN":
        c.execute("SELECT COUNT(*) FROM users WHERE role = 'ADMIN'")
        admin_count = c.fetchone()[0]
        if admin_count <= 1:
            conn.close()
            raise HTTPException(status_code=400, detail="Impossibile eliminare l'unico amministratore del sistema.")

    c.execute("DELETE FROM users WHERE id = ?", (user_id,))
    conn.commit()
    conn.close()
    return {"status": "SUCCESS", "deleted_user_id": user_id}

# --- 3. AUDIT ACCESSI IP (user_logins) ---
@admin_router.get("/logins")
def list_logins(limit: int = Query(100, ge=1, le=500)):
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("""
        SELECT id, user_id, username, ip_address, user_agent, login_status, logged_at
        FROM user_logins
        ORDER BY id DESC
        LIMIT ?
    """, (limit,))
    rows = [dict(r) for r in c.fetchall()]
    conn.close()
    return rows

# --- 4. CONFIGURATORE REGOLE TOCCHI CORRELATI (datavalley_specs.json) ---
def _load_specs() -> Dict[str, Any]:
    if os.path.exists(SPECS_PATH):
        try:
            with open(SPECS_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {"permitted_terminal_followups": []}

def _save_specs(specs: Dict[str, Any]):
    with open(SPECS_PATH, "w", encoding="utf-8") as f:
        json.dump(specs, f, indent=2, ensure_ascii=False)

@admin_router.get("/rules/terminal")
def get_terminal_rules():
    specs = _load_specs()
    return specs.get("permitted_terminal_followups", [])

@admin_router.post("/rules/terminal")
def add_terminal_rule(rule: TerminalRuleSchema):
    specs = _load_specs()
    rules = specs.get("permitted_terminal_followups", [])
    rules.append(rule.model_dump())
    specs["permitted_terminal_followups"] = rules
    _save_specs(specs)
    return rules

@admin_router.put("/rules/terminal/{index}")
def update_terminal_rule(index: int, rule: TerminalRuleSchema):
    specs = _load_specs()
    rules = specs.get("permitted_terminal_followups", [])
    if index < 0 or index >= len(rules):
        raise HTTPException(status_code=404, detail="Indice regola non valido.")
    rules[index] = rule.model_dump()
    specs["permitted_terminal_followups"] = rules
    _save_specs(specs)
    return rules

@admin_router.delete("/rules/terminal/{index}")
def delete_terminal_rule(index: int):
    specs = _load_specs()
    rules = specs.get("permitted_terminal_followups", [])
    if index < 0 or index >= len(rules):
        raise HTTPException(status_code=404, detail="Indice regola non valido.")
    rules.pop(index)
    specs["permitted_terminal_followups"] = rules
    _save_specs(specs)
    return rules

@admin_router.post("/rules/revalidate")
def revalidate_all_matches():
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("SELECT id, match_code FROM matches ORDER BY id ASC")
    matches = c.fetchall()
    conn.close()

    results = []
    for m in matches:
        engine = MatchStateEngine(match_id=m["id"])
        s_res = engine.process_match()
        results.append({
            "match_id": m["id"],
            "match_code": m["match_code"],
            "issues_count": len(engine.issues)
        })

    return {"status": "SUCCESS", "revalidated_matches": results}

@admin_router.delete("/matches/clear")
def clear_all_matches():
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("SELECT storage_path FROM matches WHERE storage_path IS NOT NULL AND storage_path != ''")
    paths = [r[0] for r in c.fetchall()]

    c.execute("DELETE FROM actions;")
    c.execute("DELETE FROM rotations;")
    c.execute("DELETE FROM events;")
    c.execute("DELETE FROM validation_logs;")
    c.execute("DELETE FROM match_sets;")
    c.execute("DELETE FROM matches;")
    c.execute("DELETE FROM sqlite_sequence WHERE name IN ('matches', 'match_sets', 'events', 'rotations', 'actions', 'validation_logs');")
    conn.commit()
    conn.close()

    try:
        from src.storage_manager import StorageManager
        sm = StorageManager()
        for p in paths:
            sm.delete_dvw(p)
    except Exception:
        pass

    return {"status": "SUCCESS", "message": "Tutte le partite sono state eliminate con successo."}
