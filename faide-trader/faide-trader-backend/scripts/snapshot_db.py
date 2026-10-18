"""Save the current faide_trader.db into seed/faide_trader.db.gz so it can be committed.

Usage: poetry run python scripts/snapshot_db.py [path/to/faide_trader.db]
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.seed import BACKEND_DIR, SEED_PATH, snapshot_db  # noqa: E402

db_path = sys.argv[1] if len(sys.argv) > 1 else os.path.join(BACKEND_DIR, "faide_trader.db")
snapshot_db(db_path)
print(f"Wrote {SEED_PATH} ({os.path.getsize(SEED_PATH)} bytes) from {db_path}")
