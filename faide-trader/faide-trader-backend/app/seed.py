import gzip
import os
import shutil
import sqlite3
import tempfile

from sqlalchemy.engine import make_url

BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SEED_PATH = os.path.join(BACKEND_DIR, "seed", "faide_trader.db.gz")
DEFAULT_DB_NAME = "faide_trader.db"


def sqlite_path(database_url: str) -> str | None:
    url = make_url(database_url)
    if not url.drivername.startswith("sqlite") or not url.database or url.database == ":memory:":
        return None
    return os.path.abspath(url.database)


def restore_seed_db(database_url: str) -> bool:
    """Restore the committed seed snapshot when the app DB file is missing."""
    path = sqlite_path(database_url)
    if not path or os.path.basename(path) != DEFAULT_DB_NAME:
        return False
    if os.path.exists(path) or not os.path.exists(SEED_PATH):
        return False
    os.makedirs(os.path.dirname(path), exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=os.path.dirname(path), suffix=".restore")
    with os.fdopen(fd, "wb") as dst, gzip.open(SEED_PATH, "rb") as src:
        shutil.copyfileobj(src, dst)
    os.chmod(tmp, 0o644)
    os.replace(tmp, path)
    return True


def snapshot_db(db_path: str, seed_path: str = SEED_PATH) -> None:
    """Write a consistent gzip snapshot of a live SQLite DB to the seed path."""
    os.makedirs(os.path.dirname(seed_path), exist_ok=True)
    fd, tmp_db = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    try:
        src = sqlite3.connect(db_path)
        dst = sqlite3.connect(tmp_db)
        with dst:
            src.backup(dst)
        src.close()
        dst.close()
        tmp_gz = seed_path + ".tmp"
        with open(tmp_db, "rb") as f, gzip.GzipFile(tmp_gz, "wb", mtime=0) as gz:
            shutil.copyfileobj(f, gz)
        os.replace(tmp_gz, seed_path)
    finally:
        os.remove(tmp_db)
