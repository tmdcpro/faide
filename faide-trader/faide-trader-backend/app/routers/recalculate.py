from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.database import get_db
from app.models.portfolio import Trade, Bot, Account, PnlRecord
from app.schemas import (
    RecalculateRequest,
    RecalculateResponse,
    TradeResponse,
    PnlRecordResponse,
    PnlRecordUpdate,
    StatsResponse,
    PeriodPnlResponse,
    PeriodPnlUpdate,
)
from app.services.calculation_engine import (
    recalculate_bot_from_trades,
    recalculate_account,
    recalculate_portfolio,
    handle_top_down_edit,
    handle_stat_edit,
    calculate_stats_from_trades,
    aggregate_period_pnl,
    handle_period_pnl_edit,
)

# Allowlist of fields that can be edited via the recalculate endpoint
EDITABLE_TRADE_FIELDS = {"entry_price", "exit_price", "quantity", "leverage", "fee", "pnl", "pnl_percent"}

router = APIRouter(prefix="/api", tags=["recalculation"])


@router.post("/recalculate", response_model=RecalculateResponse)
async def recalculate(data: RecalculateRequest, db: AsyncSession = Depends(get_db)):
    """
    Trigger cascading recalculation when a value is edited.
    Supports editing at any level: trade, bot (total_pnl), account, portfolio.
    """
    if data.entity_type == "trade":
        trade = await db.get(Trade, data.entity_id)
        if not trade:
            raise HTTPException(status_code=404, detail="Trade not found")

        # Validate field against allowlist
        if data.field not in EDITABLE_TRADE_FIELDS:
            raise HTTPException(status_code=400, detail=f"Field '{data.field}' is not editable. Allowed: {sorted(EDITABLE_TRADE_FIELDS)}")

        # Update the specified field
        setattr(trade, data.field, data.new_value)

        # If PnL is directly edited, sync the complementary field and pin the trade
        if data.field == "pnl":
            trade.is_pinned = True
            notional = trade.entry_price * trade.quantity
            trade.pnl_percent = round((trade.pnl / notional * 100) if notional > 0 else 0.0, 4)
        elif data.field == "pnl_percent":
            trade.is_pinned = True
            notional = trade.entry_price * trade.quantity
            trade.pnl = round(data.new_value / 100 * notional, 4)

        # Recalculate trade PnL if price/quantity/leverage changed
        from app.services.calculation_engine import calculate_trade_pnl
        if data.field in ("entry_price", "exit_price", "quantity", "leverage", "fee"):
            pnl, pnl_pct = calculate_trade_pnl(
                trade.entry_price, trade.exit_price, trade.quantity,
                trade.leverage, trade.direction, trade.fee,
            )
            if "pnl" not in data.pinned_fields:
                trade.pnl = pnl
            if "pnl_percent" not in data.pinned_fields:
                trade.pnl_percent = pnl_pct

        await db.flush()

        # Cascade up
        bot_stats = await recalculate_bot_from_trades(db, trade.bot_id)
        bot = await db.get(Bot, trade.bot_id)
        account = await db.get(Account, bot.account_id) if bot else None
        account_stats = {}
        if account:
            account_stats = await recalculate_account(db, account.id)

        await db.commit()

        # Get updated trades
        result = await db.execute(
            select(Trade).where(Trade.bot_id == trade.bot_id).order_by(Trade.entry_time)
        )
        updated_trades = [TradeResponse.model_validate(t) for t in result.scalars().all()]

        # Get updated PnL records
        result = await db.execute(
            select(PnlRecord).where(PnlRecord.bot_id == trade.bot_id).order_by(PnlRecord.date)
        )
        updated_pnl = [PnlRecordResponse.model_validate(r) for r in result.scalars().all()]

        return RecalculateResponse(
            updated_trades=updated_trades,
            updated_pnl_records=updated_pnl,
            bot_stats=bot_stats,
            account_stats=account_stats,
        )

    elif data.entity_type == "bot":
        bot = await db.get(Bot, data.entity_id)
        if not bot:
            raise HTTPException(status_code=404, detail="Bot not found")

        # Use handle_stat_edit for any stat field (total_pnl, win_rate, sharpe, etc.)
        await handle_stat_edit(
            db, bot.id, data.field, data.new_value, data.pinned_fields
        )
        bot_stats = await recalculate_bot_from_trades(db, bot.id)

        account = await db.get(Account, bot.account_id)
        account_stats = {}
        if account:
            account_stats = await recalculate_account(db, account.id)

        await db.commit()

        result = await db.execute(
            select(Trade).where(Trade.bot_id == bot.id).order_by(Trade.entry_time)
        )
        updated_trades = [TradeResponse.model_validate(t) for t in result.scalars().all()]

        result = await db.execute(
            select(PnlRecord).where(PnlRecord.bot_id == bot.id).order_by(PnlRecord.date)
        )
        updated_pnl = [PnlRecordResponse.model_validate(r) for r in result.scalars().all()]

        return RecalculateResponse(
            updated_trades=updated_trades,
            updated_pnl_records=updated_pnl,
            bot_stats=bot_stats,
            account_stats=account_stats,
        )

    elif data.entity_type == "account":
        account = await db.get(Account, data.entity_id)
        if not account:
            raise HTTPException(status_code=404, detail="Account not found")

        if data.field == "current_balance":
            # Back-calculate: target total PnL = new_balance - initial_balance
            # Then distribute across all bots' trades to make accounting consistent
            target_total_pnl = data.new_value - account.initial_balance
            result = await db.execute(select(Bot).where(Bot.account_id == account.id))
            bots = list(result.scalars().all())
            if bots:
                # Compute each bot's current PnL and check for unpinned trades
                bot_pnls: dict[int, float] = {}
                bot_has_editable: dict[int, bool] = {}
                for bot in bots:
                    trade_result = await db.execute(
                        select(Trade).where(Trade.bot_id == bot.id)
                    )
                    bot_trades = list(trade_result.scalars().all())
                    bot_pnls[bot.id] = sum(t.pnl for t in bot_trades)
                    bot_has_editable[bot.id] = any(not t.is_pinned for t in bot_trades)

                # Only distribute to bots that have unpinned trades
                editable_bots = [b for b in bots if bot_has_editable.get(b.id, False)]
                if not editable_bots:
                    editable_bots = bots  # fallback: try all bots anyway

                editable_pnl = sum(bot_pnls[b.id] for b in editable_bots)
                pinned_bot_pnl = sum(bot_pnls[b.id] for b in bots if b not in editable_bots)
                distributable_target = target_total_pnl - pinned_bot_pnl

                if editable_pnl != 0:
                    # Proportional: each editable bot gets its share
                    for bot in editable_bots:
                        bot_share = bot_pnls[bot.id] / editable_pnl
                        await handle_top_down_edit(
                            db, bot.id, distributable_target * bot_share, data.pinned_fields
                        )
                else:
                    # All editable bots are flat — even split
                    per_bot_pnl = distributable_target / len(editable_bots)
                    for bot in editable_bots:
                        await handle_top_down_edit(db, bot.id, per_bot_pnl, data.pinned_fields)
        elif data.field == "initial_balance":
            account.initial_balance = data.new_value

        account_stats = await recalculate_account(db, account.id)
        await db.commit()

        return RecalculateResponse(account_stats=account_stats)

    raise HTTPException(status_code=400, detail=f"Unsupported entity_type: {data.entity_type}")


@router.get("/bots/{bot_id}/pnl", response_model=list[PnlRecordResponse])
async def get_pnl_records(
    bot_id: int,
    period: str = "daily",
    db: AsyncSession = Depends(get_db),
):
    bot = await db.get(Bot, bot_id)
    if not bot:
        raise HTTPException(status_code=404, detail="Bot not found")

    result = await db.execute(
        select(PnlRecord)
        .where(PnlRecord.bot_id == bot_id, PnlRecord.period_type == period)
        .order_by(PnlRecord.date)
    )
    return list(result.scalars().all())


@router.put("/pnl/{pnl_id}", response_model=PnlRecordResponse)
async def update_pnl_record(
    pnl_id: int,
    data: PnlRecordUpdate,
    db: AsyncSession = Depends(get_db),
):
    record = await db.get(PnlRecord, pnl_id)
    if not record:
        raise HTTPException(status_code=404, detail="PnL record not found")

    if data.pnl is not None:
        record.pnl = data.pnl
    if data.trade_count is not None:
        record.trade_count = data.trade_count
    if data.win_count is not None:
        record.win_count = data.win_count
    if data.loss_count is not None:
        record.loss_count = data.loss_count
    if data.is_pinned is not None:
        record.is_pinned = data.is_pinned

    # Recalculate cumulative PnL for all records in the bot
    result = await db.execute(
        select(PnlRecord)
        .where(PnlRecord.bot_id == record.bot_id)
        .order_by(PnlRecord.date)
    )
    records = list(result.scalars().all())
    cumulative = 0.0
    for r in records:
        cumulative += r.pnl
        r.cumulative_pnl = round(cumulative, 2)

    await db.commit()
    await db.refresh(record)
    return record


@router.get("/stats/portfolio/{portfolio_id}", response_model=StatsResponse)
async def get_portfolio_stats(portfolio_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(Account).where(Account.portfolio_id == portfolio_id)
    )
    accounts = list(result.scalars().all())

    all_trades = []
    total_initial = 0.0
    for account in accounts:
        total_initial += account.initial_balance
        result = await db.execute(
            select(Bot).where(Bot.account_id == account.id)
        )
        bots = list(result.scalars().all())
        for bot in bots:
            result = await db.execute(
                select(Trade).where(Trade.bot_id == bot.id).order_by(Trade.entry_time)
            )
            all_trades.extend(result.scalars().all())

    stats = calculate_stats_from_trades(all_trades, total_initial if total_initial > 0 else 10000.0)
    return StatsResponse(**stats)


@router.get("/stats/account/{account_id}", response_model=StatsResponse)
async def get_account_stats(account_id: int, db: AsyncSession = Depends(get_db)):
    account = await db.get(Account, account_id)
    if not account:
        raise HTTPException(status_code=404, detail="Account not found")

    result = await db.execute(select(Bot).where(Bot.account_id == account_id))
    bots = list(result.scalars().all())

    all_trades = []
    for bot in bots:
        result = await db.execute(
            select(Trade).where(Trade.bot_id == bot.id).order_by(Trade.entry_time)
        )
        all_trades.extend(result.scalars().all())

    stats = calculate_stats_from_trades(all_trades, account.initial_balance)
    return StatsResponse(**stats)


@router.get("/stats/bot/{bot_id}", response_model=StatsResponse)
async def get_bot_stats(bot_id: int, db: AsyncSession = Depends(get_db)):
    bot = await db.get(Bot, bot_id)
    if not bot:
        raise HTTPException(status_code=404, detail="Bot not found")

    account = await db.get(Account, bot.account_id)
    initial_balance = account.initial_balance if account else 10000.0

    result = await db.execute(
        select(Trade).where(Trade.bot_id == bot_id).order_by(Trade.entry_time)
    )
    trades = list(result.scalars().all())

    stats = calculate_stats_from_trades(trades, initial_balance)
    return StatsResponse(**stats)


# --- Period P&L Endpoints ---

@router.get("/bots/{bot_id}/period-pnl", response_model=list[PeriodPnlResponse])
async def get_period_pnl(
    bot_id: int,
    period_type: str = "monthly",
    db: AsyncSession = Depends(get_db),
):
    """Get P&L broken down by period (daily/weekly/monthly) with drawdown."""
    bot = await db.get(Bot, bot_id)
    if not bot:
        raise HTTPException(status_code=404, detail="Bot not found")

    account = await db.get(Account, bot.account_id)
    initial_balance = account.initial_balance if account else 10000.0

    result = await db.execute(
        select(Trade).where(Trade.bot_id == bot_id).order_by(Trade.entry_time)
    )
    trades = list(result.scalars().all())

    periods = aggregate_period_pnl(trades, period_type, initial_balance)
    return [PeriodPnlResponse(**p) for p in periods]


@router.get("/accounts/{account_id}/period-pnl", response_model=list[PeriodPnlResponse])
async def get_account_period_pnl(
    account_id: int,
    period_type: str = "monthly",
    db: AsyncSession = Depends(get_db),
):
    """Get account-level P&L broken down by period."""
    account = await db.get(Account, account_id)
    if not account:
        raise HTTPException(status_code=404, detail="Account not found")

    result = await db.execute(select(Bot).where(Bot.account_id == account_id))
    bots = list(result.scalars().all())

    all_trades = []
    for bot in bots:
        result = await db.execute(
            select(Trade).where(Trade.bot_id == bot.id).order_by(Trade.entry_time)
        )
        all_trades.extend(result.scalars().all())

    all_trades.sort(key=lambda t: t.entry_time)
    periods = aggregate_period_pnl(all_trades, period_type, account.initial_balance)
    return [PeriodPnlResponse(**p) for p in periods]


@router.get("/portfolios/{portfolio_id}/period-pnl", response_model=list[PeriodPnlResponse])
async def get_portfolio_period_pnl(
    portfolio_id: int,
    period_type: str = "monthly",
    db: AsyncSession = Depends(get_db),
):
    """Get portfolio-level P&L broken down by period."""
    result = await db.execute(
        select(Account).where(Account.portfolio_id == portfolio_id)
    )
    accounts = list(result.scalars().all())

    all_trades = []
    total_initial = 0.0
    for account in accounts:
        total_initial += account.initial_balance
        result = await db.execute(select(Bot).where(Bot.account_id == account.id))
        bots = list(result.scalars().all())
        for bot in bots:
            result = await db.execute(
                select(Trade).where(Trade.bot_id == bot.id).order_by(Trade.entry_time)
            )
            all_trades.extend(result.scalars().all())

    all_trades.sort(key=lambda t: t.entry_time)
    periods = aggregate_period_pnl(all_trades, period_type, total_initial if total_initial > 0 else 10000.0)
    return [PeriodPnlResponse(**p) for p in periods]


@router.put("/bots/{bot_id}/period-pnl/{period_key}")
async def update_period_pnl(
    bot_id: int,
    period_key: str,
    data: PeriodPnlUpdate,
    period_type: str = "monthly",
    db: AsyncSession = Depends(get_db),
):
    """Edit a period's P&L and back-calculate trades to match."""
    bot = await db.get(Bot, bot_id)
    if not bot:
        raise HTTPException(status_code=404, detail="Bot not found")

    if data.pnl is not None:
        await handle_period_pnl_edit(
            db, bot_id, period_key, period_type, data.pnl, []
        )

    # Recalculate everything
    bot_stats = await recalculate_bot_from_trades(db, bot_id)
    account = await db.get(Account, bot.account_id)
    if account:
        await recalculate_account(db, account.id)

    await db.commit()

    # Return updated period P&L
    account = await db.get(Account, bot.account_id)
    initial_balance = account.initial_balance if account else 10000.0

    result = await db.execute(
        select(Trade).where(Trade.bot_id == bot_id).order_by(Trade.entry_time)
    )
    trades = list(result.scalars().all())
    periods = aggregate_period_pnl(trades, period_type, initial_balance)

    return {"periods": [PeriodPnlResponse(**p) for p in periods], "bot_stats": bot_stats}
