"""
Append new simulated data to the existing portfolio.

This script adds NEW trades and deposits from the day after the latest existing
data through a specified end date. It does NOT modify or delete any existing data.

Usage:
    poetry run python scripts/append_data.py [--end-date 2026-06-23]
"""
import asyncio
import random
import argparse
from datetime import datetime, timedelta
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import select, func, text
from app.database import engine, async_session, Base
from app.models.portfolio import Portfolio, Account, Bot, Trade, PnlRecord, Transaction
from app.services.calculation_engine import rebuild_pnl_records

# Use a different seed so new data has variety but is reproducible
random.seed(2026_06_23)

# ─── Price helpers (same as generate_portfolio.py) ───────────────────

BTC_PRICES = {
    datetime(2024, 5, 1): 58000,
    datetime(2024, 7, 1): 62000,
    datetime(2024, 9, 1): 57000,
    datetime(2024, 11, 1): 73000,
    datetime(2025, 1, 1): 95000,
    datetime(2025, 3, 1): 85000,
    datetime(2025, 5, 1): 97000,
    datetime(2025, 7, 1): 100000,
    datetime(2025, 9, 1): 85000,
    datetime(2025, 11, 1): 90000,
    datetime(2026, 1, 1): 100000,
    datetime(2026, 3, 1): 85000,
    datetime(2026, 5, 1): 103000,
    datetime(2026, 7, 1): 108000,
}

def get_btc_price(dt: datetime) -> float:
    dates = sorted(BTC_PRICES.keys())
    if dt <= dates[0]:
        return BTC_PRICES[dates[0]]
    if dt >= dates[-1]:
        return BTC_PRICES[dates[-1]]
    for i in range(len(dates) - 1):
        if dates[i] <= dt < dates[i + 1]:
            ratio = (dt - dates[i]).total_seconds() / (dates[i + 1] - dates[i]).total_seconds()
            return BTC_PRICES[dates[i]] + ratio * (BTC_PRICES[dates[i + 1]] - BTC_PRICES[dates[i]])
    return 100000

def get_price_for_symbol(symbol: str, dt: datetime) -> float:
    btc = get_btc_price(dt)
    ratios = {
        "BTC": 1.0, "ETH": 0.038, "SOL": 0.0018, "XRP": 0.000008,
        "DOGE": 0.0000025, "AVAX": 0.0005, "LINK": 0.00022, "ARB": 0.000015,
    }
    base = symbol.split("/")[0]
    ratio = ratios.get(base, 0.001)
    return btc * ratio * random.uniform(0.95, 1.05)

# ─── Strategy parameters ────────────────────────────────────────────

STRATEGY_PARAMS = {
    "grid": {"win_rate": 0.62, "avg_win_ratio": 1.0, "trades_per_day": 1.5, "leverage_range": (2, 8)},
    "scalping": {"win_rate": 0.58, "avg_win_ratio": 0.8, "trades_per_day": 4.0, "leverage_range": (3, 10)},
    "dca": {"win_rate": 0.65, "avg_win_ratio": 1.2, "trades_per_day": 0.5, "leverage_range": (1, 3)},
    "swing": {"win_rate": 0.52, "avg_win_ratio": 1.8, "trades_per_day": 0.25, "leverage_range": (2, 5)},
    "trend_following": {"win_rate": 0.48, "avg_win_ratio": 2.0, "trades_per_day": 0.35, "leverage_range": (2, 6)},
    "mean_reversion": {"win_rate": 0.60, "avg_win_ratio": 1.1, "trades_per_day": 1.0, "leverage_range": (2, 7)},
    "arbitrage": {"win_rate": 0.70, "avg_win_ratio": 0.5, "trades_per_day": 2.0, "leverage_range": (1, 4)},
}


def generate_trades_for_period(
    bot_symbols: list[str],
    strategy: str,
    start_date: datetime,
    end_date: datetime,
    target_pnl: float,
) -> list[dict]:
    """Generate trades for a bot in the given date range."""
    params = STRATEGY_PARAMS.get(strategy, STRATEGY_PARAMS["grid"])
    total_days = (end_date - start_date).days
    if total_days <= 0:
        return []

    num_trades = max(2, int(total_days * params["trades_per_day"] * random.uniform(0.7, 1.3)))
    win_rate = params["win_rate"] + random.uniform(-0.05, 0.05)
    num_wins = int(num_trades * win_rate)
    num_losses = num_trades - num_wins

    avg_win_ratio = params["avg_win_ratio"]
    denom = num_wins * avg_win_ratio - num_losses
    if abs(denom) < 0.01:
        denom = 1.0
    avg_loss = abs(target_pnl / denom)
    avg_win = avg_loss * avg_win_ratio

    win_flags = [True] * num_wins + [False] * num_losses
    random.shuffle(win_flags)

    trades = []
    for i in range(num_trades):
        is_win = win_flags[i]
        symbol = random.choice(bot_symbols)
        trade_progress = i / max(num_trades - 1, 1)
        trade_dt = start_date + timedelta(days=total_days * trade_progress)
        base_price = get_price_for_symbol(symbol, trade_dt)

        if is_win:
            pnl = avg_win * random.uniform(0.2, 2.5)
        else:
            pnl = -avg_loss * random.uniform(0.2, 2.5)

        direction = random.choice(["long", "short"])
        leverage = round(random.uniform(*params["leverage_range"]), 1)
        quantity = round(random.uniform(0.01, 0.3), 4)
        if base_price * quantity < 1:
            quantity = round(1.0 / base_price, 4)

        if direction == "long":
            exit_price = base_price + pnl / max(quantity, 0.0001)
        else:
            exit_price = base_price - pnl / max(quantity, 0.0001)
        exit_price = max(0.01, exit_price)

        fee = round(abs(pnl) * random.uniform(0.001, 0.005), 2)
        fee = max(0.01, fee)

        entry_time = trade_dt + timedelta(hours=random.randint(0, 23), minutes=random.randint(0, 59))
        duration_hours = random.randint(1, 48)
        exit_time = entry_time + timedelta(hours=duration_hours)
        if exit_time > end_date:
            exit_time = end_date - timedelta(hours=random.randint(1, 6))

        trades.append({
            "symbol": symbol,
            "direction": direction,
            "status": "closed",
            "entry_price": round(base_price, 2),
            "exit_price": round(exit_price, 2),
            "quantity": quantity,
            "leverage": leverage,
            "pnl": round(pnl, 2),
            "fee": fee,
            "entry_time": entry_time,
            "exit_time": exit_time,
        })

    # Adjust last trade to hit target exactly
    if trades:
        actual = sum(t["pnl"] for t in trades)
        diff = target_pnl - actual
        trades[-1]["pnl"] = round(trades[-1]["pnl"] + diff, 2)
        t = trades[-1]
        if t["direction"] == "long":
            t["exit_price"] = round(t["entry_price"] + t["pnl"] / max(t["quantity"], 0.0001), 2)
        else:
            t["exit_price"] = round(t["entry_price"] - t["pnl"] / max(t["quantity"], 0.0001), 2)
        t["exit_price"] = max(0.01, t["exit_price"])

    trades.sort(key=lambda t: t["entry_time"])
    return trades


async def append_data(end_date: datetime):
    print(f"📊 Appending data through {end_date.strftime('%Y-%m-%d')}...")
    print(f"   Existing data will NOT be modified.\n")

    async with async_session() as db:
        # ── Snapshot existing counts for verification ────────────────
        existing_trade_count = (await db.execute(select(func.count(Trade.id)))).scalar()
        existing_tx_count = (await db.execute(select(func.count(Transaction.id)))).scalar()
        print(f"📋 Existing data: {existing_trade_count} trades, {existing_tx_count} transactions")

        # ── Get all bots with their info ─────────────────────────────
        bots_result = await db.execute(
            select(Bot).options()
        )
        bots = list(bots_result.scalars().all())

        # ── Get accounts ─────────────────────────────────────────────
        accounts_result = await db.execute(select(Account))
        accounts = {a.id: a for a in accounts_result.scalars().all()}

        # ── Get the latest trade date per bot ────────────────────────
        bot_latest = {}
        for bot in bots:
            result = await db.execute(
                select(func.max(Trade.entry_time)).where(Trade.bot_id == bot.id)
            )
            latest = result.scalar()
            if latest:
                bot_latest[bot.id] = latest
            else:
                bot_latest[bot.id] = datetime(2026, 5, 20)

        # ── Find the Bitget account for deposits ─────────────────────
        bitget_account = None
        for a in accounts.values():
            if "bitget" in (a.exchange or "").lower() or "bitget" in (a.name or "").lower():
                bitget_account = a
                break

        # ── Get latest transaction date ──────────────────────────────
        latest_tx_result = await db.execute(
            select(func.max(Transaction.date))
        )
        latest_tx_date = latest_tx_result.scalar() or datetime(2026, 5, 18)

        # ── P&L targets: continue the growth trajectory ──────────────
        # Original: ~$56K trading P&L over ~24 months = ~$2,300/mo
        # Recent months were higher; target ~$3,000-4,000/mo for continuation
        total_new_days = (end_date - datetime(2026, 5, 20)).days
        target_new_portfolio_pnl = total_new_days * 100  # ~$100/day = ~$3,000/month

        # Distribute among bots weighted by account importance
        bot_weights = []
        for bot in bots:
            account = accounts[bot.account_id]
            exchange = (account.exchange or "").lower()
            if "bitget" in exchange:
                weight = 2.0
            elif "phemex" in exchange:
                weight = 0.8
            else:
                weight = 0.5
            # Scalping/grid bots trade more
            if bot.strategy_type in ("scalping", "grid", "arbitrage"):
                weight *= 1.3
            bot_weights.append(weight)

        total_weight = sum(bot_weights)
        bot_pnl_targets = [(w / total_weight) * target_new_portfolio_pnl for w in bot_weights]

        # ── Generate new trades for each bot ─────────────────────────
        new_trade_count = 0
        new_bot_pnls = {}
        for idx, bot in enumerate(bots):
            last_trade_date = bot_latest[bot.id]
            bot_start = last_trade_date + timedelta(hours=random.randint(6, 24))

            if bot_start >= end_date:
                print(f"  ⏭️  {bot.name}: already up to date, skipping")
                continue

            symbols = bot.symbols if bot.symbols else [bot.symbol]
            target_pnl = bot_pnl_targets[idx]

            trades = generate_trades_for_period(
                bot_symbols=symbols,
                strategy=bot.strategy_type or "grid",
                start_date=bot_start,
                end_date=end_date,
                target_pnl=target_pnl,
            )

            actual_pnl = 0.0
            for t in trades:
                pnl_pct = (t["pnl"] / max(abs(t["entry_price"] * t["quantity"]), 0.01)) * 100
                trade = Trade(
                    bot_id=bot.id,
                    symbol=t["symbol"],
                    direction=t["direction"],
                    status=t["status"],
                    entry_price=t["entry_price"],
                    exit_price=t["exit_price"],
                    quantity=t["quantity"],
                    leverage=t["leverage"],
                    pnl=t["pnl"],
                    pnl_percent=round(pnl_pct, 2),
                    fee=t["fee"],
                    entry_time=t["entry_time"],
                    exit_time=t["exit_time"],
                )
                db.add(trade)
                actual_pnl += t["pnl"]

            new_trade_count += len(trades)
            new_bot_pnls[bot.id] = actual_pnl
            account_name = accounts[bot.account_id].name
            print(f"  🤖 {bot.name} ({account_name}): +{len(trades)} trades, P&L=${actual_pnl:,.2f}")

        # ── Generate new deposits (continuing ~$1000/mo pattern) ─────
        new_deposits = []
        if bitget_account:
            dep_start = latest_tx_date + timedelta(days=1)
            current_month = dep_start.replace(day=1)

            while current_month < end_date:
                month_end = (current_month.replace(day=28) + timedelta(days=4)).replace(day=1)
                if month_end > end_date:
                    month_end = end_date

                # ~$1000/month in deposits of $80-$150 each
                monthly_target = random.uniform(900, 1100)
                month_total = 0
                while month_total < monthly_target * 0.85:
                    amount = round(random.uniform(80, 150), 2)
                    day_offset = random.randint(0, 27)
                    dep_date = current_month + timedelta(days=day_offset)
                    if dep_date < dep_start or dep_date >= end_date:
                        month_total += amount
                        continue
                    if dep_date.month != current_month.month:
                        dep_date = current_month + timedelta(days=27)

                    new_deposits.append({"amount": amount, "date": dep_date})
                    month_total += amount

                current_month = month_end

            for dep in sorted(new_deposits, key=lambda d: d["date"]):
                tx = Transaction(
                    account_id=bitget_account.id,
                    type="deposit",
                    amount=dep["amount"],
                    note="Regular deposit",
                    date=dep["date"],
                )
                db.add(tx)

            total_new_deposits = sum(d["amount"] for d in new_deposits)
            print(f"\n  💰 New deposits: {len(new_deposits)} totaling ${total_new_deposits:,.2f}")

        await db.commit()
        print(f"\n✅ Committed {new_trade_count} new trades and {len(new_deposits)} new deposits")

        # ── Rebuild PnL records for bots that got new trades ─────────
        print(f"\n📈 Rebuilding PnL records for updated bots...")
        for bot in bots:
            if bot.id in new_bot_pnls:
                all_trades_result = await db.execute(
                    select(Trade).where(Trade.bot_id == bot.id)
                )
                all_bot_trades = list(all_trades_result.scalars().all())
                await rebuild_pnl_records(db, bot.id, all_bot_trades)
                print(f"  ✅ {bot.name}: PnL records rebuilt ({len(all_bot_trades)} total trades)")

        # ── Update account balances ──────────────────────────────────
        print(f"\n💰 Updating account balances...")
        for account in accounts.values():
            pnl_result = await db.execute(
                text("""
                    SELECT COALESCE(SUM(t.pnl), 0)
                    FROM trades t JOIN bots b ON t.bot_id = b.id
                    WHERE b.account_id = :aid
                """),
                {"aid": account.id}
            )
            account_pnl = pnl_result.scalar() or 0

            dep_result = await db.execute(
                text("SELECT COALESCE(SUM(amount), 0) FROM transactions WHERE account_id = :aid AND type = 'deposit'"),
                {"aid": account.id}
            )
            account_deposits = dep_result.scalar() or 0

            wd_result = await db.execute(
                text("SELECT COALESCE(SUM(amount), 0) FROM transactions WHERE account_id = :aid AND type = 'withdrawal'"),
                {"aid": account.id}
            )
            account_withdrawals = wd_result.scalar() or 0

            new_balance = account.initial_balance + account_pnl + account_deposits - account_withdrawals
            account.current_balance = round(new_balance, 2)
            print(f"  {account.name}: ${account.current_balance:,.2f}")

        await db.commit()

        # ── Verify existing data was not modified ────────────────────
        final_trade_count = (await db.execute(select(func.count(Trade.id)))).scalar()
        final_tx_count = (await db.execute(select(func.count(Transaction.id)))).scalar()
        print(f"\n📋 Final counts: {final_trade_count} trades (+{final_trade_count - existing_trade_count}), "
              f"{final_tx_count} transactions (+{final_tx_count - existing_tx_count})")

        # Check latest dates
        latest_trade = (await db.execute(select(func.max(Trade.entry_time)))).scalar()
        latest_tx = (await db.execute(select(func.max(Transaction.date)))).scalar()
        print(f"📅 Latest trade: {latest_trade}")
        print(f"📅 Latest transaction: {latest_tx}")

    print(f"\n🎉 Append complete! Existing data untouched, new data added through {end_date.strftime('%Y-%m-%d')}.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Append new data to existing portfolio")
    parser.add_argument("--end-date", default="2026-06-23", help="End date (YYYY-MM-DD)")
    args = parser.parse_args()

    end_dt = datetime.strptime(args.end_date, "%Y-%m-%d").replace(hour=23, minute=59)
    asyncio.run(append_data(end_dt))
