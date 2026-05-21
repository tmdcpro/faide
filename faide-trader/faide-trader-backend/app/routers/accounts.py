from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.database import get_db
from app.models.portfolio import Account, Bot, Trade, Portfolio, Transaction
from app.schemas import AccountCreate, AccountUpdate, AccountResponse
from app.services.calculation_engine import recalculate_account, get_account_net_deposits

router = APIRouter(prefix="/api", tags=["accounts"])


@router.get("/portfolios/{portfolio_id}/accounts", response_model=list[AccountResponse])
async def list_accounts(portfolio_id: int, db: AsyncSession = Depends(get_db)):
    portfolio = await db.get(Portfolio, portfolio_id)
    if not portfolio:
        raise HTTPException(status_code=404, detail="Portfolio not found")

    result = await db.execute(
        select(Account)
        .where(Account.portfolio_id == portfolio_id)
        .options(selectinload(Account.bots).selectinload(Bot.trades))
    )
    accounts = result.scalars().all()

    responses = []
    for a in accounts:
        net_deps = await get_account_net_deposits(db, a.id)
        total_pnl = a.current_balance - a.initial_balance - net_deps
        total_trades = sum(len(b.trades) for b in a.bots)
        total_wins = sum(1 for b in a.bots for t in b.trades if t.pnl > 0)
        win_rate = (total_wins / total_trades * 100) if total_trades > 0 else 0.0

        responses.append(AccountResponse(
            id=a.id,
            portfolio_id=a.portfolio_id,
            name=a.name,
            exchange=a.exchange,
            initial_balance=a.initial_balance,
            current_balance=a.current_balance,
            is_pinned=a.is_pinned,
            pinned_stats=a.pinned_stats,
            pinned_stat_values=a.pinned_stat_values,
            created_at=a.created_at,
            updated_at=a.updated_at,
            bot_count=len(a.bots),
            total_pnl=round(total_pnl, 2),
            total_trades=total_trades,
            win_rate=round(win_rate, 2),
        ))
    return responses


@router.post("/portfolios/{portfolio_id}/accounts", response_model=AccountResponse)
async def create_account(
    portfolio_id: int, data: AccountCreate, db: AsyncSession = Depends(get_db)
):
    portfolio = await db.get(Portfolio, portfolio_id)
    if not portfolio:
        raise HTTPException(status_code=404, detail="Portfolio not found")

    account = Account(
        portfolio_id=portfolio_id,
        name=data.name,
        exchange=data.exchange,
        initial_balance=data.initial_balance,
        current_balance=data.initial_balance,
    )
    db.add(account)
    await db.commit()
    await db.refresh(account)
    return AccountResponse(
        id=account.id,
        portfolio_id=account.portfolio_id,
        name=account.name,
        exchange=account.exchange,
        initial_balance=account.initial_balance,
        current_balance=account.current_balance,
        created_at=account.created_at,
        updated_at=account.updated_at,
    )


@router.get("/accounts/{account_id}", response_model=AccountResponse)
async def get_account(account_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(Account)
        .where(Account.id == account_id)
        .options(selectinload(Account.bots).selectinload(Bot.trades))
    )
    account = result.scalar_one_or_none()
    if not account:
        raise HTTPException(status_code=404, detail="Account not found")

    net_deps = await get_account_net_deposits(db, account.id)
    total_pnl = account.current_balance - account.initial_balance - net_deps
    total_trades = sum(len(b.trades) for b in account.bots)
    total_wins = sum(1 for b in account.bots for t in b.trades if t.pnl > 0)
    win_rate = (total_wins / total_trades * 100) if total_trades > 0 else 0.0

    return AccountResponse(
        id=account.id,
        portfolio_id=account.portfolio_id,
        name=account.name,
        exchange=account.exchange,
        initial_balance=account.initial_balance,
        current_balance=account.current_balance,
        is_pinned=account.is_pinned,
        pinned_stats=account.pinned_stats,
        pinned_stat_values=account.pinned_stat_values,
        created_at=account.created_at,
        updated_at=account.updated_at,
        bot_count=len(account.bots),
        total_pnl=round(total_pnl, 2),
        total_trades=total_trades,
        win_rate=round(win_rate, 2),
    )


@router.put("/accounts/{account_id}", response_model=AccountResponse)
async def update_account(
    account_id: int, data: AccountUpdate, db: AsyncSession = Depends(get_db)
):
    account = await db.get(Account, account_id)
    if not account:
        raise HTTPException(status_code=404, detail="Account not found")

    if data.name is not None:
        account.name = data.name
    if data.exchange is not None:
        account.exchange = data.exchange
    if data.initial_balance is not None:
        account.initial_balance = data.initial_balance
    if data.current_balance is not None:
        account.current_balance = data.current_balance
    if data.is_pinned is not None:
        account.is_pinned = data.is_pinned

    await db.commit()
    await db.refresh(account)
    return AccountResponse(
        id=account.id,
        portfolio_id=account.portfolio_id,
        name=account.name,
        exchange=account.exchange,
        initial_balance=account.initial_balance,
        current_balance=account.current_balance,
        is_pinned=account.is_pinned,
        pinned_stats=account.pinned_stats,
        pinned_stat_values=account.pinned_stat_values,
        created_at=account.created_at,
        updated_at=account.updated_at,
    )


@router.delete("/accounts/{account_id}")
async def delete_account(account_id: int, db: AsyncSession = Depends(get_db)):
    account = await db.get(Account, account_id)
    if not account:
        raise HTTPException(status_code=404, detail="Account not found")
    await db.delete(account)
    await db.commit()
    return {"status": "deleted"}
