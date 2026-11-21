# Performance Lista Gare, Validazione Puntuale/Massiva e Filtro Anomalie Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Accelerate match list performance by storing precalculated summary metrics in the database, provide single and bulk match validation actions in the admin view with a >30 threshold confirmation, and resolve the dashboard anomaly filter type coercion and cross-match state bugs.

**Architecture:** 
1. Denormalize summary match metrics (`home_sets_won`, `away_sets_won`, `final_score`, `set_scores`, `sets_count`, `events_count`, `logs_count`, `scout_author`) directly on the `matches` table to turn `GET /api/matches` into a single, instant SQL query without N+1 subqueries.
2. Expose `POST /api/admin/matches/{id}/revalidate` alongside `POST /api/admin/rules/revalidate` with dedicated UI triggers in `#view-admin-matches` (per-row button and bulk button with confirmation alert if > 30 matches).
3. Fix JavaScript type coercion in dashboard event filtering to support both SQLite integer (`0`/`1`) and PostgreSQL boolean (`false`/`true`) flags, ensure filter state is preserved on match switch, and surface set-level anomalies from `validation_logs` when filtering by errors.

**Tech Stack:** Python 3.10+, FastAPI, SQLite 3, PostgreSQL (psycopg 3), Vanilla JS, HTML5, CSS3, Pytest.

**Spec:** `docs/superpowers/specs/2026-11-21-matches-performance-validation-and-anomalies-filter-design.md`

## Global Constraints

- Never commit secrets or API keys.
- Preserve zero-regression status on all existing 51 automated tests.
- Maintain full cross-database compatibility between SQLite (local) and PostgreSQL (Neon/Render).
- All database modifications must be accompanied by non-destructive schema migrations (`IF NOT EXISTS` / `PRAGMA table_info`).

## Review Focus

1. `is_valid` type parity: SQLite returns integer `0`/`1`, PostgreSQL returns boolean `false`/`true`. Code must handle both identically.
2. Incomplete matches or matches without events: `final_score` defaults to `'0 - 0'` and `set_scores` to `''` or `'N.D.'` without `None` errors.
3. Multi-tenant security: `GET /api/matches` must continue to enforce user team restrictions for non-admin accounts.
4. Concurrency & idempotency: revalidation of a match must replace semantic logs safely without duplicating actions or rotations.
5. Cross-match filter retention: switching matches via `#match-select` while `#filter-errors-only` is checked must immediately re-apply error filtering on the new match.

---

### Task 1: Database Schema & Migration for Precalculated Match Summary Metrics

**Files:**
- Modify: `database/schema.sql`
- Modify: `database/setup_db.py`
- Modify: `scripts/migrate_sqlite_to_postgres.py`
- Modify: `src/db.py`
- Test: `tests/test_db_setup.py`

**Interfaces:**
- Produces: `refresh_match_summary_metrics(conn_or_cursor, match_id: int) -> dict` in `src/db.py` (or shared helper). Updates columns `home_sets_won`, `away_sets_won`, `final_score`, `set_scores`, `sets_count`, `events_count`, `logs_count`, `scout_author` on `matches`.

- [ ] **Step 1: Write the failing test**

```python
# In tests/test_db_setup.py
def test_matches_schema_has_summary_metrics(tmp_path):
    from database.setup_db import create_database
    import sqlite3
    db_file = str(tmp_path / "test_schema.db")
    create_database(db_file)
    conn = sqlite3.connect(db_file)
    c = conn.cursor()
    c.execute("PRAGMA table_info(matches)")
    cols = {r[1] for r in c.fetchall()}
    for expected_col in ["home_sets_won", "away_sets_won", "final_score", "set_scores", "sets_count", "events_count", "logs_count", "scout_author"]:
        assert expected_col in cols, f"Missing column {expected_col} in matches table"
    conn.close()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_db_setup.py -k test_matches_schema_has_summary_metrics -v`
Expected: FAIL (missing summary columns in matches table)

- [ ] **Step 3: Implement columns and `refresh_match_summary_metrics`**

1. In `database/schema.sql` and `database/setup_db.py`: add summary columns to `CREATE TABLE matches` and `ALTER TABLE matches ADD COLUMN ...` migration.
2. In `scripts/migrate_sqlite_to_postgres.py`: add columns to `PG_SCHEMA` and `ALTER TABLE matches ADD COLUMN IF NOT EXISTS ...`.
3. In `src/db.py`: implement `refresh_match_summary_metrics(conn_or_cursor, match_id: int)` which calculates summary fields from `match_sets`, `events`, and `validation_logs`, extracts scout author from `match_code`, and updates the `matches` row.

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_db_setup.py -v`
Expected: PASS

- [ ] **Step 5: Verify backfill on local DB**

Run a one-off verification script to ensure all existing matches have their summary metrics populated.

---

### Task 2: High-Performance `GET /api/matches` and Automated Sync on Ingest & State Engine

**Files:**
- Modify: `src/api/routes.py:115-195`
- Modify: `src/ingestion_manager.py:160-175`
- Modify: `src/state_engine.py:120-135`
- Test: `tests/test_api.py`

**Interfaces:**
- Consumes: `refresh_match_summary_metrics` from Task 1.
- Produces: `GET /api/matches` single SQL query returning all enriched fields directly from `matches`.

- [ ] **Step 1: Write the failing test**

```python
# In tests/test_api.py
def test_list_matches_returns_precalculated_summary_fields(admin_client):
    res = admin_client.get("/api/matches")
    assert res.status_code == 200
    matches = res.json()
    if len(matches) > 0:
        m = matches[0]
        assert "final_score" in m
        assert "set_scores" in m
        assert "home_sets_won" in m
        assert "away_sets_won" in m
        assert "logs_count" in m
```

- [ ] **Step 2: Run test to verify it fails or asserts expected contract**

Run: `pytest tests/test_api.py -k test_list_matches_returns_precalculated_summary_fields -v`

- [ ] **Step 3: Update `routes.py`, `ingestion_manager.py`, and `state_engine.py`**

1. In `src/ingestion_manager.py`: call `refresh_match_summary_metrics` before `conn.commit()`.
2. In `src/state_engine.py`: call `refresh_match_summary_metrics` before `conn.commit()`.
3. In `src/api/routes.py` `list_matches`: replace the N+1 loop and subqueries with a single `SELECT m.id, m.match_code, m.scheduled_date, m.home_team_id, m.away_team_id, m.home_sets_won, m.away_sets_won, m.final_score, m.set_scores, m.sets_count, m.events_count, m.logs_count, m.scout_author, ht.code as home_code, ht.name as home_name, at.code as away_code, at.name as away_name FROM matches m LEFT JOIN teams ht ...`.

- [ ] **Step 4: Run tests to verify it passes**

Run: `pytest tests/test_api.py -v`
Expected: PASS

---

### Task 3: Backend Single Match Revalidation Endpoint

**Files:**
- Modify: `src/api/admin_routes.py`
- Test: `tests/test_admin_api.py`

**Interfaces:**
- Produces: `POST /api/admin/matches/{match_id}/revalidate` returning `{"status": "SUCCESS", "match_id": match_id, "issues_count": n, "match": dict}`.

- [ ] **Step 1: Write the failing test**

```python
# In tests/test_admin_api.py
def test_admin_revalidate_single_match(admin_client):
    # Retrieve first match
    matches_res = admin_client.get("/api/matches")
    assert matches_res.status_code == 200
    matches = matches_res.json()
    if len(matches) > 0:
        target_id = matches[0]["id"]
        res = admin_client.post(f"/api/admin/matches/{target_id}/revalidate")
        assert res.status_code == 200
        data = res.json()
        assert data["status"] == "SUCCESS"
        assert data["match_id"] == target_id
        assert "issues_count" in data
        assert "match" in data
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_admin_api.py -k test_admin_revalidate_single_match -v`
Expected: FAIL (404/405 Not Found endpoint)

- [ ] **Step 3: Implement `POST /api/admin/matches/{match_id}/revalidate`**

1. In `src/api/admin_routes.py`: add endpoint with `current_user: User = Depends(require_admin)`.
2. Instantiate `MatchStateEngine(match_id=match_id)` and invoke `process_match()`.
3. Call `refresh_match_summary_metrics(cursor, match_id)` to update summary table columns.
4. Retrieve the updated match record and return standard response.

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_admin_api.py -k test_admin_revalidate_single_match -v`
Expected: PASS

---

### Task 4: Frontend Actions on Admin Matches Page ("Valida Gara" & "Valida Tutte" with Alert > 30)

**Files:**
- Modify: `static/index.html`
- Modify: `static/app.js`
- Test: `tests/test_frontend_assets.py`

**Interfaces:**
- Produces:
  - Top action `#btn-admin-revalidate-all` in `#view-admin-matches` with alert check `matches.length > 30`.
  - Row action button `revalidateMatchFromAdmin(matchId)` in each row of `#admin-matches-tbody`.

- [ ] **Step 1: Write the failing test**

```python
# In tests/test_frontend_assets.py
def test_admin_matches_page_validation_buttons():
    with open("static/index.html", "r", encoding="utf-8") as f:
        html = f.read()
    with open("static/app.js", "r", encoding="utf-8") as f:
        js = f.read()

    assert "btn-admin-revalidate-all" in html
    assert "revalidateMatchFromAdmin" in js
    assert "handleAdminRevalidateAllMatches" in js
    assert "30" in js  # Threshold alert for > 30 matches
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_frontend_assets.py -k test_admin_matches_page_validation_buttons -v`
Expected: FAIL

- [ ] **Step 3: Implement UI and handlers in `index.html` and `app.js`**

1. In `static/index.html`: add `<button id="btn-admin-revalidate-all" class="btn btn-outline-primary">🔄 Valida Tutte le Gare</button>` in the admin matches header.
2. In `static/app.js`:
   - In `renderAdminMatchesTable()`: add `<button class="btn-sm btn-outline-secondary" onclick="revalidateMatchFromAdmin(${m.id})">🔄 Valida Gara</button>` to row actions.
   - Implement `revalidateMatchFromAdmin(matchId)`: calls `POST /api/admin/matches/${matchId}/revalidate`, updates row cells immediately.
   - Implement `handleAdminRevalidateAllMatches()`: checks `state.matches.length > 30`, prompts confirmation, calls `/api/admin/rules/revalidate`, shows loading indicator, and re-renders table.

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_frontend_assets.py -v`
Expected: PASS

---

### Task 5: Fix Dashboard Anomaly Filter & Cross-Match Synchronization

**Files:**
- Modify: `static/app.js:475-520` and `static/app.js:400-435`
- Test: `tests/test_frontend_assets.py`

**Interfaces:**
- Produces: Correct `isError` evaluation supporting `false`/`true` and `0`/`1`, preservation of `filterErrorsOnly.checked` across match switches, and display of set/match-level validation warnings.

- [ ] **Step 1: Write the failing test**

```python
# In tests/test_frontend_assets.py
def test_dashboard_anomaly_filter_robustness():
    with open("static/app.js", "r", encoding="utf-8") as f:
        js = f.read()

    # Must check boolean false/0 and error_note without relying strictly on === 1
    func_body = js[js.find("function renderEventsTable()"):js.find("function showEventOnCourt")]
    assert "ev.is_valid === 1" not in func_body
    assert "filterErrorsOnly.checked" in js
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_frontend_assets.py -k test_dashboard_anomaly_filter_robustness -v`
Expected: FAIL

- [ ] **Step 3: Implement robust filter in `static/app.js`**

1. In `renderEventsTable()`:
   ```javascript
   const isError = (ev.is_valid === 0 || ev.is_valid === false || Boolean(ev.error_note));
   if (state.errorsOnly && !isError) {
     return false;
   }
   ```
2. When `state.errorsOnly` is active:
   If there are validation logs in `state.logs` that are set-level or general (e.g. set score discrepancy, line_number is null or SET_x), prepend an alert row or banner in the table so user sees the discrepancy explanation.
3. In `selectMatch(matchId)`:
   Ensure `state.errorsOnly = filterErrorsOnly ? filterErrorsOnly.checked : false;` is respected when rendering the newly selected match.

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_frontend_assets.py -v`
Expected: PASS

---

### Task 6: Full Regression Verification & Live Sanity Check

**Files:**
- Run full pytest test suite across all 50+ tests.
- Verify zero syntax errors, lint warnings, or broken imports.

- [ ] **Step 1: Run full test suite**

Run: `pytest -v`
Expected: 100% PASS (51+ passed)
