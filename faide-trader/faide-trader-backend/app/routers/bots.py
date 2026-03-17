from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.database import get_db
from app.models.portfolio import Bot, Account, Trade
from app.schemas import BotCreate, BotUpdate, BotResponse, SymbolPnlResponse
from app.services.calculation_engine import calculate_stats_from_trades

router = APIRouter(prefix="/api", tags=["bots"])


def build_bot_response(bot: Bot, trades: list[Trade], initial_balance: float) -> BotResponse:
    stats = calculate_stats_from_trades(trades, initial_balance)
    return BotResponse(
        id=bot.id,
        account_id=bot.account_id,
        name=bot.name,
        strategy_type=bot.strategy_type,
        symbol=bot.symbol,
        symbols=bot.symbols,
        is_active=bot.is_active,
        created_at=bot.created_at,
        updated_at=bot.updated_at,
        total_pnl=stats["total_pnl"],
        total_trades=stats["total_trades"],
        win_count=stats["win_count"],
        loss_count=stats["loss_count"],
        win_rate=stats["win_rate"],
        sharpe_ratio=stats["sharpe_ratio"],
        max_drawdown=stats["max_drawdown"],
        profit_factor=stats["profit_factor"],
    )


@router.get("/accounts/{account_id}/bots", response_model=list[BotResponse])
async def list_bots(account_id: int, db: AsyncSession = Depends(get_db)):
    account = await db.get(Account, account_id)
    if not account:
        raise HTTPException(status_code=404, detail="Account not found")

    result = await db.execute(
        select(Bot)
        .where(Bot.account_id == account_id)
        .options(selectinload(Bot.trades))
    )
    bots = result.scalars().all()

    return [
        build_bot_response(b, list(b.trades), account.initial_balance)
        for b in bots
    ]


@router.post("/accounts/{account_id}/bots", response_model=BotResponse)
async def create_bot(
    account_id: int, data: BotCreate, db: AsyncSession = Depends(get_db)
):
    account = await db.get(Account, account_id)
    if not account:
        raise HTTPException(status_code=404, detail="Account not found")

    # Build symbols list: combine primary symbol + additional symbols
    all_symbols = [data.symbol] if data.symbol else []
    for s in data.symbols:
        if s not in all_symbols:
            all_symbols.append(s)

    bot = Bot(
        account_id=account_id,
        name=data.name,
        strategy_type=data.strategy_type,
        symbol=data.symbol,
        is_active=data.is_active,
    )
    if all_symbols:
        bot.symbols = all_symbols
    db.add(bot)
    await db.commit()
    await db.refresh(bot)
    return BotResponse(
        id=bot.id,
        account_id=bot.account_id,
        name=bot.name,
        strategy_type=bot.strategy_type,
        symbol=bot.symbol,
        symbols=bot.symbols,
        is_active=bot.is_active,
        created_at=bot.created_at,
        updated_at=bot.updated_at,
    )


@router.get("/bots/{bot_id}", response_model=BotResponse)
async def get_bot(bot_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(Bot).where(Bot.id == bot_id).options(selectinload(Bot.trades))
    )
    bot = result.scalar_one_or_none()
    if not bot:
        raise HTTPException(status_code=404, detail="Bot not found")

    account = await db.get(Account, bot.account_id)
    initial_balance = account.initial_balance if account else 10000.0

    return build_bot_response(bot, list(bot.trades), initial_balance)


@router.put("/bots/{bot_id}", response_model=BotResponse)
async def update_bot(
    bot_id: int, data: BotUpdate, db: AsyncSession = Depends(get_db)
):
    bot = await db.get(Bot, bot_id)
    if not bot:
        raise HTTPException(status_code=404, detail="Bot not found")

    if data.name is not None:
        bot.name = data.name
    if data.strategy_type is not None:
        bot.strategy_type = data.strategy_type
    if data.symbols is not None:
        bot.symbols = data.symbols
    elif data.symbol is not None:
        bot.symbol = data.symbol
    if data.is_active is not None:
        bot.is_active = data.is_active

    await db.commit()
    await db.refresh(bot)

    result = await db.execute(
        select(Trade).where(Trade.bot_id == bot_id)
    )
    trades = list(result.scalars().all())
    account = await db.get(Account, bot.account_id)
    initial_balance = account.initial_balance if account else 10000.0

    return build_bot_response(bot, trades, initial_balance)


@router.get("/bots/{bot_id}/symbol-pnl", response_model=list[SymbolPnlResponse])
async def get_symbol_pnl(bot_id: int, db: AsyncSession = Depends(get_db)):
    """Get per-symbol P&L breakdown for a bot."""
    result = await db.execute(
        select(Bot).where(Bot.id == bot_id).options(selectinload(Bot.trades))
    )
    bot = result.scalar_one_or_none()
    if not bot:
        raise HTTPException(status_code=404, detail="Bot not found")

    # Group trades by symbol
    symbol_trades: dict[str, list[Trade]] = {}
    for trade in bot.trades:
        symbol_trades.setdefault(trade.symbol, []).append(trade)

    # Build per-symbol stats
    symbol_pnls: list[SymbolPnlResponse] = []
    for sym in bot.symbols:
        trades = symbol_trades.get(sym, [])
        total_pnl = sum(t.pnl for t in trades)
        wins = [t for t in trades if t.pnl > 0]
        losses = [t for t in trades if t.pnl <= 0]
        total = len(trades)
        symbol_pnls.append(SymbolPnlResponse(
            symbol=sym,
            total_pnl=round(total_pnl, 2),
            total_trades=total,
            win_count=len(wins),
            loss_count=len(losses),
            win_rate=round(len(wins) / total * 100, 2) if total > 0 else 0.0,
            avg_pnl=round(total_pnl / total, 2) if total > 0 else 0.0,
        ))

    # Also include symbols that have trades but aren't in bot.symbols
    for sym, trades in symbol_trades.items():
        if sym not in bot.symbols:
            total_pnl = sum(t.pnl for t in trades)
            wins = [t for t in trades if t.pnl > 0]
            losses = [t for t in trades if t.pnl <= 0]
            total = len(trades)
            symbol_pnls.append(SymbolPnlResponse(
                symbol=sym,
                total_pnl=round(total_pnl, 2),
                total_trades=total,
                win_count=len(wins),
                loss_count=len(losses),
                win_rate=round(len(wins) / total * 100, 2) if total > 0 else 0.0,
                avg_pnl=round(total_pnl / total, 2) if total > 0 else 0.0,
            ))

    return symbol_pnls


@router.delete("/bots/{bot_id}")
async def delete_bot(bot_id: int, db: AsyncSession = Depends(get_db)):
    bot = await db.get(Bot, bot_id)
    if not bot:
        raise HTTPException(status_code=404, detail="Bot not found")
    await db.delete(bot)
    await db.commit()
    return {"status": "deleted"}
