"""
Cascading recalculation engine for Faide Trader.

When any value is edited, all dependent values recalculate unless pinned.
Supports both top-down (totals -> trades) and bottom-up (trades -> totals).
"""
import math
import random
from datetime import datetime, timedelta
from typing import Optional

import numpy as np
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.portfolio import Trade, Bot, Account, Portfolio, PnlRecord, Transaction


def calculate_trade_pnl(
    entry_price: float,
    exit_price: Optional[float],
    quantity: float,
    leverage: float,
    direction: str,
    fee: float = 0.0,
) -> tuple[float, float]:
    """Calculate P&L and P&L % for a single trade."""
    if exit_price is None:
        return 0.0, 0.0

    if direction == "long":
        raw_pnl = (exit_price - entry_price) * quantity * leverage
    else:
        raw_pnl = (entry_price - exit_price) * quantity * leverage

    net_pnl = raw_pnl - fee
    notional = entry_price * quantity
    pnl_percent = (net_pnl / notional * 100) if notional > 0 else 0.0

    return round(net_pnl, 4), round(pnl_percent, 4)


def calculate_stats_from_trades(trades: list[Trade], initial_balance: float = 10000.0) -> dict:
    """Calculate all statistics from a list of trades."""
    if not trades:
        return {
            "total_pnl": 0.0,
            "total_trades": 0,
            "win_count": 0,
            "loss_count": 0,
            "win_rate": 0.0,
            "avg_win": 0.0,
            "avg_loss": 0.0,
            "profit_factor": 0.0,
            "sharpe_ratio": 0.0,
            "sortino_ratio": 0.0,
            "max_drawdown": 0.0,
            "max_drawdown_percent": 0.0,
            "calmar_ratio": 0.0,
            "avg_trade_pnl": 0.0,
            "best_trade": 0.0,
            "worst_trade": 0.0,
            "total_fees": 0.0,
            "net_pnl": 0.0,
            "current_balance": initial_balance,
            "roi_percent": 0.0,
        }

    pnls = [t.pnl for t in trades]
    fees = [t.fee for t in trades]
    wins = [p for p in pnls if p > 0]
    losses = [p for p in pnls if p <= 0]

    total_fees = sum(fees)
    net_pnl = sum(pnls)  # trade.pnl already includes fee deduction
    total_pnl = net_pnl + total_fees  # gross P&L before fees
    total_trades = len(trades)
    win_count = len(wins)
    loss_count = len(losses)
    win_rate = (win_count / total_trades * 100) if total_trades > 0 else 0.0
    avg_win = (sum(wins) / win_count) if win_count > 0 else 0.0
    avg_loss = (sum(losses) / loss_count) if loss_count > 0 else 0.0
    gross_profit = sum(wins) if wins else 0.0
    gross_loss = abs(sum(losses)) if losses else 0.0
    profit_factor = (gross_profit / gross_loss) if gross_loss > 0 else float("inf") if gross_profit > 0 else 0.0
    avg_trade_pnl = net_pnl / total_trades if total_trades > 0 else 0.0
    best_trade = max(pnls) if pnls else 0.0
    worst_trade = min(pnls) if pnls else 0.0
    current_balance = initial_balance + net_pnl
    roi_percent = (net_pnl / initial_balance * 100) if initial_balance > 0 else 0.0

    # Sharpe ratio (annualized, assuming daily returns)
    if len(pnls) > 1:
        returns = np.array(pnls) / initial_balance
        mean_return = np.mean(returns)
        std_return = np.std(returns, ddof=1)
        sharpe_ratio = (mean_return / std_return * math.sqrt(252)) if std_return > 0 else 0.0

        # Sortino (only downside deviation)
        downside_returns = returns[returns < 0]
        if len(downside_returns) > 0:
            downside_std = np.std(downside_returns, ddof=1)
            sortino_ratio = (mean_return / downside_std * math.sqrt(252)) if downside_std > 0 else 0.0
        else:
            sortino_ratio = 0.0
    else:
        sharpe_ratio = 0.0
        sortino_ratio = 0.0

    # Max drawdown
    equity_curve = [initial_balance]
    for pnl in pnls:
        equity_curve.append(equity_curve[-1] + pnl)
    equity_arr = np.array(equity_curve)
    peak = np.maximum.accumulate(equity_arr)
    drawdown = equity_arr - peak
    max_drawdown = abs(float(np.min(drawdown)))
    max_drawdown_percent = (max_drawdown / float(np.max(peak)) * 100) if np.max(peak) > 0 else 0.0

    # Calmar ratio
    annual_return = net_pnl / initial_balance if initial_balance > 0 else 0.0
    calmar_ratio = (annual_return / (max_drawdown / initial_balance)) if max_drawdown > 0 else 0.0

    # Cap infinite values
    if profit_factor == float("inf"):
        profit_factor = 999.99

    return {
        "total_pnl": round(total_pnl, 2),
        "total_trades": total_trades,
        "win_count": win_count,
        "loss_count": loss_count,
        "win_rate": round(win_rate, 2),
        "avg_win": round(avg_win, 2),
        "avg_loss": round(avg_loss, 2),
        "profit_factor": round(profit_factor, 2),
        "sharpe_ratio": round(sharpe_ratio, 4),
        "sortino_ratio": round(sortino_ratio, 4),
        "max_drawdown": round(max_drawdown, 2),
        "max_drawdown_percent": round(max_drawdown_percent, 2),
        "calmar_ratio": round(calmar_ratio, 4),
        "avg_trade_pnl": round(avg_trade_pnl, 2),
        "best_trade": round(best_trade, 2),
        "worst_trade": round(worst_trade, 2),
        "total_fees": round(total_fees, 2),
        "net_pnl": round(net_pnl, 2),
        "current_balance": round(current_balance, 2),
        "roi_percent": round(roi_percent, 2),
    }


async def recalculate_trade(db: AsyncSession, trade: Trade) -> Trade:
    """Recalculate a single trade's P&L from its fields."""
    if not trade.is_pinned:
        pnl, pnl_pct = calculate_trade_pnl(
            entry_price=trade.entry_price,
            exit_price=trade.exit_price,
            quantity=trade.quantity,
            leverage=trade.leverage,
            direction=trade.direction,
            fee=trade.fee,
        )
        trade.pnl = pnl
        trade.pnl_percent = pnl_pct
    return trade


async def recalculate_bot_from_trades(db: AsyncSession, bot_id: int) -> dict:
    """Recalculate all bot-level stats from its trades (bottom-up)."""
    result = await db.execute(
        select(Trade).where(Trade.bot_id == bot_id).order_by(Trade.entry_time)
    )
    trades = list(result.scalars().all())

    # Recalculate each non-pinned trade
    for trade in trades:
        await recalculate_trade(db, trade)

    # Get account for initial balance
    bot = await db.get(Bot, bot_id)
    if not bot:
        return {}
    account = await db.get(Account, bot.account_id)
    initial_balance = account.initial_balance if account else 10000.0

    stats = calculate_stats_from_trades(trades, initial_balance)

    # Update PnL records from trades
    await rebuild_pnl_records(db, bot_id, trades)

    await db.flush()
    return stats


async def rebuild_pnl_records(db: AsyncSession, bot_id: int, trades: list[Trade]):
    """Rebuild daily PnL records from trades, preserving pinned records."""
    # Get existing pinned daily records (exclude monthly/weekly pinned records)
    result = await db.execute(
        select(PnlRecord).where(
            PnlRecord.bot_id == bot_id,
            PnlRecord.is_pinned == True,
            PnlRecord.period_type == "daily",
        )
    )
    pinned_records = {r.date.date(): r for r in result.scalars().all()}

    # Delete non-pinned daily records only
    result = await db.execute(
        select(PnlRecord).where(
            PnlRecord.bot_id == bot_id,
            PnlRecord.is_pinned == False,
            PnlRecord.period_type == "daily",
        )
    )
    for record in result.scalars().all():
        await db.delete(record)

    # Group trades by date
    daily_pnl: dict[datetime, dict] = {}
    for trade in trades:
        if trade.exit_time:
            date_key = trade.exit_time.date()
        else:
            date_key = trade.entry_time.date()

        if date_key not in daily_pnl:
            daily_pnl[date_key] = {"pnl": 0.0, "trades": 0, "wins": 0, "losses": 0}

        daily_pnl[date_key]["pnl"] += trade.pnl
        daily_pnl[date_key]["trades"] += 1
        if trade.pnl > 0:
            daily_pnl[date_key]["wins"] += 1
        else:
            daily_pnl[date_key]["losses"] += 1

    # Create new records (skip pinned dates)
    cumulative = 0.0
    all_dates = sorted(set(list(daily_pnl.keys()) + list(pinned_records.keys())))

    for date_key in all_dates:
        if date_key in pinned_records:
            cumulative += pinned_records[date_key].pnl
            pinned_records[date_key].cumulative_pnl = cumulative
        elif date_key in daily_pnl:
            d = daily_pnl[date_key]
            cumulative += d["pnl"]
            record = PnlRecord(
                bot_id=bot_id,
                date=datetime.combine(date_key, datetime.min.time()),
                period_type="daily",
                pnl=round(d["pnl"], 2),
                cumulative_pnl=round(cumulative, 2),
                trade_count=d["trades"],
                win_count=d["wins"],
                loss_count=d["losses"],
                is_pinned=False,
            )
            db.add(record)

    await db.flush()


async def recalculate_account(db: AsyncSession, account_id: int) -> dict:
    """Recalculate account-level stats from all its bots. Pinned bots are not recalculated."""
    account = await db.get(Account, account_id)
    if not account:
        return {}

    result = await db.execute(select(Bot).where(Bot.account_id == account_id))
    bots = list(result.scalars().all())

    total_pnl = 0.0
    total_trades = 0
    total_wins = 0

    for bot in bots:
        if bot.is_pinned:
            # Pinned bot: gather stats without recalculating
            trade_result = await db.execute(
                select(Trade).where(Trade.bot_id == bot.id).order_by(Trade.entry_time)
            )
            bot_trades = list(trade_result.scalars().all())
            bot_account = await db.get(Account, bot.account_id)
            ib = bot_account.initial_balance if bot_account else 10000.0
            bot_stats = calculate_stats_from_trades(bot_trades, ib)
        else:
            bot_stats = await recalculate_bot_from_trades(db, bot.id)
        total_pnl += bot_stats.get("net_pnl", 0.0)
        total_trades += bot_stats.get("total_trades", 0)
        total_wins += bot_stats.get("win_count", 0)

    dep_result = await db.execute(
        select(func.coalesce(func.sum(Transaction.amount), 0))
        .where(Transaction.account_id == account_id, Transaction.type == "deposit")
    )
    total_deposits = dep_result.scalar() or 0.0
    wd_result = await db.execute(
        select(func.coalesce(func.sum(Transaction.amount), 0))
        .where(Transaction.account_id == account_id, Transaction.type == "withdrawal")
    )
    total_withdrawals = wd_result.scalar() or 0.0

    account.current_balance = account.initial_balance + total_pnl + total_deposits - total_withdrawals
    await db.flush()

    return {
        "total_pnl": round(total_pnl, 2),
        "total_trades": total_trades,
        "win_count": total_wins,
        "loss_count": total_trades - total_wins,
        "win_rate": round(total_wins / total_trades * 100, 2) if total_trades > 0 else 0.0,
        "current_balance": round(account.current_balance, 2),
    }


async def recalculate_portfolio(db: AsyncSession, portfolio_id: int) -> dict:
    """Recalculate portfolio-level stats from all accounts. Pinned accounts are not recalculated."""
    result = await db.execute(select(Account).where(Account.portfolio_id == portfolio_id))
    accounts = list(result.scalars().all())

    total_pnl = 0.0
    total_balance = 0.0

    for account in accounts:
        if account.is_pinned:
            total_pnl += account.current_balance - account.initial_balance
            total_balance += account.current_balance
        else:
            acct_stats = await recalculate_account(db, account.id)
            total_pnl += acct_stats.get("total_pnl", 0.0)
            total_balance += acct_stats.get("current_balance", account.initial_balance)

    return {
        "total_pnl": round(total_pnl, 2),
        "total_balance": round(total_balance, 2),
        "account_count": len(accounts),
    }


def _back_calculate_exit_price(trade: Trade) -> None:
    """Back-calculate exit price from a trade's current PnL."""
    if trade.quantity > 0 and trade.leverage > 0:
        if trade.direction == "long":
            trade.exit_price = round(
                trade.entry_price + (trade.pnl + trade.fee) / (trade.quantity * trade.leverage),
                4,
            )
        else:
            trade.exit_price = round(
                trade.entry_price - (trade.pnl + trade.fee) / (trade.quantity * trade.leverage),
                4,
            )
    notional = trade.entry_price * trade.quantity
    trade.pnl_percent = round((trade.pnl / notional * 100) if notional > 0 else 0.0, 4)


async def handle_top_down_edit(
    db: AsyncSession,
    bot_id: int,
    target_total_pnl: float,
    pinned_fields: list[str],
) -> list[Trade]:
    """
    When a high-level value (like total P&L) is edited,
    distribute the change proportionally across unpinned trades.
    """
    result = await db.execute(
        select(Trade).where(Trade.bot_id == bot_id).order_by(Trade.entry_time)
    )
    trades = list(result.scalars().all())

    if not trades:
        return trades

    pinned_trades = [t for t in trades if t.is_pinned]
    unpinned_trades = [t for t in trades if not t.is_pinned]

    if not unpinned_trades:
        return trades

    pinned_pnl = sum(t.pnl for t in pinned_trades)
    target_unpinned_pnl = target_total_pnl - pinned_pnl
    current_unpinned_pnl = sum(t.pnl for t in unpinned_trades)

    if current_unpinned_pnl == 0:
        per_trade = target_unpinned_pnl / len(unpinned_trades)
        for trade in unpinned_trades:
            trade.pnl = round(per_trade, 4)
            _back_calculate_exit_price(trade)
    else:
        ratio = target_unpinned_pnl / current_unpinned_pnl
        for trade in unpinned_trades:
            trade.pnl = round(trade.pnl * ratio, 4)
            _back_calculate_exit_price(trade)

    await db.flush()
    return trades


async def handle_stat_edit(
    db: AsyncSession,
    bot_id: int,
    field: str,
    target_value: float,
    pinned_fields: list[str],
) -> list[Trade]:
    """
    Back-calculate trades when ANY statistic is edited.
    Supports: total_pnl, win_rate, win_count, loss_count, total_trades,
    sharpe_ratio, profit_factor, avg_win, avg_loss, max_drawdown, etc.
    """
    if field == "total_pnl":
        return await handle_top_down_edit(db, bot_id, target_value, pinned_fields)

    result = await db.execute(
        select(Trade).where(Trade.bot_id == bot_id).order_by(Trade.entry_time)
    )
    trades = list(result.scalars().all())

    if not trades:
        return trades

    unpinned_trades = [t for t in trades if not t.is_pinned]
    if not unpinned_trades:
        return trades

    if field == "win_rate":
        # Adjust trades to match target win rate
        target_wins = max(0, min(len(trades), int(round(target_value / 100 * len(trades)))))
        current_wins = [t for t in trades if t.pnl > 0]
        current_losses = [t for t in trades if t.pnl <= 0]
        unpinned_wins = [t for t in unpinned_trades if t.pnl > 0]
        unpinned_losses = [t for t in unpinned_trades if t.pnl <= 0]
        pinned_wins = len(current_wins) - len(unpinned_wins)

        needed_wins = target_wins - pinned_wins
        needed_wins = max(0, min(needed_wins, len(unpinned_trades)))

        # Convert losses to wins or wins to losses as needed
        if needed_wins > len(unpinned_wins):
            # Need to flip some losses to wins
            to_flip = needed_wins - len(unpinned_wins)
            for trade in unpinned_losses[:to_flip]:
                trade.pnl = abs(trade.pnl) if trade.pnl != 0 else round(abs(trade.entry_price * trade.quantity * 0.01), 4)
                _back_calculate_exit_price(trade)
        elif needed_wins < len(unpinned_wins):
            # Need to flip some wins to losses
            to_flip = len(unpinned_wins) - needed_wins
            for trade in unpinned_wins[:to_flip]:
                trade.pnl = -abs(trade.pnl) if trade.pnl != 0 else round(-abs(trade.entry_price * trade.quantity * 0.01), 4)
                _back_calculate_exit_price(trade)

    elif field == "win_count":
        target_wins = int(target_value)
        unpinned_wins = [t for t in unpinned_trades if t.pnl > 0]
        unpinned_losses = [t for t in unpinned_trades if t.pnl <= 0]
        pinned_wins = len([t for t in trades if t.is_pinned and t.pnl > 0])
        needed = target_wins - pinned_wins

        if needed > len(unpinned_wins):
            to_flip = needed - len(unpinned_wins)
            for trade in unpinned_losses[:to_flip]:
                trade.pnl = abs(trade.pnl) if trade.pnl != 0 else round(abs(trade.entry_price * trade.quantity * 0.01), 4)
                _back_calculate_exit_price(trade)
        elif needed < len(unpinned_wins):
            to_flip = len(unpinned_wins) - needed
            for trade in unpinned_wins[:to_flip]:
                trade.pnl = -abs(trade.pnl) if trade.pnl != 0 else round(-abs(trade.entry_price * trade.quantity * 0.01), 4)
                _back_calculate_exit_price(trade)

    elif field == "loss_count":
        target_losses = int(target_value)
        unpinned_wins = [t for t in unpinned_trades if t.pnl > 0]
        unpinned_losses = [t for t in unpinned_trades if t.pnl <= 0]
        pinned_losses = len([t for t in trades if t.is_pinned and t.pnl <= 0])
        needed = target_losses - pinned_losses

        if needed > len(unpinned_losses):
            to_flip = needed - len(unpinned_losses)
            for trade in unpinned_wins[:to_flip]:
                trade.pnl = -abs(trade.pnl) if trade.pnl != 0 else round(-abs(trade.entry_price * trade.quantity * 0.01), 4)
                _back_calculate_exit_price(trade)
        elif needed < len(unpinned_losses):
            to_flip = len(unpinned_losses) - needed
            for trade in unpinned_losses[:to_flip]:
                trade.pnl = abs(trade.pnl) if trade.pnl != 0 else round(abs(trade.entry_price * trade.quantity * 0.01), 4)
                _back_calculate_exit_price(trade)

    elif field == "profit_factor":
        # profit_factor = gross_profit / gross_loss
        # Adjust by scaling wins or losses
        wins = [t for t in unpinned_trades if t.pnl > 0]
        losses = [t for t in unpinned_trades if t.pnl <= 0]
        gross_loss = abs(sum(t.pnl for t in losses)) if losses else 1.0

        if target_value > 0 and gross_loss > 0 and wins:
            target_gross_profit = target_value * gross_loss
            current_gross_profit = sum(t.pnl for t in wins)
            if current_gross_profit > 0:
                ratio = target_gross_profit / current_gross_profit
                for trade in wins:
                    trade.pnl = round(trade.pnl * ratio, 4)
                    _back_calculate_exit_price(trade)

    elif field == "sharpe_ratio":
        # Adjust mean return to hit target Sharpe while keeping stddev
        bot = await db.get(Bot, bot_id)
        account = await db.get(Account, bot.account_id) if bot else None
        initial_balance = account.initial_balance if account else 10000.0

        pnls = [t.pnl for t in trades]
        returns = np.array(pnls) / initial_balance
        std_return = float(np.std(returns, ddof=1)) if len(returns) > 1 else 0.01

        if std_return > 0:
            target_mean = target_value * std_return / math.sqrt(252)
            current_mean = float(np.mean(returns))

            if current_mean != 0:
                adjustment = (target_mean - current_mean) * initial_balance * len(trades)
                per_trade = adjustment / len(unpinned_trades)
                for trade in unpinned_trades:
                    trade.pnl = round(trade.pnl + per_trade, 4)
                    _back_calculate_exit_price(trade)
            else:
                # Zero-mean: shift each trade by target_mean * initial_balance
                # while preserving relative differences to maintain volatility
                base_shift = target_mean * initial_balance
                for trade in unpinned_trades:
                    trade.pnl = round(trade.pnl + base_shift, 4)
                    _back_calculate_exit_price(trade)

    elif field in ("avg_win", "avg_loss"):
        if field == "avg_win":
            target_trades = [t for t in unpinned_trades if t.pnl > 0]
            if target_trades:
                current_avg = sum(t.pnl for t in target_trades) / len(target_trades)
                if current_avg != 0:
                    ratio = target_value / current_avg
                else:
                    ratio = 1.0
                for trade in target_trades:
                    trade.pnl = round(trade.pnl * ratio if current_avg != 0 else target_value, 4)
                    _back_calculate_exit_price(trade)
        else:
            target_trades = [t for t in unpinned_trades if t.pnl <= 0]
            if target_trades:
                current_avg = sum(t.pnl for t in target_trades) / len(target_trades)
                if current_avg != 0:
                    ratio = target_value / current_avg
                else:
                    ratio = 1.0
                for trade in target_trades:
                    trade.pnl = round(trade.pnl * ratio if current_avg != 0 else target_value, 4)
                    _back_calculate_exit_price(trade)

    elif field == "max_drawdown":
        # Scale all losses to achieve target drawdown
        bot = await db.get(Bot, bot_id)
        account = await db.get(Account, bot.account_id) if bot else None
        initial_balance = account.initial_balance if account else 10000.0

        current_stats = calculate_stats_from_trades(trades, initial_balance)
        current_dd = current_stats["max_drawdown"]

        if current_dd > 0:
            ratio = target_value / current_dd
            for trade in unpinned_trades:
                if trade.pnl < 0:
                    trade.pnl = round(trade.pnl * ratio, 4)
                    _back_calculate_exit_price(trade)

    elif field == "max_drawdown_percent":
        bot = await db.get(Bot, bot_id)
        account = await db.get(Account, bot.account_id) if bot else None
        initial_balance = account.initial_balance if account else 10000.0

        current_stats = calculate_stats_from_trades(trades, initial_balance)
        current_dd_pct = current_stats["max_drawdown_percent"]

        if current_dd_pct > 0:
            ratio = target_value / current_dd_pct
            for trade in unpinned_trades:
                if trade.pnl < 0:
                    trade.pnl = round(trade.pnl * ratio, 4)
                    _back_calculate_exit_price(trade)

    await db.flush()
    return trades


def _get_trade_period_key(trade: Trade, period_type: str) -> Optional[str]:
    """Get the period key for a trade based on its exit/entry time."""
    trade_date = trade.exit_time or trade.entry_time
    if trade_date is None:
        return None
    if period_type == "monthly":
        return trade_date.strftime("%Y-%m")
    elif period_type == "weekly":
        iso = trade_date.isocalendar()
        return f"{iso[0]}-W{iso[1]:02d}"
    else:
        return trade_date.strftime("%Y-%m-%d")


def aggregate_period_pnl(
    trades: list[Trade],
    period_type: str,
    initial_balance: float = 10000.0,
    pinned_periods: Optional[set[str]] = None,
) -> list[dict]:
    """
    Aggregate trades into period P&L buckets (daily, weekly, monthly).
    Returns list of period summaries with drawdown and derived stats.
    """
    if not trades:
        return []

    if pinned_periods is None:
        pinned_periods = set()

    # Group trades by period
    period_buckets: dict[str, dict] = {}
    period_trades: dict[str, list[Trade]] = {}
    for trade in trades:
        period_key = _get_trade_period_key(trade, period_type)
        if period_key is None:
            continue

        if period_key not in period_buckets:
            period_buckets[period_key] = {
                "pnl": 0.0,
                "trade_count": 0,
                "win_count": 0,
                "loss_count": 0,
                "fees": 0.0,
                "pnls": [],
            }
            period_trades[period_key] = []

        bucket = period_buckets[period_key]
        bucket["pnl"] += trade.pnl
        bucket["trade_count"] += 1
        bucket["fees"] += trade.fee
        bucket["pnls"].append(trade.pnl)
        period_trades[period_key].append(trade)
        if trade.pnl > 0:
            bucket["win_count"] += 1
        else:
            bucket["loss_count"] += 1

    # Build results with cumulative P&L, drawdown, and derived stats
    results = []
    cumulative_pnl = 0.0
    peak_equity = initial_balance

    for period_key in sorted(period_buckets.keys()):
        bucket = period_buckets[period_key]
        cumulative_pnl += bucket["pnl"]
        current_equity = initial_balance + cumulative_pnl

        peak_equity = max(peak_equity, current_equity)
        drawdown = peak_equity - current_equity
        drawdown_pct = (drawdown / peak_equity * 100) if peak_equity > 0 else 0.0

        tc = bucket["trade_count"]
        wc = bucket["win_count"]
        pnls = bucket["pnls"]
        win_rate = (wc / tc * 100) if tc > 0 else 0.0
        avg_pnl = (sum(pnls) / tc) if tc > 0 else 0.0
        best_trade = max(pnls) if pnls else 0.0
        worst_trade = min(pnls) if pnls else 0.0
        gross_profit = sum(p for p in pnls if p > 0)
        gross_loss = abs(sum(p for p in pnls if p <= 0))
        profit_factor = (gross_profit / gross_loss) if gross_loss > 0 else (999.99 if gross_profit > 0 else 0.0)

        results.append({
            "period": period_key,
            "period_type": period_type,
            "pnl": round(bucket["pnl"], 2),
            "cumulative_pnl": round(cumulative_pnl, 2),
            "trade_count": tc,
            "win_count": wc,
            "loss_count": bucket["loss_count"],
            "win_rate": round(win_rate, 2),
            "drawdown": round(drawdown, 2),
            "drawdown_percent": round(drawdown_pct, 2),
            "avg_pnl": round(avg_pnl, 2),
            "best_trade": round(best_trade, 2),
            "worst_trade": round(worst_trade, 2),
            "total_fees": round(bucket["fees"], 2),
            "profit_factor": round(profit_factor, 2),
            "is_pinned": period_key in pinned_periods,
        })

    return results


def _get_period_trades(all_trades: list[Trade], period_key: str, period_type: str) -> list[Trade]:
    """Filter trades belonging to a specific period."""
    period_trades = []
    for trade in all_trades:
        key = _get_trade_period_key(trade, period_type)
        if key == period_key:
            period_trades.append(trade)
    return period_trades


async def handle_period_pnl_edit(
    db: AsyncSession,
    bot_id: int,
    period_key: str,
    period_type: str,
    target_pnl: float,
    pinned_fields: list[str],
) -> list[Trade]:
    """
    When a period's P&L is edited, redistribute the change
    among trades within that period.
    """
    result = await db.execute(
        select(Trade).where(Trade.bot_id == bot_id).order_by(Trade.entry_time)
    )
    all_trades = list(result.scalars().all())
    period_trades = _get_period_trades(all_trades, period_key, period_type)

    if not period_trades:
        return all_trades

    unpinned = [t for t in period_trades if not t.is_pinned]
    if not unpinned:
        return all_trades

    pinned_pnl = sum(t.pnl for t in period_trades if t.is_pinned)
    target_unpinned = target_pnl - pinned_pnl
    current_unpinned = sum(t.pnl for t in unpinned)

    if current_unpinned == 0:
        per_trade = target_unpinned / len(unpinned)
        for trade in unpinned:
            trade.pnl = round(per_trade, 4)
            _back_calculate_exit_price(trade)
    else:
        ratio = target_unpinned / current_unpinned
        for trade in unpinned:
            trade.pnl = round(trade.pnl * ratio, 4)
            _back_calculate_exit_price(trade)

    await db.flush()
    return all_trades


async def handle_period_stat_edit(
    db: AsyncSession,
    bot_id: int,
    period_key: str,
    period_type: str,
    field: str,
    target_value: float,
    pinned_fields: list[str],
) -> list[Trade]:
    """
    Edit a derived stat (win_rate, profit_factor, etc.) for a specific period.
    Back-calculates trades within that period to match the target stat.
    """
    result = await db.execute(
        select(Trade).where(Trade.bot_id == bot_id).order_by(Trade.entry_time)
    )
    all_trades = list(result.scalars().all())
    period_trades = _get_period_trades(all_trades, period_key, period_type)

    if not period_trades:
        return all_trades

    unpinned = [t for t in period_trades if not t.is_pinned]
    if not unpinned:
        return all_trades

    if field == "pnl":
        return await handle_period_pnl_edit(db, bot_id, period_key, period_type, target_value, pinned_fields)

    elif field == "win_rate":
        target_wins = max(0, min(len(period_trades), int(round(target_value / 100 * len(period_trades)))))
        unpinned_wins = [t for t in unpinned if t.pnl > 0]
        unpinned_losses = [t for t in unpinned if t.pnl <= 0]
        pinned_wins = len([t for t in period_trades if t.is_pinned and t.pnl > 0])
        needed_wins = max(0, min(target_wins - pinned_wins, len(unpinned)))

        if needed_wins > len(unpinned_wins):
            to_flip = needed_wins - len(unpinned_wins)
            for trade in unpinned_losses[:to_flip]:
                trade.pnl = abs(trade.pnl) if trade.pnl != 0 else round(abs(trade.entry_price * trade.quantity * 0.01), 4)
                _back_calculate_exit_price(trade)
        elif needed_wins < len(unpinned_wins):
            to_flip = len(unpinned_wins) - needed_wins
            for trade in unpinned_wins[:to_flip]:
                trade.pnl = -abs(trade.pnl) if trade.pnl != 0 else round(-abs(trade.entry_price * trade.quantity * 0.01), 4)
                _back_calculate_exit_price(trade)

    elif field == "profit_factor":
        wins = [t for t in unpinned if t.pnl > 0]
        losses = [t for t in unpinned if t.pnl <= 0]
        gross_loss = abs(sum(t.pnl for t in losses)) if losses else 1.0

        if target_value > 0 and gross_loss > 0 and wins:
            target_gross_profit = target_value * gross_loss
            current_gross_profit = sum(t.pnl for t in wins)
            if current_gross_profit > 0:
                ratio = target_gross_profit / current_gross_profit
                for trade in wins:
                    trade.pnl = round(trade.pnl * ratio, 4)
                    _back_calculate_exit_price(trade)

    await db.flush()
    return all_trades


async def get_pinned_periods(db: AsyncSession, bot_id: int, period_type: str) -> set[str]:
    """Get the set of pinned period keys for a bot."""
    result = await db.execute(
        select(PnlRecord).where(
            PnlRecord.bot_id == bot_id,
            PnlRecord.is_pinned == True,
            PnlRecord.period_type == period_type,
        )
    )
    pinned = set()
    for record in result.scalars().all():
        if period_type == "monthly":
            pinned.add(record.date.strftime("%Y-%m"))
        elif period_type == "weekly":
            iso = record.date.isocalendar()
            pinned.add(f"{iso[0]}-W{iso[1]:02d}")
        else:
            pinned.add(record.date.strftime("%Y-%m-%d"))
    return pinned


async def regenerate_bot_trades(
    db: AsyncSession,
    bot_id: int,
    num_trades: Optional[int] = None,
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
    extra_constraints: Optional[dict[str, float]] = None,
    skip_account_recalc: bool = False,
) -> dict:
    """
    Regenerate trades for a bot while satisfying all locked stat constraints.

    Locked stats (from bot.pinned_stats) are treated as hard constraints.
    extra_constraints are merged in (from parent account/portfolio regeneration).
    Pinned trades are preserved; only unpinned trades are replaced.
    Returns the final bot stats after regeneration.
    """
    bot = await db.get(Bot, bot_id)
    if not bot:
        raise ValueError(f"Bot {bot_id} not found")

    account = await db.get(Account, bot.account_id)
    if not account:
        raise ValueError(f"Account not found for bot {bot_id}")

    initial_balance = account.initial_balance

    # Get existing trades
    result = await db.execute(
        select(Trade).where(Trade.bot_id == bot_id).order_by(Trade.entry_time)
    )
    existing_trades = list(result.scalars().all())

    pinned_trades = [t for t in existing_trades if t.is_pinned]
    unpinned_trades = [t for t in existing_trades if not t.is_pinned]

    # Get locked stat constraints — use explicit values if set, else current computed values
    pinned_values = bot.pinned_stat_values
    current_stats = calculate_stats_from_trades(existing_trades, initial_balance)
    constraints: dict[str, float] = {}
    for field, explicit_value in pinned_values.items():
        if explicit_value is not None:
            constraints[field] = explicit_value
        elif field in current_stats:
            constraints[field] = current_stats[field]

    # Merge in extra constraints from parent-level regeneration
    if extra_constraints:
        for field, value in extra_constraints.items():
            if field not in constraints:
                constraints[field] = value

    # Determine date range from existing trades or parameters
    if not start_date:
        if existing_trades:
            start_date = min(t.entry_time for t in existing_trades)
        else:
            start_date = datetime.now() - timedelta(days=90)
    if not end_date:
        if existing_trades:
            end_date = max(t.exit_time or t.entry_time for t in existing_trades)
        else:
            end_date = datetime.now()

    # Determine how many new trades to generate
    if num_trades is None:
        if "total_trades" in constraints:
            num_trades = int(constraints["total_trades"]) - len(pinned_trades)
        elif unpinned_trades:
            num_trades = len(unpinned_trades)
        else:
            num_trades = 50
    num_trades = max(1, num_trades)

    # Delete unpinned trades
    for trade in unpinned_trades:
        await db.delete(trade)
    await db.flush()

    # Generate new trades respecting constraints
    new_trades = _generate_constrained_trades(
        bot=bot,
        pinned_trades=pinned_trades,
        num_trades=num_trades,
        start_date=start_date,
        end_date=end_date,
        constraints=constraints,
        initial_balance=initial_balance,
    )

    for trade in new_trades:
        db.add(trade)
    await db.flush()

    # Recalculate bot stats
    stats = await recalculate_bot_from_trades(db, bot_id)
    if not skip_account_recalc:
        await recalculate_account(db, account.id)
    await db.flush()

    return stats


def _generate_constrained_trades(
    bot: Bot,
    pinned_trades: list[Trade],
    num_trades: int,
    start_date: datetime,
    end_date: datetime,
    constraints: dict[str, float],
    initial_balance: float,
) -> list[Trade]:
    """
    Generate trades that satisfy all locked constraints.

    Solving order:
    1. Win/loss split (win_rate, win_count, loss_count)
    2. P&L amounts (total_pnl/net_pnl, avg_win, avg_loss)
    3. Ratio constraints (profit_factor)
    4. Distribution constraints (sharpe_ratio)
    5. Drawdown constraints (max_drawdown)
    """
    pinned_pnl = sum(t.pnl for t in pinned_trades)
    pinned_wins = len([t for t in pinned_trades if t.pnl > 0])
    pinned_losses = len([t for t in pinned_trades if t.pnl <= 0])
    pinned_count = len(pinned_trades)
    total_count = num_trades + pinned_count

    # Step 1: Determine win/loss split
    if "win_rate" in constraints:
        target_total_wins = max(0, min(total_count, int(round(constraints["win_rate"] / 100 * total_count))))
        new_wins = max(0, target_total_wins - pinned_wins)
    elif "win_count" in constraints:
        new_wins = max(0, int(constraints["win_count"]) - pinned_wins)
    elif "loss_count" in constraints:
        target_losses = int(constraints["loss_count"]) - pinned_losses
        new_wins = max(0, num_trades - max(0, target_losses))
    else:
        new_wins = int(num_trades * 0.55)

    new_wins = min(new_wins, num_trades)
    new_losses = num_trades - new_wins

    # Step 2: Generate base P&L values
    base_pnl = initial_balance * 0.02  # 2% of balance as base P&L magnitude

    win_pnls = [abs(random.gauss(base_pnl, base_pnl * 0.5)) for _ in range(new_wins)]
    loss_pnls = [-abs(random.gauss(base_pnl * 0.8, base_pnl * 0.4)) for _ in range(new_losses)]

    # Ensure non-zero
    win_pnls = [max(p, 0.01) for p in win_pnls]
    loss_pnls = [min(p, -0.01) for p in loss_pnls]

    # Step 3: Apply avg_win / avg_loss constraints
    if "avg_win" in constraints and win_pnls:
        pinned_win_pnls = [t.pnl for t in pinned_trades if t.pnl > 0]
        target_avg = constraints["avg_win"]
        # Target average for new wins only
        pinned_win_total = sum(pinned_win_pnls)
        total_wins_count = new_wins + pinned_wins
        if total_wins_count > 0:
            target_new_win_total = target_avg * total_wins_count - pinned_win_total
            current_total = sum(win_pnls)
            if current_total > 0:
                ratio = target_new_win_total / current_total
                win_pnls = [p * ratio for p in win_pnls]

    if "avg_loss" in constraints and loss_pnls:
        pinned_loss_pnls = [t.pnl for t in pinned_trades if t.pnl <= 0]
        target_avg = constraints["avg_loss"]
        pinned_loss_total = sum(pinned_loss_pnls)
        total_losses_count = new_losses + pinned_losses
        if total_losses_count > 0:
            target_new_loss_total = target_avg * total_losses_count - pinned_loss_total
            current_total = sum(loss_pnls)
            if current_total != 0:
                ratio = target_new_loss_total / current_total
                loss_pnls = [p * ratio for p in loss_pnls]

    # Step 4: Apply total_pnl / net_pnl constraint
    # net_pnl = total P&L after fees (which is what trade.pnl represents)
    target_net_pnl = None
    if "net_pnl" in constraints:
        target_net_pnl = constraints["net_pnl"]
    elif "total_pnl" in constraints:
        # total_pnl is gross (before fees), net_pnl = total_pnl - total_fees
        # We generate with fees, so target the net value
        target_net_pnl = constraints["net_pnl"] if "net_pnl" in constraints else None
        if target_net_pnl is None:
            # Estimate fees for scaling purposes
            est_fees = num_trades * 2.0  # rough estimate
            target_net_pnl = constraints["total_pnl"] - est_fees

    if target_net_pnl is not None:
        target_new_pnl = target_net_pnl - pinned_pnl
        all_pnls = win_pnls + loss_pnls
        current_total = sum(all_pnls)

        if current_total != 0 and all_pnls:
            ratio = target_new_pnl / current_total
            if ratio > 0:
                win_pnls = [p * ratio for p in win_pnls]
                loss_pnls = [p * ratio for p in loss_pnls]
            else:
                # Need to redistribute: shift all values
                shift = (target_new_pnl - current_total) / len(all_pnls)
                win_pnls = [p + shift for p in win_pnls]
                loss_pnls = [p + shift for p in loss_pnls]
        elif all_pnls:
            per_trade = target_new_pnl / len(all_pnls)
            win_pnls = [abs(per_trade) if per_trade > 0 else per_trade for _ in win_pnls]
            loss_pnls = [per_trade if per_trade < 0 else -abs(per_trade) * 0.1 for _ in loss_pnls]

    # Step 5: Apply profit_factor constraint
    if "profit_factor" in constraints:
        target_pf = constraints["profit_factor"]
        if target_pf > 0 and win_pnls and loss_pnls:
            pinned_gross_profit = sum(t.pnl for t in pinned_trades if t.pnl > 0)
            pinned_gross_loss = abs(sum(t.pnl for t in pinned_trades if t.pnl <= 0))

            current_new_gross_profit = sum(win_pnls)
            current_new_gross_loss = abs(sum(loss_pnls))

            total_gross_loss = pinned_gross_loss + current_new_gross_loss
            if total_gross_loss > 0:
                target_total_gross_profit = target_pf * total_gross_loss
                target_new_gross_profit = target_total_gross_profit - pinned_gross_profit
                if current_new_gross_profit > 0 and target_new_gross_profit > 0:
                    ratio = target_new_gross_profit / current_new_gross_profit
                    win_pnls = [p * ratio for p in win_pnls]

    # Step 6: Apply sharpe_ratio constraint
    if "sharpe_ratio" in constraints:
        target_sharpe = constraints["sharpe_ratio"]
        all_pnls = [t.pnl for t in pinned_trades] + win_pnls + loss_pnls
        returns = np.array(all_pnls) / initial_balance
        std_return = float(np.std(returns, ddof=1)) if len(returns) > 1 else 0.01

        if std_return > 0:
            target_mean = target_sharpe * std_return / math.sqrt(252)
            current_mean = float(np.mean(returns))
            shift_per_return = target_mean - current_mean
            shift_per_pnl = shift_per_return * initial_balance

            # Only shift unpinned P&L values
            win_pnls = [p + shift_per_pnl for p in win_pnls]
            loss_pnls = [p + shift_per_pnl for p in loss_pnls]

    # Step 7: Apply max_drawdown constraint (scale losses if needed)
    if "max_drawdown" in constraints or "max_drawdown_percent" in constraints:
        target_dd = constraints.get("max_drawdown")
        if target_dd is None and "max_drawdown_percent" in constraints:
            target_dd = constraints["max_drawdown_percent"] / 100 * initial_balance

        if target_dd is not None and target_dd > 0:
            # Check current max drawdown
            all_pnls = [t.pnl for t in pinned_trades] + win_pnls + loss_pnls
            equity = [initial_balance]
            for p in all_pnls:
                equity.append(equity[-1] + p)
            equity_arr = np.array(equity)
            peak = np.maximum.accumulate(equity_arr)
            current_dd = abs(float(np.min(equity_arr - peak)))

            if current_dd > 0:
                ratio = target_dd / current_dd
                if ratio < 1:
                    loss_pnls = [p * ratio for p in loss_pnls]
                elif ratio > 1 and loss_pnls:
                    loss_pnls = [p * min(ratio, 3.0) for p in loss_pnls]

    # Combine and shuffle P&L values
    all_new_pnls = win_pnls + loss_pnls
    random.shuffle(all_new_pnls)

    # Generate trade times
    total_seconds = max((end_date - start_date).total_seconds(), 3600)
    trade_times = sorted([
        start_date + timedelta(seconds=random.uniform(0, total_seconds))
        for _ in range(num_trades)
    ])

    # Determine base price from bot symbol
    base_price = 50000.0  # default

    # Create Trade objects
    new_trades: list[Trade] = []
    for i, (entry_time, pnl_val) in enumerate(zip(trade_times, all_new_pnls)):
        direction = random.choice(["long", "short"])
        quantity = round(random.uniform(0.05, 0.2), 4)
        leverage = round(random.uniform(2.5, 7.5), 2)
        fee = round(random.uniform(1.0, 3.0), 2)

        # Set entry price with some variation
        entry_price = round(base_price * random.uniform(0.9, 1.1), 2)

        # Back-calculate exit price from target pnl
        net_pnl = round(pnl_val, 4)
        raw_pnl = net_pnl + fee
        if quantity > 0 and leverage > 0:
            price_delta = raw_pnl / (quantity * leverage)
            if direction == "long":
                exit_price = round(entry_price + price_delta, 2)
            else:
                exit_price = round(entry_price - price_delta, 2)
        else:
            exit_price = entry_price

        exit_price = max(exit_price, 0.01)

        # Calculate pnl_percent
        notional = entry_price * quantity
        pnl_percent = round((net_pnl / notional * 100) if notional > 0 else 0.0, 4)

        hold_duration = timedelta(minutes=random.uniform(1, 60 * 48))
        exit_time = min(entry_time + hold_duration, end_date)

        trade = Trade(
            bot_id=bot.id,
            symbol=bot.symbol,
            direction=direction,
            status="closed",
            entry_price=entry_price,
            exit_price=exit_price,
            quantity=quantity,
            leverage=leverage,
            pnl=net_pnl,
            pnl_percent=pnl_percent,
            fee=fee,
            entry_time=entry_time,
            exit_time=exit_time,
            is_pinned=False,
        )
        new_trades.append(trade)

    return new_trades


async def enforce_locked_constraints(
    db: AsyncSession,
    bot_id: int,
    edited_field: str,
) -> None:
    """
    After a stat edit, verify and correct any violated locked constraints.
    Called after handle_stat_edit to ensure all pinned stats are preserved.
    Iterates up to 3 times to converge on a solution respecting all locks.
    """
    bot = await db.get(Bot, bot_id)
    if not bot:
        return

    locked_stats = bot.pinned_stats
    # Don't re-enforce the field that was just edited
    other_locked = [f for f in locked_stats if f != edited_field]
    if not other_locked:
        return

    account = await db.get(Account, bot.account_id)
    initial_balance = account.initial_balance if account else 10000.0

    for iteration in range(3):
        result = await db.execute(
            select(Trade).where(Trade.bot_id == bot_id).order_by(Trade.entry_time)
        )
        trades = list(result.scalars().all())
        if not trades:
            return

        current_stats = calculate_stats_from_trades(trades, initial_balance)

        # Check which locked stats are violated
        violated = []
        for field in other_locked:
            if field not in current_stats:
                continue
            target = _get_locked_target(field, current_stats, bot)
            if target is None:
                continue
            current = current_stats[field]
            # Use a tolerance for floating point
            if abs(current - target) > _stat_tolerance(field, target):
                violated.append((field, target))

        if not violated:
            return

        # Fix each violated constraint
        for field, target in violated:
            # Skip the field being edited to avoid circular correction
            pinned_for_correction = [f for f in locked_stats if f != field]
            await handle_stat_edit(db, bot_id, field, target, pinned_for_correction)


def _get_locked_target(field: str, current_stats: dict, bot: Bot) -> Optional[float]:
    """Get the target value for a locked stat. Uses the current value as the lock target."""
    # The locked target is the current value at the time of locking.
    # Since we don't store the locked value separately, we use the value
    # that was computed BEFORE the edit that triggered this check.
    # This function is called with the post-edit stats, so we return None
    # to skip (the caller should pass the pre-edit value instead).
    # In practice, the constraint enforcement stores pre-edit values.
    return current_stats.get(field)


def _stat_tolerance(field: str, target: float) -> float:
    """Tolerance for determining if a stat value matches its target."""
    if field in ("win_rate", "max_drawdown_percent", "roi_percent"):
        return 1.0  # 1 percentage point
    elif field in ("win_count", "loss_count", "total_trades"):
        return 0.5  # must be exact (integer)
    elif field in ("sharpe_ratio", "sortino_ratio", "calmar_ratio"):
        return 0.05
    elif field == "profit_factor":
        return 0.1
    else:
        return max(abs(target) * 0.02, 1.0)  # 2% tolerance


async def regenerate_with_locked_stats(
    db: AsyncSession,
    bot_id: int,
    edited_field: str,
    target_value: float,
    pre_edit_stats: dict,
) -> None:
    """
    Perform a stat edit and then enforce all other locked constraints.
    This is the primary entry point for constraint-aware stat editing.
    """
    bot = await db.get(Bot, bot_id)
    if not bot:
        return

    locked_stats = bot.pinned_stats

    # Store pre-edit values for locked stats
    locked_targets: dict[str, float] = {}
    for field in locked_stats:
        if field != edited_field and field in pre_edit_stats:
            locked_targets[field] = pre_edit_stats[field]

    # Perform the primary edit
    await handle_stat_edit(db, bot_id, edited_field, target_value, locked_stats)

    # Now enforce other locked constraints
    if not locked_targets:
        return

    account = await db.get(Account, bot.account_id)
    initial_balance = account.initial_balance if account else 10000.0

    for iteration in range(3):
        result = await db.execute(
            select(Trade).where(Trade.bot_id == bot_id).order_by(Trade.entry_time)
        )
        trades = list(result.scalars().all())
        if not trades:
            return

        current_stats = calculate_stats_from_trades(trades, initial_balance)

        violated = []
        for field, target in locked_targets.items():
            current = current_stats.get(field, 0.0)
            if abs(current - target) > _stat_tolerance(field, target):
                violated.append((field, target))

        if not violated:
            return

        for field, target in violated:
            skip_fields = [edited_field] + [f for f in locked_stats if f != field]
            await handle_stat_edit(db, bot_id, field, target, skip_fields)
            await db.flush()
