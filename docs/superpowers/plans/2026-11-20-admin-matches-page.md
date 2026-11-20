# Admin Matches Page & Dropdown Cleanup Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Create a dedicated full-page admin view (`#view-admin-matches`) displaying all matches with scores, set breakdowns, event and anomaly counts, scout author, and actions (Open in Dashboard, Delete), and clean up the match selection dropdown to remove raw IDs.

**Architecture:** Enrich `GET /api/matches` backend response with set scores, final match score, and scout author. Structure the SPA into two full views (`#view-dashboard` and `#view-admin-matches`) with seamless navigation via `switchView()`. Format dropdown options cleanly without database IDs.

**Tech Stack:** Python 3.12, FastAPI, SQLite / PostgreSQL, Vanilla HTML5 / CSS3 / JavaScript.

**Spec:** `docs/superpowers/specs/2026-11-20-admin-matches-page-design.md`

## Global Constraints
- Dropdown options must NEVER display raw database IDs in their visible label text (`option.textContent`).
- Admin matches table must include columns: File Name, Scout Author, Home Team Name, Away Team Name, Final Score, Set Scores, Events Count, Anomalies Count, Actions (Open, Delete).
- "Apri Gara" must navigate back to the main dashboard (`#view-dashboard`), set the selected match in `#match-select`, and render the court and play-by-play.
- Zero regressions across existing test suite (all 46 tests green).

---

### Task 1: Backend Extension of `GET /api/matches`

**Files:**
- Modify: `src/api/routes.py:120-155`
- Test: `tests/test_api.py`

**Interfaces:**
- `GET /api/matches`: each match dictionary includes `final_score: str` (e.g. `"3 - 1"`), `set_scores: str` (e.g. `"25-21, 23-25, 25-18, 25-20"`), `scout_author: str` (e.g. `"marco"` or `"N.D."`), `home_sets_won: int`, `away_sets_won: int`.

- [ ] **Step 1: Write failing test in tests/test_api.py**
Verify that `GET /api/matches` returns `final_score`, `set_scores`, and `scout_author`.

- [ ] **Step 2: Run test to verify failure**
Run: `pytest tests/test_api.py -k "test_matches_list_enriched_fields" -v`
Expected: FAIL

- [ ] **Step 3: Implement enrichment in src/api/routes.py**
Query match_sets for each match, compute sets won, assemble set scores list, and extract scout author from `match_code` using regex `_([a-zA-Z0-9]+)$` or `_sync_([a-zA-Z0-9]+)`.

- [ ] **Step 4: Run test to verify PASS**
Run: `pytest tests/test_api.py -v`
Expected: PASS

- [ ] **Step 5: Commit**
```bash
git add src/api/routes.py tests/test_api.py
git commit -m "feat(api): enrich matches endpoint with final score, set scores and scout author"
```

---

### Task 2: Dropdown Cleanup in Frontend

**Files:**
- Modify: `static/app.js:364-377`
- Test: `tests/test_frontend_assets.py`

- [ ] **Step 1: Write test in tests/test_frontend_assets.py**
Verify `populateMatchSelect` uses clean format without ID in text.

- [ ] **Step 2: Update populateMatchSelect in static/app.js**
Format as: `${m.home_name || m.home_code} vs ${m.away_name || m.away_code} — ${m.match_code} (${m.scheduled_date || "N.D."})`
Ensure no `#${m.id}` or raw ID appears in textContent.

- [ ] **Step 3: Run frontend tests to verify PASS**
Run: `pytest tests/test_frontend_assets.py -v`
Expected: PASS

- [ ] **Step 4: Commit**
```bash
git add static/app.js tests/test_frontend_assets.py
git commit -m "style(ui): clean match dropdown labels to remove technical IDs"
```

---

### Task 3: Full-Page Admin Matches Management View

**Files:**
- Modify: `static/index.html`
- Modify: `static/style.css`
- Modify: `static/app.js`
- Test: `tests/test_frontend_assets.py`

- [ ] **Step 1: Write test in tests/test_frontend_assets.py**
Verify presence of `#view-dashboard`, `#view-admin-matches`, `#btn-back-to-dashboard`, `#admin-matches-full-table`.

- [ ] **Step 2: Update static/index.html**
Wrap main dashboard content in `<div id="view-dashboard" class="app-view active">`.
Create `<div id="view-admin-matches" class="app-view" style="display: none;">` with:
- Header bar: Title, subtitle, "⬅️ Torna alla Dashboard", "⚠️ Svuota Tutte le Gare".
- Full table with the 9 specified columns.

- [ ] **Step 3: Update static/style.css**
Style `.app-view`, `.view-header`, `.admin-matches-table-container`, `.badge-score`, `.scout-author-chip`.

- [ ] **Step 4: Update static/app.js**
Implement `switchView(viewName)`:
- Hides/shows views.
- When opening `admin-matches`: renders the enriched full table.
- Implement "👁️ Apri Gara" action: calls `selectMatch(m.id)` and `switchView('dashboard')`.
- Hook "🏐 Gestione Gare" in the admin dropdown to call `switchView('admin-matches')`.
- Hook "⬅️ Torna alla Dashboard" to call `switchView('dashboard')`.

- [ ] **Step 5: Run frontend tests to verify PASS**
Run: `pytest tests/test_frontend_assets.py -v`
Expected: PASS

- [ ] **Step 6: Commit**
```bash
git add static/index.html static/style.css static/app.js tests/test_frontend_assets.py
git commit -m "feat(ui): implement dedicated full-page admin matches view with open and delete actions"
```

---

### Task 4: Full Verification & Remote Deployment

- [ ] **Step 1: Run full test suite (all tests)**
Run `.\venv\Scripts\pytest.exe tests/ -q`
Expected: 100% green.

- [ ] **Step 2: Sync to GitHub and verify live on Render**
Push `feature/auth-multitenant-storage`, merge into `master` and `develop`, push all to `origin`.
Verify live response on `https://scoutanalyzer.onrender.com`.
