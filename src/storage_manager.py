import os
import hashlib
import re
from typing import Tuple, Optional, Union
import logging

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

import boto3
from botocore.config import Config
from botocore.exceptions import ClientError, BotoCoreError

logger = logging.getLogger(__name__)

DEFAULT_STORAGE_DIR = "storage/dvw"


def sanitize_filename(filename: str) -> str:
    """Rimuove caratteri non consentiti nei filesystem e nei percorsi storage."""
    clean = re.sub(r'[\\/*?:"<>|]', "", filename)
    clean = clean.replace(" ", "_")
    if not clean.lower().endswith(".dvw"):
        clean += ".dvw"
    return clean


def build_storage_key(
    campionato: str = "2026-2027",
    categoria: str = "B1F",
    girone: str = "B",
    giornata: Union[int, str] = "01",
    filename: str = "match.dvw"
) -> str:
    """Costruisce la chiave gerarchica standard federale:
    <campionato>/<categoria>/<girone>/<giornata>/<filename>
    Es: 2026-2027/B1F/B/03/&01_COR-VOL_Vicenza_b1fb_26_s.dvw
    """
    clean_camp = str(campionato or "2026-2027").strip()
    clean_cat = str(categoria or "B1F").strip().upper()
    clean_gir = str(girone or "B").strip().upper()

    try:
        clean_gio = f"{int(giornata):02d}"
    except (ValueError, TypeError):
        clean_gio = str(giornata or "01").strip().zfill(2)

    clean_file = sanitize_filename(filename)
    return f"{clean_camp}/{clean_cat}/{clean_gir}/{clean_gio}/{clean_file}"


class StorageManager:
    """Gestore unificato e centralizzato per l'archiviazione dei file scout (.dvw).
    Supporta storage gestito locale (server-side) e S3 / Cloudflare R2 con fallback resiliente.
    """
    def __init__(
        self,
        base_dir: str = DEFAULT_STORAGE_DIR,
        backend: Optional[str] = None,
        endpoint_url: Optional[str] = None,
        access_key: Optional[str] = None,
        secret_key: Optional[str] = None,
        bucket_name: Optional[str] = None
    ):
        self.base_dir = os.environ.get("STORAGE_DIR", base_dir)
        self.backend = backend or os.environ.get("STORAGE_BACKEND", "local")
        os.makedirs(self.base_dir, exist_ok=True)

        self.endpoint_url = endpoint_url or os.environ.get("S3_ENDPOINT_URL")
        self.access_key = access_key or os.environ.get("S3_ACCESS_KEY")
        self.secret_key = secret_key or os.environ.get("S3_SECRET_KEY")
        self.bucket_name = bucket_name or os.environ.get("S3_BUCKET_NAME", "scoutanalyzer-dvw")

        self.s3_client = None
        if self.backend == "s3" and self.endpoint_url and self.access_key and self.secret_key:
            try:
                self.s3_client = boto3.client(
                    "s3",
                    endpoint_url=self.endpoint_url,
                    aws_access_key_id=self.access_key,
                    aws_secret_access_key=self.secret_key,
                    region_name="auto",
                    config=Config(
                        s3={"addressing_style": "path"},
                        signature_version="s3v4"
                    )
                )
            except Exception as e:
                logger.warning(f"[StorageManager] Impossibile inizializzare client S3: {e}")

    def _sanitize_filename(self, filename: str) -> str:
        return sanitize_filename(filename)

    def _compute_hash(self, data: bytes) -> str:
        return hashlib.sha256(data).hexdigest()

    def save_dvw(
        self,
        file_bytes: bytes,
        filename: str,
        season: Optional[str] = None,
        campionato: Optional[str] = None,
        categoria: Optional[str] = None,
        girone: Optional[str] = None,
        giornata: Optional[Union[int, str]] = None
    ) -> Tuple[str, str]:
        """Salva i byte del file DVW nello storage gestito e ne calcola l'hash di integrità.
        Restituisce (relative_storage_path, sha256_hash).
        """
        f_hash = self._compute_hash(file_bytes)

        if categoria is not None or girone is not None or giornata is not None:
            rel_path = build_storage_key(
                campionato=campionato or season or "2026-2027",
                categoria=categoria or "B1F",
                girone=girone or "B",
                giornata=giornata or "01",
                filename=filename
            )
        elif season is not None:
            clean_name = self._sanitize_filename(filename)
            season_folder = str(season).replace("\\", "/")
            rel_path = f"{season_folder}/{clean_name}"
        else:
            rel_path = build_storage_key(
                campionato=campionato or "2026-2027",
                categoria="B1F",
                girone="B",
                giornata="01",
                filename=filename
            )

        # Salva sempre una copia nella cache gestita locale
        full_path = os.path.join(self.base_dir, rel_path)
        os.makedirs(os.path.dirname(full_path), exist_ok=True)
        with open(full_path, "wb") as f:
            f.write(file_bytes)

        # Se abilitato backend S3/R2, esegue l'upload sul bucket
        if self.backend == "s3" and self.s3_client:
            self._upload_s3(file_bytes, rel_path)

        return rel_path, f_hash

    def get_dvw_bytes(self, relative_path: str) -> bytes:
        """Legge e restituisce i byte del file DVW memorizzato."""
        full_path = os.path.join(self.base_dir, relative_path)
        if os.path.exists(full_path):
            with open(full_path, "rb") as f:
                return f.read()

        if self.backend == "s3" and self.s3_client:
            data = self._download_s3(relative_path)
            # Salva in cache locale per le prossime letture
            os.makedirs(os.path.dirname(full_path), exist_ok=True)
            with open(full_path, "wb") as f:
                f.write(data)
            return data

        raise FileNotFoundError(f"File DVW non trovato nello storage: {relative_path}")

    def get_dvw_local_path(self, relative_path: str) -> str:
        """Restituisce il path locale sul filesystem del file DVW."""
        full_path = os.path.join(self.base_dir, relative_path)
        if os.path.exists(full_path):
            return full_path
        if self.backend == "s3" and self.s3_client:
            data = self._download_s3(relative_path)
            os.makedirs(os.path.dirname(full_path), exist_ok=True)
            with open(full_path, "wb") as f:
                f.write(data)
            return full_path
        raise FileNotFoundError(f"File non trovato: {relative_path}")

    def delete_dvw(self, relative_path: str) -> bool:
        """Elimina il file dallo storage (locale e S3)."""
        full_path = os.path.join(self.base_dir, relative_path)
        removed_local = False
        if os.path.exists(full_path):
            try:
                os.remove(full_path)
                removed_local = True
            except Exception:
                pass

        if self.backend == "s3" and self.s3_client:
            try:
                self.s3_client.delete_object(Bucket=self.bucket_name, Key=relative_path)
                return True
            except Exception as e:
                logger.warning(f"[StorageManager] Errore cancellazione S3: {e}")

        return removed_local

    def save_roster(self, roster_code: str, content: bytes, is_backup: bool = False, timestamp: Optional[str] = None) -> str:
        """Salva un file roster (.sq) nello storage (current o backup).
        Restituisce il path relativo della chiave.
        """
        from datetime import datetime
        clean_code = str(roster_code).strip()
        if is_backup:
            ts = timestamp or datetime.now().strftime("%Y%m%d_%H%M%S")
            rel_path = f"rosters/backups/{clean_code}_{ts}.sq"
        else:
            rel_path = f"rosters/current/{clean_code}.sq"

        full_path = os.path.join(self.base_dir, rel_path)
        os.makedirs(os.path.dirname(full_path), exist_ok=True)
        with open(full_path, "wb") as f:
            f.write(content)

        if self.backend == "s3" and self.s3_client:
            self._upload_s3(content, rel_path)

        return rel_path

    def get_roster_bytes(self, roster_code: str) -> Optional[bytes]:
        """Recupera i byte del roster corrente (prima da cache locale, poi da S3)."""
        rel_path = f"rosters/current/{str(roster_code).strip()}.sq"
        full_path = os.path.join(self.base_dir, rel_path)
        if os.path.exists(full_path):
            with open(full_path, "rb") as f:
                return f.read()

        if self.backend == "s3" and self.s3_client:
            try:
                data = self._download_s3(rel_path)
                os.makedirs(os.path.dirname(full_path), exist_ok=True)
                with open(full_path, "wb") as f:
                    f.write(data)
                return data
            except Exception:
                return None

        return None

    def backup_database_to_storage(self, db_path: Optional[str] = None) -> bool:
        """Esegue il backup del database SQLite sul bucket Cloudflare R2."""
        if self.backend != "s3" or not self.s3_client:
            return False

        target_db = db_path
        if not target_db:
            try:
                from src.db import get_sqlite_path
                target_db = get_sqlite_path()
            except Exception:
                target_db = "scoutanalyzer.db"

        if not os.path.exists(target_db):
            return False

        try:
            with open(target_db, "rb") as f:
                content = f.read()
            return self._upload_s3(content, "database/scoutanalyzer.db")
        except Exception as e:
            logger.warning(f"[StorageManager] Errore backup database su S3: {e}")
            return False

    def restore_database_from_storage(self, target_db_path: Optional[str] = None) -> bool:
        """Scarica l'ultimo snapshot del database SQLite dal bucket Cloudflare R2 se presente."""
        if self.backend != "s3" or not self.s3_client:
            return False

        target_db = target_db_path
        if not target_db:
            try:
                from src.db import get_sqlite_path
                target_db = get_sqlite_path()
            except Exception:
                target_db = "scoutanalyzer.db"

        try:
            data = self._download_s3("database/scoutanalyzer.db")
            if data and len(data) > 0:
                os.makedirs(os.path.dirname(os.path.abspath(target_db)), exist_ok=True)
                with open(target_db, "wb") as f:
                    f.write(data)
                logger.info(f"[StorageManager] Database ripristinato con successo da S3 in {target_db}")
                return True
        except Exception as e:
            logger.info(f"[StorageManager] Nessun database trovato su S3 da ripristinare: {e}")
            return False
        return False

    def _upload_s3(self, file_bytes: bytes, relative_path: str) -> bool:
        """Esegue l'upload di un file su Cloudflare R2 / AWS S3 con gestione errori trasparente."""
        try:
            self.s3_client.put_object(
                Bucket=self.bucket_name,
                Key=relative_path,
                Body=file_bytes
            )
            return True
        except Exception as e:
            logger.warning(f"[StorageManager] Errore upload S3 su bucket '{self.bucket_name}' (Key: {relative_path}): {e}. File salvato in locale.")
            return False

    def _download_s3(self, relative_path: str) -> bytes:
        """Scarica i byte di un file dal bucket S3."""
        try:
            response = self.s3_client.get_object(
                Bucket=self.bucket_name,
                Key=relative_path
            )
            return response["Body"].read()
        except Exception as e:
            raise FileNotFoundError(f"Impossibile scaricare file da S3 ({relative_path}): {e}")
