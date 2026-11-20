import os
import pytest
from src.storage_manager import StorageManager

def test_storage_manager_save_and_retrieve(tmp_path):
    storage_dir = str(tmp_path / "storage" / "dvw")
    mgr = StorageManager(base_dir=storage_dir)

    sample_content = b"[3MATCH]\nTEST_SAMPLE_MATCH;\n"
    filename = "test_match_file.dvw"
    rel_path, f_hash = mgr.save_dvw(sample_content, filename, season="2026")

    assert os.path.exists(os.path.join(storage_dir, rel_path))
    assert len(f_hash) > 10

    # Recupero bytes
    retrieved = mgr.get_dvw_bytes(rel_path)
    assert retrieved == sample_content

    # Recupero local path
    local_path = mgr.get_dvw_local_path(rel_path)
    assert os.path.exists(local_path)
