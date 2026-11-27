import os
import json
import logging
import tempfile
from contextlib import closing
from pathlib import Path
import sqlite3
from typing import Dict, Any, List, Optional
from fastapi import APIRouter, HTTPException, Depends, Body, Query, status
from pydantic import BaseModel, Field, field_validator

from src.api.auth import User, require_admin, hash_password
from src.state_engine import DEFAULT_CONFIG_PATH, MatchStateEngine, get_max_substitutions

admin_router = APIRouter(
    prefix="/api/admin",
    tags=["Admin Management"],
    dependencies=[Depends(require_admin)]
)

SPECS_PATH = "config/datavalley_specs.json"
logger = logging.getLogger(__name__)
from src.db import get_db_connection, get_sqlite_path as get_db_path, scout_filename_metadata

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


class SubstitutionSettings(BaseModel):
    max_substitutions_per_set: int = Field(ge=0, strict=True)


class TeamRosterSettings(BaseModel):
    code: str = Field(pattern=r"^[A-Za-z0-9_-]{1,40}$")
    name: str = Field(min_length=1, max_length=200)
    roster_code: Optional[str] = Field(default=None, pattern=r"^[0-9]{1,20}$")

    @field_validator("name", mode="before")
    @classmethod
    def trim_name(cls, value):
        return value.strip() if isinstance(value, str) else value

# --- 1. SQUADRE PER ASSEGNAZIONE ---
@admin_router.get("/teams")
def list_teams_for_admin():
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("SELECT id, code, name, homestadium, roster_code, roster_inactive FROM teams ORDER BY name ASC")
    teams = [dict(r) for r in c.fetchall()]
    conn.close()
    return teams


@admin_router.post("/teams")
def create_team(payload: TeamRosterSettings):
    with closing(get_db_connection()) as conn:
        cursor = conn.cursor()
        _check_roster_code(cursor, payload.roster_code)
        cursor.execute("INSERT OR IGNORE INTO teams (code, name, roster_code) VALUES (?, ?, ?)",
                       (payload.code.upper(), payload.name.strip(), payload.roster_code))
        if cursor.rowcount == 0:
            raise HTTPException(status_code=409, detail="Codice squadra già censito.")
        conn.commit()
    return {"status": "SUCCESS"}


@admin_router.put("/teams/{team_id}")
def update_team(team_id: int, payload: TeamRosterSettings):
    with closing(get_db_connection()) as conn:
        cursor = conn.cursor()
        _check_roster_code(cursor, payload.roster_code, team_id)
        cursor.execute("UPDATE teams SET name = ?, roster_code = ? WHERE id = ? AND code = ?",
                       (payload.name.strip(), payload.roster_code, team_id, payload.code))
        if cursor.rowcount == 0:
            raise HTTPException(status_code=404, detail="Squadra non trovata.")
        conn.commit()
    return {"status": "SUCCESS"}


def _check_roster_code(cursor, roster_code, team_id=0):
    if roster_code:
        cursor.execute("SELECT name FROM teams WHERE roster_code = ? AND id != ?", (roster_code, team_id))
        row = cursor.fetchone()
        if row:
            raise HTTPException(status_code=409, detail=f"Codice roster già associato a {row[0]}.")


@admin_router.post("/teams/import-b1f-b")
def import_team_catalog():
    from database.seed_real_data import B1F_B_2026_2027_TEAMS

    added = linked = 0
    conflicts = []
    with closing(get_db_connection()) as conn:
        cursor = conn.cursor()
        cursor.execute("INSERT OR IGNORE INTO championships (code, name) VALUES (?, ?)",
                       ("2026-2027", "Campionato Serie B1 Femminile 2026/2027"))
        cursor.execute("SELECT id FROM championships WHERE code = ?", ("2026-2027",))
        championship_id = cursor.fetchone()[0]
        cursor.execute("SELECT id FROM groups WHERE championship_id = ? AND code = ? ORDER BY id", (championship_id, "B"))
        group = cursor.fetchone()
        if group is None:
            cursor.execute("INSERT INTO groups (championship_id, code, name) VALUES (?, ?, ?)",
                           (championship_id, "B", "Girone B Serie B1 Femminile"))
            group_id = cursor.lastrowid
        else:
            group_id = group[0]
        for code, name, stadium, roster_code in B1F_B_2026_2027_TEAMS:
            cursor.execute("SELECT id, roster_code FROM teams WHERE code = ?", (code,))
            existing = cursor.fetchone()
            if existing and existing[1]:
                if existing[1] != roster_code:
                    conflicts.append(f"{code}: codice roster esistente {existing[1]}, catalogo {roster_code}.")
                continue
            try:
                _check_roster_code(cursor, roster_code, existing[0] if existing else 0)
            except HTTPException as error:
                conflicts.append(f"{code}: {error.detail}")
                continue
            if existing:
                cursor.execute("UPDATE teams SET roster_code = ?, group_id = COALESCE(group_id, ?) WHERE id = ?",
                               (roster_code, group_id, existing[0]))
                linked += 1
            else:
                cursor.execute("INSERT INTO teams (code, name, homestadium, group_id, roster_code) VALUES (?, ?, ?, ?, ?)",
                               (code, name, stadium, group_id, roster_code))
                added += 1
        conn.commit()
    return {"added": added, "linked": linked, "conflicts": conflicts}


@admin_router.post("/teams/import-a3f-b")
def import_a3f_b_team_catalog():
    from database.seed_real_data import A3F_B_2026_2027_TEAMS

    added = linked = 0
    conflicts = []
    with closing(get_db_connection()) as conn:
        cursor = conn.cursor()
        championship_code = "2026-2027-A3F"
        cursor.execute("INSERT OR IGNORE INTO championships (code, name) VALUES (?, ?)",
                       (championship_code, "Campionato Serie A3 Femminile 2026/2027"))
        cursor.execute("SELECT id FROM championships WHERE code = ?", (championship_code,))
        championship_id = cursor.fetchone()[0]
        cursor.execute("SELECT id FROM groups WHERE championship_id = ? AND code = ? ORDER BY id",
                       (championship_id, "B"))
        group = cursor.fetchone()
        if group is None:
            cursor.execute("INSERT INTO groups (championship_id, code, name) VALUES (?, ?, ?)",
                           (championship_id, "B", "Girone B Serie A3 Femminile"))
            group_id = cursor.lastrowid
        else:
            group_id = group[0]

        for code, name, roster_code in A3F_B_2026_2027_TEAMS:
            cursor.execute("SELECT id, roster_code FROM teams WHERE code = ?", (code,))
            existing = cursor.fetchone()
            if existing and existing[1] and existing[1] != roster_code:
                conflicts.append(f"{name}: codice roster esistente {existing[1]}, catalogo {roster_code}.")
                continue
            try:
                _check_roster_code(cursor, roster_code, existing[0] if existing else 0)
            except HTTPException as error:
                conflicts.append(f"{name}: {error.detail}")
                continue
            if existing:
                cursor.execute("UPDATE teams SET name = ?, roster_code = ?, group_id = COALESCE(group_id, ?) WHERE id = ?",
                               (name, roster_code, group_id, existing[0]))
                linked += 1
            else:
                cursor.execute("""
                    INSERT INTO teams (code, name, group_id, roster_code)
                    VALUES (?, ?, ?, ?)
                """, (code, name, group_id, roster_code))
                added += 1
        conn.commit()
    return {"added": added, "linked": linked, "conflicts": conflicts}

@admin_router.get("/rosters")
def list_rosters():
    with closing(get_db_connection()) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT t.id, t.code, t.name, t.roster_code,
                   COUNT(tp.id) AS active_players
            FROM teams t
            LEFT JOIN team_players tp ON tp.team_id = t.id AND tp.valid_to IS NULL
            WHERE t.roster_inactive = 0
            GROUP BY t.id, t.code, t.name, t.roster_code
            ORDER BY t.name, t.code
        """)
        return [dict(row) for row in cursor.fetchall()]


@admin_router.get("/rosters/{team_id}")
def roster_detail(team_id: int):
    with closing(get_db_connection()) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT id FROM teams WHERE id = ? AND roster_inactive = 0", (team_id,))
        if cursor.fetchone() is None:
            raise HTTPException(status_code=404, detail="Squadra non trovata")
        cursor.execute("""
            SELECT p.first_name, p.last_name, r.name AS role, tp.shirt_number,
                   tp.valid_from, tp.valid_to
            FROM team_players tp
            JOIN players p ON p.id = tp.player_id
            LEFT JOIN roles r ON r.id = p.role_id
            WHERE tp.team_id = ?
            ORDER BY CASE WHEN tp.valid_to IS NULL THEN 0 ELSE 1 END,
                     tp.shirt_number, p.last_name, p.first_name
        """, (team_id,))
        return [dict(row) for row in cursor.fetchall()]


@admin_router.delete("/rosters/{team_id}")
def disable_roster(team_id: int):
    with closing(get_db_connection()) as conn:
        cursor = conn.cursor()
        cursor.execute("UPDATE teams SET roster_inactive = 1 WHERE id = ?", (team_id,))
        if cursor.rowcount == 0:
            raise HTTPException(status_code=404, detail="Squadra non trovata")
        conn.commit()
    return {"status": "SUCCESS"}


def _check_inactive_rosters(cursor, match_id=None, reactivate=False):
    sql = """
        SELECT DISTINCT t.id, t.name FROM teams t JOIN matches m
            ON t.id IN (m.home_team_id, m.away_team_id)
        WHERE t.roster_inactive = 1
    """
    cursor.execute(sql + " AND m.id = ?" if match_id is not None else sql,
                   (match_id,) if match_id is not None else ())
    teams = [dict(row) for row in cursor.fetchall()]
    if teams and not reactivate:
        raise HTTPException(status_code=409, detail={"code": "inactive_rosters", "teams": teams})
    for team in teams:
        cursor.execute("UPDATE teams SET roster_inactive = 0 WHERE id = ?", (team["id"],))


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
        try:
            from src.storage_manager import StorageManager
            StorageManager().backup_database_to_storage()
        except Exception:
            pass
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
    try:
        from src.storage_manager import StorageManager
        StorageManager().backup_database_to_storage()
    except Exception:
        pass

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
    try:
        from src.storage_manager import StorageManager
        StorageManager().backup_database_to_storage()
    except Exception:
        pass
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
@admin_router.get("/rules/substitutions")
def get_substitution_settings():
    config = json.loads(Path(DEFAULT_CONFIG_PATH).read_text(encoding="utf-8"))
    return {"max_substitutions_per_set": get_max_substitutions(config)}


@admin_router.put("/rules/substitutions")
def update_substitution_settings(settings: SubstitutionSettings):
    path = Path(DEFAULT_CONFIG_PATH)
    config = json.loads(path.read_text(encoding="utf-8"))
    config.setdefault("validation", {})["max_substitutions_per_set"] = settings.max_substitutions_per_set
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent, delete=False) as stream:
            temporary = Path(stream.name)
            json.dump(config, stream, indent=2, ensure_ascii=False)
            stream.write("\n")
        temporary.replace(path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
    return settings


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
def revalidate_all_matches(reactivate_rosters: bool = False):
    with closing(get_db_connection()) as conn:
        _check_inactive_rosters(conn.cursor(), reactivate=reactivate_rosters)
        conn.commit()
    try:
        conn = get_db_connection()
        c = conn.cursor()
        c.execute("SELECT id, match_code FROM matches ORDER BY id ASC")
        matches = c.fetchall()
        conn.close()

        results = []
        for m in matches:
            try:
                engine = MatchStateEngine(match_id=m["id"])
                s_res = engine.process_match()
                results.append({
                    "match_id": m["id"],
                    "match_code": m["match_code"],
                    "status": "SUCCESS",
                    "issues_count": len(engine.issues)
                })
            except Exception as e:
                logger.error(f"Errore durante rivalutazione match {m['id']}: {e}")
                results.append({
                    "match_id": m["id"],
                    "match_code": m["match_code"],
                    "status": "ERROR",
                    "error": str(e),
                    "issues_count": 0
                })

        return {"status": "SUCCESS", "revalidated_matches": results}
    except Exception as e:
        logger.error(f"Errore globale rivalutazione gare: {e}")
        raise HTTPException(status_code=500, detail=f"Errore durante la rivalutazione delle gare: {str(e)}")

@admin_router.post("/matches/{match_id}/revalidate")
def revalidate_single_match(match_id: int, reactivate_rosters: bool = False,
                            current_user: User = Depends(require_admin)):
    with closing(get_db_connection()) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT id FROM matches WHERE id = ?", (match_id,))
        if not cursor.fetchone():
            raise HTTPException(status_code=404, detail=f"Partita {match_id} non trovata.")
        _check_inactive_rosters(cursor, match_id, reactivate_rosters)
        conn.commit()

    try:
        engine = MatchStateEngine(match_id=match_id)
        s_res = engine.process_match()
    except Exception as e:
        logger.error(f"Errore rivalutazione match {match_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Errore durante la rivalutazione della gara: {str(e)}")

    conn = get_db_connection()
    c = conn.cursor()
    c.execute("""
        SELECT 
            m.id, COALESCE(m.source_match_code, m.match_code) AS match_code, m.scheduled_date, m.home_team_id, m.away_team_id,
            m.home_sets_won, m.away_sets_won, m.final_score, m.set_scores,
            m.sets_count, m.events_count, m.logs_count, m.scout_author,
            ht.code as home_code, ht.name as home_name,
            at.code as away_code, at.name as away_name
        FROM matches m
        LEFT JOIN teams ht ON m.home_team_id = ht.id
        LEFT JOIN teams at ON m.away_team_id = at.id
        WHERE m.id = ?
    """, (match_id,))
    m_row = c.fetchone()
    conn.close()
    if not m_row:
        raise HTTPException(status_code=404, detail=f"Partita {match_id} non trovata.")

    return {
        "status": "SUCCESS",
        "match_id": match_id,
        "issues_count": len(engine.issues),
        "match": dict(m_row)
    }

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
        sm.backup_database_to_storage()
    except Exception:
        pass

    return {"status": "SUCCESS", "message": "Tutte le partite sono state eliminate con successo."}


@admin_router.post("/matches/{match_id}/confirm-roster-variations")
def confirm_roster_variations(match_id: int, file_hash: str):
    from src.db import refresh_match_summary_metrics

    with closing(get_db_connection()) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT file_hash FROM matches WHERE id = ?", (match_id,))
        match = cursor.fetchone()
        if match is None:
            raise HTTPException(status_code=404, detail="Gara non trovata.")
        if match["file_hash"] != file_hash:
            raise HTTPException(status_code=409, detail="La rilevazione è cambiata. Ricarica la gara e verifica le variazioni correnti.")
        cursor.execute("""
            UPDATE validation_logs SET parsed_status = 'OK'
            WHERE match_id = ? AND validation_source = 'ROSTER_VARIATION' AND parsed_status = 'WARNING'
              AND EXISTS (SELECT 1 FROM matches WHERE id = ? AND file_hash = ?)
        """, (match_id, match_id, file_hash))
        confirmed = cursor.rowcount
        refresh_match_summary_metrics(cursor, match_id)
        conn.commit()
    return {"confirmed": confirmed}
