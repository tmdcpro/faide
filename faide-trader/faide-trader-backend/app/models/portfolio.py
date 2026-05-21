import json
from datetime import datetime
from sqlalchemy import Column, Integer, String, Float, DateTime, ForeignKey, Boolean, Enum as SAEnum
from sqlalchemy.orm import relationship
import enum

from app.database import Base


class ExchangeType(str, enum.Enum):
    BITGET_FUTURES = "bitget_futures"
    PHEMEX_FUTURES = "phemex_futures"
    KRAKEN = "kraken"


class TradeDirection(str, enum.Enum):
    LONG = "long"
    SHORT = "short"


class TradeStatus(str, enum.Enum):
    OPEN = "open"
    CLOSED = "closed"


class Portfolio(Base):
    __tablename__ = "portfolios"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String, nullable=False)
    description = Column(String, default="")
    _pinned_stats = Column("pinned_stats", String, default="[]")
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    accounts = relationship("Account", back_populates="portfolio", cascade="all, delete-orphan")

    @property
    def pinned_stats(self) -> list[str]:
        try:
            data = json.loads(self._pinned_stats) if self._pinned_stats else []
            if isinstance(data, dict):
                return list(data.keys())
            return data
        except (json.JSONDecodeError, TypeError):
            return []

    @pinned_stats.setter
    def pinned_stats(self, value: list[str]) -> None:
        # Preserve existing constraint values when updating the field list
        existing = self.pinned_stat_values
        new_dict = {}
        for field in (value if value else []):
            new_dict[field] = existing.get(field)
        self._pinned_stats = json.dumps(new_dict)

    @property
    def pinned_stat_values(self) -> dict[str, float | None]:
        try:
            data = json.loads(self._pinned_stats) if self._pinned_stats else {}
            if isinstance(data, list):
                return {f: None for f in data}
            return data
        except (json.JSONDecodeError, TypeError):
            return {}

    @pinned_stat_values.setter
    def pinned_stat_values(self, value: dict[str, float | None]) -> None:
        self._pinned_stats = json.dumps(value if value else {})


class Account(Base):
    __tablename__ = "accounts"

    id = Column(Integer, primary_key=True, autoincrement=True)
    portfolio_id = Column(Integer, ForeignKey("portfolios.id"), nullable=False)
    name = Column(String, nullable=False)
    exchange = Column(String, nullable=False)
    initial_balance = Column(Float, default=10000.0)
    current_balance = Column(Float, default=10000.0)
    is_pinned = Column(Boolean, default=False)
    _pinned_stats = Column("pinned_stats", String, default="[]")
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    portfolio = relationship("Portfolio", back_populates="accounts")
    bots = relationship("Bot", back_populates="account", cascade="all, delete-orphan")
    transactions = relationship("Transaction", back_populates="account", cascade="all, delete-orphan")

    @property
    def pinned_stats(self) -> list[str]:
        try:
            data = json.loads(self._pinned_stats) if self._pinned_stats else []
            if isinstance(data, dict):
                return list(data.keys())
            return data
        except (json.JSONDecodeError, TypeError):
            return []

    @pinned_stats.setter
    def pinned_stats(self, value: list[str]) -> None:
        existing = self.pinned_stat_values
        new_dict = {}
        for field in (value if value else []):
            new_dict[field] = existing.get(field)
        self._pinned_stats = json.dumps(new_dict)

    @property
    def pinned_stat_values(self) -> dict[str, float | None]:
        try:
            data = json.loads(self._pinned_stats) if self._pinned_stats else {}
            if isinstance(data, list):
                return {f: None for f in data}
            return data
        except (json.JSONDecodeError, TypeError):
            return {}

    @pinned_stat_values.setter
    def pinned_stat_values(self, value: dict[str, float | None]) -> None:
        self._pinned_stats = json.dumps(value if value else {})


class Bot(Base):
    __tablename__ = "bots"

    id = Column(Integer, primary_key=True, autoincrement=True)
    account_id = Column(Integer, ForeignKey("accounts.id"), nullable=False)
    name = Column(String, nullable=False)
    strategy_type = Column(String, default="manual")
    symbol = Column(String, default="BTC/USDT")
    _symbols = Column("symbols", String, default="[]")  # JSON-encoded list of symbols
    is_active = Column(Boolean, default=True)
    is_pinned = Column(Boolean, default=False)
    _pinned_stats = Column("pinned_stats", String, default="[]")  # JSON-encoded list of pinned stat field names
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    account = relationship("Account", back_populates="bots")
    trades = relationship("Trade", back_populates="bot", cascade="all, delete-orphan")
    pnl_records = relationship("PnlRecord", back_populates="bot", cascade="all, delete-orphan")

    @property
    def pinned_stats(self) -> list[str]:
        """Get the list of stat fields that are pinned/locked."""
        try:
            data = json.loads(self._pinned_stats) if self._pinned_stats else []
            if isinstance(data, dict):
                return list(data.keys())
            return data
        except (json.JSONDecodeError, TypeError):
            return []

    @pinned_stats.setter
    def pinned_stats(self, value: list[str]) -> None:
        """Set the list of pinned stat field names."""
        existing = self.pinned_stat_values
        new_dict = {}
        for field in (value if value else []):
            new_dict[field] = existing.get(field)
        self._pinned_stats = json.dumps(new_dict)

    @property
    def pinned_stat_values(self) -> dict[str, float | None]:
        try:
            data = json.loads(self._pinned_stats) if self._pinned_stats else {}
            if isinstance(data, list):
                return {f: None for f in data}
            return data
        except (json.JSONDecodeError, TypeError):
            return {}

    @pinned_stat_values.setter
    def pinned_stat_values(self, value: dict[str, float | None]) -> None:
        self._pinned_stats = json.dumps(value if value else {})

    @property
    def symbols(self) -> list[str]:
        """Get the list of all symbols this bot trades."""
        try:
            stored = json.loads(self._symbols) if self._symbols else []
        except (json.JSONDecodeError, TypeError):
            stored = []
        # Always include primary symbol
        all_symbols = [self.symbol] if self.symbol else []
        for s in stored:
            if s not in all_symbols:
                all_symbols.append(s)
        return all_symbols

    @symbols.setter
    def symbols(self, value: list[str]) -> None:
        """Set the list of symbols. First symbol becomes the primary."""
        if value:
            self.symbol = value[0]
            self._symbols = json.dumps(value)
        else:
            self._symbols = "[]"


class Trade(Base):
    __tablename__ = "trades"

    id = Column(Integer, primary_key=True, autoincrement=True)
    bot_id = Column(Integer, ForeignKey("bots.id"), nullable=False)
    symbol = Column(String, nullable=False)
    direction = Column(String, default="long")
    status = Column(String, default="closed")
    entry_price = Column(Float, nullable=False)
    exit_price = Column(Float, nullable=True)
    quantity = Column(Float, nullable=False)
    leverage = Column(Float, default=1.0)
    pnl = Column(Float, default=0.0)
    pnl_percent = Column(Float, default=0.0)
    fee = Column(Float, default=0.0)
    entry_time = Column(DateTime, nullable=False)
    exit_time = Column(DateTime, nullable=True)
    is_pinned = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    bot = relationship("Bot", back_populates="trades")


class PnlRecord(Base):
    __tablename__ = "pnl_records"

    id = Column(Integer, primary_key=True, autoincrement=True)
    bot_id = Column(Integer, ForeignKey("bots.id"), nullable=False)
    date = Column(DateTime, nullable=False)
    period_type = Column(String, default="daily")  # daily, weekly, monthly
    pnl = Column(Float, default=0.0)
    cumulative_pnl = Column(Float, default=0.0)
    trade_count = Column(Integer, default=0)
    win_count = Column(Integer, default=0)
    loss_count = Column(Integer, default=0)
    is_pinned = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    bot = relationship("Bot", back_populates="pnl_records")


class Transaction(Base):
    __tablename__ = "transactions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    account_id = Column(Integer, ForeignKey("accounts.id"), nullable=False)
    type = Column(String, nullable=False)  # "deposit" or "withdrawal"
    amount = Column(Float, nullable=False)
    note = Column(String, default="")
    date = Column(DateTime, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    account = relationship("Account", back_populates="transactions")


class MarketData(Base):
    __tablename__ = "market_data"

    id = Column(Integer, primary_key=True, autoincrement=True)
    exchange = Column(String, nullable=False)
    symbol = Column(String, nullable=False)
    timeframe = Column(String, default="1d")
    timestamp = Column(DateTime, nullable=False)
    open = Column(Float, nullable=False)
    high = Column(Float, nullable=False)
    low = Column(Float, nullable=False)
    close = Column(Float, nullable=False)
    volume = Column(Float, nullable=False)
