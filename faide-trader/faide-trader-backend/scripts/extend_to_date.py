"""Extend the portfolio's history forward to a given date without touching existing data.

Generates trades for the window after the latest existing activity, using the same
range-scoped engine as the Regenerate dialog: each bot follows its own historical trade
rate and P&L size, and the run aborts if any pre-existing row would change.

Each account's net P&L for the new window continues its own trend: its average daily
trading P&L over the trailing LOOKBACK_DAYS (or its whole history, if younger) times
the window length. Accounts with no remaining balance (e.g. emptied by a transfer out)
are left idle.

Usage:
    poetry run python scripts/extend_to_date.py --end-date 2026-10-18
"""
import argparse
import asyncio
import sys
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import func, select  # noqa: E402

from app.database import async_session  # noqa: E402
from app.models.portfolio import Account, Bot, PnlRecord, Trade, Transaction  # noqa: E402
from app.services.range_regenerate import RangeRegenerateOptions, regenerate_range  # noqa: E402

LOOKBACK_DAYS = 90


async def latest_activity(db) -> datetime:
    candidates = [
        (await db.execute(select(func.max(func.coalesce(Trade.exit_time, Trade.entry_time))))).scalar(),
        (await db.execute(select(func.max(Transaction.date)))).scalar(),
        (await db.execute(select(func.max(PnlRecord.date)))).scalar(),
    ]
    values = [datetime.fromisoformat(v) if isinstance(v, str) else v for v in candidates if v]
    return max(values)


async def trend_target(db, account: Account, last: datetime, window_days: float) -> float:
    activity = func.coalesce(Trade.exit_time, Trade.entry_time)
    since = last - timedelta(days=LOOKBACK_DAYS)
    pnl, first = (
        await db.execute(
            select(func.coalesce(func.sum(Trade.pnl), 0.0), func.min(activity))
            .join(Bot, Trade.bot_id == Bot.id)
            .where(Bot.account_id == account.id, activity > since, activity <= last)
        )
    ).one()
    if not first:
        return 0.0
    first = datetime.fromisoformat(first) if isinstance(first, str) else first
    span_days = max((last - first).total_seconds() / 86400, 1.0)
    return round(float(pnl) / span_days * window_days, 2)


async def main(end: datetime, seed: int) -> None:
    async with async_session() as db:
        last = await latest_activity(db)
        start = datetime.combine(last.date() + timedelta(days=1), datetime.min.time())
        if start >= end:
            print(f"Data already reaches {last}; nothing to do")
            return

        accounts = list((await db.execute(select(Account))).scalars().all())
        active = [a for a in accounts if not a.is_pinned and (a.current_balance or 0) > 0]
        idle = [a.name for a in accounts if a not in active]
        window_days = (end - start).total_seconds() / 86400
        print(f"Window: {start} -> {end}; idle accounts: {idle}")

        for account in active:
            target = await trend_target(db, account, last, window_days)
            bots = list(
                (await db.execute(select(Bot).where(Bot.account_id == account.id))).scalars().all()
            )
            result = await regenerate_range(
                db,
                bots,
                RangeRegenerateOptions(start=start, end=end, target_net_pnl=target, seed=seed + account.id),
                {account.id},
            )
            print(
                f"{account.name}: target ${target:,.2f}, +{result['generated_trades']} trades, "
                f"net ${result['net_pnl']:,.2f}"
            )

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--end-date", required=True, help="Last day to fill (YYYY-MM-DD), inclusive")
    parser.add_argument("--seed", type=int, default=20261018)
    args = parser.parse_args()
    end_dt = datetime.strptime(args.end_date, "%Y-%m-%d").replace(hour=23, minute=59, second=59)
    asyncio.run(main(end_dt, args.seed))
