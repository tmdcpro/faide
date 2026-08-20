"""Date-range filtering helpers shared by the read endpoints.

A range is inclusive on both ends. A bare date (``2026-06-13``) as ``end`` covers
the whole day, so the caller does not have to pass ``23:59:59``.
"""
from datetime import datetime, time, timedelta
from typing import Optional

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.portfolio import Account, Bot, Trade, Transaction


def parse_range(
    start_date: Optional[str], end_date: Optional[str]
) -> tuple[Optional[datetime], Optional[datetime]]:
    """Parse ISO date/datetime strings into an inclusive [start, end] window."""
    start: Optional[datetime] = None
    end: Optional[datetime] = None

    if start_date:
        try:
            start = datetime.fromisoformat(start_date)
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid start_date format")
    if end_date:
        try:
            end = datetime.fromisoformat(end_date)
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid end_date format")
        if end.time() == time.min:
            end = end + timedelta(days=1) - timedelta(microseconds=1)

    if start and end and start > end:
        raise HTTPException(status_code=400, detail="start_date must be before end_date")

    return start, end


def trade_date(trade: Trade) -> datetime:
    """The date a trade is attributed to (its close, falling back to its open)."""
    return trade.exit_time or trade.entry_time


def filter_trades(
    trades: list[Trade], start: Optional[datetime], end: Optional[datetime]
) -> list[Trade]:
    if start is None and end is None:
        return trades
    out = []
    for t in trades:
        d = trade_date(t)
        if start and d < start:
            continue
        if end and d > end:
            continue
        out.append(t)
    return out


def filter_transactions(
    transactions: list[Transaction], start: Optional[datetime], end: Optional[datetime]
) -> list[Transaction]:
    if start is None and end is None:
        return transactions
    return [
        tx
        for tx in transactions
        if not (start and tx.date < start) and not (end and tx.date > end)
    ]


async def balance_at(
    db: AsyncSession, account_ids: list[int], initial_balance: float, before: Optional[datetime]
) -> float:
    """Account/portfolio balance immediately before ``before``.

    Used as the baseline for range-scoped ROI and drawdown so a window's
    percentages are relative to the equity the window actually started with.
    """
    if before is None or not account_ids:
        return initial_balance

    pnl = (
        await db.execute(
            select(func.coalesce(func.sum(Trade.pnl), 0.0))
            .join(Bot, Trade.bot_id == Bot.id)
            .where(
                Bot.account_id.in_(account_ids),
                func.coalesce(Trade.exit_time, Trade.entry_time) < before,
            )
        )
    ).scalar() or 0.0

    deposits = (
        await db.execute(
            select(func.coalesce(func.sum(Transaction.amount), 0.0)).where(
                Transaction.account_id.in_(account_ids),
                Transaction.type == "deposit",
                Transaction.date < before,
            )
        )
    ).scalar() or 0.0

    withdrawals = (
        await db.execute(
            select(func.coalesce(func.sum(Transaction.amount), 0.0)).where(
                Transaction.account_id.in_(account_ids),
                Transaction.type == "withdrawal",
                Transaction.date < before,
            )
        )
    ).scalar() or 0.0

    return round(initial_balance + pnl + deposits - withdrawals, 2)


async def account_ids_for_portfolio(db: AsyncSession, portfolio_id: int) -> list[int]:
    result = await db.execute(select(Account.id).where(Account.portfolio_id == portfolio_id))
    return list(result.scalars().all())
