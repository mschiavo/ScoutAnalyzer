# Cloudflare R2 / S3 Storage Integration & Sports Hierarchy Cataloging Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Integrate Cloudflare R2 (S3-compatible) storage using `boto3`, cataloging DVW scout files into the sports hierarchy `<campionato>/<categoria>/<girone>/<giornata>/<filename>`, and enrich the upload modal with dedicated fields and smart auto-detection.

**Architecture:** Extend `StorageManager` with a `boto3` S3 client configured via `.env` (git-ignored) with automatic local cache fallback. Update `/api/audit/upload` and `/api/audit/file` to accept hierarchy parameters. Enhance the web UI modal to expose these parameters with intelligent client-side regex auto-detection from filename. Provide a migration script to upload existing matches directly to the live R2 bucket.

**Tech Stack:** Python 3.15, `boto3`, FastAPI, SQLite, Vanilla HTML/CSS/JS, Cloudflare R2 (S3 API).

**Spec:** `docs/superpowers/specs/2026-11-20-r2-cloud-storage-hierarchy-design.md`

## Global Constraints
- Strictly avoid committing credentials: `.env` must remain in `.gitignore`, `.env.example` provides placeholder values.
- Hierarchy format: `{campionato}/{categoria}/{girone}/{giornata:02d}/{filename}` (e.g. `2026-2027/B1F/B/03/&01_COR-VOL_Vicenza_b1fb_26_s.dvw`).
- Offline/Local resiliency: If S3 credentials are missing or the cloud bucket is unreachable, `StorageManager` must seamlessly fall back to local disk storage without failing match audits.
- No regression across all 35 existing tests.

## Review Focus
- Filename sanitization must preserve extension and eliminate dangerous path traversal (`../`) while allowing standard DVW prefixes (`&01_...`).
- Group normalization must uppercase the letter (e.g., `b` -> `B`).
- Giornata normalization must zero-pad numbers to 2 digits (e.g., `3` -> `03`).
- Form submission with missing hierarchy parameters must fall back to default values (`2026-2027`, `B1F`, `B`, `01`).
- S3 upload failure handling must log error and not crash local match creation.

---

### Task 1: Environment & Dependency Setup (`boto3`, `.env`, `.env.example`)

**Files:**
- Modify: `requirements.txt`
- Create: `.env` (git-ignored, real credentials)
- Create: `.env.example` (template with placeholders)
- Modify: `.gitignore` (ensure `.env` is ignored)

- [ ] **Step 1: Update requirements.txt to include boto3**
Add `boto3>=1.34.0` and `python-dotenv>=1.0.0` to `requirements.txt`.

- [ ] **Step 2: Install dependencies into venv**
Run `.\venv\Scripts\pip.exe install boto3 python-dotenv` and verify with `python -c "import boto3"`.

- [ ] **Step 3: Create .env and .env.example**
Write the Cloudflare R2 credentials to `.env`:
`STORAGE_BACKEND=s3`
`S3_ENDPOINT_URL=https://43ba6ad8c9582bba26c5261844a877f3.r2.cloudflarestorage.com`
`S3_ACCESS_KEY=aedc58c9c58efcdea03fb44139024438`
`S3_SECRET_KEY=b7f2cc433606a2d6cd923ebccd6c9afc1a49151550f0aeac5e767a9a6e31d835`
`S3_BUCKET_NAME=scoutanalyzer-dvw`

Create `.env.example` with masked placeholder values.

- [ ] **Step 4: Verify git status to confirm .env is ignored**
Run `git status` and verify that `.env` is NOT tracked.

- [ ] **Step 5: Commit dependencies and .env.example**
```bash
git add requirements.txt .env.example .gitignore
git commit -m "chore(deps): add boto3 and python-dotenv with .env.example template"
```

---

### Task 2: StorageManager Cloud Hierarchy & Boto3 Integration

**Files:**
- Modify: `src/storage_manager.py`
- Test: `tests/test_storage_manager.py`

**Interfaces:**
- `build_storage_key(campionato: str, categoria: str, girone: str, giornata: Union[int, str], filename: str) -> str`
- `StorageManager.save_dvw(file_bytes: bytes, filename: str, campionato: str = "2026-2027", categoria: str = "B1F", girone: str = "B", giornata: Union[int, str] = "01") -> Tuple[str, str]`
- `StorageManager.get_dvw_bytes(relative_path: str) -> bytes`

- [ ] **Step 1: Write unit tests for build_storage_key and S3 mock upload in tests/test_storage_manager.py**
Test normalization of `girone` (uppercase), `giornata` (zero-padded `03`), clean filename, and path formation.
Test mock S3 client `put_object` and `get_object` invocation.
Test fallback when S3 fails.

- [ ] **Step 2: Run tests to verify failure**
Run `.\venv\Scripts\pytest.exe tests/test_storage_manager.py -v`.
Expected: FAIL due to missing hierarchy parameters and `build_storage_key`.

- [ ] **Step 3: Implement build_storage_key and boto3 S3 backend in src/storage_manager.py**
Implement `build_storage_key`, initialize `boto3.client('s3', ...)` using loaded `.env` variables, implement `_upload_s3` and `_download_s3` with graceful fallback to disk.

- [ ] **Step 4: Run tests to verify PASS**
Run `.\venv\Scripts\pytest.exe tests/test_storage_manager.py -v`.
Expected: PASS.

- [ ] **Step 5: Commit**
```bash
git add src/storage_manager.py tests/test_storage_manager.py
git commit -m "feat(storage): implement boto3 S3 client with sports hierarchy cataloging"
```

---

### Task 3: Update API Endpoints with Hierarchy Parameters

**Files:**
- Modify: `src/api/routes.py`
- Test: `tests/test_api.py`

**Interfaces:**
- `POST /api/audit/upload`: receives `file`, `campionato` (Form), `categoria` (Form), `girone` (Form), `giornata` (Form).
- `POST /api/audit/file`: receives `file`, `campionato` (Form), `categoria` (Form), `girone` (Form), `giornata` (Form).

- [ ] **Step 1: Write failing test in tests/test_api.py for upload with hierarchy metadata**
Verify that `/api/audit/file` and `/api/audit/upload` store match with `storage_path` matching `{campionato}/{categoria}/{girone}/{giornata}/{filename}`.

- [ ] **Step 2: Run test to verify failure**
Run `.\venv\Scripts\pytest.exe tests/test_api.py -k "test_upload_with_hierarchy" -v`.
Expected: FAIL.

- [ ] **Step 3: Update routes.py to accept Form parameters and pass to StorageManager**
Extract `campionato`, `categoria`, `girone`, `giornata` from Form with default fallbacks, pass to `storage.save_dvw(...)`.

- [ ] **Step 4: Run tests to verify PASS**
Run `.\venv\Scripts\pytest.exe tests/test_api.py tests/test_admin_api.py -v`.
Expected: PASS.

- [ ] **Step 5: Commit**
```bash
git add src/api/routes.py tests/test_api.py
git commit -m "feat(api): accept sports hierarchy parameters on audit and upload endpoints"
```

---

### Task 4: Frontend Upload Modal Enrichment & Smart Auto-Detection

**Files:**
- Modify: `static/index.html`
- Modify: `static/app.js`
- Modify: `static/style.css`
- Test: `tests/test_frontend_assets.py`

- [ ] **Step 1: Write test for new form fields in tests/test_frontend_assets.py**
Verify existence of `upload-campionato`, `upload-categoria`, `upload-girone`, `upload-giornata` in `static/index.html`.

- [ ] **Step 2: Run test to verify failure**
Run `.\venv\Scripts\pytest.exe tests/test_frontend_assets.py -v`.
Expected: FAIL.

- [ ] **Step 3: Update static/index.html with 4-column metadata inputs in upload modal**
Add form row with `Campionato` (default `2026-2027`), `Categoria` (select `B1F`, `B2F`, `CF`, `DF`), `Girone` (text, default `B`), and `Giornata` (text, default `01`).

- [ ] **Step 4: Update static/app.js with auto-detection regex on file change and FormData append**
Add `autoDetectMatchHierarchy(filename)`: parses tokens like `b1fb` (B1F, Girone B) and `&01`/`giornata_01` (Giornata 01). Pre-fills the modal inputs.
Append `campionato`, `categoria`, `girone`, `giornata` to `FormData` on submit.

- [ ] **Step 5: Update static/style.css for compact upload modal grid**
Style `.upload-hierarchy-grid` with a responsive 4-column compact layout.

- [ ] **Step 6: Run tests to verify PASS**
Run `.\venv\Scripts\pytest.exe tests/test_frontend_assets.py tests/test_frontend_auth_assets.py -v`.
Expected: PASS.

- [ ] **Step 7: Commit**
```bash
git add static/index.html static/app.js static/style.css tests/test_frontend_assets.py
git commit -m "feat(ui): add sports hierarchy fields and auto-detection to upload modal"
```

---

### Task 5: Cloud Synchronization Script & Live R2 Verification

**Files:**
- Create: `scripts/sync_to_r2_bucket.py`

- [ ] **Step 1: Create scripts/sync_to_r2_bucket.py**
Reads all existing matches in SQLite `scoutanalyzer.db`, resolves their DVW content, parses or extracts their hierarchy (e.g. `2026-2027/B1F/B/01`), uploads each to the live Cloudflare R2 bucket, updates `matches.storage_path` in SQLite, and prints a verification summary.

- [ ] **Step 2: Execute sync_to_r2_bucket.py against live Cloudflare R2**
Run `.\venv\Scripts\python.exe scripts/sync_to_r2_bucket.py` to upload the 7 real matches into the R2 bucket.
Verify HTTP 200 OK responses from Cloudflare R2 API.

- [ ] **Step 3: Run full automated test suite (all 35+ tests)**
Run `.\venv\Scripts\pytest.exe tests/ -q` to guarantee 100% green tests.

- [ ] **Step 4: Commit migration script**
```bash
git add scripts/sync_to_r2_bucket.py
git commit -m "feat(scripts): sync existing matches to Cloudflare R2 with federal hierarchy"
```
