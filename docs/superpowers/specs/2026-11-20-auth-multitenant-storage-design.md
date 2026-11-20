# Design Doc: Auth, Multi-Tenancy, Cloud Storage & Admin Rule Configurator

**Data:** 20 Novembre 2026  
**Autore:** Principal Software Architect & Domain Engineer  
**Stato:** Draft for Builder Check & Approval  
**Branch:** `feature/auth-multitenant-storage`

---

## 1. Intent e Motivazione

ScoutAnalyzer 3000 si evolve da applicazione di audit desktop/locale monoutente a una vera **piattaforma sportiva multi-utente, protetta e cloud-ready**.  
La nuova architettura risponde a quattro esigenze correlate:
1. **Protezione e Autenticazione Completa (Login Gate):** nessuna funzionalità o dato deve essere visibile senza autenticazione valida.
2. **Controllo Accessi Basato sui Ruoli (RBAC) e Multi-Tenancy:**
   * **ADMIN:** accesso completo, caricamento file DVW, gestione utenti e configurazione delle regole di dominio.
   * **SCOUT:** consultazione in sola lettura esclusivamente delle partite che coinvolgono una o più delle squadre ad esso assegnate; divieto assoluto di upload file.
   * **Politica di Scadenza Sessione Differenziata:** sessione perenne / a lunghissima scadenza (es. 30 giorni rinnovabili) per l'accesso in locale (localhost/admin), scadenza rigorosa a 2 ore di inattività per gli utenti standard SCOUT.
3. **Disaccoppiamento del Filesystem Locale verso Storage Centralizzato e Remoto:** migrazione dei file `.dvw` dall'hard disk locale (`D:\Volley\...`) a uno storage gestito e centralizzato (`storage/dvw/` server-side, predisposto per S3 / Cloudflare R2), per consentire il deploy remoto su server / cloud e la condivisione web.
4. **Configuratore Visuale delle Regole di Fine Azione (Admin Tool):** interfaccia utente interattiva per visualizzare, censire e modificare in modo dinamico i fondamentali correlati di fine scambio (es. attacco punto `A#` seguito da invasione a rete `B/`), aggiornando la configurazione JSON o DB senza riavvii del server.

---

## 2. Obiettivi, Non-Obiettivi e Anti-Obiettivi

### Obiettivi (Goals)
* **Login Gate Assoluto:** la pagina iniziale `/` reindirizza al form di login se l'utente non è autenticato. Nessun dato scout o anagrafico viene esposto senza token JWT valido.
* **Database Utenze e Relazioni:** tabelle `users` (con password cifrate in modo sicuro con salt tramite `bcrypt` o `argon2`) e `user_teams` (associazione 1:N tra utente e squadre abilitate).
* **Filtro Dati Multi-Tenant per Squadra:** gli endpoint `/api/matches` e `/api/matches/{id}` verificano il token dell'utente:
  * Se `role == 'ADMIN'`, restituiscono tutte le partite a database.
  * Se `role == 'SCOUT'`, restituiscono unicamente le partite in cui `home_team_id` o `away_team_id` coincide con uno dei `team_id` presenti in `user_teams` per quell'utente.
  * Gli endpoint di caricamento (`/api/audit/file`, `/api/audit/upload`) rifiutano le richieste con `403 Forbidden` se l'utente non è `ADMIN`.
* **Session Lifetime Intelligente:** emissione di JWT con claim `exp`:
  * Per utente `ADMIN` o connessioni locali: scadenza a 30 giorni.
  * Per utente `SCOUT`: scadenza rigorosa a 2 ore.
* **Pannelli ADMIN:**
  * **Gestione Utenti:** creazione e modifica utente (username, password, email, ruolo ADMIN/SCOUT, selezione multipla squadre con elenco ordinato e ricerca rapida).
  * **Configuratore Regole Tocchi Correlati:** visualizzatore e form editor per `permitted_terminal_followups` con dropdown per fondamentale (`A`, `S`, `B`, `D`, `R`, `E`, `F`), valutazione (`#`, `=`, `/`, ecc.), flag avversario/stessa squadra e descrizione.
* **Storage Provider Remoto / Gestito:**
  * Modulo `StorageManager` che archivia i file `.dvw` caricati in `storage/dvw/{season}/{match_code}.dvw`.
  * Memorizzazione del percorso relativo e hash MD5 nel record di `matches`.
  * Script di migrazione per trasferire lo storico esistente da `D:\Volley\B1FB` allo storage centralizzato.

### Non-Obiettivi (Non-Goals)
* Non costruire un server OAuth2 esterno complesso con identity provider di terze parti (Google, Auth0): l'autenticazione è autocontenuta e indipendente in ScoutAnalyzer tramite JWT interni.
* Non implementare permessi granulari per singolo set o singola atleta: il controllo accessi si basa sulle squadre associate all'utente.

### Anti-Obiettivi (Anti-Goals)
* Non lasciare nessuna API aperta o esposta a utenti non autenticati.
* Non memorizzare mai password in chiaro o con hashing debole (MD5/SHA1).

---

## 3. Vincoli Tecnici e di Piattaforma

* **Ambiente Backend:** Python 3.15, FastAPI, Uvicorn, SQLite 3 con Foreign Keys.
* **Librerie di Sicurezza:** `pyjwt` (o `python-jose`) per token JWT, `passlib` con `bcrypt` (o `argon2-cffi`) per password hashing.
* **Frontend:** Vanilla CSS / JavaScript ES6+ responsive con Dark Theme "ScoutAnalyzer 3000", esteso per supportare Login View e pannelli di amministrazione.
* **Git:** Branch dedicato `feature/auth-multitenant-storage`. Nessun commit sui branch protetti `master`, `main` o `develop`.

---

## 4. Architettura Tecnica Dettagliata

### 4.1 Schema Database (Aggiornamento DDL)

Vengono introdotte due nuove tabelle relazionali e aggiornata la tabella `matches`:

```sql
-- 14. Tabella Utenti
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    email TEXT UNIQUE,
    role TEXT CHECK(role IN ('ADMIN', 'SCOUT')) DEFAULT 'SCOUT',
    is_active BOOLEAN DEFAULT 1,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 15. Tabella Associazioni Utente - Squadre Autorizzate
CREATE TABLE IF NOT EXISTS user_teams (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    team_id INTEGER NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
    FOREIGN KEY (team_id) REFERENCES teams(id) ON DELETE CASCADE,
    UNIQUE(user_id, team_id)
);

-- 16. Tabella Tracciamento Accessi / Audit Login
CREATE TABLE IF NOT EXISTS user_logins (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,
    username TEXT NOT NULL,
    ip_address TEXT,
    user_agent TEXT,
    login_status TEXT CHECK(login_status IN ('SUCCESS', 'FAILED')) DEFAULT 'SUCCESS',
    logged_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE SET NULL
);

-- Aggiunta colonna percorso storage in matches (se non presente)
ALTER TABLE matches ADD COLUMN storage_path TEXT;
ALTER TABLE matches ADD COLUMN file_hash TEXT;
```

All'inizializzazione del database (`database/setup_db.py`), viene automaticamente garantita la presenza dell'utente predefinito amministratore:
* Username: `admin`
* Ruolo: `ADMIN`
* Password predefinita (configurabile o resettabile da CLI/script).

---

### 4.2 Gestione Autenticazione e Token JWT (`src/api/auth.py`)

* **Endpoint Login:** `POST /api/auth/login`
  * Input: `{"username": "...", "password": "..."}`
  * Processo:
    1. Verifica username nel database e password hashata con `bcrypt`.
    2. Registrazione immediata del tentativo in `user_logins` con:
       * `user_id` (se trovato)
       * `username`
       * `ip_address` (estratto da `request.client.host` o header `X-Forwarded-For`)
       * `user_agent`
       * `login_status`: `'SUCCESS'` o `'FAILED'`.
    3. Calcolo durata token (Sliding Window):
       * Se `role == 'ADMIN'` oppure client da `127.0.0.1` / `localhost`: `timedelta(days=30)` (non scade mai durante l'uso locale).
       * Se `role == 'SCOUT'`: `timedelta(minutes=60)` (finestra scorrevole di inattività da 1 ora, configurabile anche a 30m).
    4. Generazione JWT contenente `sub`, `username`, `role`, `exp`.
    5. Restituisce il token e le informazioni utente.
* **Sliding Session Renewal Middleware:**
  * Sulle richieste autenticate degli utenti `SCOUT`, se il token è valido e mancano meno di 30 minuti alla scadenza, il server include nell'header di risposta `X-Renewed-Token: <nuovo_token>` che il client memorizza automaticamente, garantendo che finché l'utente è attivo la sessione non scada mai.
* **Dependency FastAPI di Protezione:** `get_current_user` e `require_admin`
  * Estrae il token dall'header `Authorization: Bearer <token>` o dal cookie.
  * Valida la firma e la scadenza (`exp`). Se scaduto -> `401 Unauthorized`.
  * Fornisce l'oggetto `User` al router API.

---

### 4.3 Filtro Partite, Sicurezza Sub-Risorse e Multi-Tenancy

In `src/api/routes.py`:
* **Dependency Unificata `verify_match_access(match_id, current_user)`:**
  * Tutti gli endpoint relativi alla partita (`GET /api/matches/{id}`, `GET /api/matches/{id}/events`, `GET /api/matches/{id}/logs`) applicano obbligatoriamente questo controllo:
    * Se `current_user.role == 'ADMIN'`: accesso garantito.
    * Se `current_user.role == 'SCOUT'`: verifica che `home_team_id` o `away_team_id` della partita appartenga all'insieme dei `team_id` associati all'utente in `user_teams`. In caso contrario, restituisce immediatamente `403 Forbidden: Accesso negato alla partita`.
* `GET /api/matches`:
  * `ADMIN`: restituisce l'elenco completo di tutte le partite a database.
  * `SCOUT`: restituisce unicamente le partite in cui `home_team_id` o `away_team_id` coincide con uno dei `team_id` presenti in `user_teams` per quell'utente.
* `POST /api/audit/file` e `POST /api/audit/upload`:
  * Decorati con `Depends(require_admin)`. Se invocati da uno `SCOUT`, restituiscono `403 Forbidden: Operazione riservata agli amministratori`.

---

### 4.4 Storage Centralizzato dei File DVW (`src/storage_manager.py`)

* **Classe `StorageManager`:**
  * Gestisce il salvataggio fisico dei file `.dvw` caricati con pattern adapter.
  * Configurazione storage via `config.json` o variabili d'ambiente:
    * `STORAGE_BACKEND`: `"local"` (default) o `"s3"`.
    * `LOCAL_STORAGE_DIR`: default `"storage/dvw"`.
    * Per S3 / Cloudflare R2: `S3_ENDPOINT_URL`, `S3_ACCESS_KEY`, `S3_SECRET_KEY`, `S3_BUCKET_NAME`.
  * Path gestito standard: `storage/dvw/{season}/{match_code}.dvw`.
  * Calcola hash SHA256/MD5 per evitare duplicati fisici e verifica integrità.
  * Metodo `save_dvw(file_bytes, filename, season=None) -> str (relative_storage_path)`.
  * Metodo `get_dvw_path(relative_storage_path) -> str (local_path_or_temp)`.
* **Script di migrazione (`scripts/migrate_local_files_to_storage.py`):**
  * Esegue la scansione dei percorsi storici, copia i file nella cartella `storage/dvw/` e aggiorna i record in `matches.storage_path`.

---

### 4.5 Gestione Utenti & Regole Correlate (Pannelli Admin)

#### Endpoint Admin Utenti:
* `GET /api/admin/users`: lista utenti con conteggio squadre assegnate.
* `POST /api/admin/users`: creazione utente (username, password, email, role, team_ids).
* `PUT /api/admin/users/{id}`: modifica dati utente, cambio password e riassegnazione squadre.
* `DELETE /api/admin/users/{id}`: cancellazione utente (protetta contro l'autocancellazione dell'ultimo admin).
* `GET /api/admin/teams`: lista completa delle squadre censite per il selettore multi-selezione.

#### Endpoint Admin Regole Tocchi Correlati:
* `GET /api/admin/rules/terminal`: legge le regole attive da `config/datavalley_specs.json`.
* `POST /api/admin/rules/terminal`: aggiunge una nuova regola di tocco correlato consentito.
* `PUT /api/admin/rules/terminal/{index}`: modifica una regola esistente.
* `DELETE /api/admin/rules/terminal/{index}`: rimuove una regola.
* `POST /api/admin/rules/revalidate`: endpoint opzionale per rivalutare e aggiornare i log delle partite esistenti con le nuove regole.
* `MatchStateEngine` ricarica istantaneamente la configurazione aggiornata.

---

### 4.6 Flusso dell'Interfaccia Grafica Frontend (SPA)

1. **Schermata di Login:**
   * Al primo avvio o in assenza di token JWT in `localStorage`, l'intera interfaccia operativa è nascosta (`display: none`).
   * Viene visualizzata una scheda di autenticazione elegante centrata a schermo:
     * Logo ScoutAnalyzer 3000
     * Input Username e Password
     * Messaggi di errore espliciti (credenziali errate, sessione scaduta).
2. **Post-Login & Ruoli Utente:**
   * Una volta autenticato, il token viene memorizzato in `localStorage`.
   * L'header visualizza:
     * Badge utente: `👤 [username] (ADMIN / SCOUT)`
     * Pulsante **Logout** (elimina il token e rimanda al login).
     * Se `ADMIN`: pulsanti per navigare ai pannelli *"👥 Gestione Utenti"* e *"⚙️ Regole Correlate"*, oltre al pulsante *"➕ Nuovo Audit .DVW"*.
     * Se `SCOUT`: il pulsante di caricamento e i menu admin sono invisibili; il selettore partite mostra solo le partite autorizzate.
3. **Pannello Admin Utenti:**
   * Modale o scheda con tabella utenti (Username, Ruolo, Email, Squadre).
   * Form per aggiungere o modificare: username, password, email, ruolo (`ADMIN`/`SCOUT`) e lista checkbox di squadre per associazione immediata.
4. **Pannello Admin Regole:**
   * Visualizzazione a schede delle sequenze terminali consentite (es. `Attacco A# -> Muro B/`).
   * Form rapido per inserire nuove combinazioni con menu a discesa per Fondamentale e Valutazione.

---

## 5. Decisioni Delegate al Builder

* Selezione del costo computazionale dell'algoritmo di hashing password (raccomandato bcrypt con 12 round).
* Gestione della notifica di sessione scaduta con toast o alert contestuale prima del redirect al login.
* Posizionamento e impaginazione delle checkbox delle squadre nel form di registrazione utente.
