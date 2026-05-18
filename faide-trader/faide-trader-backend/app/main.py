from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.database import init_db
from app.routers import (
    portfolios_router,
    accounts_router,
    bots_router,
    trades_router,
    recalculate_router,
    market_data_router,
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    yield


app = FastAPI(title="Faide Trader", version="0.1.0", lifespan=lifespan)

# Disable CORS. Do not remove this for full-stack development.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allows all origins
    allow_credentials=True,
    allow_methods=["*"],  # Allows all methods
    allow_headers=["*"],  # Allows all headers
)

app.include_router(portfolios_router)
app.include_router(accounts_router)
app.include_router(bots_router)
app.include_router(trades_router)
app.include_router(recalculate_router)
app.include_router(market_data_router)


@app.get("/healthz")
async def healthz():
    return {"status": "ok"}
