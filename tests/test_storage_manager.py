import os
import pytest
from unittest.mock import MagicMock, patch
from src.storage_manager import StorageManager, build_storage_key

def test_build_storage_key_normalization():
    # Normalizzazione girone, giornata 2 cifre e pulizia nome file
    key = build_storage_key(
        campionato="2026-2027",
        categoria="B1F",
        girone="b",
        giornata=3,
        filename="&01_COR-VOL Vicenza:test.dvw"
    )
    assert key == "2026-2027/B1F/B/03/&01_COR-VOL_Vicenzatest.dvw"

    # Giornata a due cifre già formattata
    key2 = build_storage_key(
        campionato="2026-2027",
        categoria="CF",
        girone="C",
        giornata="05",
        filename="match_partita.dvw"
    )
    assert key2 == "2026-2027/CF/C/05/match_partita.dvw"


def test_storage_manager_save_and_retrieve_local(tmp_path):
    storage_dir = str(tmp_path / "storage" / "dvw")
    mgr = StorageManager(base_dir=storage_dir, backend="local")

    sample_content = b"[3MATCH]\nTEST_SAMPLE_MATCH;\n"
    filename = "test_match_file.dvw"
    rel_path, f_hash = mgr.save_dvw(
        sample_content,
        filename,
        campionato="2026-2027",
        categoria="B1F",
        girone="B",
        giornata="01"
    )

    assert rel_path == "2026-2027/B1F/B/01/test_match_file.dvw"
    assert os.path.exists(os.path.join(storage_dir, rel_path))
    assert len(f_hash) > 10

    # Recupero bytes
    retrieved = mgr.get_dvw_bytes(rel_path)
    assert retrieved == sample_content

    # Recupero local path
    local_path = mgr.get_dvw_local_path(rel_path)
    assert os.path.exists(local_path)


def test_storage_manager_s3_upload(tmp_path):
    storage_dir = str(tmp_path / "storage" / "dvw")
    mock_s3 = MagicMock()

    with patch("boto3.client", return_value=mock_s3):
        mgr = StorageManager(
            base_dir=storage_dir,
            backend="s3",
            endpoint_url="https://fake-endpoint.r2.cloudflarestorage.com",
            access_key="fake-key",
            secret_key="fake-secret",
            bucket_name="test-bucket"
        )

        sample_content = b"[3MATCH]\nS3_SAMPLE_CONTENT\n"
        rel_path, f_hash = mgr.save_dvw(
            sample_content,
            "s3_match.dvw",
            campionato="2026-2027",
            categoria="B1F",
            girone="B",
            giornata="02"
        )

        assert rel_path == "2026-2027/B1F/B/02/s3_match.dvw"
        # Deve aver chiamato put_object
        mock_s3.put_object.assert_called_once_with(
            Bucket="test-bucket",
            Key="2026-2027/B1F/B/02/s3_match.dvw",
            Body=sample_content
        )
        # E deve comunque aver salvato anche nella cache locale
        assert os.path.exists(os.path.join(storage_dir, rel_path))


def test_storage_manager_s3_fallback_on_network_error(tmp_path):
    storage_dir = str(tmp_path / "storage" / "dvw")
    mock_s3 = MagicMock()
    mock_s3.put_object.side_effect = Exception("Connection Timeout to Cloudflare R2")

    with patch("boto3.client", return_value=mock_s3):
        mgr = StorageManager(
            base_dir=storage_dir,
            backend="s3",
            endpoint_url="https://fake-endpoint.r2.cloudflarestorage.com",
            access_key="fake-key",
            secret_key="fake-secret",
            bucket_name="test-bucket"
        )

        sample_content = b"[3MATCH]\nFALLBACK_TEST\n"
        # Non deve lanciare eccezione, ma fare fallback e salvare in locale
        rel_path, f_hash = mgr.save_dvw(
            sample_content,
            "fallback_match.dvw",
            campionato="2026-2027",
            categoria="CF",
            girone="A",
            giornata="01"
        )

        assert rel_path == "2026-2027/CF/A/01/fallback_match.dvw"
        assert os.path.exists(os.path.join(storage_dir, rel_path))


def test_roster_storage_on_bucket_and_local(tmp_path):
    storage_dir = str(tmp_path / "storage")
    mock_s3 = MagicMock()

    with patch("boto3.client", return_value=mock_s3):
        mgr = StorageManager(
            base_dir=storage_dir,
            backend="s3",
            endpoint_url="https://fake-endpoint.r2.cloudflarestorage.com",
            access_key="fake-key",
            secret_key="fake-secret",
            bucket_name="test-bucket"
        )

        content = b"0;1;Rossi;Mario;P;\n"
        # 1. Salvataggio roster corrente
        rel_path = mgr.save_roster(roster_code="2761", content=content, is_backup=False)
        assert rel_path == "rosters/current/2761.sq"
        assert os.path.exists(os.path.join(storage_dir, rel_path))
        mock_s3.put_object.assert_called_with(
            Bucket="test-bucket",
            Key="rosters/current/2761.sq",
            Body=content
        )

        # 2. Salvataggio backup roster con timestamp
        rel_bak = mgr.save_roster(roster_code="2761", content=content, is_backup=True, timestamp="20261120_153000")
        assert rel_bak == "rosters/backups/2761_20261120_153000.sq"
        assert os.path.exists(os.path.join(storage_dir, rel_bak))

        # 3. Recupero bytes roster
        retrieved = mgr.get_roster_bytes("2761")
        assert retrieved == content

