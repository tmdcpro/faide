from datetime import datetime
from typing import Optional
from pydantic import BaseModel


# --- Portfolio ---
class PortfolioCreate(BaseModel):
    name: str
    description: str = ""


class PortfolioUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None


class PortfolioResponse(BaseModel):
    id: int
    name: str
    description: str
    pinned_stats: list[str] = []
    pinned_stat_values: dict[str, float | None] = {}
    created_at: datetime
    updated_at: datetime
    account_count: int = 0
    total_pnl: float = 0.0
    total_balance: float = 0.0

    model_config = {"from_attributes": True}


# --- Account ---
class AccountCreate(BaseModel):
    name: str
    exchange: str
    initial_balance: float = 10000.0


class AccountUpdate(BaseModel):
    name: Optional[str] = None
    exchange: Optional[str] = None
    initial_balance: Optional[float] = None
    current_balance: Optional[float] = None
    is_pinned: Optional[bool] = None


class AccountResponse(BaseModel):
    id: int
    portfolio_id: int
    name: str
    exchange: str
    initial_balance: float
    current_balance: float
    is_pinned: bool = False
    pinned_stats: list[str] = []
    pinned_stat_values: dict[str, float | None] = {}
    created_at: datetime
    updated_at: datetime
    bot_count: int = 0
    total_pnl: float = 0.0
    total_trades: int = 0
    win_rate: float = 0.0

    model_config = {"from_attributes": True}


# --- Bot ---
class BotCreate(BaseModel):
    name: str
    strategy_type: str = "manual"
    symbol: str = "BTC/USDT"  # primary symbol (backward compat)
    symbols: list[str] = []  # additional symbols
    is_active: bool = True


class BotUpdate(BaseModel):
    name: Optional[str] = None
    strategy_type: Optional[str] = None
    symbol: Optional[str] = None
    symbols: Optional[list[str]] = None
    is_active: Optional[bool] = None
    is_pinned: Optional[bool] = None
    pinned_stats: Optional[list[str]] = None


class BotResponse(BaseModel):
    id: int
    account_id: int
    name: str
    strategy_type: str
    symbol: str
    symbols: list[str] = []
    is_active: bool
    is_pinned: bool = False
    pinned_stats: list[str] = []
    pinned_stat_values: dict[str, float | None] = {}
    created_at: datetime
    updated_at: datetime
    total_pnl: float = 0.0
    total_trades: int = 0
    win_count: int = 0
    loss_count: int = 0
    win_rate: float = 0.0
    sharpe_ratio: float = 0.0
    max_drawdown: float = 0.0
    profit_factor: float = 0.0

    model_config = {"from_attributes": True}


class SymbolPnlResponse(BaseModel):
    symbol: str
    total_pnl: float = 0.0
    total_trades: int = 0
    win_count: int = 0
    loss_count: int = 0
    win_rate: float = 0.0
    avg_pnl: float = 0.0


# --- Trade ---
class TradeCreate(BaseModel):
    symbol: str
    direction: str = "long"
    status: str = "closed"
    entry_price: float
    exit_price: Optional[float] = None
    quantity: float
    leverage: float = 1.0
    fee: float = 0.0
    entry_time: datetime
    exit_time: Optional[datetime] = None


class TradeUpdate(BaseModel):
    symbol: Optional[str] = None
    direction: Optional[str] = None
    status: Optional[str] = None
    entry_price: Optional[float] = None
    exit_price: Optional[float] = None
    quantity: Optional[float] = None
    leverage: Optional[float] = None
    fee: Optional[float] = None
    pnl: Optional[float] = None
    pnl_percent: Optional[float] = None
    entry_time: Optional[datetime] = None
    exit_time: Optional[datetime] = None
    is_pinned: Optional[bool] = None


class TradeResponse(BaseModel):
    id: int
    bot_id: int
    symbol: str
    direction: str
    status: str
    entry_price: float
    exit_price: Optional[float]
    quantity: float
    leverage: float
    pnl: float
    pnl_percent: float
    fee: float
    entry_time: datetime
    exit_time: Optional[datetime]
    is_pinned: bool
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


# --- PnL Record ---
class PnlRecordUpdate(BaseModel):
    pnl: Optional[float] = None
    trade_count: Optional[int] = None
    win_count: Optional[int] = None
    loss_count: Optional[int] = None
    is_pinned: Optional[bool] = None


class PnlRecordResponse(BaseModel):
    id: int
    bot_id: int
    date: datetime
    period_type: str
    pnl: float
    cumulative_pnl: float
    trade_count: int
    win_count: int
    loss_count: int
    is_pinned: bool

    model_config = {"from_attributes": True}


# --- Trade Generation ---
class TradeGenerateRequest(BaseModel):
    start_date: str  # ISO date string
    end_date: str  # ISO date string
    num_trades: int = 50
    win_rate_target: float = 55.0
    avg_pnl_percent: float = 2.0
    base_quantity: float = 0.1
    base_leverage: float = 5.0
    base_fee: float = 2.0
    base_price: float = 50000.0


class TradeGenerateResponse(BaseModel):
    generated: int
    bot_id: int
    start_date: str
    end_date: str


class RegenerateRequest(BaseModel):
    num_trades: Optional[int] = None
    start_date: Optional[str] = None  # ISO date string
    end_date: Optional[str] = None  # ISO date string


class RegenerateResponse(BaseModel):
    generated: int
    bot_id: int
    constraints_applied: dict[str, float] = {}
    bot_stats: dict = {}
    final_stats: dict = {}


# --- Market Data ---
class MarketDataImport(BaseModel):
    exchange: str
    symbol: Optional[str] = None  # single symbol (backward compat)
    symbols: Optional[list[str]] = None  # multiple symbols
    timeframe: str = "1d"
    since: Optional[str] = None  # ISO date string
    end_date: Optional[str] = None  # ISO date string for end of range
    limit: int = 365


class OHLCVResponse(BaseModel):
    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float


# --- Recalculation ---
class RecalculateRequest(BaseModel):
    entity_type: str  # "trade", "pnl_record", "bot", "account"
    entity_id: int
    field: str
    new_value: float
    pinned_fields: list[str] = []
    period_key: Optional[str] = None  # for per-period stat editing
    period_type: Optional[str] = None  # "daily", "weekly", "monthly"


class TogglePinRequest(BaseModel):
    entity_type: str  # "bot", "account", "trade", "period"
    entity_id: int
    field: Optional[str] = None  # for stat-level pin; None for entity-level
    period_key: Optional[str] = None  # for period-level pin
    period_type: Optional[str] = None
    pinned: bool = True


class TogglePinResponse(BaseModel):
    success: bool
    entity_type: str
    entity_id: int
    field: Optional[str] = None
    pinned: bool


class SetConstraintRequest(BaseModel):
    entity_type: str  # "bot", "account", "portfolio"
    entity_id: int
    field: str
    value: float


class SetConstraintResponse(BaseModel):
    success: bool
    entity_type: str
    entity_id: int
    field: str
    value: float


class RecalculateResponse(BaseModel):
    updated_trades: list[TradeResponse] = []
    updated_pnl_records: list[PnlRecordResponse] = []
    bot_stats: Optional[dict] = None
    account_stats: Optional[dict] = None
    portfolio_stats: Optional[dict] = None


# --- Period P&L ---
class PeriodPnlResponse(BaseModel):
    period: str  # e.g. "2024-01", "2024-W03", "2024-01-15"
    period_type: str  # "monthly", "weekly", "daily"
    pnl: float = 0.0
    cumulative_pnl: float = 0.0
    trade_count: int = 0
    win_count: int = 0
    loss_count: int = 0
    win_rate: float = 0.0
    drawdown: float = 0.0
    drawdown_percent: float = 0.0
    avg_pnl: float = 0.0
    best_trade: float = 0.0
    worst_trade: float = 0.0
    total_fees: float = 0.0
    profit_factor: float = 0.0
    is_pinned: bool = False

    model_config = {"from_attributes": True}


class PeriodPnlUpdate(BaseModel):
    pnl: Optional[float] = None
    trade_count: Optional[int] = None
    win_count: Optional[int] = None
    loss_count: Optional[int] = None
    win_rate: Optional[float] = None
    profit_factor: Optional[float] = None
    is_pinned: Optional[bool] = None


# --- Stats ---
class StatsResponse(BaseModel):
    total_pnl: float = 0.0
    total_trades: int = 0
    win_count: int = 0
    loss_count: int = 0
    win_rate: float = 0.0
    avg_win: float = 0.0
    avg_loss: float = 0.0
    profit_factor: float = 0.0
    sharpe_ratio: float = 0.0
    sortino_ratio: float = 0.0
    max_drawdown: float = 0.0
    max_drawdown_percent: float = 0.0
    calmar_ratio: float = 0.0
    avg_trade_pnl: float = 0.0
    best_trade: float = 0.0
    worst_trade: float = 0.0
    total_fees: float = 0.0
    net_pnl: float = 0.0
    current_balance: float = 0.0
    roi_percent: float = 0.0
