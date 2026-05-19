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
    TogglePinRequest,
    TogglePinResponse,
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
    handle_period_stat_edit,
    get_pinned_periods,
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

        # Per-period stat editing (edit a stat for a specific time period)
        if data.period_key and data.period_type:
            await handle_period_stat_edit(
                db, bot.id, data.period_key, data.period_type,
                data.field, data.new_value, data.pinned_fields,
            )
        else:
            # Global stat editing
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

                # Only distribute to bots that are not pinned and have unpinned trades
                editable_bots = [b for b in bots if not b.is_pinned and bot_has_editable.get(b.id, False)]
                if not editable_bots:
                    raise HTTPException(
                        status_code=400,
                        detail="Cannot edit current_balance because all bot trades are pinned",
                    )

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


@router.post("/toggle-pin", response_model=TogglePinResponse)
async def toggle_pin(data: TogglePinRequest, db: AsyncSession = Depends(get_db)):
    """Toggle pin/lock on any entity, stat field, or period."""
    if data.entity_type == "trade":
        trade = await db.get(Trade, data.entity_id)
        if not trade:
            raise HTTPException(status_code=404, detail="Trade not found")
        trade.is_pinned = data.pinned
        await db.commit()
        return TogglePinResponse(
            success=True, entity_type="trade", entity_id=data.entity_id,
            pinned=data.pinned,
        )

    elif data.entity_type == "bot":
        bot = await db.get(Bot, data.entity_id)
        if not bot:
            raise HTTPException(status_code=404, detail="Bot not found")

        if data.field:
            # Stat-level pin: pin/unpin a specific stat field
            current = bot.pinned_stats
            if data.pinned and data.field not in current:
                current.append(data.field)
            elif not data.pinned and data.field in current:
                current.remove(data.field)
            bot.pinned_stats = current
        else:
            # Entity-level pin: pin/unpin the entire bot
            bot.is_pinned = data.pinned

        await db.commit()
        return TogglePinResponse(
            success=True, entity_type="bot", entity_id=data.entity_id,
            field=data.field, pinned=data.pinned,
        )

    elif data.entity_type == "account":
        account = await db.get(Account, data.entity_id)
        if not account:
            raise HTTPException(status_code=404, detail="Account not found")
        account.is_pinned = data.pinned
        await db.commit()
        return TogglePinResponse(
            success=True, entity_type="account", entity_id=data.entity_id,
            pinned=data.pinned,
        )

    elif data.entity_type == "period":
        # Pin/unpin a period by creating/updating a PnlRecord with is_pinned
        bot = await db.get(Bot, data.entity_id)
        if not bot:
            raise HTTPException(status_code=404, detail="Bot not found")

        period_type = data.period_type or "monthly"
        period_key = data.period_key
        if not period_key:
            raise HTTPException(status_code=400, detail="period_key required for period pin")

        # Find existing PnlRecord for this period or find trades in this period
        result = await db.execute(
            select(PnlRecord).where(
                PnlRecord.bot_id == data.entity_id,
                PnlRecord.period_type == period_type,
            ).order_by(PnlRecord.date)
        )
        records = list(result.scalars().all())

        # Match records to period key
        matched = False
        for record in records:
            if period_type == "monthly":
                rk = record.date.strftime("%Y-%m")
            elif period_type == "weekly":
                iso = record.date.isocalendar()
                rk = f"{iso[0]}-W{iso[1]:02d}"
            else:
                rk = record.date.strftime("%Y-%m-%d")

            if rk == period_key:
                record.is_pinned = data.pinned
                matched = True

        if not matched:
            # Create a placeholder pinned PnlRecord if none exists
            from datetime import datetime as dt
            if period_type == "monthly":
                date = dt.strptime(period_key + "-01", "%Y-%m-%d")
            elif period_type == "daily":
                date = dt.strptime(period_key, "%Y-%m-%d")
            else:
                # weekly: parse "YYYY-Www"
                date = dt.strptime(period_key + "-1", "%G-W%V-%u")

            new_record = PnlRecord(
                bot_id=data.entity_id,
                date=date,
                period_type=period_type,
                pnl=0.0,
                cumulative_pnl=0.0,
                is_pinned=data.pinned,
            )
            db.add(new_record)

        await db.commit()
        return TogglePinResponse(
            success=True, entity_type="period", entity_id=data.entity_id,
            field=data.period_key, pinned=data.pinned,
        )

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

    # Recalculate cumulative PnL for records of the same period type
    result = await db.execute(
        select(PnlRecord)
        .where(PnlRecord.bot_id == record.bot_id, PnlRecord.period_type == record.period_type)
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

    pinned = await get_pinned_periods(db, bot_id, period_type)
    periods = aggregate_period_pnl(trades, period_type, initial_balance, pinned)
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
    """Edit a period's P&L or derived stats and back-calculate trades to match."""
    bot = await db.get(Bot, bot_id)
    if not bot:
        raise HTTPException(status_code=404, detail="Bot not found")

    if data.pnl is not None:
        await handle_period_pnl_edit(
            db, bot_id, period_key, period_type, data.pnl, []
        )
    if data.win_rate is not None:
        await handle_period_stat_edit(
            db, bot_id, period_key, period_type, "win_rate", data.win_rate, []
        )
    if data.profit_factor is not None:
        await handle_period_stat_edit(
            db, bot_id, period_key, period_type, "profit_factor", data.profit_factor, []
        )
    if data.is_pinned is not None:
        # Pin/unpin the period
        result = await db.execute(
            select(PnlRecord).where(
                PnlRecord.bot_id == bot_id,
                PnlRecord.period_type == period_type,
            ).order_by(PnlRecord.date)
        )
        for record in result.scalars().all():
            if period_type == "monthly":
                rk = record.date.strftime("%Y-%m")
            elif period_type == "weekly":
                iso = record.date.isocalendar()
                rk = f"{iso[0]}-W{iso[1]:02d}"
            else:
                rk = record.date.strftime("%Y-%m-%d")
            if rk == period_key:
                record.is_pinned = data.is_pinned

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
    pinned = await get_pinned_periods(db, bot_id, period_type)
    periods = aggregate_period_pnl(trades, period_type, initial_balance, pinned)

    return {"periods": [PeriodPnlResponse(**p) for p in periods], "bot_stats": bot_stats}


@router.put("/accounts/{account_id}/period-pnl/{period_key}")
async def update_account_period_pnl(
    account_id: int,
    period_key: str,
    data: PeriodPnlUpdate,
    period_type: str = "monthly",
    db: AsyncSession = Depends(get_db),
):
    """Edit an account-level period's P&L by distributing across bots."""
    account = await db.get(Account, account_id)
    if not account:
        raise HTTPException(status_code=404, detail="Account not found")

    if data.pnl is not None:
        result = await db.execute(select(Bot).where(Bot.account_id == account_id))
        bots = [b for b in result.scalars().all() if not b.is_pinned]
        if not bots:
            raise HTTPException(status_code=400, detail="All bots are pinned")

        # Get each bot's current P&L for this period to distribute proportionally
        bot_period_pnls: dict[int, float] = {}
        for bot in bots:
            trade_result = await db.execute(
                select(Trade).where(Trade.bot_id == bot.id).order_by(Trade.entry_time)
            )
            bot_trades = list(trade_result.scalars().all())
            from app.services.calculation_engine import _get_trade_period_key
            period_pnl = sum(
                t.pnl for t in bot_trades
                if _get_trade_period_key(t, period_type) == period_key
            )
            bot_period_pnls[bot.id] = period_pnl

        total_current = sum(bot_period_pnls.values())
        for bot in bots:
            if total_current != 0:
                share = bot_period_pnls[bot.id] / total_current
            else:
                share = 1.0 / len(bots)
            bot_target = data.pnl * share
            await handle_period_pnl_edit(db, bot.id, period_key, period_type, bot_target, [])

    # Recalculate
    account_stats = await recalculate_account(db, account_id)
    await db.commit()

    # Return updated periods
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
    return {"periods": [PeriodPnlResponse(**p) for p in periods], "account_stats": account_stats}


@router.put("/portfolios/{portfolio_id}/period-pnl/{period_key}")
async def update_portfolio_period_pnl(
    portfolio_id: int,
    period_key: str,
    data: PeriodPnlUpdate,
    period_type: str = "monthly",
    db: AsyncSession = Depends(get_db),
):
    """Edit a portfolio-level period's P&L by distributing across accounts."""
    result = await db.execute(
        select(Account).where(Account.portfolio_id == portfolio_id)
    )
    accounts = [a for a in result.scalars().all() if not a.is_pinned]
    if not accounts:
        raise HTTPException(status_code=400, detail="All accounts are pinned")

    if data.pnl is not None:
        # Pre-filter to accounts that have at least one unpinned bot
        distributable: list[tuple] = []
        for account in accounts:
            bot_result = await db.execute(select(Bot).where(Bot.account_id == account.id))
            bots = [b for b in bot_result.scalars().all() if not b.is_pinned]
            if bots:
                distributable.append((account, bots))
        if not distributable:
            raise HTTPException(status_code=400, detail="All bots are pinned across accounts")

        per_account = data.pnl / len(distributable)
        for account, bots in distributable:
            per_bot = per_account / len(bots)
            for bot in bots:
                await handle_period_pnl_edit(db, bot.id, period_key, period_type, per_bot, [])

    # Recalculate
    portfolio_stats = await recalculate_portfolio(db, portfolio_id)
    await db.commit()

    # Return updated periods
    result = await db.execute(
        select(Account).where(Account.portfolio_id == portfolio_id)
    )
    all_accounts = list(result.scalars().all())
    all_trades = []
    total_initial = 0.0
    for account in all_accounts:
        total_initial += account.initial_balance
        bot_result = await db.execute(select(Bot).where(Bot.account_id == account.id))
        for bot in bot_result.scalars().all():
            trade_result = await db.execute(
                select(Trade).where(Trade.bot_id == bot.id).order_by(Trade.entry_time)
            )
            all_trades.extend(trade_result.scalars().all())
    all_trades.sort(key=lambda t: t.entry_time)
    periods = aggregate_period_pnl(all_trades, period_type, total_initial if total_initial > 0 else 10000.0)
    return {"periods": [PeriodPnlResponse(**p) for p in periods], "portfolio_stats": portfolio_stats}
