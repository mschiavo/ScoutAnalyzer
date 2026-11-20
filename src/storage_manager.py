import os
import hashlib
import re
from typing import Tuple, Optional

DEFAULT_STORAGE_DIR = "storage/dvw"

class StorageManager:
    """Gestore unificato e centralizzato per l'archiviazione dei file scout (.dvw).
    Supporta storage gestito locale (server-side) e predisposizione S3 / Cloudflare R2.
    """
    def __init__(self, base_dir: str = DEFAULT_STORAGE_DIR, backend: Optional[str] = None):
        self.base_dir = os.environ.get("STORAGE_DIR", base_dir)
        self.backend = backend or os.environ.get("STORAGE_BACKEND", "local")
        os.makedirs(self.base_dir, exist_ok=True)

    def _sanitize_filename(self, filename: str) -> str:
        clean = re.sub(r'[\\/*?:"<>|]', "", filename)
        clean = clean.replace(" ", "_")
        if not clean.lower().endswith(".dvw"):
            clean += ".dvw"
        return clean

    def _compute_hash(self, data: bytes) -> str:
        return hashlib.sha256(data).hexdigest()

    def save_dvw(self, file_bytes: bytes, filename: str, season: Optional[str] = None) -> Tuple[str, str]:
        """Salva i byte del file DVW nello storage gestito e ne calcola l'hash di integrità.
        Restituisce (relative_storage_path, sha256_hash).
        """
        f_hash = self._compute_hash(file_bytes)
        clean_name = self._sanitize_filename(filename)
        season_folder = str(season or "default")

        target_folder = os.path.join(self.base_dir, season_folder)
        os.makedirs(target_folder, exist_ok=True)

        rel_path = f"{season_folder}/{clean_name}".replace("\\", "/")
        full_path = os.path.join(self.base_dir, rel_path)

        with open(full_path, "wb") as f:
            f.write(file_bytes)

        # Se abilitato backend S3/R2
        if self.backend == "s3":
            self._upload_s3(file_bytes, rel_path)

        return rel_path, f_hash

    def get_dvw_bytes(self, relative_path: str) -> bytes:
        """Legge e restituisce i byte del file DVW memorizzato."""
        full_path = os.path.join(self.base_dir, relative_path)
        if os.path.exists(full_path):
            with open(full_path, "rb") as f:
                return f.read()

        if self.backend == "s3":
            return self._download_s3(relative_path)

        raise FileNotFoundError(f"File DVW non trovato nello storage: {relative_path}")

    def get_dvw_local_path(self, relative_path: str) -> str:
        """Restituisce il path locale sul filesystem del file DVW."""
        full_path = os.path.join(self.base_dir, relative_path)
        if os.path.exists(full_path):
            return full_path
        if self.backend == "s3":
            data = self._download_s3(relative_path)
            os.makedirs(os.path.dirname(full_path), exist_ok=True)
            with open(full_path, "wb") as f:
                f.write(data)
            return full_path
        raise FileNotFoundError(f"File non trovato: {relative_path}")

    def delete_dvw(self, relative_path: str) -> bool:
        """Elimina il file dallo storage."""
        full_path = os.path.join(self.base_dir, relative_path)
        if os.path.exists(full_path):
            try:
                os.remove(full_path)
                return True
            except Exception:
                return False
        return False

    def _upload_s3(self, file_bytes: bytes, relative_path: str):
        # Predisposizione S3 compatibile
        pass

    def _download_s3(self, relative_path: str) -> bytes:
        # Predisposizione S3 compatibile
        raise NotImplementedError("Storage S3 non configurato o offline.")
