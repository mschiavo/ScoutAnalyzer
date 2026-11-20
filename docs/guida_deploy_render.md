# Guida al Deploy di ScoutAnalyzer 3000 su Render.com

ScoutAnalyzer 3000 è completamente predisposto per essere distribuito gratuitamente su **Render.com** tramite connessione diretta a GitHub.

---

### Prerequisiti
1. Account gratuito su **[render.com](https://render.com)** (accedi cliccando **"Sign in with GitHub"**).
2. Il tuo repository GitHub: `https://github.com/mschiavo/ScoutAnalyzer`.

---

### Passo 1: Crea un nuovo Web Service su Render
1. Nella Dashboard di Render, clicca sul pulsante in alto a destra **"New +"** e seleziona **"Web Service"**.
2. Scegli l'opzione **"Build and deploy from a Git repository"** e clicca **Next**.
3. Seleziona il tuo repository **`ScoutAnalyzer`** (se non compare nell'elenco, clicca su *Configure GitHub App* e concedi i permessi di lettura per questo repository).

---

### Passo 2: Configura il Servizio
Render leggerà automaticamente il file `render.yaml` presente nel repository. Se crei il servizio manualmente dal form:

* **Name:** `scoutanalyzer-3000` (o il nome che preferisci)
* **Region:** `Frankfurt (EU)` (per massima velocità dall'Italia)
* **Branch:** `feature/auth-multitenant-storage` (oppure il branch che intendi pubblicare, es. `main`/`develop` una volta unito)
* **Runtime:** `Python 3`
* **Build Command:**
  ```bash
  pip install -r requirements.txt && python database/setup_db.py
  ```
* **Start Command:**
  ```bash
  uvicorn web_app:app --host 0.0.0.0 --port $PORT
  ```
* **Instance Type:** Seleziona **"Free"**.

---

### Passo 3: Variabili d'Ambiente (Environment Variables)
Nella sezione **Environment Variables**, aggiungi le seguenti chiavi:

| Nome Chiave | Valore |
|---|---|
| `STORAGE_BACKEND` | `s3` |
| `S3_ENDPOINT_URL` | `https://43ba6ad8c9582bba26c5261844a877f3.r2.cloudflarestorage.com` |
| `S3_BUCKET_NAME` | `scoutanalyzer-dvw` |
| `S3_ACCESS_KEY` | *(La tua Access Key di Cloudflare R2)* |
| `S3_SECRET_KEY` | *(La tua Secret Key di Cloudflare R2)* |
| `JWT_SECRET_KEY` | *(Una stringa casuale lunga a piacere per firmare i token JWT)* |

---

### Passo 4: Avvia il Deploy!
1. Clicca in basso su **"Deploy Web Service"**.
2. Render installerà le dipendenze Python, verificherà il database SQLite e avvierà il server FastAPI su un indirizzo pubblico HTTPS protetto (es. `https://scoutanalyzer-3000.onrender.com`).
3. L'applicazione sarà online e accessibile da qualsiasi computer, smartphone o tablet!
