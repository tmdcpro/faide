---
name: testing-faide-trader
description: Test the Faide Trader algo-trading platform end-to-end. Use when verifying CRUD, calculations, lock/pin, or time-series editing features.
---

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

### Generating Trades (Faster)
Use the "Generate Trades" dialog on bot detail view:
- Set count (e.g., 10), avg_pnl, win_rate
- This auto-creates trades with back-calculated prices
- Faster than manually adding individual trades for testing

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

## Testing Lock/Pin System

### Per-Stat Locking (Bot Stats)
- Hover over a stat label (e.g., "Win Rate") in Bot Statistics card → small lock icon appears
- Click lock icon → stat shows yellow Lock icon, value dimmed (opacity-75)
- Locked stat **cannot be clicked to edit** (code: `if (canEdit && !isPinned)` in EditableStatsCard.tsx)
- Locked stat **survives recalculation** — editing another unlocked stat triggers recalc but locked value stays fixed
- **Test approach**: Lock Win Rate → edit Total P&L → verify Win Rate unchanged, other stats updated

### Entity-Level Bot/Account Lock
- "Lock" / "Locked" button in bot/account header (top right area)
- When locked: button turns yellow, subtitle shows "🔒 Locked"
- Lock indicator (small yellow lock icon) appears on bot/account cards in parent list views
- **Known bug**: Entity-level bot lock may NOT prevent recalculation when account balance is edited via `/api/recalculate`. The recalculate endpoint's account balance distribution path might not check `is_pinned` on child bots. Verify this is fixed before relying on it in tests.

### Period-Level Pinning
- In "Period P&L Breakdown" section (bot detail), each row has a pin/lock toggle
- Pinned period: yellow lock icon next to date, yellow row tint (`bg-yellow-900/10`)
- Pinned period values are **preserved during recalculation** of other periods
- **Test approach**: Pin a month → edit Win % on a different (unpinned) month → verify pinned month unchanged

### Per-Period Stat Editing
- Win % and Profit Factor are editable per-period in the Period P&L table
- Click the value → inline edit → press Enter → triggers back-calculation on trades in that period
- **Discrete win rate limitation**: Win rate can only take values achievable with the trade count. With N trades, achievable values are 0%, 1/N*100%, 2/N*100%, ..., 100%. For 5 trades: 0%, 20%, 40%, 60%, 80%, 100%. Editing to a non-achievable value (e.g., 90% with 5 trades) fails silently — no error feedback.
- **Workaround for non-achievable values**: Use the API directly: `PUT /api/bots/{id}/period-pnl/{key}` with `{"win_rate": value}`. The API also enforces discrete values but returns an error rather than failing silently.
- **Stale state after edit**: Period table may not auto-refresh after inline edits. Full page refresh (F5) resolves this.

## Testing Tips

### UI Interaction Gotchas
- Lock icons on stats are **hover-only** — they appear when you hover over the stat label. Use DOM targeting by `devinid` attribute if coordinate-based clicking is unreliable: `document.querySelector('[devinid="N"]').click()`
- After any inline edit, wait briefly for the API call to complete. If the UI doesn't update, try F5 refresh.
- When testing recalculation, compare before/after values carefully. Use the API (`GET /api/bots/{id}`) for precise numeric comparison instead of relying on rounded UI display.

### API Shortcuts for Testing
- **Recalculate**: `POST /api/recalculate` with `{"entity_type": "bot|account|portfolio", "entity_id": N, "field": "total_pnl|current_balance|...", "new_value": X}`
- **Period edit**: `PUT /api/bots/{id}/period-pnl/{key}?period_type=monthly` with `{"win_rate": 0.6}` or `{"pnl": 500}` or `{"is_pinned": true}`
- **Toggle lock**: `PUT /api/bots/{id}` with `{"is_pinned": true}` or `PUT /api/accounts/{id}` with `{"is_pinned": true}`

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
- **Entity-level lock enforcement**: Bot/account lock may not fully prevent recalculation from parent-level edits (see Lock/Pin section above). This may be fixed in future updates — always verify.
- **Silent validation on period win rate**: Editing win rate to a non-achievable discrete value fails silently in the UI. No error toast or feedback.
