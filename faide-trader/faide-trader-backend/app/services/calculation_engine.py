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

    total_pnl = sum(pnls)
    total_fees = sum(fees)
    net_pnl = total_pnl
    total_trades = len(trades)
    win_count = len(wins)
    loss_count = len(losses)
    win_rate = (win_count / total_trades * 100) if total_trades > 0 else 0.0
    avg_win = (sum(wins) / win_count) if win_count > 0 else 0.0
    avg_loss = (sum(losses) / loss_count) if loss_count > 0 else 0.0
    gross_profit = sum(wins) if wins else 0.0
    gross_loss = abs(sum(losses)) if losses else 0.0
    profit_factor = (gross_profit / gross_loss) if gross_loss > 0 else float("inf") if gross_profit > 0 else 0.0
    avg_trade_pnl = total_pnl / total_trades if total_trades > 0 else 0.0
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
    """Recalculate account-level stats from all its bots."""
    account = await db.get(Account, account_id)
    if not account:
        return {}

    result = await db.execute(select(Bot).where(Bot.account_id == account_id))
    bots = list(result.scalars().all())

    total_pnl = 0.0
    total_trades = 0
    total_wins = 0

    for bot in bots:
        bot_stats = await recalculate_bot_from_trades(db, bot.id)
        total_pnl += bot_stats.get("total_pnl", 0.0)
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
    """Recalculate portfolio-level stats from all accounts."""
    result = await db.execute(select(Account).where(Account.portfolio_id == portfolio_id))
    accounts = list(result.scalars().all())

    total_pnl = 0.0
    total_balance = 0.0

    for account in accounts:
        acct_stats = await recalculate_account(db, account.id)
        total_pnl += acct_stats.get("total_pnl", 0.0)
        total_balance += acct_stats.get("current_balance", account.initial_balance)

    return {
        "total_pnl": round(total_pnl, 2),
        "total_balance": round(total_balance, 2),
        "account_count": len(accounts),
    }


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
        # Distribute evenly
        per_trade = target_unpinned_pnl / len(unpinned_trades)
        for trade in unpinned_trades:
            trade.pnl = round(per_trade, 4)
            # Back-calculate exit price from new PnL
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
    else:
        # Distribute proportionally
        ratio = target_unpinned_pnl / current_unpinned_pnl
        for trade in unpinned_trades:
            trade.pnl = round(trade.pnl * ratio, 4)
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

    await db.flush()
    return trades
