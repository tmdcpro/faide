"""Restore faide_trader.db from seed/faide_trader.db.gz if the DB file is missing.

The backend also does this automatically on startup.
Usage: poetry run python scripts/restore_seed_db.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.seed import BACKEND_DIR, restore_seed_db  # noqa: E402

url = os.getenv("DATABASE_URL", f"sqlite+aiosqlite:///{os.path.join(BACKEND_DIR, 'faide_trader.db')}")
print("Restored DB from seed" if restore_seed_db(url) else "DB already present (or no seed); nothing restored")
