import os
import json
import sqlite3
from typing import Dict, Any, List, Optional
from fastapi import APIRouter, HTTPException, Query, Body
from pydantic import BaseModel

from src.dvw_parser import DVWParser
from src.ingestion_manager import IngestionManager
from src.state_engine import MatchStateEngine
from src.roster_manager import RosterManager

router = APIRouter(prefix="/api", tags=["ScoutAnalyzer API"])

DEFAULT_CONFIG_PATH = "config/config.json"

def get_db_path() -> str:
    if os.path.exists(DEFAULT_CONFIG_PATH):
        try:
            with open(DEFAULT_CONFIG_PATH, "r", encoding="utf-8") as f:
                cfg = json.load(f)
                return cfg.get("db_path", "scoutanalyzer.db")
        except Exception:
            pass
    return "scoutanalyzer.db"

def get_db_connection(db_path: Optional[str] = None) -> sqlite3.Connection:
    path = db_path or get_db_path()
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    return conn

class AuditFileRequest(BaseModel):
    file_path: str

class RosterSyncRequest(BaseModel):
    team_code: Optional[str] = None

@router.get("/matches")
def list_matches():
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("""
        SELECT 
            m.id, m.match_code, m.scheduled_date,
            ht.code as home_code, ht.name as home_name,
            at.code as away_code, at.name as away_name,
            (SELECT COUNT(*) FROM match_sets ms WHERE ms.match_id = m.id) as sets_count,
            (SELECT COUNT(*) FROM events e WHERE e.match_id = m.id) as events_count,
            (SELECT COUNT(*) FROM validation_logs vl WHERE vl.match_id = m.id) as logs_count
        FROM matches m
        LEFT JOIN teams ht ON m.home_team_id = ht.id
        LEFT JOIN teams at ON m.away_team_id = at.id
        ORDER BY m.id DESC
    """)
    rows = [dict(r) for r in c.fetchall()]
    conn.close()
    return rows

@router.get("/matches/{match_id}")
def get_match_detail(match_id: int):
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

@router.get("/matches/{match_id}/events")
def get_match_events(
    match_id: int,
    set_number: Optional[int] = Query(None, description="Filtra per numero di set"),
    only_errors: bool = Query(False, description="Filtra solo eventi con anomalie"),
    limit: int = Query(2500, ge=1, le=5000),
    offset: int = Query(0, ge=0)
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
    for r in c.fetchall():
        d = dict(r)
        d["home_lineup"] = [d.pop(f"home_pos{i}") for i in range(1, 7)]
        d["away_lineup"] = [d.pop(f"away_pos{i}") for i in range(1, 7)]
        events.append(d)

    conn.close()
    return events

@router.get("/matches/{match_id}/logs")
def get_match_logs(match_id: int):
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

@router.post("/audit/file")
def audit_file(payload: AuditFileRequest):
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

        # 3. State Engine
        engine = MatchStateEngine(match_id=match_id)
        state_res = engine.process_match()

        return {
            "status": "SUCCESS",
            "match_id": match_id,
            "match_code": ingest_res["match_code"],
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
def sync_rosters(payload: Optional[RosterSyncRequest] = None):
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
