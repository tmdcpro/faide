"""Date-range scoped trade regeneration.

Unlike :func:`app.services.calculation_engine.regenerate_bot_trades`, which
replaces a bot's whole unpinned history, this service only ever touches rows
whose timestamps fall completely inside the requested window:

* a trade is replaceable only when it is unpinned and both its entry and its
  exit fall inside ``[start, end]`` (trades straddling a boundary are kept);
* transactions are only touched when the caller explicitly asks for it;
* derived rows (daily P&L records, account balances) are rebuilt without
  re-deriving individual trade P&L, so out-of-range trades keep their exact
  stored values.

Every run snapshots every out-of-range trade and transaction, and re-checks the
snapshot before committing. A mismatch rolls the whole run back.
"""
import hashlib
import random
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import Optional

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.portfolio import Account, Bot, MarketData, Trade, Transaction
from app.services.calculation_engine import rebuild_pnl_records

STRATEGY_TRADES_PER_DAY = {
    "grid": 1.0,
    "scalping": 2.5,
    "dca": 0.3,
    "swing": 0.15,
    "trend_following": 0.2,
    "mean_reversion": 0.6,
    "arbitrage": 1.2,
}

STRATEGY_WIN_RATE = {
    "grid": 0.50,
    "scalping": 0.48,
    "dca": 0.55,
    "swing": 0.45,
    "trend_following": 0.42,
    "mean_reversion": 0.50,
    "arbitrage": 0.55,
}

FALLBACK_PRICES = {
    "BTC": 100000.0,
    "ETH": 3800.0,
    "SOL": 180.0,
    "XRP": 0.8,
    "DOGE": 0.25,
    "AVAX": 50.0,
    "LINK": 22.0,
    "ARB": 1.5,
}


class RangeRegenerationError(RuntimeError):
    """Raised when out-of-range data would have been modified."""


@dataclass
class RangeRegenerateOptions:
    start: datetime
    end: datetime
    target_net_pnl: Optional[float] = None
    trades_per_day: Optional[float] = None
    zero_activity_dates: list[date] = field(default_factory=list)
    seed: Optional[int] = None
    regenerate_transactions: bool = False
    deposit_total: Optional[float] = None
    withdrawal_total: Optional[float] = None
    transaction_count: int = 2


def _fingerprint(rows: list[tuple]) -> str:
    h = hashlib.sha256()
    for row in rows:
        h.update(repr(row).encode())
    return h.hexdigest()


async def _out_of_range_fingerprint(
    db: AsyncSession, start: datetime, end: datetime, include_transactions: bool
) -> tuple[str, int]:
    """Fingerprint every trade (and optionally transaction) outside the window."""
    activity = func.coalesce(Trade.exit_time, Trade.entry_time)
    trade_rows = (
        await db.execute(
            select(
                Trade.id,
                Trade.bot_id,
                Trade.symbol,
                Trade.direction,
                Trade.status,
                Trade.entry_price,
                Trade.exit_price,
                Trade.quantity,
                Trade.leverage,
                Trade.pnl,
                Trade.pnl_percent,
                Trade.fee,
                Trade.entry_time,
                Trade.exit_time,
                Trade.is_pinned,
            )
            .where(or_(Trade.entry_time < start, activity > end))
            .order_by(Trade.id)
        )
    ).all()

    rows = [("trade",) + tuple(r) for r in trade_rows]

    if include_transactions:
        tx_rows = (
            await db.execute(
                select(
                    Transaction.id,
                    Transaction.account_id,
                    Transaction.type,
                    Transaction.amount,
                    Transaction.note,
                    Transaction.date,
                )
                .where(or_(Transaction.date < start, Transaction.date > end))
                .order_by(Transaction.id)
            )
        ).all()
        rows += [("tx",) + tuple(r) for r in tx_rows]

    return _fingerprint(rows), len(rows)


async def _reference_price(db: AsyncSession, bot: Bot, symbol: str, when: datetime) -> float:
    """Best-effort price for a symbol: the bot's own history, market data, or a default."""
    price = (
        await db.execute(
            select(Trade.entry_price)
            .where(Trade.bot_id == bot.id, Trade.symbol == symbol)
            .order_by(func.abs(func.julianday(Trade.entry_time) - func.julianday(when)))
            .limit(1)
        )
    ).scalar()
    if price:
        return float(price)

    price = (
        await db.execute(
            select(MarketData.close)
            .where(MarketData.symbol == symbol)
            .order_by(MarketData.timestamp.desc())
            .limit(1)
        )
    ).scalar()
    if price:
        return float(price)

    return FALLBACK_PRICES.get(symbol.split("/")[0].upper(), 1000.0)


def _active_days(start: datetime, end: datetime, zero_days: set[date]) -> list[date]:
    days = []
    cursor = start.date()
    while cursor <= end.date():
        if cursor not in zero_days:
            days.append(cursor)
        cursor += timedelta(days=1)
    return days


def _build_trades(
    bot: Bot,
    target_pnl: float,
    active_days: list[date],
    start: datetime,
    end: datetime,
    trades_per_day: Optional[float],
    prices: dict[str, float],
    rng: random.Random,
) -> list[Trade]:
    strategy = bot.strategy_type or "grid"
    per_day = trades_per_day if trades_per_day else STRATEGY_TRADES_PER_DAY.get(strategy, 1.0)
    win_rate = STRATEGY_WIN_RATE.get(strategy, 0.5) + rng.uniform(-0.08, 0.08)

    num_trades = max(1, int(round(len(active_days) * per_day * rng.uniform(0.7, 1.2))))
    num_wins = int(num_trades * win_rate)
    win_flags = [True] * num_wins + [False] * (num_trades - num_wins)
    rng.shuffle(win_flags)

    avg_magnitude = max(abs(target_pnl) / num_trades * 3, 1.0)
    symbols = list(prices.keys())
    active_day_set = set(active_days)

    trades: list[Trade] = []
    for is_win in win_flags:
        symbol = rng.choice(symbols)
        day = rng.choice(active_days)
        entry_time = datetime.combine(day, datetime.min.time()) + timedelta(
            hours=rng.randint(0, 22), minutes=rng.randint(0, 59)
        )
        entry_time = min(max(entry_time, start), end)

        exit_time = entry_time + timedelta(hours=rng.randint(1, 30))
        while exit_time > end or exit_time.date() not in active_day_set:
            exit_time -= timedelta(hours=rng.randint(1, 6))
            if exit_time <= entry_time:
                exit_time = min(
                    entry_time + timedelta(minutes=30),
                    datetime.combine(entry_time.date(), datetime.max.time()),
                    end,
                )
                break

        pnl = abs(rng.gauss(avg_magnitude, avg_magnitude * 0.6))
        pnl = max(0.10, pnl) if is_win else -max(0.10, pnl)

        entry_price = prices[symbol] * rng.uniform(0.97, 1.03)
        quantity = round(rng.uniform(0.01, 0.25), 4)
        if entry_price * quantity < 1:
            quantity = round(1.0 / entry_price, 4)
        leverage = round(rng.uniform(1, 8), 1)
        fee = round(max(0.01, abs(pnl) * rng.uniform(0.001, 0.005)), 2)

        trades.append(
            Trade(
                bot_id=bot.id,
                symbol=symbol,
                direction=rng.choice(["long", "short"]),
                status="closed",
                entry_price=round(entry_price, 2),
                exit_price=round(entry_price, 2),
                quantity=quantity,
                leverage=leverage,
                pnl=round(pnl, 2),
                pnl_percent=0.0,
                fee=fee,
                entry_time=entry_time,
                exit_time=exit_time,
                is_pinned=False,
            )
        )

    if trades:
        drift = target_pnl - sum(t.pnl for t in trades)
        trades[-1].pnl = round(trades[-1].pnl + drift, 2)

    for t in trades:
        _apply_exit_price(t)

    trades.sort(key=lambda t: t.entry_time)
    return trades


def _apply_exit_price(trade: Trade) -> None:
    """Back-derive the exit price so the trade's own fields reproduce its P&L."""
    denom = max(trade.quantity * trade.leverage, 1e-9)
    gross = trade.pnl + trade.fee
    if trade.direction == "long":
        trade.exit_price = round(trade.entry_price + gross / denom, 4)
    else:
        trade.exit_price = round(trade.entry_price - gross / denom, 4)
    trade.exit_price = max(0.01, trade.exit_price)
    notional = trade.entry_price * trade.quantity
    trade.pnl_percent = round((trade.pnl / notional * 100) if notional > 0 else 0.0, 4)


def _distribute_targets(
    bots: list[Bot], total: float, rng: random.Random
) -> dict[int, float]:
    if len(bots) == 1:
        return {bots[0].id: round(total, 2)}

    raw = []
    for _ in bots:
        if rng.random() < 0.55:
            raw.append(rng.uniform(1.0, 6.0))
        else:
            raw.append(rng.uniform(-5.0, -1.0))
    adj = (total - sum(raw)) / len(raw)
    targets = {b.id: round(raw[i] + adj, 2) for i, b in enumerate(bots)}
    targets[bots[-1].id] = round(
        targets[bots[-1].id] + (total - sum(targets.values())), 2
    )
    return targets


async def _update_account_balance(db: AsyncSession, account: Account) -> None:
    """Recompute the account balance from stored trade P&L and transactions.

    Deliberately does not re-derive individual trade P&L, so historical trades
    are read-only here.
    """
    pnl = (
        await db.execute(
            select(func.coalesce(func.sum(Trade.pnl), 0.0))
            .join(Bot, Trade.bot_id == Bot.id)
            .where(Bot.account_id == account.id)
        )
    ).scalar() or 0.0
    deposits = (
        await db.execute(
            select(func.coalesce(func.sum(Transaction.amount), 0.0)).where(
                Transaction.account_id == account.id, Transaction.type == "deposit"
            )
        )
    ).scalar() or 0.0
    withdrawals = (
        await db.execute(
            select(func.coalesce(func.sum(Transaction.amount), 0.0)).where(
                Transaction.account_id == account.id, Transaction.type == "withdrawal"
            )
        )
    ).scalar() or 0.0
    account.current_balance = round(account.initial_balance + pnl + deposits - withdrawals, 2)


async def regenerate_range(
    db: AsyncSession,
    bots: list[Bot],
    opts: RangeRegenerateOptions,
) -> dict:
    """Replace in-range activity for ``bots``, leaving everything else untouched."""
    if not bots:
        return {
            "deleted_trades": 0,
            "generated_trades": 0,
            "deleted_transactions": 0,
            "generated_transactions": 0,
            "net_pnl": 0.0,
            "bots_regenerated": 0,
            "bots_skipped_locked": 0,
            "preserved_rows": 0,
        }

    start, end = opts.start, opts.end
    rng = random.Random(opts.seed if opts.seed is not None else int(start.timestamp()))
    zero_days = set(opts.zero_activity_dates)
    active_days = _active_days(start, end, zero_days)
    if not active_days:
        raise RangeRegenerationError(
            "Every day in the selected period is marked as zero-activity"
        )

    before_fp, preserved_rows = await _out_of_range_fingerprint(
        db, start, end, include_transactions=True
    )

    open_bots = [b for b in bots if not b.is_pinned]
    skipped = len(bots) - len(open_bots)
    account_ids = {b.account_id for b in open_bots}

    # ── delete in-range, unpinned, fully-contained trades ──────────────
    activity = func.coalesce(Trade.exit_time, Trade.entry_time)
    doomed = list(
        (
            await db.execute(
                select(Trade).where(
                    Trade.bot_id.in_([b.id for b in open_bots]),
                    Trade.is_pinned == False,  # noqa: E712
                    Trade.entry_time >= start,
                    activity <= end,
                )
            )
        )
        .scalars()
        .all()
    )
    for trade in doomed:
        await db.delete(trade)
    await db.flush()

    # ── optional transaction replacement inside the window ─────────────
    deleted_tx = 0
    generated_tx = 0
    if opts.regenerate_transactions:
        in_range_tx = list(
            (
                await db.execute(
                    select(Transaction).where(
                        Transaction.account_id.in_(account_ids),
                        Transaction.date >= start,
                        Transaction.date <= end,
                    )
                )
            )
            .scalars()
            .all()
        )
        for tx in in_range_tx:
            await db.delete(tx)
        deleted_tx = len(in_range_tx)
        await db.flush()

        specs = [
            ("deposit", opts.deposit_total or 0.0),
            ("withdrawal", opts.withdrawal_total or 0.0),
        ]
        target_accounts = sorted(account_ids)
        for tx_type, total in specs:
            if total <= 0 or not target_accounts:
                continue
            count = max(1, opts.transaction_count)
            per_tx = round(total / count, 2)
            span = max((end - start).total_seconds(), 1)
            for i in range(count):
                when = start + timedelta(seconds=span * (i + 1) / (count + 1))
                amount = per_tx if i < count - 1 else round(total - per_tx * (count - 1), 2)
                db.add(
                    Transaction(
                        account_id=target_accounts[i % len(target_accounts)],
                        type=tx_type,
                        amount=amount,
                        note=f"Generated {tx_type} ({start.date()} - {end.date()})",
                        date=when,
                    )
                )
                generated_tx += 1
        await db.flush()

    # ── generate replacement trades ────────────────────────────────────
    target_total = opts.target_net_pnl if opts.target_net_pnl is not None else 0.0
    targets = (
        _distribute_targets(open_bots, target_total, rng)
        if opts.target_net_pnl is not None
        else {b.id: rng.uniform(-40, 60) for b in open_bots}
    )

    generated = 0
    net_pnl = 0.0
    for bot in open_bots:
        symbols = bot.symbols or ([bot.symbol] if bot.symbol else ["BTC/USDT"])
        prices = {s: await _reference_price(db, bot, s, start) for s in symbols}
        new_trades = _build_trades(
            bot=bot,
            target_pnl=targets[bot.id],
            active_days=active_days,
            start=start,
            end=end,
            trades_per_day=opts.trades_per_day,
            prices=prices,
            rng=rng,
        )
        for trade in new_trades:
            db.add(trade)
            net_pnl += trade.pnl
        generated += len(new_trades)
    await db.flush()

    # ── rebuild derived rows only ──────────────────────────────────────
    for bot in open_bots:
        bot_trades = list(
            (await db.execute(select(Trade).where(Trade.bot_id == bot.id))).scalars().all()
        )
        await rebuild_pnl_records(db, bot.id, bot_trades)

    for account_id in account_ids:
        account = await db.get(Account, account_id)
        if account:
            await _update_account_balance(db, account)
    await db.flush()

    # ── verify nothing outside the window moved ────────────────────────
    after_fp, _ = await _out_of_range_fingerprint(db, start, end, include_transactions=True)
    if after_fp != before_fp:
        await db.rollback()
        raise RangeRegenerationError(
            "Aborted: data outside the selected period would have changed"
        )

    await db.commit()

    return {
        "deleted_trades": len(doomed),
        "generated_trades": generated,
        "deleted_transactions": deleted_tx,
        "generated_transactions": generated_tx,
        "net_pnl": round(net_pnl, 2),
        "bots_regenerated": len(open_bots),
        "bots_skipped_locked": skipped,
        "preserved_rows": preserved_rows,
        "zero_activity_days": [d.isoformat() for d in sorted(zero_days)],
    }
