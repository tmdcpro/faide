from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.portfolio import Trade, Bot, Account
from app.schemas import TradeCreate, TradeUpdate, TradeResponse, TradeGenerateRequest, TradeGenerateResponse
from app.services.calculation_engine import (
    calculate_trade_pnl,
    recalculate_bot_from_trades,
    recalculate_account,
)
from app.services.trade_generator import generate_trades_for_bot

router = APIRouter(prefix="/api", tags=["trades"])


@router.get("/bots/{bot_id}/trades", response_model=list[TradeResponse])
async def list_trades(bot_id: int, db: AsyncSession = Depends(get_db)):
    bot = await db.get(Bot, bot_id)
    if not bot:
        raise HTTPException(status_code=404, detail="Bot not found")

    result = await db.execute(
        select(Trade).where(Trade.bot_id == bot_id).order_by(Trade.entry_time.desc())
    )
    return list(result.scalars().all())


@router.post("/bots/{bot_id}/trades", response_model=TradeResponse)
async def create_trade(
    bot_id: int, data: TradeCreate, db: AsyncSession = Depends(get_db)
):
    bot = await db.get(Bot, bot_id)
    if not bot:
        raise HTTPException(status_code=404, detail="Bot not found")

    pnl, pnl_pct = calculate_trade_pnl(
        entry_price=data.entry_price,
        exit_price=data.exit_price,
        quantity=data.quantity,
        leverage=data.leverage,
        direction=data.direction,
        fee=data.fee,
    )

    trade = Trade(
        bot_id=bot_id,
        symbol=data.symbol,
        direction=data.direction,
        status=data.status,
        entry_price=data.entry_price,
        exit_price=data.exit_price,
        quantity=data.quantity,
        leverage=data.leverage,
        pnl=pnl,
        pnl_percent=pnl_pct,
        fee=data.fee,
        entry_time=data.entry_time,
        exit_time=data.exit_time,
    )
    db.add(trade)
    await db.flush()

    # Recalculate bot and account
    await recalculate_bot_from_trades(db, bot_id)
    account = await db.get(Account, bot.account_id)
    if account:
        await recalculate_account(db, account.id)

    await db.commit()
    await db.refresh(trade)
    return trade


@router.get("/trades/{trade_id}", response_model=TradeResponse)
async def get_trade(trade_id: int, db: AsyncSession = Depends(get_db)):
    trade = await db.get(Trade, trade_id)
    if not trade:
        raise HTTPException(status_code=404, detail="Trade not found")
    return trade


@router.put("/trades/{trade_id}", response_model=TradeResponse)
async def update_trade(
    trade_id: int, data: TradeUpdate, db: AsyncSession = Depends(get_db)
):
    trade = await db.get(Trade, trade_id)
    if not trade:
        raise HTTPException(status_code=404, detail="Trade not found")

    # Apply field updates
    if data.symbol is not None:
        trade.symbol = data.symbol
    if data.direction is not None:
        trade.direction = data.direction
    if data.status is not None:
        trade.status = data.status
    if data.entry_price is not None:
        trade.entry_price = data.entry_price
    if data.exit_price is not None:
        trade.exit_price = data.exit_price
    if data.quantity is not None:
        trade.quantity = data.quantity
    if data.leverage is not None:
        trade.leverage = data.leverage
    if data.fee is not None:
        trade.fee = data.fee
    if data.entry_time is not None:
        trade.entry_time = data.entry_time
    if data.exit_time is not None:
        trade.exit_time = data.exit_time
    if data.is_pinned is not None:
        trade.is_pinned = data.is_pinned

    # If PnL is directly set, pin it so cascading recalc doesn't overwrite
    if data.pnl is not None:
        trade.pnl = data.pnl
        trade.is_pinned = True
        notional = trade.entry_price * trade.quantity
        trade.pnl_percent = round((trade.pnl / notional * 100) if notional > 0 else 0.0, 4)
    elif data.pnl_percent is not None:
        notional = trade.entry_price * trade.quantity
        trade.pnl = round(data.pnl_percent / 100 * notional, 4)
        trade.pnl_percent = data.pnl_percent
        trade.is_pinned = True
    else:
        # Recalculate from price/quantity/leverage
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

    await db.flush()

    # Cascade recalculation up
    bot = await db.get(Bot, trade.bot_id)
    if bot:
        await recalculate_bot_from_trades(db, bot.id)
        account = await db.get(Account, bot.account_id)
        if account:
            await recalculate_account(db, account.id)

    await db.commit()
    await db.refresh(trade)
    return trade


@router.post("/bots/{bot_id}/trades/generate", response_model=TradeGenerateResponse)
async def generate_trades(
    bot_id: int, data: TradeGenerateRequest, db: AsyncSession = Depends(get_db)
):
    """Generate simulated trades for a bot within a date range."""
    bot = await db.get(Bot, bot_id)
    if not bot:
        raise HTTPException(status_code=404, detail="Bot not found")

    try:
        start_dt = datetime.fromisoformat(data.start_date)
        end_dt = datetime.fromisoformat(data.end_date)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid date format. Use ISO format (YYYY-MM-DD)")

    if end_dt <= start_dt:
        raise HTTPException(status_code=400, detail="end_date must be after start_date")

    try:
        trades = await generate_trades_for_bot(
            db=db,
            bot_id=bot_id,
            start_date=start_dt,
            end_date=end_dt,
            num_trades=data.num_trades,
            win_rate_target=data.win_rate_target,
            avg_pnl_percent=data.avg_pnl_percent,
            base_quantity=data.base_quantity,
            base_leverage=data.base_leverage,
            base_fee=data.base_fee,
            base_price=data.base_price,
        )
        return TradeGenerateResponse(
            generated=len(trades),
            bot_id=bot_id,
            start_date=data.start_date,
            end_date=data.end_date,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Trade generation failed: {str(e)}")


@router.delete("/trades/{trade_id}")
async def delete_trade(trade_id: int, db: AsyncSession = Depends(get_db)):
    trade = await db.get(Trade, trade_id)
    if not trade:
        raise HTTPException(status_code=404, detail="Trade not found")

    bot_id = trade.bot_id
    bot = await db.get(Bot, bot_id)

    await db.delete(trade)
    await db.flush()

    # Recalculate
    await recalculate_bot_from_trades(db, bot_id)
    if bot:
        account = await db.get(Account, bot.account_id)
        if account:
            await recalculate_account(db, account.id)

    await db.commit()
    return {"status": "deleted"}
