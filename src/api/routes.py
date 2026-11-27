import os
import hashlib
import logging
import json
import sqlite3
import re
from typing import Dict, Any, List, Literal, Optional
from fastapi import APIRouter, HTTPException, Query, Body, File, UploadFile, Depends, Request, Form
from pydantic import BaseModel

from src.dvw_parser import DVWParser
from src.ingestion_manager import DuplicateMatch, IngestionManager, UnknownRoster, scout_section_hash
from src.state_engine import MatchStateEngine
from src.roster_manager import RosterManager
from src.api.auth import User, get_current_user, require_admin, verify_password, create_access_token

router = APIRouter(prefix="/api", tags=["ScoutAnalyzer API"])
logger = logging.getLogger(__name__)

from src.db import get_db_connection, get_sqlite_path as get_db_path, scout_filename_metadata

class LoginRequest(BaseModel):
    username: str
    password: str

class AuditFileRequest(BaseModel):
    file_path: str
    campionato: Optional[str] = None
    categoria: Optional[str] = None
    girone: Optional[str] = None
    giornata: Optional[str] = None
    replace_match_id: Optional[int] = None
    replace_file_hash: Optional[str] = None
    create_new: bool = False
    roster_policy: Literal["ask", "add", "skip"] = "ask"

class RosterSyncRequest(BaseModel):
    team_code: Optional[str] = None
    download: bool = False

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
        m.id, COALESCE(m.source_match_code, m.match_code) AS match_code, m.scheduled_date, m.home_team_id, m.away_team_id,
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
        m["scout_author"] = scout_filename_metadata(m["match_code"])[1] or m.get("scout_author") or "N.D."
        rows.append(m)

    conn.close()
    return rows

@router.get("/matches/{match_id}")
def get_match_detail(match_id: int, current_user: User = Depends(verify_match_access)):
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("""
        SELECT 
            m.id, COALESCE(m.source_match_code, m.match_code) AS match_code, m.scheduled_date, m.file_hash,
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

    c.execute("""
        SELECT s.team_side, p.id, s.player_code AS code, s.first_name, s.last_name, s.shirt_number,
               CASE WHEN s.is_libero = 1 THEN 'L' ELSE COALESCE(r.code, s.role_code) END AS role_code,
               CASE WHEN s.is_libero = 1 THEN 'Libero' ELSE r.name END AS role_name
        FROM match_roster_players s
        LEFT JOIN players p ON p.code = s.player_code
        LEFT JOIN roles r ON s.role_code = r.dv_role_code OR s.role_code = r.code
        WHERE s.match_id = ?
        ORDER BY s.shirt_number
    """, (match_id,))
    roster = [dict(row) for row in c.fetchall()]
    if roster:
        players_home = [row for row in roster if row["team_side"] == "*"] or players_home
        players_away = [row for row in roster if row["team_side"] == "a"] or players_away

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
        SELECT id, match_id, file_name, line_number, raw_code, parsed_status, error_summary, validated_at, validation_source
        FROM validation_logs
        WHERE match_id = ?
        ORDER BY line_number ASC, id ASC
    """, (match_id,))
    rows = [dict(r) for r in c.fetchall()]
    conn.close()
    return rows

def _audit_dvw(content, filename, path, campionato, categoria, girone, giornata, replace_match_id, roster_policy,
               create_new, replace_file_hash):
    from src.storage_manager import StorageManager, build_storage_key

    parsed = DVWParser(path).parse()
    match_code = os.path.splitext(filename)[0]
    match_info = parsed.setdefault("match_info", {})
    match_info["match_code"] = match_code
    filename_round, _ = scout_filename_metadata(match_code)
    try:
        round_number = filename_round if filename_round is not None else int(giornata or 1)
    except ValueError:
        raise HTTPException(status_code=400, detail="Giornata non valida")
    if round_number < 1:
        raise HTTPException(status_code=400, detail="Giornata non valida")
    season = campionato or match_info.get("season") or "2026-2027"
    category = categoria or "B1F"
    group = girone or "B"
    scope = build_storage_key(season, category, group, round_number, filename).rsplit("/", 2)[0]
    if create_new and replace_match_id is not None:
        raise HTTPException(status_code=400, detail="Scegli una sola azione per il caricamento.")
    file_hash = hashlib.sha256(content).hexdigest()
    scout_hash = scout_section_hash(content)
    storage = StorageManager()

    def save_file(cursor, match_id, separate_file):
        if not separate_file:
            proposed_path = build_storage_key(season, category, group, round_number, filename)
            cursor.execute("SELECT 1 FROM matches WHERE storage_path = ? LIMIT 1", (proposed_path,))
            separate_file = bool(cursor.fetchone()) or os.path.exists(os.path.join(storage.base_dir, proposed_path))
        stored_name = f"{match_code[:160]}__{match_id}_{file_hash[:12]}.dvw" if separate_file else filename
        storage_path, _ = storage.save_dvw(
            content, stored_name, campionato=season, categoria=category, girone=group, giornata=round_number
        )
        return storage_path

    try:
        result = IngestionManager().ingest_dvw(
            parsed, audit_scope=scope, giornata=round_number, replace_match_id=replace_match_id,
            roster_policy=roster_policy, create_new=create_new, file_hash=file_hash, scout_hash=scout_hash, save_file=save_file,
            replace_file_hash=replace_file_hash
        )
    except UnknownRoster as error:
        raise HTTPException(status_code=409, detail={"code": "unknown_rosters", "teams": error.teams}) from error
    except DuplicateMatch as error:
        raise HTTPException(status_code=409, detail={
            "code": "identical_file" if error.identical else "duplicate_match",
            "message": "File identico già importato." if error.identical else "Esiste già una rilevazione da confrontare.",
            "incoming": error.incoming,
            "matches": [{key: value for key, value in match.items() if key not in {"internal_code", "identical"}}
                        for match in error.matches],
        }) from error

    match_id = result["match_id"]
    state_result = MatchStateEngine(match_id=match_id).process_match()
    try:
        storage.backup_database_to_storage()
    except Exception:
        logger.warning("Backup database non riuscito dopo l'import della rilevazione %s", match_id, exc_info=True)
    return {
        **result,
        "file_hash": file_hash,
        "state_issues_count": state_result["issues_found"],
        "rotations_created": state_result["rotations_created"],
        "actions_created": state_result["actions_created"],
    }


@router.post("/audit/upload")
async def audit_upload(
    file: UploadFile = File(...),
    campionato: Optional[str] = Form(None),
    categoria: Optional[str] = Form(None),
    girone: Optional[str] = Form(None),
    giornata: Optional[str] = Form(None),
    replace_match_id: Optional[int] = Form(None),
    replace_file_hash: Optional[str] = Form(None),
    create_new: bool = Form(False),
    roster_policy: Literal["ask", "add", "skip"] = Form("ask"),
    current_user: User = Depends(require_admin)
):
    import tempfile
    filename = os.path.basename(file.filename or "match.dvw")
    content = await file.read()
    with tempfile.TemporaryDirectory() as temporary_dir:
        path = os.path.join(temporary_dir, "upload.dvw")
        with open(path, "wb") as stream:
            stream.write(content)
        try:
            return _audit_dvw(content, filename, path, campionato, categoria, girone, giornata, replace_match_id,
                              roster_policy, create_new, replace_file_hash)
        except HTTPException:
            raise
        except Exception as error:
            raise HTTPException(status_code=500, detail=f"Errore durante l'audit del file caricato: {error}") from error


@router.post("/audit/file")
def audit_file(payload: AuditFileRequest, current_user: User = Depends(require_admin)):
    path = payload.file_path.strip().strip('"')
    if not os.path.isfile(path):
        raise HTTPException(status_code=400, detail=f"File non trovato sul filesystem: {path}")
    try:
        with open(path, "rb") as stream:
            return _audit_dvw(stream.read(), os.path.basename(path), path, payload.campionato,
                              payload.categoria, payload.girone, payload.giornata, payload.replace_match_id,
                              payload.roster_policy, payload.create_new, payload.replace_file_hash)
    except HTTPException:
        raise
    except Exception as error:
        raise HTTPException(status_code=500, detail=f"Errore durante l'audit del file: {error}") from error


@router.post("/rosters/sync")
def sync_rosters(payload: Optional[RosterSyncRequest] = None, current_user: User = Depends(require_admin)):
    try:
        mgr = RosterManager()
        if payload and payload.download:
            if payload.team_code:
                downloads = [(payload.team_code, mgr.download_roster_for_team(payload.team_code))]
            else:
                downloads = mgr.download_all_rosters()
            results = []
            for team_code, download in downloads:
                if download["status"] != "SUCCESS":
                    results.append(download)
                    continue
                synced = mgr.sync_roster_file_to_db(team_code)
                results.append({**synced, "backup_created": download.get("backup_created", False)})
            return {"status": "SUCCESS", "results": results}
        if payload and payload.team_code:
            res = mgr.sync_roster_file_to_db(payload.team_code)
            return {"status": "SUCCESS", "results": [res]}
        else:
            results = mgr.sync_all_rosters_to_db()
            return {"status": "SUCCESS", "results": results}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Errore sincronizzazione roster: {str(e)}")
