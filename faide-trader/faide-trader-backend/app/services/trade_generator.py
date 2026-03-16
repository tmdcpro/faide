"""
Trade generation service for Faide Trader.

Generates realistic simulated trades within a specified date range.
Uses imported market data for realistic prices when available,
otherwise generates synthetic prices based on configurable parameters.
"""
import random
import math
from datetime import datetime, timedelta
from typing import Optional

from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.portfolio import Trade, Bot, Account, MarketData
from app.services.calculation_engine import (
    calculate_trade_pnl,
    recalculate_bot_from_trades,
    recalculate_account,
)


async def get_market_prices(
    db: AsyncSession,
    exchange: str,
    symbol: str,
    start_date: datetime,
    end_date: datetime,
) -> list[dict]:
    """Get stored market data for price reference."""
    result = await db.execute(
        select(MarketData)
        .where(
            and_(
                MarketData.exchange == exchange,
                MarketData.symbol == symbol,
                MarketData.timestamp >= start_date,
                MarketData.timestamp <= end_date,
            )
        )
        .order_by(MarketData.timestamp)
    )
    records = list(result.scalars().all())
    return [
        {
            "timestamp": r.timestamp,
            "open": r.open,
            "high": r.high,
            "low": r.low,
            "close": r.close,
            "volume": r.volume,
        }
        for r in records
    ]


def generate_synthetic_prices(
    base_price: float,
    num_points: int,
    volatility: float = 0.02,
) -> list[float]:
    """Generate synthetic price series using geometric Brownian motion."""
    prices = [base_price]
    for _ in range(num_points - 1):
        change = random.gauss(0, volatility)
        new_price = prices[-1] * (1 + change)
        prices.append(max(new_price, base_price * 0.1))  # Floor at 10% of base
    return prices


async def generate_trades_for_bot(
    db: AsyncSession,
    bot_id: int,
    start_date: datetime,
    end_date: datetime,
    num_trades: int = 50,
    win_rate_target: float = 55.0,
    avg_pnl_percent: float = 2.0,
    base_quantity: float = 0.1,
    base_leverage: float = 5.0,
    base_fee: float = 2.0,
    base_price: float = 50000.0,
) -> list[Trade]:
    """
    Generate simulated trades for a bot within a date range.

    Args:
        db: Database session
        bot_id: Bot to generate trades for
        start_date: Start of trading period
        end_date: End of trading period
        num_trades: Number of trades to generate
        win_rate_target: Target win rate percentage (0-100)
        avg_pnl_percent: Average P&L per trade as percentage of entry
        base_quantity: Base position size
        base_leverage: Base leverage
        base_fee: Base fee per trade
        base_price: Base price if no market data available
    """
    bot = await db.get(Bot, bot_id)
    if not bot:
        raise ValueError(f"Bot {bot_id} not found")

    account = await db.get(Account, bot.account_id)
    if not account:
        raise ValueError(f"Account not found for bot {bot_id}")

    # Try to get market data for realistic prices
    market_prices = await get_market_prices(
        db, account.exchange, bot.symbol, start_date, end_date
    )

    # Generate time slots for trades
    total_seconds = (end_date - start_date).total_seconds()
    if total_seconds <= 0:
        raise ValueError("end_date must be after start_date")

    # Generate random trade times, sorted
    trade_times = sorted([
        start_date + timedelta(seconds=random.uniform(0, total_seconds))
        for _ in range(num_trades)
    ])

    # Determine prices from market data or synthetic
    if market_prices:
        # Use market data for entry prices
        price_series = [m["close"] for m in market_prices]
    else:
        # Generate synthetic prices
        price_series = generate_synthetic_prices(base_price, num_trades * 2)

    num_wins = int(num_trades * win_rate_target / 100)
    win_indices = set(random.sample(range(num_trades), min(num_wins, num_trades)))

    created_trades = []
    for i, entry_time in enumerate(trade_times):
        # Pick entry price from available prices
        if market_prices:
            price_idx = int(i / num_trades * len(price_series))
            price_idx = min(price_idx, len(price_series) - 1)
            entry_price = price_series[price_idx]
        else:
            entry_price = price_series[min(i * 2, len(price_series) - 1)]

        # Randomize direction
        direction = random.choice(["long", "short"])

        # Determine if this is a winning or losing trade
        is_win = i in win_indices

        # Calculate exit price based on win/loss
        pnl_magnitude = abs(random.gauss(avg_pnl_percent, avg_pnl_percent * 0.5))
        if not is_win:
            pnl_magnitude = -pnl_magnitude

        price_change_pct = pnl_magnitude / 100
        if direction == "long":
            exit_price = entry_price * (1 + price_change_pct)
        else:
            exit_price = entry_price * (1 - price_change_pct)

        exit_price = max(exit_price, 0.01)

        # Randomize quantity and leverage slightly
        quantity = base_quantity * random.uniform(0.5, 2.0)
        leverage = base_leverage * random.uniform(0.5, 1.5)
        fee = base_fee * random.uniform(0.5, 1.5)

        # Exit time: 1 minute to 48 hours after entry
        hold_duration = timedelta(
            minutes=random.uniform(1, 60 * 48)
        )
        exit_time = min(entry_time + hold_duration, end_date)

        # Calculate P&L
        pnl, pnl_percent = calculate_trade_pnl(
            entry_price=round(entry_price, 2),
            exit_price=round(exit_price, 2),
            quantity=round(quantity, 4),
            leverage=round(leverage, 2),
            direction=direction,
            fee=round(fee, 2),
        )

        trade = Trade(
            bot_id=bot_id,
            symbol=bot.symbol,
            direction=direction,
            status="closed",
            entry_price=round(entry_price, 2),
            exit_price=round(exit_price, 2),
            quantity=round(quantity, 4),
            leverage=round(leverage, 2),
            pnl=pnl,
            pnl_percent=pnl_percent,
            fee=round(fee, 2),
            entry_time=entry_time,
            exit_time=exit_time,
            is_pinned=False,
        )
        db.add(trade)
        created_trades.append(trade)

    await db.flush()

    # Recalculate bot stats after generating trades
    await recalculate_bot_from_trades(db, bot_id)
    await recalculate_account(db, account.id)
    await db.commit()

    return created_trades
