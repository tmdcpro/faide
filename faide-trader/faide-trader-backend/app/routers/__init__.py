from app.routers.portfolios import router as portfolios_router
from app.routers.accounts import router as accounts_router
from app.routers.bots import router as bots_router
from app.routers.trades import router as trades_router
from app.routers.recalculate import router as recalculate_router
from app.routers.market_data import router as market_data_router
from app.routers.transactions import router as transactions_router

__all__ = [
    "portfolios_router",
    "accounts_router",
    "bots_router",
    "trades_router",
    "recalculate_router",
    "market_data_router",
    "transactions_router",
]
