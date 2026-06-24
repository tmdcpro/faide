"""
Re-generate trades from June 13-22, 2026 with specific parameters:
- Total net profit ~$20 over the 10-day period
- 2 days with zero trading activity
- All data before June 13 stays EXACTLY as-is
"""
import asyncio
import random
from datetime import datetime, timedelta
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import select, func, text, delete
from app.database import engine, async_session, Base
from app.models.portfolio import Portfolio, Account, Bot, Trade, PnlRecord, Transaction
from app.services.calculation_engine import rebuild_pnl_records

random.seed(20260622)

# ─── Price helpers ────────────────────────────────────────────────

BTC_PRICES = {
    datetime(2024, 5, 1): 58000, datetime(2024, 7, 1): 62000,
    datetime(2024, 9, 1): 57000, datetime(2024, 11, 1): 73000,
    datetime(2025, 1, 1): 95000, datetime(2025, 3, 1): 85000,
    datetime(2025, 5, 1): 97000, datetime(2025, 7, 1): 100000,
    datetime(2025, 9, 1): 85000, datetime(2025, 11, 1): 90000,
    datetime(2026, 1, 1): 100000, datetime(2026, 3, 1): 85000,
    datetime(2026, 5, 1): 103000, datetime(2026, 7, 1): 108000,
}

def get_btc_price(dt: datetime) -> float:
    dates = sorted(BTC_PRICES.keys())
    if dt <= dates[0]: return BTC_PRICES[dates[0]]
    if dt >= dates[-1]: return BTC_PRICES[dates[-1]]
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

STRATEGY_PARAMS = {
    "grid": {"win_rate": 0.50, "trades_per_day": 1.0, "leverage_range": (2, 8)},
    "scalping": {"win_rate": 0.48, "trades_per_day": 2.5, "leverage_range": (3, 10)},
    "dca": {"win_rate": 0.55, "trades_per_day": 0.3, "leverage_range": (1, 3)},
    "swing": {"win_rate": 0.45, "trades_per_day": 0.15, "leverage_range": (2, 5)},
    "trend_following": {"win_rate": 0.42, "trades_per_day": 0.2, "leverage_range": (2, 6)},
    "mean_reversion": {"win_rate": 0.50, "trades_per_day": 0.6, "leverage_range": (2, 7)},
    "arbitrage": {"win_rate": 0.55, "trades_per_day": 1.2, "leverage_range": (1, 4)},
}

# 2 zero-activity days: June 15 (Sunday) and June 19 (Thursday)
ZERO_DAYS = {datetime(2026, 6, 15).date(), datetime(2026, 6, 19).date()}

START_DATE = datetime(2026, 6, 13, 0, 0, 0)
END_DATE = datetime(2026, 6, 22, 23, 59, 59)
TARGET_NET_PNL = 20.0  # ~$20 total net profit over the period


def generate_trades_for_bot(
    bot_symbols: list[str],
    strategy: str,
    target_pnl: float,
) -> list[dict]:
    params = STRATEGY_PARAMS.get(strategy, STRATEGY_PARAMS["grid"])

    # Generate trades spread across 8 active days (10 days minus 2 zero days)
    active_days = []
    current = START_DATE
    while current.date() <= END_DATE.date():
        if current.date() not in ZERO_DAYS:
            active_days.append(current)
        current += timedelta(days=1)

    total_active_days = len(active_days)
    num_trades = max(2, int(total_active_days * params["trades_per_day"] * random.uniform(0.6, 1.2)))
    win_rate = params["win_rate"] + random.uniform(-0.08, 0.08)
    num_wins = int(num_trades * win_rate)
    num_losses = num_trades - num_wins

    # Small P&L magnitudes since target is only ~$20 total across all bots
    avg_magnitude = max(abs(target_pnl) / max(num_trades, 1) * 3, 1.0)

    win_flags = [True] * num_wins + [False] * num_losses
    random.shuffle(win_flags)

    trades = []
    for i in range(num_trades):
        is_win = win_flags[i]
        symbol = random.choice(bot_symbols)

        # Pick a random active day
        trade_day = random.choice(active_days)
        trade_dt = trade_day + timedelta(hours=random.randint(1, 22), minutes=random.randint(0, 59))

        base_price = get_price_for_symbol(symbol, trade_dt)

        if is_win:
            pnl = abs(random.gauss(avg_magnitude, avg_magnitude * 0.6))
            pnl = max(0.10, pnl)
        else:
            pnl = -abs(random.gauss(avg_magnitude, avg_magnitude * 0.6))
            pnl = min(-0.10, pnl)

        direction = random.choice(["long", "short"])
        leverage = round(random.uniform(*params["leverage_range"]), 1)
        quantity = round(random.uniform(0.01, 0.2), 4)
        if base_price * quantity < 1:
            quantity = round(1.0 / base_price, 4)

        if direction == "long":
            exit_price = base_price + pnl / max(quantity, 0.0001)
        else:
            exit_price = base_price - pnl / max(quantity, 0.0001)
        exit_price = max(0.01, exit_price)

        fee = round(abs(pnl) * random.uniform(0.001, 0.005), 2)
        fee = max(0.01, fee)

        duration_hours = random.randint(1, 36)
        exit_time = trade_dt + timedelta(hours=duration_hours)
        if exit_time > END_DATE:
            exit_time = END_DATE - timedelta(hours=random.randint(1, 4))
        # Ensure exit_time does NOT fall on a zero-activity day
        while exit_time.date() in ZERO_DAYS:
            exit_time -= timedelta(hours=random.randint(1, 6))

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
            "entry_time": trade_dt,
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


async def regen_last_10_days():
    print("=" * 60)
    print("RE-GENERATING June 13-22, 2026")
    print(f"Target: ~${TARGET_NET_PNL} net profit, 2 zero-activity days")
    print("=" * 60)

    async with async_session() as db:
        # ── Snapshot pre-June 13 data for verification ────────────────
        pre_trade_count = (await db.execute(
            select(func.count(Trade.id)).where(Trade.entry_time < START_DATE)
        )).scalar()
        pre_tx_count = (await db.execute(
            select(func.count(Transaction.id)).where(Transaction.date < START_DATE)
        )).scalar()
        pre_pnl = (await db.execute(
            select(func.sum(Trade.pnl)).where(Trade.entry_time < START_DATE)
        )).scalar() or 0

        print(f"\nPre-June 13 baseline: {pre_trade_count} trades, {pre_tx_count} txns, PnL=${pre_pnl:,.2f}")

        # ── Delete ALL trades and transactions from June 13 onward ────
        del_trades = await db.execute(
            delete(Trade).where(Trade.entry_time >= START_DATE)
        )
        del_txns = await db.execute(
            delete(Transaction).where(Transaction.date >= START_DATE)
        )
        # Delete PnL records for dates in the window too
        del_pnl = await db.execute(
            delete(PnlRecord).where(PnlRecord.date >= START_DATE.date())
        )
        await db.flush()
        print(f"Deleted: {del_trades.rowcount} trades, {del_txns.rowcount} txns, {del_pnl.rowcount} PnL records from June 13+")

        # ── Get all bots ──────────────────────────────────────────────
        bots = list((await db.execute(select(Bot))).scalars().all())
        accounts = {a.id: a for a in (await db.execute(select(Account))).scalars().all()}

        # ── Distribute ~$20 across bots ───────────────────────────────
        # Some bots positive, some negative, net = ~$20
        # Bitget bots get more weight
        bot_targets = {}
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
            if bot.strategy_type in ("scalping", "grid", "arbitrage"):
                weight *= 1.2
            bot_weights.append(weight)

        total_weight = sum(bot_weights)

        # Create a mix: some bots slightly positive, some slightly negative, net ~$20
        # First assign random per-bot PnL, then adjust to hit $20
        raw_targets = []
        for i, bot in enumerate(bots):
            w = bot_weights[i] / total_weight
            # Random direction per bot: some up, some down
            if random.random() < 0.55:
                raw_targets.append(random.uniform(2, 15) * w * len(bots))
            else:
                raw_targets.append(random.uniform(-12, -2) * w * len(bots))

        # Scale to hit exactly $20
        raw_sum = sum(raw_targets)
        if abs(raw_sum) > 0.01:
            # Add adjustment evenly
            adj = (TARGET_NET_PNL - raw_sum) / len(raw_targets)
            raw_targets = [t + adj for t in raw_targets]

        for i, bot in enumerate(bots):
            bot_targets[bot.id] = round(raw_targets[i], 2)

        # Fine-tune: adjust last bot to make sum exactly $20
        current_sum = sum(bot_targets.values())
        last_bot_id = bots[-1].id
        bot_targets[last_bot_id] = round(bot_targets[last_bot_id] + (TARGET_NET_PNL - current_sum), 2)

        print(f"\nBot PnL targets (sum=${sum(bot_targets.values()):.2f}):")
        for bot in bots:
            print(f"  {bot.name}: ${bot_targets[bot.id]:+.2f}")

        # ── Generate new trades for each bot ──────────────────────────
        new_trade_count = 0
        actual_bot_pnls = {}
        for bot in bots:
            symbols = bot.symbols if bot.symbols else [bot.symbol] if bot.symbol else ["BTC/USDT"]
            trades = generate_trades_for_bot(
                bot_symbols=symbols,
                strategy=bot.strategy_type or "grid",
                target_pnl=bot_targets[bot.id],
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
            actual_bot_pnls[bot.id] = actual_pnl
            account_name = accounts[bot.account_id].name
            print(f"  {bot.name} ({account_name}): {len(trades)} trades, PnL=${actual_pnl:+.2f}")

        total_new_pnl = sum(actual_bot_pnls.values())
        print(f"\nTotal new trades: {new_trade_count}, Total new PnL: ${total_new_pnl:.2f}")

        await db.commit()

        # ── Rebuild PnL records for all bots ──────────────────────────
        print("\nRebuilding PnL records...")
        for bot in bots:
            all_trades_result = await db.execute(
                select(Trade).where(Trade.bot_id == bot.id)
            )
            all_bot_trades = list(all_trades_result.scalars().all())
            await rebuild_pnl_records(db, bot.id, all_bot_trades)

        # ── Update account balances ───────────────────────────────────
        print("Updating account balances...")
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

        # ── Verify pre-June 13 data unchanged ─────────────────────────
        post_pre_count = (await db.execute(
            select(func.count(Trade.id)).where(Trade.entry_time < START_DATE)
        )).scalar()
        post_pre_pnl = (await db.execute(
            select(func.sum(Trade.pnl)).where(Trade.entry_time < START_DATE)
        )).scalar() or 0

        assert post_pre_count == pre_trade_count, f"Pre-June 13 trade count changed! {pre_trade_count} -> {post_pre_count}"
        assert abs(post_pre_pnl - pre_pnl) < 0.01, f"Pre-June 13 PnL changed! {pre_pnl} -> {post_pre_pnl}"
        print(f"\nVerified: Pre-June 13 data unchanged ({post_pre_count} trades, PnL=${post_pre_pnl:,.2f})")

        # ── Verify zero-activity days ─────────────────────────────────
        for zd in ZERO_DAYS:
            zd_start = datetime.combine(zd, datetime.min.time())
            zd_end = zd_start + timedelta(days=1)
            zd_count = (await db.execute(
                select(func.count(Trade.id)).where(
                    Trade.entry_time >= zd_start, Trade.entry_time < zd_end
                )
            )).scalar()
            print(f"  Zero-activity day {zd}: {zd_count} trades (should be 0)")

        # ── Final stats ───────────────────────────────────────────────
        final_count = (await db.execute(select(func.count(Trade.id)))).scalar()
        final_pnl = (await db.execute(select(func.sum(Trade.pnl)))).scalar() or 0
        print(f"\nFinal: {final_count} total trades, Total PnL=${final_pnl:,.2f}")
        print(f"June 13-22 net PnL: ${total_new_pnl:.2f}")

        # Check date range
        last_trade = (await db.execute(select(func.max(Trade.entry_time)))).scalar()
        print(f"Last trade: {last_trade}")

    print("\nDone!")


if __name__ == "__main__":
    asyncio.run(regen_last_10_days())
