# Design Doc: Cloudflare R2 / S3 Storage Integration & Sports Hierarchy Cataloging

**Data:** 20 Novembre 2026  
**Autore:** Principal Software Architect & Domain Engineer  
**Stato:** Approvato  
**Branch:** `feature/auth-multitenant-storage`

---

## 1. Intent e Motivazione

ScoutAnalyzer 3000 richiede l'integrazione di uno **storage cloud S3-compatibile (Cloudflare R2)** per archiviare in modo centralizzato e scalabile tutti i file scout `.dvw`.  
La catalogazione dei file non deve essere piatta, ma strutturata secondo la rigorosa gerarchia federale della pallavolo:  
`<campionato>/<categoria>/<girone>/<giornata>/<nome_file>.dvw`  
*(es. `2026-2027/B1F/B/03/&01_COR-VOL_Vicenza_b1fb_26_s.dvw` o `2026-2027/CF/C/05/...`)*.

Il form di upload dell'interfaccia web deve consentire all'amministratore di impostare e confermare questi quattro parametri prima del caricamento, supportato da un sistema di auto-rilevamento intelligente dal nome del file.

---

## 2. Obiettivi, Non-Obiettivi e Anti-Obiettivi

### Obiettivi (Goals)
* **Protezione Credenziali:** Memorizzare le credenziali fornite (Access Key, Secret Key, Endpoint R2, Bucket) nel file `.env` rigorosamente protetto da `.gitignore`. Fornire `.env.example` con placeholder per il repo git.
* **Integrazione `boto3`:** Implementare in `StorageManager` i metodi `_upload_s3` e `_download_s3` tramite client `boto3.client("s3", ...)`.
* **Gerarchia Standard Cloud:** Funzione `build_storage_key(campionato, categoria, girone, giornata, filename) -> str` applicata sia al caricamento web sia allo script di migrazione.
* **Form Upload Arricchito nel Frontend:**
  * Campi nel modal: Campionato/Stagione, Categoria, Girone, Giornata.
  * Auto-detection client-side: all'atto della selezione del file, analizza il filename (es. `b1fb` -> Categoria B1F, Girone B; `&01` -> Giornata 01) e pre-compila i campi.
* **Aggiornamento Database:** Memorizzazione del percorso relativo completo R2 e hash SHA-256 nel record di `matches`.
* **Script di Sincronizzazione R2:** Script `scripts/sync_to_r2_bucket.py` per caricare immediatamente le partite reali esistenti sul bucket Cloudflare R2.

### Non-Obiettivi (Non-Goals)
* Non bloccare il funzionamento dell'app se il bucket è offline: se la chiamata S3 fallisce o non c'è rete, `StorageManager` salva in locale come fallback e notifica l'avviso senza interrompere l'audit.

### Anti-Obiettivi (Anti-Goals)
* Non committare mai chiavi segrete o file `.env` su git.

---

## 3. Vincoli Tecnici e di Piattaforma

* **Libreria S3:** `boto3>=1.34.0`
* **Cloudflare R2 Endpoint:** `https://43ba6ad8c9582bba26c5261844a877f3.r2.cloudflarestorage.com`
* **Bucket predefinito:** `scoutanalyzer-dvw`
* **Formato Path:** `{campionato}/{categoria}/{girone}/{giornata:02d}/{filename}`

---

## 4. Dettaglio dei Componenti

### 4.1 Configurazione `.env` e Caricamento Parametri
In `.env` (non tracciato da git):
```
STORAGE_BACKEND=s3
S3_ENDPOINT_URL=https://43ba6ad8c9582bba26c5261844a877f3.r2.cloudflarestorage.com
S3_ACCESS_KEY=aedc58c9c58efcdea03fb44139024438
S3_SECRET_KEY=b7f2cc433606a2d6cd923ebccd6c9afc1a49151550f0aeac5e767a9a6e31d835
S3_BUCKET_NAME=scoutanalyzer-dvw
```
In `config.json`: caricamento con fallback alle variabili d'ambiente.

### 4.2 StorageManager con Client `boto3` (`src/storage_manager.py`)
* Inizializzazione client S3 con:
  ```python
  boto3.client(
      "s3",
      endpoint_url=self.s3_endpoint,
      aws_access_key_id=self.s3_access_key,
      aws_secret_access_key=self.s3_secret_key,
      region_name="auto"
  )
  ```
* `save_dvw(file_bytes, filename, season, category, group, giornata) -> (relative_key, hash)`:
  1. Costruisce la chiave: `{campionato}/{categoria}/{girone}/{giornata:02d}/{clean_filename}`.
  2. Salva copia cache locale in `storage/dvw/{key}`.
  3. Esegue `put_object(Bucket=self.bucket_name, Key=key, Body=file_bytes)`.
  4. Restituisce la chiave e l'hash.

### 4.3 Endpoint Upload (`src/api/routes.py`)
* Accetta campi form: `file: UploadFile`, `campionato: str = Form("2026-2027")`, `categoria: str = Form("B1F")`, `girone: str = Form("B")`, `giornata: str = Form("01")`.
* Passa la gerarchia a `StorageManager.save_dvw()`.

### 4.4 Frontend Modal Upload (`static/index.html` e `static/app.js`)
* Grid a 4 campi compatti per Campionato, Categoria, Girone, Giornata.
* Regex di auto-parsing su `change` dell'input file.
* Invio tramite `FormData` con tutti i parametri al backend.
