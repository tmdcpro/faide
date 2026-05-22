"""
Generate a realistic simulated portfolio for Faide Trader.

Timeline: May 14, 2024 → May 20, 2026
Starting: $960.14 in Bitget Futures
Ending: $67,304.20 total portfolio balance

Accounts:
- Bitget Futures (primary, from day 1)
- Phemex Futures (added ~Sep 2024)
- Kraken (added ~Mar 2025)

Deposits: ~$300/mo early → ~$1000/mo late, individual amounts ~$110 ($80-$150)
Withdrawals: 9x $500 during Aug 2025 - May 15, 2026

Bots progressively added over time.
"""
import asyncio
import random
import math
from datetime import datetime, timedelta
from pathlib import Path
import sys

# Add parent to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import text
from app.database import engine, async_session, Base
from app.models.portfolio import (
    Portfolio, Account, Bot, Trade, PnlRecord, Transaction,
)


random.seed(42)

# ─── Configuration ──────────────────────────────────────────────────

START_DATE = datetime(2024, 5, 14)
END_DATE = datetime(2026, 5, 20)
INITIAL_BALANCE = 960.14
TARGET_FINAL_BALANCE = 67304.20

SYMBOLS = {
    "bitget_futures": ["BTC/USDT", "ETH/USDT", "SOL/USDT", "XRP/USDT", "DOGE/USDT", "AVAX/USDT", "LINK/USDT"],
    "phemex_futures": ["BTC/USDT", "ETH/USDT", "SOL/USDT", "ARB/USDT"],
    "kraken": ["BTC/USD", "ETH/USD", "SOL/USD"],
}

STRATEGY_TYPES = ["grid", "dca", "scalping", "swing", "trend_following", "mean_reversion"]

# Rough BTC price timeline for realism
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
}

def get_btc_price(dt: datetime) -> float:
    """Interpolate BTC price for a given date."""
    dates = sorted(BTC_PRICES.keys())
    if dt <= dates[0]:
        return BTC_PRICES[dates[0]]
    if dt >= dates[-1]:
        return BTC_PRICES[dates[-1]]
    for i in range(len(dates) - 1):
        if dates[i] <= dt < dates[i + 1]:
            ratio = (dt - dates[i]).total_seconds() / (dates[i + 1] - dates[i]).total_seconds()
            return BTC_PRICES[dates[i]] + ratio * (BTC_PRICES[dates[i + 1]] - BTC_PRICES[dates[i]])
    return 60000

def get_price_for_symbol(symbol: str, dt: datetime) -> float:
    """Get a realistic base price for any symbol at a given date."""
    btc = get_btc_price(dt)
    ratios = {
        "BTC": 1.0, "ETH": 0.038, "SOL": 0.0018, "XRP": 0.000008,
        "DOGE": 0.0000025, "AVAX": 0.0005, "LINK": 0.00022, "ARB": 0.000015,
    }
    base = symbol.split("/")[0]
    ratio = ratios.get(base, 0.001)
    return btc * ratio * random.uniform(0.95, 1.05)


# ─── Deposit Schedule ───────────────────────────────────────────────

def generate_deposits() -> list[dict]:
    """Generate deposit schedule: ~$300/mo early → ~$1000/mo late, individual ~$110."""
    deposits = []
    current = START_DATE + timedelta(days=random.randint(1, 5))

    total_months = (END_DATE.year - START_DATE.year) * 12 + (END_DATE.month - START_DATE.month)

    while current < END_DATE:
        month_idx = (current.year - START_DATE.year) * 12 + (current.month - START_DATE.month)
        progress = month_idx / max(total_months, 1)

        # Monthly target: $300 → $1000 linearly
        monthly_target = 300 + progress * 700

        # Generate individual deposits for this month
        month_total = 0
        month_deposits = []
        while month_total < monthly_target * 0.85:
            amount = random.uniform(80, 150)
            amount = round(amount, 2)
            # Random day within the month
            day_offset = random.randint(0, 28)
            dep_date = current.replace(day=1) + timedelta(days=day_offset)
            if dep_date.month != current.month:
                dep_date = current.replace(day=28)
            if dep_date >= END_DATE:
                break
            month_deposits.append({"amount": amount, "date": dep_date})
            month_total += amount

        deposits.extend(month_deposits)

        # Move to next month
        if current.month == 12:
            current = current.replace(year=current.year + 1, month=1, day=1)
        else:
            current = current.replace(month=current.month + 1, day=1)

    return sorted(deposits, key=lambda d: d["date"])


def generate_withdrawals() -> list[dict]:
    """Generate 9x $500 withdrawals during Aug 2025 - May 15, 2026."""
    withdrawals = []
    start = datetime(2025, 8, 1)
    end = datetime(2026, 5, 15)
    total_days = (end - start).days

    for _ in range(9):
        day_offset = random.randint(0, total_days)
        w_date = start + timedelta(days=day_offset)
        withdrawals.append({"amount": 500.0, "date": w_date})

    return sorted(withdrawals, key=lambda d: d["date"])


# ─── Bot Timeline ───────────────────────────────────────────────────

BOT_TIMELINE = [
    # (start_date, account_exchange, bot_name, strategy, symbols)
    (datetime(2024, 5, 14), "bitget_futures", "BTC Grid Alpha", "grid", ["BTC/USDT"]),
    (datetime(2024, 6, 20), "bitget_futures", "ETH Scalper", "scalping", ["ETH/USDT"]),
    (datetime(2024, 8, 5), "bitget_futures", "SOL DCA", "dca", ["SOL/USDT"]),
    (datetime(2024, 9, 15), "phemex_futures", "BTC Swing", "swing", ["BTC/USDT"]),
    (datetime(2024, 10, 1), "bitget_futures", "Multi Trend", "trend_following", ["BTC/USDT", "ETH/USDT", "SOL/USDT"]),
    (datetime(2024, 11, 20), "phemex_futures", "ETH ARB Hunter", "arbitrage", ["ETH/USDT", "ARB/USDT"]),
    (datetime(2025, 1, 10), "bitget_futures", "DOGE Moon", "grid", ["DOGE/USDT"]),
    (datetime(2025, 2, 15), "bitget_futures", "XRP Reversion", "mean_reversion", ["XRP/USDT"]),
    (datetime(2025, 3, 1), "kraken", "BTC Accumulator", "dca", ["BTC/USD"]),
    (datetime(2025, 4, 10), "bitget_futures", "AVAX Grid", "grid", ["AVAX/USDT"]),
    (datetime(2025, 5, 20), "phemex_futures", "SOL Momentum", "trend_following", ["SOL/USDT"]),
    (datetime(2025, 7, 1), "kraken", "ETH Stacker", "dca", ["ETH/USD"]),
    (datetime(2025, 8, 15), "bitget_futures", "LINK Swing", "swing", ["LINK/USDT"]),
    (datetime(2025, 10, 1), "bitget_futures", "Multi Scalper V2", "scalping", ["BTC/USDT", "ETH/USDT"]),
    (datetime(2025, 12, 1), "kraken", "SOL DCA Kraken", "dca", ["SOL/USD"]),
    (datetime(2026, 1, 15), "bitget_futures", "BTC Grid V2", "grid", ["BTC/USDT"]),
    (datetime(2026, 3, 1), "phemex_futures", "Altcoin Momentum", "trend_following", ["BTC/USDT", "ETH/USDT", "SOL/USDT"]),
]

ACCOUNT_TIMELINE = [
    (datetime(2024, 5, 14), "bitget_futures", "Bitget Futures Main"),
    (datetime(2024, 9, 10), "phemex_futures", "Phemex Trading"),
    (datetime(2025, 2, 25), "kraken", "Kraken Spot & Futures"),
]


# ─── Trade Generation ───────────────────────────────────────────────

def generate_trades_for_bot(
    bot_start: datetime,
    bot_end: datetime,
    symbols: list[str],
    strategy: str,
    target_pnl: float,
    trades_per_month: float = 12,
) -> list[dict]:
    """Generate realistic trades for a bot between start and end dates."""
    trades = []
    total_days = (bot_end - bot_start).days
    if total_days <= 0:
        return trades

    total_months = total_days / 30.0
    num_trades = max(3, int(total_months * trades_per_month * random.uniform(0.7, 1.3)))

    # Strategy-specific parameters
    strategy_params = {
        "grid": {"win_rate": 0.62, "avg_win_ratio": 1.0, "trades_mult": 1.5, "leverage_range": (2, 8)},
        "scalping": {"win_rate": 0.58, "avg_win_ratio": 0.8, "trades_mult": 3.0, "leverage_range": (3, 10)},
        "dca": {"win_rate": 0.65, "avg_win_ratio": 1.2, "trades_mult": 0.5, "leverage_range": (1, 3)},
        "swing": {"win_rate": 0.52, "avg_win_ratio": 1.8, "trades_mult": 0.3, "leverage_range": (2, 5)},
        "trend_following": {"win_rate": 0.48, "avg_win_ratio": 2.0, "trades_mult": 0.4, "leverage_range": (2, 6)},
        "mean_reversion": {"win_rate": 0.60, "avg_win_ratio": 1.1, "trades_mult": 1.0, "leverage_range": (2, 7)},
        "arbitrage": {"win_rate": 0.70, "avg_win_ratio": 0.5, "trades_mult": 2.0, "leverage_range": (1, 4)},
    }
    params = strategy_params.get(strategy, strategy_params["grid"])
    num_trades = max(3, int(num_trades * params["trades_mult"]))

    win_rate = params["win_rate"] + random.uniform(-0.05, 0.05)
    num_wins = int(num_trades * win_rate)
    num_losses = num_trades - num_wins

    # Distribute target P&L
    if num_wins > 0 and num_losses > 0:
        avg_win_ratio = params["avg_win_ratio"]
        # target_pnl = num_wins * avg_win - num_losses * avg_loss
        # avg_win = avg_win_ratio * avg_loss
        # target_pnl = num_wins * avg_win_ratio * avg_loss - num_losses * avg_loss
        # avg_loss = target_pnl / (num_wins * avg_win_ratio - num_losses)
        denom = num_wins * avg_win_ratio - num_losses
        if abs(denom) < 0.01:
            denom = 1.0
        avg_loss = abs(target_pnl / denom)
        avg_win = avg_loss * avg_win_ratio
    else:
        avg_win = abs(target_pnl) / max(num_trades, 1)
        avg_loss = avg_win * 0.5

    # Create shuffled win/loss flags so wins are spread across the timeline
    win_flags = [True] * num_wins + [False] * num_losses
    random.shuffle(win_flags)

    running_pnl = 0.0
    for i in range(num_trades):
        is_win = win_flags[i]
        symbol = random.choice(symbols)
        base_price = get_price_for_symbol(symbol, bot_start + timedelta(days=int(total_days * i / num_trades)))

        if is_win:
            pnl = avg_win * random.uniform(0.2, 2.5)
        else:
            pnl = -avg_loss * random.uniform(0.2, 2.5)

        running_pnl += pnl

        direction = random.choice(["long", "short"])
        leverage = random.uniform(*params["leverage_range"])
        leverage = round(leverage, 1)

        # Calculate realistic entry/exit from pnl
        quantity = round(random.uniform(0.01, 0.3), 4)
        notional = base_price * quantity
        if notional < 1:
            quantity = round(1.0 / base_price, 4)

        if direction == "long":
            if pnl >= 0:
                exit_price = base_price + abs(pnl) / max(quantity, 0.0001)
            else:
                exit_price = base_price - abs(pnl) / max(quantity, 0.0001)
        else:
            if pnl >= 0:
                exit_price = base_price - abs(pnl) / max(quantity, 0.0001)
            else:
                exit_price = base_price + abs(pnl) / max(quantity, 0.0001)

        exit_price = max(0.01, exit_price)
        fee = round(abs(pnl) * random.uniform(0.001, 0.005), 2)
        fee = max(0.01, fee)

        # Random time within the bot's period
        trade_day = int(total_days * i / num_trades) + random.randint(0, max(1, total_days // num_trades))
        entry_time = bot_start + timedelta(days=min(trade_day, total_days - 1), hours=random.randint(0, 23), minutes=random.randint(0, 59))
        duration_hours = random.randint(1, 72)
        exit_time = entry_time + timedelta(hours=duration_hours)
        if exit_time > bot_end:
            exit_time = bot_end - timedelta(hours=random.randint(1, 12))

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
        actual_total = sum(t["pnl"] for t in trades)
        diff = target_pnl - actual_total
        trades[-1]["pnl"] = round(trades[-1]["pnl"] + diff, 2)
        # Recalculate exit price for last trade
        t = trades[-1]
        if t["direction"] == "long":
            t["exit_price"] = round(t["entry_price"] + t["pnl"] / max(t["quantity"], 0.0001), 2)
        else:
            t["exit_price"] = round(t["entry_price"] - t["pnl"] / max(t["quantity"], 0.0001), 2)
        t["exit_price"] = max(0.01, t["exit_price"])

    random.shuffle(trades)
    trades.sort(key=lambda t: t["entry_time"])
    return trades


# ─── Main Generation ────────────────────────────────────────────────

async def generate():
    print("🚀 Starting portfolio generation...")

    # Reset DB
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    print("✅ Database reset")

    deposits = generate_deposits()
    withdrawals = generate_withdrawals()

    total_deposits = sum(d["amount"] for d in deposits)
    total_withdrawals = sum(w["amount"] for w in withdrawals)
    print(f"📊 Deposits: {len(deposits)} totaling ${total_deposits:,.2f}")
    print(f"📊 Withdrawals: {len(withdrawals)} totaling ${total_withdrawals:,.2f}")

    # Target trading P&L = final_balance - initial_balance - deposits + withdrawals
    target_trading_pnl = TARGET_FINAL_BALANCE - INITIAL_BALANCE - total_deposits + total_withdrawals
    print(f"📊 Target trading P&L: ${target_trading_pnl:,.2f}")

    # Distribute P&L across bots (more to bitget, which is the main account)
    num_bots = len(BOT_TIMELINE)
    bot_weights = []
    for start, exchange, name, strategy, symbols in BOT_TIMELINE:
        months_active = (END_DATE - start).days / 30.0
        weight = months_active
        if exchange == "bitget_futures":
            weight *= 2.0  # Bitget gets more activity
        elif exchange == "phemex_futures":
            weight *= 0.8
        else:
            weight *= 0.5
        bot_weights.append(weight)

    total_weight = sum(bot_weights)
    bot_pnls = [(w / total_weight) * target_trading_pnl for w in bot_weights]

    print(f"\n📋 Bot P&L allocation:")
    for i, (start, exchange, name, strategy, symbols) in enumerate(BOT_TIMELINE):
        print(f"  {name} ({exchange}): ${bot_pnls[i]:,.2f}")

    async with async_session() as db:
        # Create portfolio
        portfolio = Portfolio(name="Trading Portfolio", description="Main algorithmic trading portfolio — May 2024 to present")
        db.add(portfolio)
        await db.flush()
        print(f"\n✅ Portfolio created: {portfolio.name} (id={portfolio.id})")

        # Create accounts
        account_map = {}  # exchange -> Account
        for acct_start, exchange, acct_name in ACCOUNT_TIMELINE:
            initial = INITIAL_BALANCE if exchange == "bitget_futures" else 0
            account = Account(
                portfolio_id=portfolio.id,
                name=acct_name,
                exchange=exchange,
                initial_balance=initial,
                current_balance=initial,
            )
            db.add(account)
            await db.flush()
            account_map[exchange] = account
            print(f"✅ Account: {acct_name} ({exchange}, id={account.id})")

        # Create bots and trades
        total_trades = 0
        for i, (bot_start, exchange, bot_name, strategy, bot_symbols) in enumerate(BOT_TIMELINE):
            account = account_map[exchange]
            bot = Bot(
                account_id=account.id,
                name=bot_name,
                strategy_type=strategy,
                symbol=bot_symbols[0],
                is_active=True,
            )
            bot.symbols = bot_symbols
            db.add(bot)
            await db.flush()

            # Generate trades
            trades = generate_trades_for_bot(
                bot_start=bot_start,
                bot_end=END_DATE,
                symbols=bot_symbols,
                strategy=strategy,
                target_pnl=bot_pnls[i],
            )

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

            total_trades += len(trades)
            actual_pnl = sum(t["pnl"] for t in trades)
            print(f"  🤖 {bot_name}: {len(trades)} trades, P&L=${actual_pnl:,.2f}")

        # Create deposits (all go to Bitget main)
        bitget_account = account_map["bitget_futures"]
        for dep in deposits:
            tx = Transaction(
                account_id=bitget_account.id,
                type="deposit",
                amount=dep["amount"],
                note="Regular deposit",
                date=dep["date"],
            )
            db.add(tx)

        # Create withdrawals (from Bitget main)
        for w in withdrawals:
            tx = Transaction(
                account_id=bitget_account.id,
                type="withdrawal",
                amount=w["amount"],
                note="Withdrawal",
                date=w["date"],
            )
            db.add(tx)

        await db.commit()

        # Now rebuild PnL records for each bot
        print(f"\n📈 Building PnL records...")
        from sqlalchemy import select as sa_select
        from app.services.calculation_engine import rebuild_pnl_records
        for i, (bot_start, exchange, bot_name, strategy, bot_symbols) in enumerate(BOT_TIMELINE):
            bot_id_result = await db.execute(
                text("SELECT id FROM bots WHERE name = :name"),
                {"name": bot_name}
            )
            bot_row = bot_id_result.first()
            if bot_row:
                trade_result = await db.execute(
                    sa_select(Trade).where(Trade.bot_id == bot_row[0])
                )
                bot_trades = list(trade_result.scalars().all())
                await rebuild_pnl_records(db, bot_row[0], bot_trades)
                print(f"  ✅ PnL records built for {bot_name}")

        # Update account balances
        for exchange, account in account_map.items():
            # Sum all bot P&L for this account
            pnl_result = await db.execute(
                text("""
                    SELECT COALESCE(SUM(t.pnl), 0)
                    FROM trades t
                    JOIN bots b ON t.bot_id = b.id
                    WHERE b.account_id = :aid
                """),
                {"aid": account.id}
            )
            account_pnl = pnl_result.scalar() or 0

            # Sum deposits/withdrawals
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
            print(f"  💰 {account.name}: balance=${account.current_balance:,.2f} (initial=${account.initial_balance:,.2f} + pnl=${account_pnl:,.2f} + deps=${account_deposits:,.2f} - wds=${account_withdrawals:,.2f})")

        await db.commit()

    print(f"\n🎉 Generation complete!")
    print(f"   Total trades: {total_trades}")
    print(f"   Bots: {len(BOT_TIMELINE)}")
    print(f"   Accounts: {len(ACCOUNT_TIMELINE)}")
    print(f"   Deposits: {len(deposits)}")
    print(f"   Withdrawals: {len(withdrawals)}")


if __name__ == "__main__":
    asyncio.run(generate())
