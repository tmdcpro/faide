"""
Market data service using CCXT for historical OHLCV data.
Supports: Bitget Futures, Phemex Futures, Kraken.
"""
import asyncio
from datetime import datetime
from typing import Optional

import ccxt
from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.portfolio import MarketData

EXCHANGE_MAP = {
    "bitget_futures": lambda: ccxt.bitget({"options": {"defaultType": "swap"}}),
    "phemex_futures": lambda: ccxt.phemex({"options": {"defaultType": "swap"}}),
    "kraken": lambda: ccxt.kraken(),
}


def get_exchange(exchange_name: str):
    """Get a CCXT exchange instance."""
    factory = EXCHANGE_MAP.get(exchange_name)
    if not factory:
        raise ValueError(f"Unsupported exchange: {exchange_name}. Supported: {list(EXCHANGE_MAP.keys())}")
    return factory()


async def fetch_ohlcv(
    exchange_name: str,
    symbol: str,
    timeframe: str = "1d",
    since: Optional[str] = None,
    limit: int = 365,
) -> list[dict]:
    """Fetch OHLCV data from exchange via CCXT."""
    exchange = get_exchange(exchange_name)

    since_ts = None
    if since:
        since_ts = int(datetime.fromisoformat(since).timestamp() * 1000)

    try:
        ohlcv = await asyncio.to_thread(
            exchange.fetch_ohlcv, symbol, timeframe, since_ts, limit
        )
    finally:
        if hasattr(exchange, 'close'):
            exchange.close()

    results = []
    for candle in ohlcv:
        results.append({
            "timestamp": datetime.utcfromtimestamp(candle[0] / 1000),
            "open": candle[1],
            "high": candle[2],
            "low": candle[3],
            "close": candle[4],
            "volume": candle[5],
        })

    return results


async def import_market_data(
    db: AsyncSession,
    exchange_name: str,
    symbol: str,
    timeframe: str = "1d",
    since: Optional[str] = None,
    limit: int = 365,
) -> int:
    """Import OHLCV data into the database."""
    candles = await fetch_ohlcv(exchange_name, symbol, timeframe, since, limit)

    count = 0
    for candle in candles:
        # Check if already exists
        existing = await db.execute(
            select(MarketData).where(
                and_(
                    MarketData.exchange == exchange_name,
                    MarketData.symbol == symbol,
                    MarketData.timeframe == timeframe,
                    MarketData.timestamp == candle["timestamp"],
                )
            )
        )
        if existing.scalar_one_or_none():
            continue

        record = MarketData(
            exchange=exchange_name,
            symbol=symbol,
            timeframe=timeframe,
            timestamp=candle["timestamp"],
            open=candle["open"],
            high=candle["high"],
            low=candle["low"],
            close=candle["close"],
            volume=candle["volume"],
        )
        db.add(record)
        count += 1

    await db.commit()
    return count


async def get_available_symbols(exchange_name: str) -> list[str]:
    """Get available trading symbols for an exchange."""
    exchange = get_exchange(exchange_name)
    try:
        await asyncio.to_thread(exchange.load_markets)
        symbols = list(exchange.symbols)
        return sorted(symbols)[:100]  # Return top 100
    finally:
        if hasattr(exchange, 'close'):
            exchange.close()


async def get_stored_ohlcv(
    db: AsyncSession,
    exchange: str,
    symbol: str,
    timeframe: str = "1d",
    start: Optional[datetime] = None,
    end: Optional[datetime] = None,
) -> list[MarketData]:
    """Get stored OHLCV data from database."""
    query = select(MarketData).where(
        and_(
            MarketData.exchange == exchange,
            MarketData.symbol == symbol,
            MarketData.timeframe == timeframe,
        )
    )
    if start:
        query = query.where(MarketData.timestamp >= start)
    if end:
        query = query.where(MarketData.timestamp <= end)

    query = query.order_by(MarketData.timestamp)
    result = await db.execute(query)
    return list(result.scalars().all())
