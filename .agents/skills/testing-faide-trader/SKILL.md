# Testing Faide Trader

This skill documents how to test the Faide Trader application locally.

## Devin Secrets Needed

No secrets required — the app runs fully locally with SQLite.

## Architecture

- **Backend**: FastAPI + SQLite (async via aiosqlite), runs on port 8000
- **Frontend**: React + TypeScript + Vite, runs on port 5173 (may vary)
- **Database**: SQLite file at `faide-trader/faide-trader-backend/faide_trader.db`
- No authentication required

## Starting Servers

### Fresh Database
Delete `faide_trader.db` before starting the backend for a clean test:
```bash
rm -f faide-trader/faide-trader-backend/faide_trader.db
```

### Backend
```bash
cd faide-trader/faide-trader-backend
poetry run fastapi dev app/main.py --port 8000
```

### Frontend
```bash
cd faide-trader/faide-trader-frontend
npm run dev
```
Note: The frontend port may vary (5173, 5174, etc.) — check the Vite output.

## UI Navigation

The app has a drill-down hierarchy:
1. **Portfolios** (home page) → click portfolio card
2. **Portfolio Detail** → shows accounts → click account card
3. **Account Detail** → shows bots → click bot card
4. **Bot Detail** → shows stats, per-symbol P&L, period P&L, trades

### Creating Test Data
1. Click "+ New Portfolio" → enter name → Create
2. Click into portfolio → "+ Add Account" → set exchange (Bitget Futures), name, initial balance ($10,000)
3. Click into account → "+ Add Bot" → enter name, select strategy, use SymbolSelector to pick symbols
4. Click into bot → "+ Add Trade" → fill in symbol, direction, entry/exit prices, quantity, leverage, fee

### Multi-Symbol Features
- **SymbolSelector**: Type to search symbols from the exchange. Click to select multiple. Blue tags show selected symbols.
- **Critical**: SymbolSelector buttons have `type="button"` — clicking a dropdown option must NOT submit the parent form. If the dialog closes when selecting a symbol, the fix is broken.
- **Per-Symbol P&L Breakdown**: Only appears on bot detail when the bot has trades across 2+ different symbols. May require page refresh after adding trades for a new symbol (known stale state issue).

### Market Data Import
- Click "Import Data" in the top nav bar
- Select exchange, use SymbolSelector to pick multiple symbols
- Set timeframe and max candles
- Button text updates to "Import N Symbols"
- Results show per-symbol candle counts

## Common Test Assertions

### P&L Calculation
For a long trade: `PnL = (exit_price - entry_price) * quantity * leverage - fee`
For a short trade: `PnL = (entry_price - exit_price) * quantity * leverage - fee`

Example: Long, entry $50,000, exit $52,000, qty 0.5, leverage 10, fee $5
→ PnL = (52000 - 50000) * 0.5 * 10 - 5 = **$9,995.00**

### Gross vs Net P&L
- `total_pnl` = gross (before fees) = net_pnl + total_fees
- `net_pnl` = actual money after fees = sum of trade.pnl values
- `current_balance` = initial_balance + net_pnl (NOT gross)

### Cascading Recalculation
When any value is edited, all dependent values should update:
- Edit a trade → bot stats recalculate → account stats recalculate → portfolio stats recalculate
- Edit a stat (e.g., Total P&L) → trades are proportionally redistributed

## Known Issues

- **Stale frontend state**: After editing stats or adding trades, SymbolPnlView and PeriodPnlView may not auto-refresh. A full page refresh (F5) or tab switch resolves this.
- **Database migrations**: Uses `create_all` on startup (no Alembic). Schema changes require deleting the DB file.
- **CCXT exchange connectivity**: Market data import requires internet access to reach exchange APIs. If import fails, check network.
- **SymbolSelector loading**: First time opening may take a few seconds to load symbols from the exchange API. If the dropdown is empty, wait or check backend logs for CCXT errors.
