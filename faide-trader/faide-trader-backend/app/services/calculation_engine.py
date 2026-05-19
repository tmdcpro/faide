"""
Cascading recalculation engine for Faide Trader.

When any value is edited, all dependent values recalculate unless pinned.
Supports both top-down (totals -> trades) and bottom-up (trades -> totals).
"""
import math
from datetime import datetime, timedelta
from typing import Optional

import numpy as np
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.portfolio import Trade, Bot, Account, Portfolio, PnlRecord


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
    # Get existing pinned records
    result = await db.execute(
        select(PnlRecord).where(PnlRecord.bot_id == bot_id, PnlRecord.is_pinned == True)
    )
    pinned_records = {r.date.date(): r for r in result.scalars().all()}

    # Delete non-pinned records
    result = await db.execute(
        select(PnlRecord).where(PnlRecord.bot_id == bot_id, PnlRecord.is_pinned == False)
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

    account.current_balance = account.initial_balance + total_pnl
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
