"""Checks for the statistics engine: drawdown, flows, fees, outliers, day/week extremes.

Run with `poetry run python scripts/verify_stats_metrics.py` (the project has no
pytest dependency). Uses in-memory objects only -- it never touches the database.
"""
import sys
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.models.portfolio import Trade, Transaction  # noqa: E402
from app.services.calculation_engine import calculate_stats_from_trades  # noqa: E402

BASE = datetime(2025, 1, 6)  # a Monday, so ISO weeks line up with calendar weeks

failures: list[str] = []


def check(label: str, actual, expected) -> None:
    if actual != expected:
        failures.append(f"{label}: expected {expected}, got {actual}")


def trade(day: int, pnl: float, fee: float = 0.0, hour: int = 12) -> Trade:
    entry = BASE + timedelta(days=day, hours=hour)
    return Trade(
        symbol="BTC/USDT",
        direction="long",
        status="closed",
        entry_price=100.0,
        exit_price=100.0 + pnl,
        quantity=1.0,
        leverage=1.0,
        pnl=pnl,
        pnl_percent=pnl,
        fee=fee,
        entry_time=entry,
        exit_time=entry + timedelta(hours=1),
    )


def tx(day: int, amount: float, kind: str) -> Transaction:
    return Transaction(type=kind, amount=amount, date=BASE + timedelta(days=day, hours=6))


def test_empty() -> None:
    s = calculate_stats_from_trades([], 1000.0)
    check("empty total_trades", s["total_trades"], 0)
    check("empty max_drawdown", s["max_drawdown"], 0.0)
    check("empty best_day", s["best_day"], None)


def test_chronological_drawdown() -> None:
    """Trades arrive grouped by bot; drawdown must still follow real time order."""
    bot_a = [trade(0, 500.0), trade(4, 500.0)]
    bot_b = [trade(1, -300.0), trade(2, -100.0), trade(3, 200.0)]
    s = calculate_stats_from_trades(bot_a + bot_b, 1000.0)
    # Real path: 1000, 1500, 1200, 1100, 1300, 1800 -> trough 1100 off peak 1500.
    check("chronological dd amount", s["max_drawdown"], 400.0)
    check("chronological dd percent", s["max_drawdown_percent"], 26.67)
    check("chronological dd date", s["max_drawdown_date"], "2025-01-08")
    check("trading balance", s["trading_balance"], 1800.0)


def test_percent_first_beats_larger_dollar_dip() -> None:
    """A shallower but larger dip must not beat a deeper percentage one."""
    trades = [trade(0, -3000.0), trade(1, 10_000.0), trade(2, -4000.0)]
    s = calculate_stats_from_trades(trades, 10_000.0)
    # 30% off 10,000 vs 23.5% off 17,000 -- the $4,000 dip is bigger in dollars.
    check("percent-first dd percent", s["max_drawdown_percent"], 30.0)
    check("percent-first dd amount", s["max_drawdown"], 3000.0)


def test_early_low_equity_dip_does_not_win() -> None:
    """A dip that was only huge in percent because the account was tiny is skipped."""
    trades = [trade(0, -700.0), trade(1, 70_000.0), trade(2, -20_000.0)]
    s = calculate_stats_from_trades(trades, 2000.0)
    # 35% off 2,000 is nominally deeper than 28.2% off 71,300, but $700 is under
    # 2% of the 71,300 the account went on to reach.
    check("low-equity dd amount", s["max_drawdown"], 20_000.0)
    check("low-equity dd percent", s["max_drawdown_percent"], 28.05)


def test_minimum_amount_filters_small_dips() -> None:
    trades = [trade(0, -50.0), trade(1, 5000.0), trade(2, -500.0)]
    s = calculate_stats_from_trades(trades, 100.0, min_drawdown_amount=100.0)
    check("min-amount dd amount", s["max_drawdown"], 500.0)
    check("min-amount dd percent", s["max_drawdown_percent"], 9.9)


def test_zero_initial_balance_does_not_divide_by_zero() -> None:
    s = calculate_stats_from_trades([trade(0, 100.0), trade(1, -40.0)], 0.0)
    check("zero-balance calmar", s["calmar_ratio"], 0.0)
    check("zero-balance roi", s["roi_percent"], 0.0)
    check("zero-balance net pnl", s["net_pnl"], 60.0)


def test_minimum_amount_fallback() -> None:
    """When every dip is under the floor, report the largest one anyway."""
    s = calculate_stats_from_trades([trade(0, -20.0)], 1000.0, min_drawdown_amount=100.0)
    check("fallback dd amount", s["max_drawdown"], 20.0)
    check("fallback dd percent", s["max_drawdown_percent"], 2.0)


def test_flows_change_only_the_flow_drawdown() -> None:
    trades = [trade(0, 500.0), trade(3, -200.0)]
    transactions = [tx(1, 1000.0, "deposit"), tx(2, 900.0, "withdrawal")]
    s = calculate_stats_from_trades(trades, 1000.0, transactions)
    # Trading only: 1000, 1500, 1300 -> 200 off 1500 (over 2% of the 1500 peak).
    check("trading dd amount", s["max_drawdown"], 200.0)
    check("trading dd percent", s["max_drawdown_percent"], 13.33)
    # With flows: 1500, 2500, 1600, 1400 -> 1100 off 2500.
    check("flow dd amount", s["max_drawdown_flows"], 1100.0)
    check("flow dd percent", s["max_drawdown_flows_percent"], 44.0)
    check("deposits", s["total_deposits"], 1000.0)
    check("withdrawals", s["total_withdrawals"], 900.0)
    check("net flows", s["net_flows"], 100.0)


def test_flows_before_and_after_trades() -> None:
    trades = [trade(5, 100.0)]
    transactions = [tx(0, 500.0, "deposit"), tx(20, 200.0, "withdrawal")]
    s = calculate_stats_from_trades(trades, 1000.0, transactions)
    check("flow balance", s["current_balance"], 1400.0)
    check("flow trading balance", s["trading_balance"], 1100.0)
    # Only the trailing withdrawal pulls equity off its 1600 peak.
    check("late-withdrawal dd", s["max_drawdown_flows"], 200.0)


def test_fee_and_flow_variants() -> None:
    trades = [trade(0, 300.0, fee=10.0), trade(1, -100.0, fee=5.0)]
    transactions = [tx(2, 400.0, "deposit"), tx(3, 100.0, "withdrawal")]
    s = calculate_stats_from_trades(trades, 1000.0, transactions)
    check("net pnl", s["net_pnl"], 200.0)
    check("total fees", s["total_fees"], 15.0)
    check("gross pnl", s["gross_pnl"], 215.0)
    check("gross equals total_pnl", s["total_pnl"], s["gross_pnl"])
    check("gross with flows", s["gross_pnl_with_flows"], 515.0)
    check("net with flows", s["net_pnl_with_flows"], 500.0)
    check("balance", s["current_balance"], 1500.0)


def test_roi_uses_deployed_capital() -> None:
    trades = [trade(0, 500.0)]
    s = calculate_stats_from_trades(trades, 1000.0, [tx(1, 1000.0, "deposit")])
    check("roi on deployed capital", s["roi_percent"], 25.0)
    check("roi on initial", s["roi_on_initial_percent"], 50.0)


def test_outlier_trade_filtering() -> None:
    trades = [trade(i % 30, 100.0 if i % 2 else -80.0) for i in range(60)]
    trades.append(trade(29, 50_000.0))
    s = calculate_stats_from_trades(trades, 1000.0)
    check("outlier count", s["outlier_trade_count"], 1)
    check("best trade excludes outlier", s["best_trade"], 100.0)
    check("raw best trade", s["best_trade_raw"], 50_000.0)
    check("worst trade", s["worst_trade"], -80.0)
    check("outlier still in totals", s["net_pnl"], round(sum(t.pnl for t in trades), 2))


def test_no_outliers_in_ordinary_data() -> None:
    trades = [trade(i % 30, 100.0 if i % 2 else -80.0) for i in range(60)]
    s = calculate_stats_from_trades(trades, 1000.0)
    check("no outliers flagged", s["outlier_trade_count"], 0)
    check("best trade", s["best_trade"], 100.0)


def test_small_sample_flags_nothing() -> None:
    trades = [trade(0, 10.0), trade(1, 9_000.0)]
    s = calculate_stats_from_trades(trades, 1000.0)
    check("small sample outliers", s["outlier_trade_count"], 0)
    check("small sample best", s["best_trade"], 9_000.0)


def test_day_and_week_extremes() -> None:
    trades = [
        trade(0, 100.0), trade(0, 50.0),      # Mon w1: +150
        trade(2, -400.0),                     # Wed w1: -400 -> week1 -250
        trade(7, 900.0),                      # Mon w2: +900
        trade(9, -100.0),                     # Wed w2: -100 -> week2 +800
    ]
    s = calculate_stats_from_trades(trades, 1000.0)
    check("best day pnl", s["best_day_pnl"], 900.0)
    check("best day", s["best_day"], "2025-01-13")
    check("worst day pnl", s["worst_day_pnl"], -400.0)
    check("worst day", s["worst_day"], "2025-01-08")
    check("best week pnl", s["best_week_pnl"], 800.0)
    check("best week", s["best_week"], "2025-W03")
    check("worst week pnl", s["worst_week_pnl"], -250.0)
    check("worst week", s["worst_week"], "2025-W02")


def test_open_trades_use_entry_time() -> None:
    open_trade = trade(3, -300.0)
    open_trade.exit_time = None
    open_trade.status = "open"
    s = calculate_stats_from_trades([trade(0, 500.0), open_trade], 1000.0)
    check("open trade day", s["worst_day"], "2025-01-09")
    check("open trade dd", s["max_drawdown"], 300.0)


def main() -> int:
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
    if failures:
        print(f"FAILED ({len(failures)}):")
        for f in failures:
            print("  -", f)
        return 1
    print("all statistics checks passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
