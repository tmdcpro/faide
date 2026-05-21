from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.database import get_db
from app.models.portfolio import Trade, Bot, Account, Portfolio, PnlRecord, Transaction
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
    SetConstraintRequest,
    SetConstraintResponse,
    RegenerateRequest,
    RegenerateResponse,
)
from app.services.calculation_engine import get_account_net_deposits
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
    regenerate_bot_trades,
    regenerate_with_locked_stats,
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
            # Global stat editing with constraint enforcement
            locked_stats = bot.pinned_stats
            other_locked = [f for f in locked_stats if f != data.field]

            if other_locked:
                # Capture pre-edit stats for constraint enforcement
                trade_result = await db.execute(
                    select(Trade).where(Trade.bot_id == bot.id).order_by(Trade.entry_time)
                )
                pre_trades = list(trade_result.scalars().all())
                account_for_stats = await db.get(Account, bot.account_id)
                ib = account_for_stats.initial_balance if account_for_stats else 10000.0
                pre_edit_stats = calculate_stats_from_trades(pre_trades, ib)

                await regenerate_with_locked_stats(
                    db, bot.id, data.field, data.new_value, pre_edit_stats,
                )
            else:
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

        supported_account_fields = {"current_balance", "initial_balance", "total_pnl", "net_pnl"}
        if data.field not in supported_account_fields:
            raise HTTPException(status_code=400, detail=f"Field '{data.field}' is not editable on accounts. Supported: {sorted(supported_account_fields)}")

        if data.field == "current_balance":
            # Back-calculate: target total PnL = new_balance - initial_balance - net_deposits
            # Then distribute across all bots' trades to make accounting consistent
            net_deposits = await get_account_net_deposits(db, account.id)
            target_total_pnl = data.new_value - account.initial_balance - net_deposits
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
                        detail="Cannot edit current_balance because all bots are locked or have all trades pinned",
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
        elif data.field in ("total_pnl", "net_pnl"):
            target_total_pnl = data.new_value
            result = await db.execute(select(Bot).where(Bot.account_id == account.id))
            bots = list(result.scalars().all())
            if bots:
                bot_pnls: dict[int, float] = {}
                bot_has_editable: dict[int, bool] = {}
                for bot in bots:
                    trade_result = await db.execute(
                        select(Trade).where(Trade.bot_id == bot.id)
                    )
                    bot_trades = list(trade_result.scalars().all())
                    bot_pnls[bot.id] = sum(t.pnl for t in bot_trades)
                    bot_has_editable[bot.id] = any(not t.is_pinned for t in bot_trades)

                editable_bots = [b for b in bots if not b.is_pinned and bot_has_editable.get(b.id, False)]
                if not editable_bots:
                    raise HTTPException(
                        status_code=400,
                        detail="Cannot edit total_pnl because all bots are locked or have all trades pinned",
                    )

                editable_pnl = sum(bot_pnls[b.id] for b in editable_bots)
                pinned_bot_pnl = sum(bot_pnls[b.id] for b in bots if b not in editable_bots)
                distributable_target = target_total_pnl - pinned_bot_pnl

                if editable_pnl != 0:
                    for bot in editable_bots:
                        bot_share = bot_pnls[bot.id] / editable_pnl
                        await handle_top_down_edit(
                            db, bot.id, distributable_target * bot_share, data.pinned_fields
                        )
                else:
                    per_bot_pnl = distributable_target / len(editable_bots)
                    for bot in editable_bots:
                        await handle_top_down_edit(db, bot.id, per_bot_pnl, data.pinned_fields)
        elif data.field == "initial_balance":
            account.initial_balance = data.new_value

        account_stats = await recalculate_account(db, account.id)
        await db.commit()

        return RecalculateResponse(account_stats=account_stats)

    elif data.entity_type == "portfolio":
        portfolio_result = await db.execute(
            select(Portfolio).where(Portfolio.id == data.entity_id).options(selectinload(Portfolio.accounts))
        )
        portfolio = portfolio_result.scalar_one_or_none()
        if not portfolio:
            raise HTTPException(status_code=404, detail="Portfolio not found")

        supported_portfolio_fields = {"total_pnl"}
        if data.field not in supported_portfolio_fields:
            raise HTTPException(status_code=400, detail=f"Field '{data.field}' is not editable on portfolios. Supported: {sorted(supported_portfolio_fields)}")

        if data.field == "total_pnl":
            # Distribute target PnL across accounts, then cascade to trades
            editable_accounts = [a for a in portfolio.accounts if not a.is_pinned]
            if not editable_accounts:
                raise HTTPException(status_code=400, detail="All accounts are frozen")

            # Compute trading PnL excluding deposits/withdrawals for each account
            account_trading_pnl: dict[int, float] = {}
            for a in portfolio.accounts:
                net_deps = await get_account_net_deposits(db, a.id)
                account_trading_pnl[a.id] = a.current_balance - a.initial_balance - net_deps

            pinned_pnl = sum(account_trading_pnl[a.id] for a in portfolio.accounts if a.is_pinned)
            distributable_target = data.new_value - pinned_pnl
            editable_pnl = sum(account_trading_pnl[a.id] for a in editable_accounts)

            for a in editable_accounts:
                a_pnl = account_trading_pnl[a.id]
                share = a_pnl / editable_pnl if editable_pnl != 0 else 1.0 / len(editable_accounts)
                account_target_pnl = distributable_target * share

                # Cascade to bots/trades (same pattern as account current_balance edit)
                bot_result = await db.execute(select(Bot).where(Bot.account_id == a.id))
                bots = list(bot_result.scalars().all())
                if bots:
                    bot_pnls: dict[int, float] = {}
                    bot_has_editable: dict[int, bool] = {}
                    for bot in bots:
                        trade_result = await db.execute(select(Trade).where(Trade.bot_id == bot.id))
                        bot_trades = list(trade_result.scalars().all())
                        bot_pnls[bot.id] = sum(t.pnl for t in bot_trades)
                        bot_has_editable[bot.id] = any(not t.is_pinned for t in bot_trades)

                    editable_bots = [b for b in bots if not b.is_pinned and bot_has_editable.get(b.id, False)]
                    if editable_bots:
                        eb_pnl = sum(bot_pnls[b.id] for b in editable_bots)
                        pinned_bot_pnl = sum(bot_pnls[b.id] for b in bots if b not in editable_bots)
                        bot_distributable = account_target_pnl - pinned_bot_pnl

                        if eb_pnl != 0:
                            for bot in editable_bots:
                                bot_share = bot_pnls[bot.id] / eb_pnl
                                await handle_top_down_edit(db, bot.id, bot_distributable * bot_share, data.pinned_fields)
                        else:
                            per_bot = bot_distributable / len(editable_bots)
                            for bot in editable_bots:
                                await handle_top_down_edit(db, bot.id, per_bot, data.pinned_fields)

                await recalculate_account(db, a.id)

        portfolio_stats = await recalculate_portfolio(db, portfolio.id)
        await db.commit()

        return RecalculateResponse(portfolio_stats=portfolio_stats)

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

        if data.field:
            current = account.pinned_stats
            if data.pinned and data.field not in current:
                current.append(data.field)
            elif not data.pinned and data.field in current:
                current.remove(data.field)
            account.pinned_stats = current
        else:
            account.is_pinned = data.pinned

        await db.commit()
        return TogglePinResponse(
            success=True, entity_type="account", entity_id=data.entity_id,
            field=data.field, pinned=data.pinned,
        )

    elif data.entity_type == "portfolio":
        portfolio = await db.get(Portfolio, data.entity_id)
        if not portfolio:
            raise HTTPException(status_code=404, detail="Portfolio not found")

        if data.field:
            current = portfolio.pinned_stats
            if data.pinned and data.field not in current:
                current.append(data.field)
            elif not data.pinned and data.field in current:
                current.remove(data.field)
            portfolio.pinned_stats = current
        else:
            raise HTTPException(status_code=400, detail="Portfolio entity-level pinning not supported; use field-level pinning")

        await db.commit()
        return TogglePinResponse(
            success=True, entity_type="portfolio", entity_id=data.entity_id,
            field=data.field, pinned=data.pinned,
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


@router.post("/set-constraint", response_model=SetConstraintResponse)
async def set_constraint(data: SetConstraintRequest, db: AsyncSession = Depends(get_db)):
    """Set a constraint value for a locked stat. The stat must already be pinned."""
    if data.entity_type == "bot":
        entity = await db.get(Bot, data.entity_id)
    elif data.entity_type == "account":
        entity = await db.get(Account, data.entity_id)
    elif data.entity_type == "portfolio":
        entity = await db.get(Portfolio, data.entity_id)
    else:
        raise HTTPException(status_code=400, detail=f"Unsupported entity_type: {data.entity_type}")

    if not entity:
        raise HTTPException(status_code=404, detail=f"{data.entity_type} not found")

    # Ensure the field is pinned first; if not, pin it
    current_values = entity.pinned_stat_values
    current_values[data.field] = data.value
    entity.pinned_stat_values = current_values

    await db.commit()
    return SetConstraintResponse(
        success=True,
        entity_type=data.entity_type,
        entity_id=data.entity_id,
        field=data.field,
        value=data.value,
    )


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
        matched = False
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
                matched = True

        if not matched:
            from datetime import datetime as dt
            if period_type == "monthly":
                date = dt.strptime(period_key + "-01", "%Y-%m-%d")
            elif period_type == "daily":
                date = dt.strptime(period_key, "%Y-%m-%d")
            else:
                date = dt.strptime(period_key + "-1", "%G-W%V-%u")
            new_record = PnlRecord(
                bot_id=bot_id,
                date=date,
                period_type=period_type,
                pnl=0.0,
                cumulative_pnl=0.0,
                is_pinned=data.is_pinned,
            )
            db.add(new_record)

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
        from app.services.calculation_engine import _get_trade_period_key

        result = await db.execute(select(Bot).where(Bot.account_id == account_id))
        all_bots = list(result.scalars().all())
        unpinned_bots = [b for b in all_bots if not b.is_pinned]
        if not unpinned_bots:
            raise HTTPException(status_code=400, detail="All bots are pinned")

        # Compute pinned bots' period PnL to subtract from target
        pinned_period_pnl = 0.0
        for bot in all_bots:
            if bot.is_pinned:
                trade_result = await db.execute(
                    select(Trade).where(Trade.bot_id == bot.id).order_by(Trade.entry_time)
                )
                pinned_period_pnl += sum(
                    t.pnl for t in trade_result.scalars().all()
                    if _get_trade_period_key(t, period_type) == period_key
                )

        distributable_target = data.pnl - pinned_period_pnl

        # Get each unpinned bot's current P&L for this period to distribute proportionally
        bot_period_pnls: dict[int, float] = {}
        for bot in unpinned_bots:
            trade_result = await db.execute(
                select(Trade).where(Trade.bot_id == bot.id).order_by(Trade.entry_time)
            )
            bot_trades = list(trade_result.scalars().all())
            period_pnl = sum(
                t.pnl for t in bot_trades
                if _get_trade_period_key(t, period_type) == period_key
            )
            bot_period_pnls[bot.id] = period_pnl

        total_current = sum(bot_period_pnls.values())
        for bot in unpinned_bots:
            if total_current != 0:
                share = bot_period_pnls[bot.id] / total_current
            else:
                share = 1.0 / len(unpinned_bots)
            bot_target = distributable_target * share
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
        from app.services.calculation_engine import _get_trade_period_key

        # Query ALL accounts (including pinned) to compute pinned PnL
        all_acct_result = await db.execute(
            select(Account).where(Account.portfolio_id == portfolio_id)
        )
        all_accounts_list = list(all_acct_result.scalars().all())

        pinned_period_pnl = 0.0
        # Add period PnL from pinned accounts
        for acct in all_accounts_list:
            if acct.is_pinned:
                bot_result = await db.execute(select(Bot).where(Bot.account_id == acct.id))
                for bot in bot_result.scalars().all():
                    trade_result = await db.execute(
                        select(Trade).where(Trade.bot_id == bot.id)
                    )
                    pinned_period_pnl += sum(
                        t.pnl for t in trade_result.scalars().all()
                        if _get_trade_period_key(t, period_type) == period_key
                    )

        # Pre-filter unpinned accounts to those with at least one unpinned bot
        # Also accumulate period PnL from pinned bots within unpinned accounts
        distributable: list[tuple] = []
        for account in accounts:
            bot_result = await db.execute(select(Bot).where(Bot.account_id == account.id))
            all_bots = list(bot_result.scalars().all())
            unpinned_bots = [b for b in all_bots if not b.is_pinned]
            # Add period PnL from pinned bots within this unpinned account
            for bot in all_bots:
                if bot.is_pinned:
                    trade_result = await db.execute(
                        select(Trade).where(Trade.bot_id == bot.id)
                    )
                    pinned_period_pnl += sum(
                        t.pnl for t in trade_result.scalars().all()
                        if _get_trade_period_key(t, period_type) == period_key
                    )
            if unpinned_bots:
                distributable.append((account, unpinned_bots))
        if not distributable:
            raise HTTPException(status_code=400, detail="All bots are pinned across accounts")

        distributable_target = data.pnl - pinned_period_pnl
        per_account = distributable_target / len(distributable)
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


# --- Regenerate Endpoints ---

@router.post("/bots/{bot_id}/regenerate", response_model=RegenerateResponse)
async def regenerate_bot(
    bot_id: int,
    data: RegenerateRequest,
    db: AsyncSession = Depends(get_db),
):
    """
    Regenerate trades for a bot while respecting all locked stat constraints.

    Locked stats (from pinned_stats) are used as hard constraints.
    Pinned trades are preserved; unpinned trades are deleted and replaced.
    """
    bot = await db.get(Bot, bot_id)
    if not bot:
        raise HTTPException(status_code=404, detail="Bot not found")

    # Parse dates if provided
    start_date = None
    end_date = None
    if data.start_date:
        try:
            start_date = datetime.fromisoformat(data.start_date)
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid start_date format")
    if data.end_date:
        try:
            end_date = datetime.fromisoformat(data.end_date)
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid end_date format")

    # Get constraints for the response
    account = await db.get(Account, bot.account_id)
    initial_balance = account.initial_balance if account else 10000.0

    trade_result = await db.execute(
        select(Trade).where(Trade.bot_id == bot_id).order_by(Trade.entry_time)
    )
    existing_trades = list(trade_result.scalars().all())
    pre_stats = calculate_stats_from_trades(existing_trades, initial_balance)

    constraints_applied: dict[str, float] = {}
    for field in bot.pinned_stats:
        if field in pre_stats:
            constraints_applied[field] = pre_stats[field]

    try:
        stats = await regenerate_bot_trades(
            db, bot_id,
            num_trades=data.num_trades,
            start_date=start_date,
            end_date=end_date,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    await db.commit()

    # Get final trade count
    result = await db.execute(
        select(Trade).where(Trade.bot_id == bot_id)
    )
    final_count = len(list(result.scalars().all()))

    return RegenerateResponse(
        generated=final_count,
        bot_id=bot_id,
        constraints_applied=constraints_applied,
        bot_stats=stats,
        final_stats=stats,
    )


async def _get_account_stats(db: AsyncSession, account: Account) -> dict:
    """Get current aggregated stats for an account."""
    result = await db.execute(select(Bot).where(Bot.account_id == account.id))
    bots = list(result.scalars().all())
    total_pnl = 0.0
    total_trades = 0
    total_wins = 0
    for bot in bots:
        trade_result = await db.execute(
            select(Trade).where(Trade.bot_id == bot.id).order_by(Trade.entry_time)
        )
        bot_trades = list(trade_result.scalars().all())
        bot_stats = calculate_stats_from_trades(bot_trades, account.initial_balance)
        total_pnl += bot_stats.get("net_pnl", 0.0)
        total_trades += bot_stats.get("total_trades", 0)
        total_wins += bot_stats.get("win_count", 0)
    dep_result = await db.execute(
        select(func.coalesce(func.sum(Transaction.amount), 0))
        .where(Transaction.account_id == account.id, Transaction.type == "deposit")
    )
    total_deposits = dep_result.scalar() or 0.0
    wd_result = await db.execute(
        select(func.coalesce(func.sum(Transaction.amount), 0))
        .where(Transaction.account_id == account.id, Transaction.type == "withdrawal")
    )
    total_withdrawals = wd_result.scalar() or 0.0

    return {
        "total_pnl": round(total_pnl, 2),
        "net_pnl": round(total_pnl, 2),
        "total_trades": total_trades,
        "win_count": total_wins,
        "loss_count": total_trades - total_wins,
        "win_rate": round(total_wins / total_trades * 100, 2) if total_trades > 0 else 0.0,
        "current_balance": round(account.initial_balance + total_pnl + total_deposits - total_withdrawals, 2),
    }


@router.post("/accounts/{account_id}/regenerate", response_model=dict)
async def regenerate_account(
    account_id: int,
    data: RegenerateRequest,
    db: AsyncSession = Depends(get_db),
):
    """
    Regenerate trades for all unlocked bots in an account.

    Account-level pinned_stats are respected as constraints.
    If account has total_pnl pinned, the target is distributed proportionally
    across unlocked bots (subtracting frozen bots' contribution).
    """
    account = await db.get(Account, account_id)
    if not account:
        raise HTTPException(status_code=404, detail="Account not found")

    result = await db.execute(select(Bot).where(Bot.account_id == account_id))
    bots = list(result.scalars().all())

    unlocked_bots = [b for b in bots if not b.is_pinned]
    locked_bots = [b for b in bots if b.is_pinned]
    if not unlocked_bots:
        raise HTTPException(status_code=400, detail="All bots are locked")

    start_date = None
    end_date = None
    if data.start_date:
        try:
            start_date = datetime.fromisoformat(data.start_date)
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid start_date format")
    if data.end_date:
        try:
            end_date = datetime.fromisoformat(data.end_date)
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid end_date format")

    # Build account-level constraints from pinned_stats (use explicit values if set)
    account_constraints: dict[str, float] = {}
    if account.pinned_stats:
        acct_stats = await _get_account_stats(db, account)
        pinned_values = account.pinned_stat_values
        for field in account.pinned_stats:
            if pinned_values.get(field) is not None:
                account_constraints[field] = pinned_values[field]
            elif field in acct_stats:
                account_constraints[field] = acct_stats[field]

    # Calculate frozen bots' contribution to subtract from account targets
    frozen_pnl = 0.0
    frozen_trades = 0
    frozen_wins = 0
    for bot in locked_bots:
        trade_result = await db.execute(
            select(Trade).where(Trade.bot_id == bot.id).order_by(Trade.entry_time)
        )
        bot_trades = list(trade_result.scalars().all())
        bot_stats = calculate_stats_from_trades(bot_trades, account.initial_balance)
        frozen_pnl += bot_stats.get("net_pnl", 0.0)
        frozen_trades += bot_stats.get("total_trades", 0)
        frozen_wins += bot_stats.get("win_count", 0)

    # Distribute account-level constraints across unlocked bots
    bot_extra_constraints: dict[int, dict[str, float]] = {}
    num_unlocked = len(unlocked_bots)

    if "total_pnl" in account_constraints or "net_pnl" in account_constraints:
        target_key = "total_pnl" if "total_pnl" in account_constraints else "net_pnl"
        target_total = account_constraints[target_key]
        distributable = target_total - frozen_pnl
        per_bot = distributable / num_unlocked if num_unlocked > 0 else 0
        for bot in unlocked_bots:
            bot_extra_constraints.setdefault(bot.id, {})["net_pnl"] = per_bot

    if "win_rate" in account_constraints:
        target_wr = account_constraints["win_rate"]
        for bot in unlocked_bots:
            bot_extra_constraints.setdefault(bot.id, {})["win_rate"] = target_wr

    bot_results = {}
    for bot in unlocked_bots:
        stats = await regenerate_bot_trades(
            db, bot.id,
            num_trades=data.num_trades,
            start_date=start_date,
            end_date=end_date,
            extra_constraints=bot_extra_constraints.get(bot.id),
            skip_account_recalc=True,
        )
        bot_results[bot.name] = stats

    account_stats = await recalculate_account(db, account_id)
    await db.commit()

    return {
        "account_id": account_id,
        "bots_regenerated": len(unlocked_bots),
        "bots_skipped_locked": len(bots) - len(unlocked_bots),
        "bot_results": bot_results,
        "account_stats": account_stats,
        "constraints_applied": account_constraints,
    }


@router.post("/portfolios/{portfolio_id}/regenerate", response_model=dict)
async def regenerate_portfolio(
    portfolio_id: int,
    data: RegenerateRequest,
    db: AsyncSession = Depends(get_db),
):
    """
    Regenerate trades for all unlocked bots across all unlocked accounts in a portfolio.

    Portfolio-level pinned_stats are respected as constraints.
    If portfolio has total_pnl pinned, the target is distributed proportionally
    across unlocked accounts, then down to their unlocked bots.
    """
    portfolio = await db.get(Portfolio, portfolio_id)
    if not portfolio:
        raise HTTPException(status_code=404, detail="Portfolio not found")

    result = await db.execute(
        select(Account).where(Account.portfolio_id == portfolio_id)
    )
    accounts = list(result.scalars().all())
    if not accounts:
        raise HTTPException(status_code=400, detail="Portfolio has no accounts")

    start_date = None
    end_date = None
    if data.start_date:
        try:
            start_date = datetime.fromisoformat(data.start_date)
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid start_date format")
    if data.end_date:
        try:
            end_date = datetime.fromisoformat(data.end_date)
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid end_date format")

    # Build portfolio-level constraints from pinned_stats (use explicit values if set)
    portfolio_constraints: dict[str, float] = {}
    if portfolio.pinned_stats:
        port_stats = await _get_portfolio_stats(db, portfolio_id, accounts)
        pinned_values = portfolio.pinned_stat_values
        for field in portfolio.pinned_stats:
            if pinned_values.get(field) is not None:
                portfolio_constraints[field] = pinned_values[field]
            elif field in port_stats:
                portfolio_constraints[field] = port_stats[field]

    unlocked_accounts = [a for a in accounts if not a.is_pinned]
    locked_accounts = [a for a in accounts if a.is_pinned]

    # Calculate frozen accounts' trading PnL (excluding deposits/withdrawals)
    frozen_pnl = 0.0
    for acct in locked_accounts:
        net_deps = await get_account_net_deposits(db, acct.id)
        frozen_pnl += acct.current_balance - acct.initial_balance - net_deps

    # Distribute portfolio-level total_pnl constraint across unlocked accounts
    account_pnl_targets: dict[int, float] = {}
    if "total_pnl" in portfolio_constraints or "net_pnl" in portfolio_constraints:
        target_key = "total_pnl" if "total_pnl" in portfolio_constraints else "net_pnl"
        target_total = portfolio_constraints[target_key]
        distributable = target_total - frozen_pnl
        num_unlocked_accts = len(unlocked_accounts)
        if num_unlocked_accts > 0:
            per_acct = distributable / num_unlocked_accts
            for acct in unlocked_accounts:
                account_pnl_targets[acct.id] = per_acct

    total_regenerated = 0
    total_skipped = 0

    for account in locked_accounts:
        bot_result = await db.execute(select(Bot).where(Bot.account_id == account.id))
        total_skipped += len(list(bot_result.scalars().all()))

    for account in unlocked_accounts:
        bot_result = await db.execute(select(Bot).where(Bot.account_id == account.id))
        bots = list(bot_result.scalars().all())
        unlocked_bots = [b for b in bots if not b.is_pinned]
        locked_bots = [b for b in bots if b.is_pinned]

        # Calculate frozen bots' contribution within this account
        acct_frozen_pnl = 0.0
        for bot in locked_bots:
            trade_result = await db.execute(
                select(Trade).where(Trade.bot_id == bot.id)
            )
            bot_trades = list(trade_result.scalars().all())
            bot_stats = calculate_stats_from_trades(bot_trades, account.initial_balance)
            acct_frozen_pnl += bot_stats.get("net_pnl", 0.0)
            total_skipped += 1

        # Build extra constraints for each unlocked bot
        for bot in unlocked_bots:
            extra: dict[str, float] = {}

            # Push down account-level P&L target
            if account.id in account_pnl_targets and unlocked_bots:
                acct_target = account_pnl_targets[account.id]
                bot_share = (acct_target - acct_frozen_pnl) / len(unlocked_bots)
                extra["net_pnl"] = bot_share

            # Push down account-level pinned win_rate
            if account.pinned_stats and "win_rate" in account.pinned_stats:
                acct_stats = await _get_account_stats(db, account)
                extra["win_rate"] = acct_stats.get("win_rate", 50.0)

            # Push down portfolio-level pinned win_rate
            if "win_rate" in portfolio_constraints and "win_rate" not in extra:
                extra["win_rate"] = portfolio_constraints["win_rate"]

            await regenerate_bot_trades(
                db, bot.id,
                num_trades=data.num_trades,
                start_date=start_date,
                end_date=end_date,
                extra_constraints=extra if extra else None,
                skip_account_recalc=True,
            )
            total_regenerated += 1

        await recalculate_account(db, account.id)

    portfolio_stats = await recalculate_portfolio(db, portfolio_id)
    await db.commit()

    return {
        "portfolio_id": portfolio_id,
        "bots_regenerated": total_regenerated,
        "bots_skipped_locked": total_skipped,
        "portfolio_stats": portfolio_stats,
        "constraints_applied": portfolio_constraints,
    }


async def _get_portfolio_stats(db: AsyncSession, portfolio_id: int, accounts: list[Account]) -> dict:
    """Get current aggregated stats for a portfolio."""
    total_pnl = 0.0
    total_balance = 0.0
    total_trades = 0
    total_wins = 0
    for account in accounts:
        acct_stats = await _get_account_stats(db, account)
        total_pnl += acct_stats.get("net_pnl", 0.0)
        total_balance += acct_stats.get("current_balance", account.initial_balance)
        total_trades += acct_stats.get("total_trades", 0)
        total_wins += acct_stats.get("win_count", 0)
    return {
        "total_pnl": round(total_pnl, 2),
        "net_pnl": round(total_pnl, 2),
        "total_balance": round(total_balance, 2),
        "total_trades": total_trades,
        "win_count": total_wins,
        "win_rate": round(total_wins / total_trades * 100, 2) if total_trades > 0 else 0.0,
        "account_count": len(accounts),
    }
