# Auth, Multi-Tenancy, Cloud Storage & Admin Rule Configurator Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implementare un sistema completo di autenticazione e controllo accessi basato su ruoli (ADMIN vs SCOUT), con Login Gate assoluto, filtro multi-tenant delle partite per squadre assegnate, tracciamento accessi (IP e orario in `user_logins`), sessioni scorrevoli per inattività (1h per scout, perenne per admin/locale), storage gestito/remoto dei file `.dvw` (`storage/dvw/`) e due pannelli amministrativi dedicati (Gestione Utenti e Configuratore Regole Tocchi Correlati).

**Architecture:**
1. **Sicurezza & Autenticazione:** FastAPI con token JWT firmati, password hashate tramite `bcrypt` (12 rounds), Dependency injection per `get_current_user` e `require_admin`. Registro login `user_logins` con IP e user-agent. Rinnovo sliding window su richieste autenticate.
2. **Multi-Tenancy & RBAC:** Tabelle `users` e `user_teams`. Endpoint `/api/matches` e relative sub-risorse protetti con dependency `verify_match_access`. Utenti SCOUT vedono solo le loro squadre; upload file riservato ad ADMIN (`403 Forbidden` per scout).
3. **Storage Centralizzato:** Modulo `StorageManager` che incapsula il salvataggio dei `.dvw` in `storage/dvw/{season}/{match_code}.dvw` (con hash MD5/SHA256) e predisposizione S3/R2.
4. **Admin UI & Login Gate:** SPA estesa con Login Gate (schermata di login a pieno schermo al caricamento se privi di token), navigazione a schede/modali per Gestione Utenti (con multi-selezione squadre), Log Accessi, e Configuratore Regole Correlate di Fine Azione con aggiornamento immediato di `config/datavalley_specs.json`.

**Tech Stack:** Python 3.15, SQLite 3, FastAPI, PyJWT, passlib[bcrypt], Vanilla CSS/JS, HTML5.

**Spec:** `docs/superpowers/specs/2026-11-20-auth-multitenant-storage-design.md`

## Global Constraints
- Git: Tutte le modifiche e i commit devono avvenire esclusivamente sul branch `feature/auth-multitenant-storage`. Nessun commit su `master`, `main` o `develop`.
- Sicurezza: Nessuna password memorizzata in chiaro. Nessun endpoint relativo alle partite o ai dati accessibile senza token valido (Login Gate totale).
- Retrocompatibilità: Il database esistente `scoutanalyzer.db` deve migrare senza distruggere i dati esistenti, garantendo la creazione dell'utente predefinito `admin`.
- TDD: Ogni task segue il ciclo Red-Green-Refactor provato tramite `pytest`.

## Review Focus
1. **Leakage di partite non autorizzate a utenti SCOUT:** Tentativi di chiamata diretta a `/api/matches/{id}/events` o `/api/matches/{id}/logs` con un ID partita appartenente ad altre squadre devono tassativamente restituire `403 Forbidden`.
2. **Bypass del caricamento DVW da parte di utenti SCOUT:** Chiamate dirette a `/api/audit/file` o `/api/audit/upload` devono essere bloccate a livello di backend con `403 Forbidden`.
3. **Session Lifetime differenziata:** Verificare che il token di un utente SCOUT contenga scadenza coerente con la finestra scorrevole (1 ora) mentre l'utente ADMIN o connesso localmente riceva token permanente/30 giorni.
4. **Tracciamento IP e User-Agent:** Ogni tentativo di login (sia con successo che con errore) deve registrare una riga in `user_logins`.
5. **Autocancellazione Admin:** Un amministratore non può cancellare se stesso se è l'unico utente ADMIN nel sistema.

---

### Task 1: Scaffolding, Dipendenze e Tabelle Database (Users, UserTeams, UserLogins)

**Files:**
- Modify: `requirements.txt`
- Modify: `database/schema.sql`
- Modify: `database/setup_db.py`
- Test: `tests/test_auth_db_setup.py`

**Interfaces:**
- Consumes: Configurazione SQLite standard
- Produces: Tabelle `users`, `user_teams`, `user_logins`, colonne `storage_path` e `file_hash` in `matches`, utente `admin` predefinito in `setup_db.py`.

- [ ] **Step 1: Scrivi il test di configurazione database per utenti e login (RED)**

```python
# tests/test_auth_db_setup.py
import sqlite3
from database.setup_db import create_database

def test_auth_tables_and_default_admin(tmp_path):
    test_db = str(tmp_path / "test_auth.db")
    create_database(test_db)
    conn = sqlite3.connect(test_db)
    cur = conn.cursor()

    # Verifica presenza tabelle
    cur.execute("SELECT name FROM sqlite_master WHERE type='table'")
    tables = [r[0] for r in cur.fetchall()]
    assert "users" in tables
    assert "user_teams" in tables
    assert "user_logins" in tables

    # Verifica colonne matches
    cur.execute("PRAGMA table_info(matches)")
    m_cols = [r[1] for r in cur.fetchall()]
    assert "storage_path" in m_cols
    assert "file_hash" in m_cols

    # Verifica creazione utente admin predefinito
    cur.execute("SELECT username, role, is_active FROM users WHERE username = 'admin'")
    row = cur.fetchone()
    assert row is not None
    assert row[1] == "ADMIN"
    assert row[2] == 1
    conn.close()
```

- [ ] **Step 2: Esegui il test per verificare che fallisca**

Esegui: `pytest tests/test_auth_db_setup.py`  
Atteso: FAIL (tabelle o colonne non presenti).

- [ ] **Step 3: Aggiorna `requirements.txt`, `database/schema.sql` e `database/setup_db.py`**

Aggiungi a `requirements.txt`:
```
pyjwt>=2.8.0
passlib[bcrypt]>=1.7.4
bcrypt>=4.1.0
```
Installa le dipendenze in `venv`.  
Aggiungi a `schema.sql` e `setup_db.py` le definizioni DDL per `users`, `user_teams`, `user_logins` e le colonne `storage_path`, `file_hash` in `matches`.  
Aggiungi in `setup_db.py` la creazione dell'utente predefinito `admin` con password predefinita hashata con bcrypt.

- [ ] **Step 4: Esegui il test per verificare che passi (GREEN)**

Esegui: `pytest tests/test_auth_db_setup.py`  
Atteso: PASS

- [ ] **Step 5: Commit sul branch `feature/auth-multitenant-storage`**

```bash
git add requirements.txt database/schema.sql database/setup_db.py tests/test_auth_db_setup.py
git commit -m "feat(db): add users, user_teams, user_logins tables and default admin seeding"
```

---

### Task 2: Core Auth Engine (JWT, Password Hashing, Login Tracking con IP & Expiration)

**Files:**
- Create: `src/api/auth.py`
- Test: `tests/test_auth_engine.py`

**Interfaces:**
- Consumes: `users`, `user_logins` da SQLite
- Produces:
  - `hash_password(raw_password: str) -> str`
  - `verify_password(raw_password: str, hashed_password: str) -> bool`
  - `create_access_token(user_id: int, username: str, role: str, is_local: bool) -> str`
  - `verify_access_token(token: str) -> Dict[str, Any]`
  - `get_current_user(...) -> User`
  - `require_admin(...) -> User`

- [ ] **Step 1: Scrivi il test di unità per hashing, JWT e login (RED)**

```python
# tests/test_auth_engine.py
import pytest
from src.api.auth import hash_password, verify_password, create_access_token, verify_access_token

def test_password_hashing():
    pw = "SuperSecret123!"
    h = hash_password(pw)
    assert h != pw
    assert verify_password(pw, h) is True
    assert verify_password("WrongPassword", h) is False

def test_jwt_token_generation_and_verification():
    token = create_access_token(user_id=1, username="admin", role="ADMIN", is_local=True)
    payload = verify_access_token(token)
    assert payload["sub"] == "1"
    assert payload["username"] == "admin"
    assert payload["role"] == "ADMIN"
```

- [ ] **Step 2: Esegui il test per verificare che fallisca**

Esegui: `pytest tests/test_auth_engine.py`  
Atteso: FAIL (`src/api/auth.py` non presente).

- [ ] **Step 3: Implementa `src/api/auth.py`**

Implementa:
- Hashing password con `passlib.context.CryptContext(schemes=["bcrypt"], deprecated="auto")`.
- JWT encoding/decoding con `pyjwt` (chiave segreta caricabile da `config.json` o variabile d'ambiente, con fallback sicuro).
- Scadenza: 30 giorni per `ADMIN` o `is_local=True`, 60 minuti (sliding window) per `SCOUT`.
- Dependency FastAPI: `oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login")`.
- `get_current_user` estrae utente dal DB verificando che sia `is_active == 1`.
- `require_admin` solleva `403 Forbidden` se `role != 'ADMIN'`.

- [ ] **Step 4: Esegui il test per verificare che passi (GREEN)**

Esegui: `pytest tests/test_auth_engine.py`  
Atteso: PASS

- [ ] **Step 5: Commit sul branch `feature/auth-multitenant-storage`**

```bash
git add src/api/auth.py tests/test_auth_engine.py
git commit -m "feat(auth): add password hashing, JWT token lifecycle and role dependencies"
```

---

### Task 3: Login Endpoint, Audit Accessi (IP) & Protezione API Multi-Tenant

**Files:**
- Modify: `src/api/routes.py`
- Modify: `web_app.py`
- Test: `tests/test_multitenant_access.py`

**Interfaces:**
- Consumes: `src/api/auth.py`, `scoutanalyzer.db`
- Produces:
  - `POST /api/auth/login` (registra IP in `user_logins`)
  - `GET /api/auth/me`
  - Filtro multi-tenancy su `/api/matches` e sub-risorse per squadra assegnata
  - Blocco `403 Forbidden` su upload per utenti `SCOUT`.

- [ ] **Step 1: Scrivi i test di integrazione per login, tracciamento IP e multi-tenancy (RED)**

```python
# tests/test_multitenant_access.py
from fastapi.testclient import TestClient
from database.setup_db import create_database
from web_app import app
import sqlite3

client = TestClient(app)

def test_login_tracking_and_multitenant_matches(tmp_path):
    test_db = str(tmp_path / "test_mt.db")
    create_database(test_db)
    # Imposta db per i test se necessario o usa default
    
    # Tentativo login fallito -> registra FAILED in user_logins
    res_fail = client.post("/api/auth/login", json={"username": "fake", "password": "wrong"})
    assert res_fail.status_code == 401

    # Login admin -> successo
    res_ok = client.post("/api/auth/login", json={"username": "admin", "password": "adminpassword"})
    assert res_ok.status_code == 200
    token = res_ok.json()["access_token"]

    # Verifica headers autenticati
    headers = {"Authorization": f"Bearer {token}"}
    res_me = client.get("/api/auth/me", headers=headers)
    assert res_me.status_code == 200
    assert res_me.json()["role"] == "ADMIN"
```

- [ ] **Step 2: Esegui il test per verificare che fallisca**

Esegui: `pytest tests/test_multitenant_access.py`  
Atteso: FAIL (endpoint `/api/auth/login` o me non ancora registrati).

- [ ] **Step 3: Implementa gli endpoint di autenticazione e i filtri di tenancy in `src/api/routes.py`**

1. Aggiungi `POST /api/auth/login`:
   - Estrae IP client (`request.client.host` o `X-Forwarded-For`) e `User-Agent`.
   - Verifica credenziali.
   - Inserisce record in `user_logins (user_id, username, ip_address, user_agent, login_status)`.
   - Restituisce `access_token`, `token_type`, `user` (`id`, `username`, `role`, `team_ids`).
2. Aggiungi `GET /api/auth/me` con `Depends(get_current_user)`.
3. Proteggi `GET /api/matches` e sub-risorse:
   - Se `role == 'SCOUT'`, filtra le gare unicamente sulle squadre in `user_teams`.
   - `verify_match_access` solleva `403` se uno scout tenta di accedere a una partita non sua.
   - `POST /api/audit/file` e `POST /api/audit/upload` protetti con `Depends(require_admin)`.

- [ ] **Step 4: Esegui il test per verificare che passi (GREEN)**

Esegui: `pytest tests/test_multitenant_access.py`  
Atteso: PASS

- [ ] **Step 5: Commit sul branch `feature/auth-multitenant-storage`**

```bash
git add src/api/routes.py tests/test_multitenant_access.py web_app.py
git commit -m "feat(routes): login endpoint with IP audit tracking and multi-tenant match filters"
```

---

### Task 4: Pannelli Admin Backend (Gestione Utenti, Squadre e Regole Correlate)

**Files:**
- Create: `src/api/admin_routes.py`
- Modify: `web_app.py`
- Test: `tests/test_admin_api.py`

**Interfaces:**
- Consumes: `users`, `user_teams`, `user_logins`, `config/datavalley_specs.json`
- Produces:
  - `GET /api/admin/users`, `POST /api/admin/users`, `PUT /api/admin/users/{id}`, `DELETE /api/admin/users/{id}`
  - `GET /api/admin/teams`
  - `GET /api/admin/logins`
  - `GET /api/admin/rules/terminal`, `POST /api/admin/rules/terminal`, `PUT /api/admin/rules/terminal/{index}`, `DELETE /api/admin/rules/terminal/{index}`
  - `POST /api/admin/rules/revalidate`

- [ ] **Step 1: Scrivi il test delle API Admin (RED)**

```python
# tests/test_admin_api.py
from fastapi.testclient import TestClient
from web_app import app

client = TestClient(app)

def test_admin_endpoints_require_admin():
    # Chiamata anonima -> 401
    res = client.get("/api/admin/users")
    assert res.status_code == 401

def test_admin_terminal_rules_crud(admin_token):
    headers = {"Authorization": f"Bearer {admin_token}"}
    res = client.get("/api/admin/rules/terminal", headers=headers)
    assert res.status_code == 200
    assert isinstance(res.json(), list)
```

- [ ] **Step 2: Esegui il test per verificare che fallisca**

Esegui: `pytest tests/test_admin_api.py`  
Atteso: FAIL.

- [ ] **Step 3: Implementa `src/api/admin_routes.py` e montalo in `web_app.py`**

1. Implementa router `admin_router = APIRouter(prefix="/api/admin", tags=["Admin"], dependencies=[Depends(require_admin)])`.
2. CRUD Utenti con associazione atomica delle squadre in `user_teams` (transazione SQLite).
3. Lettura e paginazione di `user_logins` per visualizzare gli ultimi accessi (IP, orario, esito).
4. CRUD Regole Tocchi Correlati su `config/datavalley_specs.json`:
   - Validazione schemi input Pydantic.
   - Scrittura sicura su file JSON e ricaricamento a caldo del motore.
   - Endpoint `POST /api/admin/rules/revalidate` per rieseguire `MatchStateEngine` sulle partite registrate.

- [ ] **Step 4: Esegui il test per verificare che passi (GREEN)**

Esegui: `pytest tests/test_admin_api.py`  
Atteso: PASS

- [ ] **Step 5: Commit sul branch `feature/auth-multitenant-storage`**

```bash
git add src/api/admin_routes.py tests/test_admin_api.py web_app.py
git commit -m "feat(admin): endpoints for user management, login audit log and terminal rule configurator"
```

---

### Task 5: Centralized Storage Manager & Script di Migrazione

**Files:**
- Create: `src/storage_manager.py`
- Create: `scripts/migrate_local_files_to_storage.py`
- Modify: `src/api/routes.py`
- Test: `tests/test_storage_manager.py`

**Interfaces:**
- Consumes: File `.dvw` caricati
- Produces:
  - `StorageManager.save_dvw(file_bytes, filename, season) -> str (relative_path)`
  - `StorageManager.get_dvw_bytes(relative_path) -> bytes`
  - Salvataggio `storage_path` e `file_hash` in `matches`.

- [ ] **Step 1: Scrivi i test di unità per StorageManager (RED)**

```python
# tests/test_storage_manager.py
import os
from src.storage_manager import StorageManager

def test_storage_manager_save_and_retrieve(tmp_path):
    storage_dir = str(tmp_path / "storage" / "dvw")
    mgr = StorageManager(base_dir=storage_dir)
    
    sample_content = b"[3MATCH]\nTEST;\n"
    rel_path, file_hash = mgr.save_dvw(sample_content, "sample.dvw", season="2026")
    
    assert os.path.exists(os.path.join(storage_dir, rel_path))
    retrieved = mgr.get_dvw_bytes(rel_path)
    assert retrieved == sample_content
```

- [ ] **Step 2: Esegui il test per verificare che fallisca**

Esegui: `pytest tests/test_storage_manager.py`  
Atteso: FAIL.

- [ ] **Step 3: Implementa `src/storage_manager.py` e script di migrazione**

1. Implementa `StorageManager`:
   - Archiviazione in `storage/dvw/{season}/{clean_filename}`.
   - Calcolo hash SHA-256 e MD5 per controllo integrità.
   - Metodi di lettura, salvataggio e cancellazione.
   - Predisposizione S3: se `STORAGE_BACKEND == "s3"`, si appoggia alle credenziali `S3_*`.
2. Aggiorna `/api/audit/upload`:
   - Salva il file tramite `StorageManager`.
   - Registra `storage_path` e `file_hash` nel record `matches`.
3. Crea `scripts/migrate_local_files_to_storage.py` per copiare lo storico di `D:\Volley\B1FB` in `storage/dvw/`.

- [ ] **Step 4: Esegui il test per verificare che passi (GREEN)**

Esegui: `pytest tests/test_storage_manager.py`  
Atteso: PASS

- [ ] **Step 5: Commit sul branch `feature/auth-multitenant-storage`**

```bash
git add src/storage_manager.py scripts/migrate_local_files_to_storage.py src/api/routes.py tests/test_storage_manager.py
git commit -m "feat(storage): centralized managed storage for DVW files and historical migration script"
```

---

### Task 6: Frontend Login Gate, Navigazione Utente e Modali Admin

**Files:**
- Modify: `static/index.html`
- Modify: `static/style.css`
- Modify: `static/app.js`
- Test: `tests/test_frontend_auth_assets.py`

**Interfaces:**
- Consumes: REST API `/api/auth/*` e `/api/admin/*`
- Produces:
  - Schermata di login a pieno schermo (Login Gate)
  - Badge utente con Logout nell'header
  - Modale Gestione Utenti con multi-selezione squadre
  - Modale Configuratore Regole Correlate
  - Modale Log Accessi

- [ ] **Step 1: Scrivi il test di verifica degli asset statici per autenticazione (RED)**

```python
# tests/test_frontend_auth_assets.py
import os

def test_auth_frontend_elements():
    with open("static/index.html", "r", encoding="utf-8") as f:
        html = f.read()
    assert "login-overlay" in html
    assert "btn-login" in html
    assert "admin-users-modal" in html
    assert "admin-rules-modal" in html
    assert "user-badge" in html
```

- [ ] **Step 2: Esegui il test per verificare che fallisca**

Esegui: `pytest tests/test_frontend_auth_assets.py`  
Atteso: FAIL.

- [ ] **Step 3: Implementa il Login Gate e i componenti Admin in `index.html`, `style.css` e `app.js`**

1. **`index.html`**:
   - Inserisci `#login-overlay`: scheda di login elegante che copre la schermata quando `authToken` non è presente o è scaduto.
   - Header: pulsanti Admin *"👥 Utenti"*, *"⚙️ Regole"*, *"📋 Accessi"*, badge `👤 [Username] ([Ruolo])` e pulsante *"Logout"*.
   - Modale Gestione Utenti: form (username, pass, email, ruolo) + lista scrollabile di checkbox squadre con ricerca rapida + tabella utenti esistenti.
   - Modale Regole Correlate: tabella delle regole esistenti da `datavalley_specs.json` con form di aggiunta/eliminazione rapida.
   - Modale Log Accessi: visualizzazione degli ultimi login con IP, data e stato.
2. **`style.css`**:
   - Stile del `#login-overlay` con sfondo scuro a gradiente e card elegante.
   - Stili per il badge utente, pulsanti admin dedicati e form di selezione squadre.
3. **`app.js`**:
   - Interceptor per richieste API: aggiunge automaticamente `Authorization: Bearer <token>`.
   - Riconoscimento rinnovo sliding session: se riceve `X-Renewed-Token`, aggiorna `localStorage`.
   - Se riceve `401 Unauthorized`, cancella il token e mostra immediatamente il `#login-overlay`.
   - Gestione visibilità selettiva in base al ruolo (`ADMIN` vs `SCOUT`).

- [ ] **Step 4: Esegui il test per verificare che passi (GREEN)**

Esegui: `pytest tests/test_frontend_auth_assets.py`  
Atteso: PASS

- [ ] **Step 5: Commit sul branch `feature/auth-multitenant-storage`**

```bash
git add static/index.html static/style.css static/app.js tests/test_frontend_auth_assets.py
git commit -m "feat(ui): login gate overlay, admin user management, rule configurator and login audit modals"
```

---

### Task 7: Verifica E2E del Flusso Completo (Auth, Multi-Tenancy, Storage e Regole)

**Files:**
- Create: `tests/test_e2e_auth_workflow.py`

**Interfaces:**
- Consumes: Tutta l'applicazione (FastAPI, SQLite, StorageManager, StateEngine)
- Produces: Verifica integrata end-to-end automatizzata.

- [ ] **Step 1: Scrivi il test E2E completo**

```python
# tests/test_e2e_auth_workflow.py
from fastapi.testclient import TestClient
from web_app import app

client = TestClient(app)

def test_full_auth_multitenant_lifecycle():
    # 1. Login Admin
    res_login = client.post("/api/auth/login", json={"username": "admin", "password": "adminpassword"})
    assert res_login.status_code == 200
    admin_token = res_login.json()["access_token"]
    admin_headers = {"Authorization": f"Bearer {admin_token}"}

    # 2. Creazione utente SCOUT con assegnazione a singola squadra (es. team_id 9)
    res_cu = client.post("/api/admin/users", json={
        "username": "scout_vicenza",
        "password": "Password123!",
        "email": "scout@vicenza.it",
        "role": "SCOUT",
        "team_ids": [9]
    }, headers=admin_headers)
    assert res_cu.status_code == 201
    
    # 3. Login SCOUT
    res_scout_login = client.post("/api/auth/login", json={"username": "scout_vicenza", "password": "Password123!"})
    assert res_scout_login.status_code == 200
    scout_token = res_scout_login.json()["access_token"]
    scout_headers = {"Authorization": f"Bearer {scout_token}"}

    # 4. Verifica che SCOUT veda solo gare di team 9
    res_matches = client.get("/api/matches", headers=scout_headers)
    assert res_matches.status_code == 200
    for m in res_matches.json():
        assert m["home_code"] == "VIC26" or m["away_code"] == "VIC26" or m.get("home_team_id") == 9 or m.get("away_team_id") == 9

    # 5. Verifica che SCOUT riceva 403 Forbidden su upload
    res_upload = client.post("/api/audit/file", json={"file_path": "dummy.dvw"}, headers=scout_headers)
    assert res_upload.status_code == 403

    # 6. Verifica audit log accessi
    res_logins = client.get("/api/admin/logins", headers=admin_headers)
    assert res_logins.status_code == 200
    assert len(res_logins.json()) >= 2
```

- [ ] **Step 2: Esegui l'intera suite di test del progetto**

Esegui: `pytest tests/ -v`  
Atteso: Tutti i test (19 precedenti + 7 nuovi) passano (100% green).

- [ ] **Step 3: Commit finale sul branch `feature/auth-multitenant-storage`**

```bash
git add tests/test_e2e_auth_workflow.py
git commit -m "test(e2e): end-to-end verification of authentication, multitenant isolation and audit log"
```
