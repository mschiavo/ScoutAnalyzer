# Admin Match Management & Cloud Roster Storage Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Provide an administrative interface and API to manage and delete matches from the SQLite database, clean all historical sample matches, and migrate roster (.sq) storage and backups from local Windows disk paths to the Cloudflare R2 bucket.

**Architecture:** Extend `StorageManager` to handle roster files (`rosters/current/` and `rosters/backups/`) in Cloudflare R2 with local fallback. Refactor `RosterManager` to remove hardcoded Windows paths (`D:\Volley\...`) and rely entirely on `StorageManager`. Add admin endpoints `DELETE /api/matches/{id}` and `DELETE /api/admin/matches/clear`. Add an Admin Matches Modal and quick delete button in the frontend. Clean all sample matches from `scoutanalyzer.db`.

**Tech Stack:** Python 3.12/3.15, FastAPI, SQLite, boto3, Cloudflare R2, Vanilla HTML/CSS/JS.

**Spec:** Direct user directive for database cleanup, admin match deletion, and cloud roster storage.

## Global Constraints
- `scoutanalyzer.db` cleanup must remove all rows from `actions`, `rotations`, `events`, `validation_logs`, `match_sets`, `matches` while preserving `users`, `user_teams`, `user_logins`, `championships`, `groups`, `roles`, `teams`, `players`, `team_players`.
- Roster files in bucket must be placed under `rosters/current/{roster_code}.sq` and `rosters/backups/{roster_code}_{timestamp}.sq`.
- Deleting a match via `DELETE /api/matches/{id}` must cascade delete its match_sets, events, rotations, actions, validation_logs, and remove the raw DVW file from `StorageManager` (both local and R2).
- Zero regression across existing test suite.

---

### Task 1: Clean Sample Matches from SQLite Database

**Files:**
- Create: `scripts/clean_matches_db.py`
- Modify: `scoutanalyzer.db`

- [ ] **Step 1: Write scripts/clean_matches_db.py**
Deletes all records from `actions`, `rotations`, `events`, `validation_logs`, `match_sets`, `matches`.
Resets sequences in `sqlite_sequence`.
Verifies that `users` and `teams` are intact.

- [ ] **Step 2: Execute script to clean database**
Run `.\venv\Scripts\python.exe scripts/clean_matches_db.py`.
Verify that 0 matches remain in `matches`.

- [ ] **Step 3: Commit clean database**
```bash
git add scoutanalyzer.db scripts/clean_matches_db.py
git commit -m "chore(db): clean all sample matches, events and logs from database"
```

---

### Task 2: Admin Match Deletion Endpoints (`DELETE /api/matches/{id}` & `DELETE /api/admin/matches/clear`)

**Files:**
- Modify: `src/api/routes.py`
- Modify: `src/api/admin_routes.py`
- Test: `tests/test_api.py`
- Test: `tests/test_admin_api.py`

- [ ] **Step 1: Write test for match deletion in tests/test_admin_api.py**
Create a match via ingestion, call `DELETE /api/matches/{id}`, verify 200 OK and that match is gone from DB.
Call `DELETE /api/admin/matches/clear` as admin, verify all matches removed.

- [ ] **Step 2: Run test to verify failure**
Run `.\venv\Scripts\pytest.exe tests/test_admin_api.py -k "test_delete_match" -v`.
Expected: FAIL (404/405).

- [ ] **Step 3: Implement DELETE /api/matches/{match_id} and DELETE /api/admin/matches/clear**
Cascades deletion through foreign key tables and calls `StorageManager.delete_dvw(storage_path)`.

- [ ] **Step 4: Run tests to verify PASS**
Run `.\venv\Scripts\pytest.exe tests/test_admin_api.py -v`.
Expected: PASS.

- [ ] **Step 5: Commit**
```bash
git add src/api/routes.py src/api/admin_routes.py tests/test_admin_api.py
git commit -m "feat(api): add admin endpoints to delete individual match or clear all matches"
```

---

### Task 3: Migrate Roster (.sq) Storage to Cloud Bucket (StorageManager + RosterManager)

**Files:**
- Modify: `src/storage_manager.py`
- Modify: `src/roster_manager.py`
- Modify: `config/config.json`
- Test: `tests/test_storage_manager.py`
- Test: `tests/test_roster_extraction_and_subs.py`

- [ ] **Step 1: Write test for roster cloud storage in tests/test_storage_manager.py**
Test `save_roster` (current & backup) with S3 put_object and local cache.
Test `get_roster_bytes`.

- [ ] **Step 2: Run test to verify failure**
Run `.\venv\Scripts\pytest.exe tests/test_storage_manager.py -k "test_roster_storage" -v`.
Expected: FAIL (method not found).

- [ ] **Step 3: Implement save_roster and get_roster_bytes in src/storage_manager.py**
Implement storage under `rosters/current/` and `rosters/backups/`.

- [ ] **Step 4: Refactor src/roster_manager.py to use StorageManager**
Remove `r"D:\Volley\B1FB\rosters\..."`. Use `StorageManager` to store current roster and backups on Cloudflare R2 and local cache.
Update `config/config.json` to remove old Windows directory paths.

- [ ] **Step 5: Run tests to verify PASS**
Run `.\venv\Scripts\pytest.exe tests/test_storage_manager.py tests/test_roster_extraction_and_subs.py -v`.
Expected: PASS.

- [ ] **Step 6: Commit**
```bash
git add src/storage_manager.py src/roster_manager.py config/config.json tests/test_storage_manager.py
git commit -m "feat(rosters): migrate roster storage and backups to Cloudflare R2 and managed storage"
```

---

### Task 4: Frontend Admin Matches Management Modal & Quick Delete Button

**Files:**
- Modify: `static/index.html`
- Modify: `static/style.css`
- Modify: `static/app.js`
- Test: `tests/test_frontend_assets.py`

- [ ] **Step 1: Write test in tests/test_frontend_assets.py**
Verify existence of `btn-open-matches-modal`, `admin-matches-modal`, `btn-quick-delete-match`.

- [ ] **Step 2: Update static/index.html**
Add `🗑️ Elimina Gara` quick button next to `#match-select` (visible only for admin).
Add `btn-open-matches-modal` in `#admin-nav-group`.
Add `admin-matches-modal` with table of all matches, delete buttons, and "Svuota Tutte le Gare".

- [ ] **Step 3: Update static/app.js**
Implement match management modal logic: load matches, delete single match with confirmation, clear all matches with confirmation, update UI and reset displays.
Implement quick delete button on the active match.

- [ ] **Step 4: Update static/style.css**
Style the matches management table and delete buttons.

- [ ] **Step 5: Run frontend tests to verify PASS**
Run `.\venv\Scripts\pytest.exe tests/test_frontend_assets.py -v`.
Expected: PASS.

- [ ] **Step 6: Commit**
```bash
git add static/index.html static/style.css static/app.js tests/test_frontend_assets.py
git commit -m "feat(ui): add admin matches management modal and quick delete button"
```

---

### Task 5: Full Verification & Remote Deployment

- [ ] **Step 1: Run full test suite (all tests)**
Run `.\venv\Scripts\pytest.exe tests/ -q`.
Expected: 100% green.

- [ ] **Step 2: Sync to GitHub and verify live on Render**
Push `feature/auth-multitenant-storage`, merge into `master`, push `master`.
Verify live response on `https://scoutanalyzer.onrender.com`.
