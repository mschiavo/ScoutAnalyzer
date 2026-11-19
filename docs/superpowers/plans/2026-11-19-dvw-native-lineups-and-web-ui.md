# DVW Native Lineups, Domain Rules & Web UI Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Risolvere le anomalie del core engine di lettura dei file `.dvw` (utilizzando le formazioni e rotazioni native registrate in ogni riga dello scout), integrare i controlli federali di pallavolo (battitore in Z1, divieto battuta Libero, max 6 sostituzioni per set, regole parziali set) e realizzare una prima interfaccia web moderna ed ergonomica (FastAPI + Vanilla CSS/JS) con campo da gioco interattivo e API pronte anche per frontend Vite esterni.

**Architecture:** 
1. **Core Parser & State Engine:** `DVWParser` estrae direttamente dalle colonne 9-10 e 14-25 di ogni riga scout la posizione del palleggiatore e le formazioni native delle due squadre, con regex robusta per numeri a 1-2 cifre e zone con tilde multiple. `MatchStateEngine` valida battitore in Zona 1 sulla formazione reale, controlla i falli del Libero al servizio e il limite di sostituzioni.
2. **Backend REST API:** FastAPI espone endpoint JSON documentati con supporto CORS per servire sia la dashboard interna che qualsiasi app client (inclusa la futura o esistente app Vite).
3. **Frontend Dashboard:** SPA moderna in Vanilla CSS/JS con Dark Theme, riepilogo gara/set, campo da pallavolo SVG con posizioni dinamiche delle atlete e visualizzatore play-by-play filtrabile per severità.

**Tech Stack:** Python 3.15, SQLite 3, FastAPI, Uvicorn, Vanilla CSS, HTML5 Canvas/SVG, JavaScript ES6+.

**Spec:** `docs/superpowers/specs/2026-11-19-dvw-native-lineups-and-web-ui-design.md`

## Global Constraints
- Git: Tutte le modifiche e i commit devono avvenire esclusivamente sul branch `feature/dvw-native-lineups-and-fixes`. Mai commit su `master`, `main` o `develop`.
- Compatibilità DB: Preservare la struttura di `scoutanalyzer.db`, aggiungendo colonne opzionali/indici senza distruggere i dati esistenti.
- Autocontenimento Web: La dashboard principale non deve richiedere compilazione Node.js per avviarsi, deve girare direttamente tramite `python web_app.py`.
- TDD: Ogni modifica al core engine deve avere test di unità automatizzati eseguibili con `pytest`.

## Review Focus
1. **Formazioni native parziali o assenti:** se una riga speciale non ha tutte le 6 atlete (es. righe di commento o interruzioni), il parser non deve generare eccezioni e lo state engine deve usare la formazione precedente come fallback.
2. **Battitore in Zona 1 con maglia a 1 cifra:** codici come `*5SM+...` devono associare correttamente la maglia `5` alla Zona 1.
3. **Fallo del Libero al servizio:** se un'atleta designata con ruolo '1' o contrassegnata come Libero effettua un tocco `S`, deve essere sollevato `ERRORE` immediato.
4. **CORS per app esterne:** l'API deve consentire richieste da `http://localhost:5173` (porta default Vite) senza blocchi cross-origin.
5. **Navigazione fluida su partite da oltre 1.500 eventi:** l'interfaccia web deve caricare gli eventi senza bloccare il rendering del browser.

---

### Task 1: Scaffolding, Dipendenze e Indici Database

**Files:**
- Modify: `requirements.txt`
- Modify: `database/schema.sql`
- Modify: `database/setup_db.py`
- Test: `tests/test_db_setup.py`

**Interfaces:**
- Consumes: Configurazione SQLite standard
- Produces: Tabelle SQLite ottimizzate con indici su `events(match_id, set_id, event_index)` e colonne formazioni native in `events`.

- [ ] **Step 1: Scrivi il test di configurazione database e dipendenze**

```python
# tests/test_db_setup.py
import sqlite3
import os
from database.setup_db import create_database

def test_database_indices_and_columns(tmp_path):
    test_db = str(tmp_path / "test.db")
    create_database(test_db)
    conn = sqlite3.connect(test_db)
    cur = conn.cursor()
    
    # Verifica indici
    cur.execute("SELECT name FROM sqlite_master WHERE type='index'")
    indices = [r[0] for r in cur.fetchall()]
    assert any("idx_events_match" in idx for idx in indices)
    
    # Verifica colonne native in events
    cur.execute("PRAGMA table_info(events)")
    cols = [r[1] for r in cur.fetchall()]
    assert "home_pos1" in cols
    assert "away_pos1" in cols
    assert "home_setter_pos" in cols
    assert "away_setter_pos" in cols
    conn.close()
```

- [ ] **Step 2: Esegui il test per verificare che fallisca**

Esegui: `pytest tests/test_db_setup.py`  
Atteso: FAIL (colonne o indici mancanti).

- [ ] **Step 3: Aggiorna `requirements.txt`, `database/schema.sql` e `database/setup_db.py`**

Aggiungi `fastapi`, `uvicorn`, `pydantic`, `pytest` a `requirements.txt`.  
Aggiungi a `schema.sql` e `setup_db.py` le colonne native in `events`:
`home_setter_pos INTEGER, away_setter_pos INTEGER, home_pos1..6 INTEGER, away_pos1..6 INTEGER`.  
Aggiungi gli indici:
`CREATE INDEX IF NOT EXISTS idx_events_match ON events(match_id, set_id, event_index);`  
`CREATE INDEX IF NOT EXISTS idx_rotations_match ON rotations(match_id, set_id);`  
`CREATE INDEX IF NOT EXISTS idx_logs_match ON validation_logs(match_id, line_number);`

- [ ] **Step 4: Esegui il test per verificare che passi**

Esegui: `pytest tests/test_db_setup.py`  
Atteso: PASS

- [ ] **Step 5: Commit sul branch `feature/dvw-native-lineups-and-fixes`**

```bash
git add requirements.txt database/schema.sql database/setup_db.py tests/test_db_setup.py
git commit -m "chore: add web dependencies, indices and native lineup columns to schema"
```

---

### Task 2: Fix DVW Parser (Colonne Native, Regex e Tilde)

**Files:**
- Modify: `src/dvw_parser.py`
- Test: `tests/test_dvw_parser.py`

**Interfaces:**
- Consumes: Righe `.dvw` con formazioni native alle colonne 14-25 e rotazioni alle colonne 9-10.
- Produces: Dizionario evento con:
  - `home_setter_pos`: int (1-6)
  - `away_setter_pos`: int (1-6)
  - `home_lineup`: list di 6 int/None
  - `away_lineup`: list di 6 int/None
  - `shirt_number`: supporta maglie a 1 e 2 cifre
  - `start_zone`, `end_zone`, `end_subzone`: corretta estrazione anche con tilde multiple (es. `*13BQ#~~~~4~~2`)

- [ ] **Step 1: Scrivi i test di unità per il parsing delle formazioni e dei codici estesi**

```python
# tests/test_dvw_parser.py
from src.dvw_parser import DVWParser

def test_parse_scout_line_native_lineup():
    parser = DVWParser("dummy.dvw")
    line = "*18SM-~~~58B;;;;;;;20.30.09;1;2;1;1;398;;18;15;1;5;7;4;9;8;2;1;11;13;"
    ev = parser._parse_scout_line(line, 1, 1)
    
    assert ev["is_valid"] == 1
    assert ev["team_code"] == "*"
    assert ev["shirt_number"] == 18
    assert ev["skill"] == "S"
    assert ev["home_setter_pos"] == 2
    assert ev["away_setter_pos"] == 1
    assert ev["home_lineup"] == [18, 15, 1, 5, 7, 4]
    assert ev["away_lineup"] == [9, 8, 2, 1, 11, 13]
    assert ev["video_frame"] == 398

def test_parse_single_digit_shirt_and_tilde_zones():
    parser = DVWParser("dummy.dvw")
    # Maglia a 1 cifra
    line1 = "*5SM+;;;;;;;;1;1;1;;;;;;;;;;;;;;"
    ev1 = parser._parse_scout_line(line1, 1, 1)
    assert ev1["shirt_number"] == 5
    
    # Zone con tilde sparse: *13BQ#~~~~4~~2
    line2 = "*13BQ#~~~~4~~2;;;;;;;;1;1;1;;;;;;;;;;;;;;"
    ev2 = parser._parse_scout_line(line2, 2, 1)
    assert ev2["start_zone"] == 4
    assert ev2["end_zone"] == 2
```

- [ ] **Step 2: Esegui i test per verificare che falliscano**

Esegui: `pytest tests/test_dvw_parser.py`  
Atteso: FAIL (chiavi mancanti o regex incompatibile).

- [ ] **Step 3: Implementa le correzioni in `src/dvw_parser.py`**

1. Correggi l'estrazione:
   - `col_set = int(parts[8]) if ...`
   - `home_setter_pos = int(parts[9]) if len(parts) > 9 and parts[9].isdigit() else None`
   - `away_setter_pos = int(parts[10]) if len(parts) > 10 and parts[10].isdigit() else None`
   - `video_frame = int(parts[12]) if len(parts) > 12 and parts[12].isdigit() else None`
   - Formazioni native da `parts[14:20]` e `parts[20:26]`.
2. Aggiorna la regex della riga scout per supportare maglie a 1 o 2 cifre:
   `^([*aA])(\d{1,2})([SRABDEFBsrabdefb])([A-Za-z0-9 ]?)([#\+!\-/\=])(.*)$`
3. Affina l'estrazione delle zone sparse con tilde `~`:
   Estrai le cifre isolate per zona di partenza e arrivo rispettando i segmenti separati da tilde.

- [ ] **Step 4: Esegui i test per verificare che passino**

Esegui: `pytest tests/test_dvw_parser.py`  
Atteso: PASS

- [ ] **Step 5: Commit sul branch `feature/dvw-native-lineups-and-fixes`**

```bash
git add src/dvw_parser.py tests/test_dvw_parser.py
git commit -m "fix(parser): extract native lineups, setter positions and support flexible codes"
```

---

### Task 3: Aggiornamento Ingestion Manager

**Files:**
- Modify: `src/ingestion_manager.py`
- Test: `tests/test_ingestion_manager.py`

**Interfaces:**
- Consumes: Dizionario evento da `dvw_parser.py` con `home_setter_pos`, `away_setter_pos`, `home_lineup`, `away_lineup`, `video_frame`.
- Produces: Record salvati nella tabella `events` con tutte le colonne native popolate.

- [ ] **Step 1: Scrivi il test di ingestione con colonne native**

```python
# tests/test_ingestion_manager.py
import sqlite3
from database.setup_db import create_database
from src.ingestion_manager import IngestionManager

def test_ingest_native_lineups(tmp_path):
    db_file = str(tmp_path / "test.db")
    create_database(db_file)
    
    ingester = IngestionManager()
    ingester.db_path = db_file
    
    mock_data = {
        "match_info": {"match_code": "TEST_01", "date": "2026-10-15"},
        "teams": {"home_code": "H_TEAM", "home_name": "Home", "away_code": "A_TEAM", "away_name": "Away"},
        "sets": [{"set_number": 1, "home_score": 25, "away_score": 20, "duration_minutes": 22, "winning_team": "*"}],
        "players_home": [{"number": "18", "name": "Player 18"}],
        "players_visiting": [{"number": "9", "name": "Player 9"}],
        "events": [{
            "event_index": 1, "set_number": 1, "team_code": "*", "shirt_number": 18,
            "skill": "S", "skill_type": "M", "evaluation": "-", "extended_code": "*18SM-~~~58B",
            "is_valid": 1, "home_setter_pos": 2, "away_setter_pos": 1,
            "home_lineup": [18, 15, 1, 5, 7, 4], "away_lineup": [9, 8, 2, 1, 11, 13],
            "video_frame": 398
        }]
    }
    
    res = ingester.ingest_dvw(mock_data)
    assert res["status"] == "SUCCESS"
    
    conn = sqlite3.connect(db_file)
    c = conn.cursor()
    c.execute("SELECT home_pos1, away_pos1, home_setter_pos, video_frame FROM events WHERE match_id = ?", (res["match_id"],))
    row = c.fetchone()
    assert row == (18, 9, 2, 398)
    conn.close()
```

- [ ] **Step 2: Esegui il test per verificare che fallisca**

Esegui: `pytest tests/test_ingestion_manager.py`  
Atteso: FAIL

- [ ] **Step 3: Modifica `src/ingestion_manager.py`**

Aggiorna la query di inserimento in `events` includendo `home_setter_pos`, `away_setter_pos`, `home_pos1..6`, `away_pos1..6` e `video_frame`.

- [ ] **Step 4: Esegui il test per verificare che passi**

Esegui: `pytest tests/test_ingestion_manager.py`  
Atteso: PASS

- [ ] **Step 5: Commit sul branch `feature/dvw-native-lineups-and-fixes`**

```bash
git add src/ingestion_manager.py tests/test_ingestion_manager.py
git commit -m "feat(ingestion): persist native lineup and setter positions to events table"
```

---

### Task 4: Aggiornamento State Engine e Regole Federali di Pallavolo

**Files:**
- Modify: `src/state_engine.py`
- Test: `tests/test_state_engine.py`

**Interfaces:**
- Consumes: Tabella `events` con dati nativi.
- Produces: Validazione semantica accurata al 100%:
  - Battitore in Z1 verificato rispetto alla formazione nativa.
  - Fallo battuta Libero: `skill == 'S'` da parte di un Libero -> `ERRORE`.
  - Max 6 sostituzioni per set -> `ERRORE` oltre la 6ª.
  - Set end margin: controllo scarto 2 punti e soglie 25 / 15.

- [ ] **Step 1: Scrivi i test di unità per le regole di pallavolo nello State Engine**

```python
# tests/test_state_engine.py
import sqlite3
from database.setup_db import create_database
from src.ingestion_manager import IngestionManager
from src.state_engine import MatchStateEngine

def test_volleyball_domain_rules(tmp_path):
    db_file = str(tmp_path / "test.db")
    create_database(db_file)
    
    # Setup dati match con battitore corretto in Z1 tramite lineup nativa
    ingester = IngestionManager()
    ingester.db_path = db_file
    mock_data = {
        "match_info": {"match_code": "VB_TEST", "date": "2026-10-15"},
        "teams": {"home_code": "H", "home_name": "Home", "away_code": "A", "away_name": "Away"},
        "sets": [{"set_number": 1, "home_score": 25, "away_score": 23, "duration_minutes": 25, "winning_team": "*"}],
        "players_home": [{"number": "18", "name": "H18"}, {"number": "1", "name": "Libero H", "role_code": "1"}],
        "players_visiting": [{"number": "9", "name": "A9"}],
        "events": [
            {
                "event_index": 1, "set_number": 1, "team_code": "*", "shirt_number": 18,
                "skill": "S", "skill_type": "M", "evaluation": "+", "extended_code": "*18SM+~~~58B",
                "is_valid": 1, "home_setter_pos": 2, "away_setter_pos": 1,
                "home_lineup": [18, 15, 1, 5, 7, 4], "away_lineup": [9, 8, 2, 1, 11, 13]
            }
        ]
    }
    res = ingester.ingest_dvw(mock_data)
    
    engine = MatchStateEngine(match_id=res["match_id"])
    engine.db_path = db_file
    status = engine.process_match()
    assert status["issues_found"] == 0  # Nessun falso allarme su Z1!
```

- [ ] **Step 2: Esegui il test per verificare che fallisca**

Esegui: `pytest tests/test_state_engine.py`  
Atteso: FAIL

- [ ] **Step 3: Implementa le nuove verifiche in `src/state_engine.py`**

1. Quando viene processato un servizio (`skill == 'S'`), controlla se `home_pos1` o `away_pos1` è valorizzato dall'evento:
   - Se presente, confronta direttamente con `shirt_number`.
   - Se differisce, emette `ERRORE` (*Fallo di rotazione / battitore non in Zona 1*).
2. Carica la lista dei liberi per squadra dal DB (`roles.dv_role_code == '1'` o ruolo libero):
   - Se un Libero esegue una battuta (`skill == 'S'`), emette `ERRORE` (*Fallo del Libero al servizio*).
3. Conta le sostituzioni per squadra nel set corrente (`is_subst`):
   - Se per una squadra i cambi superano 6, emette `ERRORE` (*Superato il limite massimo di 6 sostituzioni nel set*).
4. Al termine del set, verifica che la squadra vincente abbia raggiunto almeno 25 punti (15 al 5° set) con uno scarto $\ge 2$ punti rispetto all'avversaria.

- [ ] **Step 4: Esegui il test per verificare che passi**

Esegui: `pytest tests/test_state_engine.py`  
Atteso: PASS

- [ ] **Step 5: Commit sul branch `feature/dvw-native-lineups-and-fixes`**

```bash
git add src/state_engine.py tests/test_state_engine.py
git commit -m "feat(state_engine): native lineup Z1 check, libero serving rule and 6-substitution limit"
```

---

### Task 5: Backend Web REST con FastAPI

**Files:**
- Create: `src/api/__init__.py`
- Create: `src/api/routes.py`
- Create: `web_app.py`
- Test: `tests/test_api.py`

**Interfaces:**
- Consumes: `scoutanalyzer.db`, moduli core (`dvw_parser`, `header_validator`, `ingestion_manager`, `state_engine`, `roster_manager`).
- Produces: API RESTful:
  - `GET /api/matches`
  - `GET /api/matches/{id}`
  - `GET /api/matches/{id}/events`
  - `GET /api/matches/{id}/logs`
  - `POST /api/audit/file`
  - Abilitazione CORS per qualsiasi client esterno (es. Vite).

- [ ] **Step 1: Scrivi il test delle API REST**

```python
# tests/test_api.py
from fastapi.testclient import TestClient
from web_app import app

client = TestClient(app)

def test_get_matches_api():
    response = client.get("/api/matches")
    assert response.status_code == 200
    assert isinstance(response.json(), list)

def test_cors_headers():
    response = client.options("/api/matches", headers={"Origin": "http://localhost:5173", "Access-Control-Request-Method": "GET"})
    assert response.status_code == 200
    assert response.headers.get("access-control-allow-origin") == "*"
```

- [ ] **Step 2: Esegui il test per verificare che fallisca**

Esegui: `pytest tests/test_api.py`  
Atteso: FAIL (`web_app` non definita).

- [ ] **Step 3: Crea i router FastAPI e l'app `web_app.py`**

1. Implementa `src/api/routes.py` con gli endpoint REST per partite, set, eventi play-by-play, audit logs e sincronizzazione.
2. In `web_app.py`, monta `CORSMiddleware`, registra i router e monta la cartella `static/` per servire l'interfaccia utente.

- [ ] **Step 4: Esegui il test per verificare che passi**

Esegui: `pytest tests/test_api.py`  
Atteso: PASS

- [ ] **Step 5: Commit sul branch `feature/dvw-native-lineups-and-fixes`**

```bash
git add src/api/__init__.py src/api/routes.py web_app.py tests/test_api.py
git commit -m "feat(api): FastAPI REST backend with CORS and match inspection endpoints"
```

---

### Task 6: Frontend Dashboard Grafica Interattiva (Vanilla CSS/JS + Campo Volley SVG)

**Files:**
- Create: `static/index.html`
- Create: `static/style.css`
- Create: `static/app.js`
- Test: `tests/test_frontend_assets.py`

**Interfaces:**
- Consumes: REST API di FastAPI (`/api/matches`, `/api/matches/{id}/events`, ecc.).
- Produces: Interfaccia utente web reattiva, visualizzazione 2D del campo con le 6 zone di rotazione e navigatore eventi play-by-play.

- [ ] **Step 1: Scrivi il test di integrità degli asset statici**

```python
# tests/test_frontend_assets.py
import os

def test_static_files_exist():
    assert os.path.exists("static/index.html")
    assert os.path.exists("static/style.css")
    assert os.path.exists("static/app.js")
    
    with open("static/index.html", "r", encoding="utf-8") as f:
        html = f.read()
    assert "court-container" in html
    assert "events-table" in html
```

- [ ] **Step 2: Esegui il test per verificare che fallisca**

Esegui: `pytest tests/test_frontend_assets.py`  
Atteso: FAIL (file non ancora creati).

- [ ] **Step 3: Crea `index.html`, `style.css` e `app.js`**

1. **`index.html`**: Layout moderno con sidebar selettore match, barra superiore con KPI partita (punteggio set, durata, anomalie), sezione centrale con:
   - **Campo da Pallavolo SVG Interattivo**: Rappresentazione visiva di Casa e Ospite, divisa dalla rete, con le posizioni 1, 2, 3, 4, 5, 6 per ciascun lato e indicatori speciali per Battitore, Palleggiatore (`P`) e Libero (`L`).
   - **Visualizzatore Play-by-Play**: Tabella reattiva con filtri veloci (Tutti, Errori Critici, Errori, Warning), badge colpi terminali ed evidenziazione riga attiva. Cliccando su un evento, il campo da gioco si aggiorna istantaneamente mostrando la rotazione esatta di quell'istante.
2. **`style.css`**: Design Dark Theme elegante ispirato ai software di analisi sportiva professionale (grafica pulita, palette a contrasto elevato, font leggibile).
3. **`app.js`**: Gestione fetch verso le API FastAPI, aggiornamento dello stato della partita, disegno dinamico delle atlete sulle 6 zone del campo e filtro in tempo reale dei log.

- [ ] **Step 4: Esegui il test per verificare che passi**

Esegui: `pytest tests/test_frontend_assets.py`  
Atteso: PASS

- [ ] **Step 5: Commit sul branch `feature/dvw-native-lineups-and-fixes`**

```bash
git add static/index.html static/style.css static/app.js tests/test_frontend_assets.py
git commit -m "feat(ui): interactive volleyball court visualizer and play-by-play audit dashboard"
```

---

### Task 7: Verifica e Audit E2E su File Reali di Campionato

**Files:**
- Create: `tests/test_e2e_real_audit.py`

**Interfaces:**
- Consumes: File reali `.dvw` (es. `D:\Volley\B1FB\giornata_01\&01_COR-VOL_Vicenza_b1fb_26_s.dvw`).
- Produces: Verifica che l'audit end-to-end (Parser -> Ingestion -> State Engine) esegua senza errori e con zero falsi allarmi di rotazione.

- [ ] **Step 1: Scrivi il test E2E**

```python
# tests/test_e2e_real_audit.py
import os
import pytest
from src.dvw_parser import DVWParser
from src.ingestion_manager import IngestionManager
from src.state_engine import MatchStateEngine

def test_real_match_audit_end_to_end():
    sample_file = r"D:\Volley\B1FB\giornata_01\&01_COR-VOL_Vicenza_b1fb_26_s.dvw"
    if not os.path.exists(sample_file):
        pytest.skip("File di test reale non presente sul path locale")
        
    parser = DVWParser(sample_file)
    parsed = parser.parse()
    assert len(parsed["events"]) > 1000
    
    ingester = IngestionManager()
    res = ingester.ingest_dvw(parsed)
    assert res["status"] == "SUCCESS"
    
    engine = MatchStateEngine(match_id=res["match_id"])
    s_res = engine.process_match()
    assert s_res["status"] == "SUCCESS"
    assert s_res["rotations_created"] > 0
```

- [ ] **Step 2: Esegui l'intera suite di test**

Esegui: `pytest tests/ -v`  
Atteso: Tutti i test passano con successo (100% green).

- [ ] **Step 3: Commit finale sul branch `feature/dvw-native-lineups-and-fixes`**

```bash
git add tests/test_e2e_real_audit.py
git commit -m "test(e2e): full end-to-end validation test on real championship match"
```
