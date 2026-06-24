from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.portfolio import Transaction, Account
from app.schemas import TransactionCreate, TransactionUpdate, TransactionResponse
from app.services.calculation_engine import recalculate_account

router = APIRouter(prefix="/api", tags=["transactions"])


@router.get("/accounts/{account_id}/transactions", response_model=list[TransactionResponse])
async def list_transactions(account_id: int, db: AsyncSession = Depends(get_db)):
    account = await db.get(Account, account_id)
    if not account:
        raise HTTPException(status_code=404, detail="Account not found")
    result = await db.execute(
        select(Transaction)
        .where(Transaction.account_id == account_id)
        .order_by(Transaction.date.desc())
    )
    return result.scalars().all()


@router.post("/accounts/{account_id}/transactions", response_model=TransactionResponse)
async def create_transaction(account_id: int, data: TransactionCreate, db: AsyncSession = Depends(get_db)):
    account = await db.get(Account, account_id)
    if not account:
        raise HTTPException(status_code=404, detail="Account not found")

    if data.type not in ("deposit", "withdrawal"):
        raise HTTPException(status_code=400, detail="Type must be 'deposit' or 'withdrawal'")

    tx = Transaction(
        account_id=account_id,
        type=data.type,
        amount=data.amount,
        note=data.note,
        date=datetime.fromisoformat(data.date),
    )
    db.add(tx)
    await db.flush()
    await db.refresh(tx)
    await recalculate_account(db, account_id)
    await db.commit()
    return tx


@router.put("/transactions/{tx_id}", response_model=TransactionResponse)
async def update_transaction(tx_id: int, data: TransactionUpdate, db: AsyncSession = Depends(get_db)):
    tx = await db.get(Transaction, tx_id)
    if not tx:
        raise HTTPException(status_code=404, detail="Transaction not found")

    if data.type is not None:
        if data.type not in ("deposit", "withdrawal"):
            raise HTTPException(status_code=400, detail="Type must be 'deposit' or 'withdrawal'")
        tx.type = data.type
    if data.amount is not None:
        tx.amount = data.amount
    if data.note is not None:
        tx.note = data.note
    if data.date is not None:
        tx.date = datetime.fromisoformat(data.date)

    account_id = tx.account_id
    await db.flush()
    await db.refresh(tx)
    await recalculate_account(db, account_id)
    await db.commit()
    return tx


@router.delete("/transactions/{tx_id}")
async def delete_transaction(tx_id: int, db: AsyncSession = Depends(get_db)):
    tx = await db.get(Transaction, tx_id)
    if not tx:
        raise HTTPException(status_code=404, detail="Transaction not found")

    account_id = tx.account_id
    await db.delete(tx)
    await db.flush()
    await recalculate_account(db, account_id)
    await db.commit()
    return {"status": "deleted"}


@router.get("/portfolios/{portfolio_id}/transactions", response_model=list[TransactionResponse])
async def list_portfolio_transactions(portfolio_id: int, db: AsyncSession = Depends(get_db)):
    """List all transactions across all accounts in a portfolio."""
    result = await db.execute(
        select(Transaction)
        .join(Account)
        .where(Account.portfolio_id == portfolio_id)
        .order_by(Transaction.date.desc())
    )
    return result.scalars().all()
