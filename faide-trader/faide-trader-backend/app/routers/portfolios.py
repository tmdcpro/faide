from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.database import get_db
from app.models.portfolio import Portfolio, Account, Bot, Trade
from app.schemas import PortfolioCreate, PortfolioUpdate, PortfolioResponse
from app.services.calculation_engine import recalculate_portfolio

router = APIRouter(prefix="/api/portfolios", tags=["portfolios"])


@router.get("", response_model=list[PortfolioResponse])
async def list_portfolios(db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(Portfolio).options(selectinload(Portfolio.accounts))
    )
    portfolios = result.scalars().all()

    responses = []
    for p in portfolios:
        total_pnl = 0.0
        total_balance = 0.0
        for a in p.accounts:
            total_pnl += (a.current_balance - a.initial_balance)
            total_balance += a.current_balance

        responses.append(PortfolioResponse(
            id=p.id,
            name=p.name,
            description=p.description,
            pinned_stats=p.pinned_stats,
            pinned_stat_values=p.pinned_stat_values,
            created_at=p.created_at,
            updated_at=p.updated_at,
            account_count=len(p.accounts),
            total_pnl=round(total_pnl, 2),
            total_balance=round(total_balance, 2),
        ))
    return responses


@router.post("", response_model=PortfolioResponse)
async def create_portfolio(data: PortfolioCreate, db: AsyncSession = Depends(get_db)):
    portfolio = Portfolio(name=data.name, description=data.description)
    db.add(portfolio)
    await db.commit()
    await db.refresh(portfolio)
    return PortfolioResponse(
        id=portfolio.id,
        name=portfolio.name,
        description=portfolio.description,
        pinned_stats=portfolio.pinned_stats,
        pinned_stat_values=portfolio.pinned_stat_values,
        created_at=portfolio.created_at,
        updated_at=portfolio.updated_at,
    )


@router.get("/{portfolio_id}", response_model=PortfolioResponse)
async def get_portfolio(portfolio_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(Portfolio).where(Portfolio.id == portfolio_id).options(selectinload(Portfolio.accounts))
    )
    portfolio = result.scalar_one_or_none()
    if not portfolio:
        raise HTTPException(status_code=404, detail="Portfolio not found")

    total_pnl = 0.0
    total_balance = 0.0
    for a in portfolio.accounts:
        total_pnl += (a.current_balance - a.initial_balance)
        total_balance += a.current_balance

    return PortfolioResponse(
        id=portfolio.id,
        name=portfolio.name,
        description=portfolio.description,
        pinned_stats=portfolio.pinned_stats,
        pinned_stat_values=portfolio.pinned_stat_values,
        created_at=portfolio.created_at,
        updated_at=portfolio.updated_at,
        account_count=len(portfolio.accounts),
        total_pnl=round(total_pnl, 2),
        total_balance=round(total_balance, 2),
    )


@router.put("/{portfolio_id}", response_model=PortfolioResponse)
async def update_portfolio(
    portfolio_id: int, data: PortfolioUpdate, db: AsyncSession = Depends(get_db)
):
    portfolio = await db.get(Portfolio, portfolio_id)
    if not portfolio:
        raise HTTPException(status_code=404, detail="Portfolio not found")

    if data.name is not None:
        portfolio.name = data.name
    if data.description is not None:
        portfolio.description = data.description

    await db.commit()
    await db.refresh(portfolio)
    return PortfolioResponse(
        id=portfolio.id,
        name=portfolio.name,
        description=portfolio.description,
        pinned_stats=portfolio.pinned_stats,
        pinned_stat_values=portfolio.pinned_stat_values,
        created_at=portfolio.created_at,
        updated_at=portfolio.updated_at,
    )


@router.delete("/{portfolio_id}")
async def delete_portfolio(portfolio_id: int, db: AsyncSession = Depends(get_db)):
    portfolio = await db.get(Portfolio, portfolio_id)
    if not portfolio:
        raise HTTPException(status_code=404, detail="Portfolio not found")
    await db.delete(portfolio)
    await db.commit()
    return {"status": "deleted"}
