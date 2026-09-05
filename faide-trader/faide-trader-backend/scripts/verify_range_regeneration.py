"""Verify range-scoped regeneration never touches rows outside the window.

Runs against a throwaway copy of the local database:

    poetry run python scripts/verify_range_regeneration.py
"""
import asyncio
import os
import shutil
import sqlite3
import sys
import tempfile
from datetime import datetime

BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BACKEND_DIR)

SOURCE_DB = os.path.join(BACKEND_DIR, "faide_trader.db")

TRADE_SNAPSHOT = """
    SELECT id, bot_id, symbol, direction, status, entry_price, exit_price, quantity,
           leverage, pnl, pnl_percent, fee, entry_time, exit_time, is_pinned
    FROM trades
    WHERE entry_time < ? OR COALESCE(exit_time, entry_time) > ?
    ORDER BY id
"""

TX_SNAPSHOT = """
    SELECT id, account_id, type, amount, note, date FROM transactions
    WHERE date < ? OR date > ? ORDER BY id
"""

# cumulative_pnl is a running total and legitimately shifts with in-range P&L.
PNL_SNAPSHOT = """
    SELECT id, bot_id, date, period_type, pnl, trade_count, win_count, loss_count, is_pinned
    FROM pnl_records
    WHERE date < ? OR date > ? ORDER BY id
"""


def snapshot(path: str, start: datetime, end: datetime) -> tuple[list, list, list]:
    s, e = start.isoformat(sep=" "), end.isoformat(sep=" ")
    day_start = datetime.combine(start.date(), datetime.min.time()).isoformat(sep=" ")
    day_end = datetime.combine(end.date(), datetime.max.time()).isoformat(sep=" ")
    conn = sqlite3.connect(path)
    trades = conn.execute(TRADE_SNAPSHOT, (s, e)).fetchall()
    txs = conn.execute(TX_SNAPSHOT, (s, e)).fetchall()
    pnl = conn.execute(PNL_SNAPSHOT, (day_start, day_end)).fetchall()
    conn.close()
    return trades, txs, pnl


async def run_case(db_path: str, start: datetime, end: datetime, **opts) -> dict:
    os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{db_path}"
    from sqlalchemy import select
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    from app.models.portfolio import Bot
    from app.services.range_regenerate import RangeRegenerateOptions, regenerate_range

    engine = create_async_engine(f"sqlite+aiosqlite:///{db_path}")
    session_maker = async_sessionmaker(engine, expire_on_commit=False)
    async with session_maker() as db:
        bots = list((await db.execute(select(Bot))).scalars().all())
        result = await regenerate_range(
            db, bots, RangeRegenerateOptions(start=start, end=end, **opts)
        )
    await engine.dispose()
    return result


async def main() -> int:
    if not os.path.exists(SOURCE_DB):
        print("no local database found, nothing to verify")
        return 0

    failures = 0
    cases = [
        (datetime(2026, 6, 1), datetime(2026, 6, 7, 23, 59, 59), {"target_net_pnl": 250.0, "seed": 7}),
        (datetime(2026, 6, 8), datetime(2026, 6, 11, 23, 59, 59), {"target_net_pnl": -100.0, "seed": 3}),
    ]

    for start, end, opts in cases:
        with tempfile.TemporaryDirectory() as tmp:
            db_path = os.path.join(tmp, "copy.db")
            shutil.copy(SOURCE_DB, db_path)

            before = snapshot(db_path, start, end)
            result = await run_case(db_path, start, end, **opts)
            after = snapshot(db_path, start, end)

            label = f"{start.date()} .. {end.date()}"
            if before != after:
                print(f"FAIL {label}: out-of-range rows changed")
                failures += 1
                continue
            if result["generated_trades"] <= 0:
                print(f"FAIL {label}: no trades generated")
                failures += 1
                continue
            target = opts.get("target_net_pnl")
            if target is not None and abs(result["net_pnl"] - target) > 1.0:
                print(f"FAIL {label}: period net P&L {result['net_pnl']} != target {target}")
                failures += 1
                continue
            print(
                f"PASS {label}: -{result['deleted_trades']} / +{result['generated_trades']} "
                f"trades, {len(before[0])} trades + {len(before[1])} transactions "
                f"+ {len(before[2])} P&L records preserved byte-identical"
            )

    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
