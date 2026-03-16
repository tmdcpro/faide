from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.schemas import MarketDataImport, OHLCVResponse
from app.services.market_data import (
    import_market_data,
    get_available_symbols,
    get_stored_ohlcv,
)

router = APIRouter(prefix="/api/market-data", tags=["market-data"])


@router.get("/exchanges")
async def list_exchanges():
    return {
        "exchanges": [
            {"id": "bitget_futures", "name": "Bitget Futures", "type": "futures"},
            {"id": "phemex_futures", "name": "Phemex Futures", "type": "futures"},
            {"id": "kraken", "name": "Kraken", "type": "spot"},
        ]
    }


@router.get("/symbols/{exchange}")
async def list_symbols(exchange: str):
    try:
        symbols = await get_available_symbols(exchange)
        return {"exchange": exchange, "symbols": symbols}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch symbols: {str(e)}")


@router.post("/import")
async def import_data(data: MarketDataImport, db: AsyncSession = Depends(get_db)):
    try:
        count = await import_market_data(
            db=db,
            exchange_name=data.exchange,
            symbol=data.symbol,
            timeframe=data.timeframe,
            since=data.since,
            limit=data.limit,
        )
        return {"imported": count, "exchange": data.exchange, "symbol": data.symbol}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Import failed: {str(e)}")


@router.get("/ohlcv", response_model=list[OHLCVResponse])
async def get_ohlcv(
    exchange: str = Query(...),
    symbol: str = Query(...),
    timeframe: str = Query("1d"),
    start: Optional[str] = Query(None),
    end: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
):
    start_dt = datetime.fromisoformat(start) if start else None
    end_dt = datetime.fromisoformat(end) if end else None

    records = await get_stored_ohlcv(db, exchange, symbol, timeframe, start_dt, end_dt)
    return [
        OHLCVResponse(
            timestamp=r.timestamp,
            open=r.open,
            high=r.high,
            low=r.low,
            close=r.close,
            volume=r.volume,
        )
        for r in records
    ]
