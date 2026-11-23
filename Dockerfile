# ScoutAnalyzer 3000 - Dockerfile per Synology NAS e ambienti on-premise
FROM python:3.11-slim

# Evita la generazione di file .pyc e forza l'output log non bufferizzato
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    SCOUT_DB_PATH=/app/data/scoutanalyzer.db \
    STORAGE_BACKEND=local \
    PORT=8000

WORKDIR /app

# Installazione dipendenze di sistema minime per compilazione e salute container
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Installazione dipendenze Python
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Copia dei sorgenti dell'applicazione
COPY . .

# Creazione delle directory per i volumi persistenti e symlink di sicurezza
RUN mkdir -p /app/data /app/storage /app/config && \
    ln -sf /app/data/scoutanalyzer.db /app/scoutanalyzer.db

# Esposizione della porta Web
EXPOSE 8000

# Healthcheck per monitorare lo stato del container
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:8000/ || exit 1

# Inizializzazione DB (migrazioni automatiche) e avvio server Uvicorn
CMD ["sh", "-c", "mkdir -p /app/data && ln -sf /app/data/scoutanalyzer.db /app/scoutanalyzer.db && python database/setup_db.py && uvicorn web_app:app --host 0.0.0.0 --port 8000"]
