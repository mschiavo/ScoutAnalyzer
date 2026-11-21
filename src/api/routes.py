import os
import json
import sqlite3
import re
from typing import Dict, Any, List, Optional
from fastapi import APIRouter, HTTPException, Query, Body, File, UploadFile, Depends, Request, Form
from pydantic import BaseModel

from src.dvw_parser import DVWParser
from src.ingestion_manager import IngestionManager
from src.state_engine import MatchStateEngine
from src.roster_manager import RosterManager
from src.api.auth import User, get_current_user, require_admin, verify_password, create_access_token

router = APIRouter(prefix="/api", tags=["ScoutAnalyzer API"])

from src.db import get_db_connection, get_sqlite_path as get_db_path

class LoginRequest(BaseModel):
    username: str
    password: str

class AuditFileRequest(BaseModel):
    file_path: str
    campionato: Optional[str] = None
    categoria: Optional[str] = None
    girone: Optional[str] = None
    giornata: Optional[str] = None

class RosterSyncRequest(BaseModel):
    team_code: Optional[str] = None

def verify_match_access(match_id: int, current_user: User = Depends(get_current_user)) -> User:
    if current_user.role == "ADMIN":
        return current_user

    conn = get_db_connection()
    c = conn.cursor()
    c.execute("SELECT home_team_id, away_team_id FROM matches WHERE id = ?", (match_id,))
    m_row = c.fetchone()
    conn.close()

    if not m_row:
        raise HTTPException(status_code=404, detail="Partita non trovata.")

    h_id = m_row["home_team_id"]
    a_id = m_row["away_team_id"]
    if h_id not in current_user.team_ids and a_id not in current_user.team_ids:
        raise HTTPException(
            status_code=403,
            detail="Accesso negato: non sei autorizzato a consultare i dati di questa partita."
        )
    return current_user

@router.post("/auth/login")
def login(payload: LoginRequest, request: Request):
    ip_addr = request.headers.get("X-Forwarded-For") or (request.client.host if request.client else "127.0.0.1")
    user_agent = request.headers.get("User-Agent", "")

    conn = get_db_connection()
    c = conn.cursor()
    c.execute("SELECT id, username, password_hash, email, role, is_active FROM users WHERE username = ?", (payload.username,))
    row = c.fetchone()

    if not row or not verify_password(payload.password, row["password_hash"]):
        c.execute("""
            INSERT INTO user_logins (user_id, username, ip_address, user_agent, login_status)
            VALUES (?, ?, ?, ?, 'FAILED')
        """, (row["id"] if row else None, payload.username, ip_addr, user_agent))
        conn.commit()
        conn.close()
        raise HTTPException(status_code=401, detail="Nome utente o password non corretti.")

    user_id = row["id"]
    if row["is_active"] != 1:
        c.execute("""
            INSERT INTO user_logins (user_id, username, ip_address, user_agent, login_status)
            VALUES (?, ?, ?, ?, 'FAILED')
        """, (user_id, payload.username, ip_addr, user_agent))
        conn.commit()
        conn.close()
        raise HTTPException(status_code=401, detail="Utenza disabilitata. Contatta l'amministratore.")

    # Accesso riuscito
    c.execute("""
        INSERT INTO user_logins (user_id, username, ip_address, user_agent, login_status)
        VALUES (?, ?, ?, ?, 'SUCCESS')
    """, (user_id, payload.username, ip_addr, user_agent))

    # Carica squadre autorizzate
    c.execute("SELECT team_id FROM user_teams WHERE user_id = ?", (user_id,))
    team_ids = [r["team_id"] for r in c.fetchall()]

    conn.commit()
    conn.close()

    is_local = (request.client.host in ("127.0.0.1", "localhost", "::1")) if request.client else False
    token = create_access_token(user_id=user_id, username=row["username"], role=row["role"], is_local=is_local)

    return {
        "access_token": token,
        "token_type": "bearer",
        "user": {
            "id": user_id,
            "username": row["username"],
            "role": row["role"],
            "email": row["email"],
            "team_ids": team_ids
        }
    }

@router.get("/auth/me")
def get_me(current_user: User = Depends(get_current_user)):
    return current_user.model_dump()

@router.get("/matches")
def list_matches(current_user: User = Depends(get_current_user)):
    conn = get_db_connection()
    c = conn.cursor()
    base_cols = """
        m.id, m.match_code, m.scheduled_date, m.home_team_id, m.away_team_id,
        m.home_sets_won, m.away_sets_won, m.final_score, m.set_scores,
        m.sets_count, m.events_count, m.logs_count, m.scout_author,
        ht.code as home_code, ht.name as home_name,
        at.code as away_code, at.name as away_name
    """
    if current_user.role == "ADMIN":
        c.execute(f"""
            SELECT {base_cols}
            FROM matches m
            LEFT JOIN teams ht ON m.home_team_id = ht.id
            LEFT JOIN teams at ON m.away_team_id = at.id
            ORDER BY m.id DESC
        """)
    else:
        if not current_user.team_ids:
            conn.close()
            return []
        placeholders = ",".join("?" for _ in current_user.team_ids)
        query = f"""
            SELECT {base_cols}
            FROM matches m
            LEFT JOIN teams ht ON m.home_team_id = ht.id
            LEFT JOIN teams at ON m.away_team_id = at.id
            WHERE m.home_team_id IN ({placeholders}) OR m.away_team_id IN ({placeholders})
            ORDER BY m.id DESC
        """
        c.execute(query, current_user.team_ids + current_user.team_ids)

    rows = []
    for r in c.fetchall():
        m = dict(r)
        m["final_score"] = m.get("final_score") or "0 - 0"
        m["set_scores"] = m.get("set_scores") or "N.D."
        m["scout_author"] = m.get("scout_author") or "N.D."
        rows.append(m)

    conn.close()
    return rows

@router.get("/matches/{match_id}")
def get_match_detail(match_id: int, current_user: User = Depends(verify_match_access)):
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("""
        SELECT 
            m.id, m.match_code, m.scheduled_date,
            ht.code as home_code, ht.name as home_name,
            at.code as away_code, at.name as away_name
        FROM matches m
        LEFT JOIN teams ht ON m.home_team_id = ht.id
        LEFT JOIN teams at ON m.away_team_id = at.id
        WHERE m.id = ?
    """, (match_id,))
    match_row = c.fetchone()
    if not match_row:
        conn.close()
        raise HTTPException(status_code=404, detail=f"Match con ID {match_id} non trovato.")

    # Sets
    c.execute("""
        SELECT id, set_number, home_score, away_score, duration_minutes, winning_team
        FROM match_sets
        WHERE match_id = ?
        ORDER BY set_number
    """, (match_id,))
    sets = [dict(r) for r in c.fetchall()]

    # Atlete Casa
    c.execute("""
        SELECT p.id, p.code, p.first_name, p.last_name, tp.shirt_number, r.code as role_code, r.name as role_name
        FROM matches m
        JOIN team_players tp ON tp.team_id = m.home_team_id
        JOIN players p ON tp.player_id = p.id
        LEFT JOIN roles r ON p.role_id = r.id
        WHERE m.id = ?
        ORDER BY tp.shirt_number
    """, (match_id,))
    players_home = [dict(r) for r in c.fetchall()]

    # Atlete Ospite
    c.execute("""
        SELECT p.id, p.code, p.first_name, p.last_name, tp.shirt_number, r.code as role_code, r.name as role_name
        FROM matches m
        JOIN team_players tp ON tp.team_id = m.away_team_id
        JOIN players p ON tp.player_id = p.id
        LEFT JOIN roles r ON p.role_id = r.id
        WHERE m.id = ?
        ORDER BY tp.shirt_number
    """, (match_id,))
    players_away = [dict(r) for r in c.fetchall()]

    conn.close()
    return {
        "match": dict(match_row),
        "sets": sets,
        "players_home": players_home,
        "players_visiting": players_away
    }

@router.delete("/matches/{match_id}")
def delete_match(match_id: int, current_user: User = Depends(require_admin)):
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("SELECT id, storage_path FROM matches WHERE id = ?", (match_id,))
    row = c.fetchone()
    if not row:
        conn.close()
        raise HTTPException(status_code=404, detail=f"Partita con ID {match_id} non trovata.")

    storage_path = row["storage_path"]

    # Cascading deletes
    c.execute("DELETE FROM actions WHERE match_id = ?", (match_id,))
    c.execute("DELETE FROM rotations WHERE match_id = ?", (match_id,))
    c.execute("DELETE FROM events WHERE match_id = ?", (match_id,))
    c.execute("DELETE FROM validation_logs WHERE match_id = ?", (match_id,))
    c.execute("DELETE FROM match_sets WHERE match_id = ?", (match_id,))
    c.execute("DELETE FROM matches WHERE id = ?", (match_id,))
    conn.commit()
    conn.close()

    try:
        from src.storage_manager import StorageManager
        sm = StorageManager()
        if storage_path:
            sm.delete_dvw(storage_path)
        sm.backup_database_to_storage()
    except Exception:
        pass

    return {"status": "SUCCESS", "deleted_match_id": match_id}

@router.get("/matches/{match_id}/events")
def get_match_events(
    match_id: int,
    set_number: Optional[int] = Query(None, description="Filtra per numero di set"),
    only_errors: bool = Query(False, description="Filtra solo eventi con anomalie"),
    limit: int = Query(2500, ge=1, le=5000),
    offset: int = Query(0, ge=0),
    current_user: User = Depends(verify_match_access)
):
    conn = get_db_connection()
    c = conn.cursor()

    query = """
        SELECT 
            e.id, e.set_id, ms.set_number, e.event_index, e.team_code, e.shirt_number,
            e.skill, e.skill_type, e.evaluation, e.combo_code, e.target_attacker,
            e.start_zone, e.end_zone, e.end_subzone, e.extended_code, e.video_frame,
            e.home_setter_pos, e.away_setter_pos,
            e.home_pos1, e.home_pos2, e.home_pos3, e.home_pos4, e.home_pos5, e.home_pos6,
            e.away_pos1, e.away_pos2, e.away_pos3, e.away_pos4, e.away_pos5, e.away_pos6,
            e.is_valid, e.error_note
        FROM events e
        JOIN match_sets ms ON e.set_id = ms.id
        WHERE e.match_id = ?
    """
    params = [match_id]

    if set_number is not None:
        query += " AND ms.set_number = ?"
        params.append(set_number)

    if only_errors:
        query += " AND (e.is_valid = 0 OR e.error_note IS NOT NULL)"

    query += " ORDER BY e.event_index LIMIT ? OFFSET ?"
    params.extend([limit, offset])

    c.execute(query, params)
    events = []
    last_home_lineup = [None] * 6
    last_away_lineup = [None] * 6
    last_home_setter_pos = None
    last_away_setter_pos = None

    for r in c.fetchall():
        d = dict(r)
        h_lineup = [d.pop(f"home_pos{i}") for i in range(1, 7)]
        a_lineup = [d.pop(f"away_pos{i}") for i in range(1, 7)]

        if any(x is not None for x in h_lineup):
            last_home_lineup = h_lineup
        if any(x is not None for x in a_lineup):
            last_away_lineup = a_lineup
        if d.get("home_setter_pos") is not None:
            last_home_setter_pos = d["home_setter_pos"]
        if d.get("away_setter_pos") is not None:
            last_away_setter_pos = d["away_setter_pos"]

        d["home_lineup"] = list(last_home_lineup)
        d["away_lineup"] = list(last_away_lineup)
        if d.get("home_setter_pos") is None and last_home_setter_pos is not None:
            d["home_setter_pos"] = last_home_setter_pos
        if d.get("away_setter_pos") is None and last_away_setter_pos is not None:
            d["away_setter_pos"] = last_away_setter_pos

        events.append(d)

    conn.close()
    return events

@router.get("/matches/{match_id}/logs")
def get_match_logs(match_id: int, current_user: User = Depends(verify_match_access)):
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("""
        SELECT id, match_id, file_name, line_number, raw_code, parsed_status, error_summary, validated_at
        FROM validation_logs
        WHERE match_id = ?
        ORDER BY line_number ASC, id ASC
    """, (match_id,))
    rows = [dict(r) for r in c.fetchall()]
    conn.close()
    return rows

@router.post("/audit/upload")
async def audit_upload(
    file: UploadFile = File(...),
    campionato: Optional[str] = Form(None),
    categoria: Optional[str] = Form(None),
    girone: Optional[str] = Form(None),
    giornata: Optional[str] = Form(None),
    current_user: User = Depends(require_admin)
):
    import tempfile
    suffix = os.path.splitext(file.filename)[1] or ".dvw"
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        content = await file.read()
        tmp.write(content)
        tmp_path = tmp.name

    try:
        parser = DVWParser(tmp_path)
        parsed = parser.parse()
        clean_code = os.path.splitext(file.filename)[0]
        parsed["match_info"]["match_code"] = clean_code

        ingester = IngestionManager()
        ingest_res = ingester.ingest_dvw(parsed)
        match_id = ingest_res["match_id"]

        # Archiviazione permanente in StorageManager con gerarchia federale
        rel_path = None
        try:
            from src.storage_manager import StorageManager
            storage = StorageManager()
            eff_camp = campionato or parsed.get("match_info", {}).get("season") or "2026-2027"
            rel_path, f_hash = storage.save_dvw(
                content,
                file.filename,
                campionato=eff_camp,
                categoria=categoria or "B1F",
                girone=girone or "B",
                giornata=giornata or "01"
            )
            conn = get_db_connection()
            c = conn.cursor()
            c.execute("UPDATE matches SET storage_path = ?, file_hash = ? WHERE id = ?", (rel_path, f_hash, match_id))
            conn.commit()
            conn.close()
            try:
                storage.backup_database_to_storage()
            except Exception:
                pass
        except Exception:
            pass

        engine = MatchStateEngine(match_id=match_id)
        state_res = engine.process_match()

        return {
            "status": "SUCCESS",
            "match_id": match_id,
            "match_code": ingest_res["match_code"],
            "storage_path": rel_path,
            "events_count": ingest_res["events_count"],
            "sets_count": ingest_res["sets_count"],
            "syntax_issues_count": ingest_res["syntax_issues_count"],
            "state_issues_count": state_res["issues_found"],
            "rotations_created": state_res["rotations_created"],
            "actions_created": state_res["actions_created"]
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Errore durante l'audit del file caricato: {str(e)}")
    finally:
        if os.path.exists(tmp_path):
            try:
                os.remove(tmp_path)
            except Exception:
                pass

@router.post("/audit/file")
def audit_file(payload: AuditFileRequest, current_user: User = Depends(require_admin)):
    file_path = payload.file_path.strip().strip('"')
    if not os.path.exists(file_path):
        raise HTTPException(status_code=400, detail=f"File non trovato sul filesystem: {file_path}")

    try:
        # 1. Parsing
        parser = DVWParser(file_path)
        parsed = parser.parse()

        # 2. Ingestione
        ingester = IngestionManager()
        ingest_res = ingester.ingest_dvw(parsed)
        match_id = ingest_res["match_id"]

        # Archiviazione in StorageManager con gerarchia federale
        rel_path = None
        try:
            with open(file_path, "rb") as f_in:
                content = f_in.read()
            from src.storage_manager import StorageManager
            storage = StorageManager()
            eff_camp = payload.campionato or parsed.get("match_info", {}).get("season") or "2026-2027"
            rel_path, f_hash = storage.save_dvw(
                content,
                os.path.basename(file_path),
                campionato=eff_camp,
                categoria=payload.categoria or "B1F",
                girone=payload.girone or "B",
                giornata=payload.giornata or "01"
            )
            conn = get_db_connection()
            c = conn.cursor()
            c.execute("UPDATE matches SET storage_path = ?, file_hash = ? WHERE id = ?", (rel_path, f_hash, match_id))
            conn.commit()
            conn.close()
            try:
                storage.backup_database_to_storage()
            except Exception:
                pass
        except Exception:
            pass

        # 3. State Engine
        engine = MatchStateEngine(match_id=match_id)
        state_res = engine.process_match()

        return {
            "status": "SUCCESS",
            "match_id": match_id,
            "match_code": ingest_res["match_code"],
            "storage_path": rel_path,
            "events_count": ingest_res["events_count"],
            "sets_count": ingest_res["sets_count"],
            "syntax_issues_count": ingest_res["syntax_issues_count"],
            "state_issues_count": state_res["issues_found"],
            "rotations_created": state_res["rotations_created"],
            "actions_created": state_res["actions_created"]
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Errore durante l'audit del file: {str(e)}")

@router.post("/rosters/sync")
def sync_rosters(payload: Optional[RosterSyncRequest] = None, current_user: User = Depends(require_admin)):
    try:
        mgr = RosterManager()
        if payload and payload.team_code:
            res = mgr.sync_roster_file_to_db(payload.team_code)
            return {"status": "SUCCESS", "results": [res]}
        else:
            results = mgr.sync_all_rosters_to_db()
            return {"status": "SUCCESS", "results": results}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Errore sincronizzazione roster: {str(e)}")
