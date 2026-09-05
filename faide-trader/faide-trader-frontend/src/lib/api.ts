const API_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000';

interface ValidationIssue {
  loc?: (string | number)[];
  msg?: string;
}

/** FastAPI returns a string for HTTPException and a list of issues for 422s. */
function formatDetail(detail: unknown): string {
  if (typeof detail === 'string') return detail;
  if (Array.isArray(detail)) {
    return (detail as ValidationIssue[])
      .map((issue) => {
        const field = issue.loc?.filter((p) => p !== 'body').join('.');
        return field ? `${field}: ${issue.msg ?? 'invalid value'}` : issue.msg ?? 'invalid value';
      })
      .join('; ');
  }
  return '';
}

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const res = await fetch(`${API_URL}${path}`, {
    headers: { 'Content-Type': 'application/json' },
    ...options,
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(formatDetail(err.detail) || res.statusText);
  }
  return res.json();
}

// Types
export interface Portfolio {
  id: number;
  name: string;
  description: string;
  pinned_stats: string[];
  pinned_stat_values: Record<string, number | null>;
  created_at: string;
  updated_at: string;
  account_count: number;
  total_pnl: number;
  total_balance: number;
}

export interface Account {
  id: number;
  portfolio_id: number;
  name: string;
  exchange: string;
  initial_balance: number;
  current_balance: number;
  is_pinned: boolean;
  pinned_stats: string[];
  pinned_stat_values: Record<string, number | null>;
  created_at: string;
  updated_at: string;
  bot_count: number;
  total_pnl: number;
  total_trades: number;
  win_rate: number;
}

export interface Bot {
  id: number;
  account_id: number;
  name: string;
  strategy_type: string;
  symbol: string;
  symbols: string[];
  is_active: boolean;
  is_pinned: boolean;
  pinned_stats: string[];
  pinned_stat_values: Record<string, number | null>;
  created_at: string;
  updated_at: string;
  total_pnl: number;
  total_trades: number;
  win_count: number;
  loss_count: number;
  win_rate: number;
  sharpe_ratio: number;
  max_drawdown: number;
  profit_factor: number;
}

export interface Trade {
  id: number;
  bot_id: number;
  symbol: string;
  direction: string;
  status: string;
  entry_price: number;
  exit_price: number | null;
  quantity: number;
  leverage: number;
  pnl: number;
  pnl_percent: number;
  fee: number;
  entry_time: string;
  exit_time: string | null;
  is_pinned: boolean;
  created_at: string;
  updated_at: string;
}

export interface PnlRecord {
  id: number;
  bot_id: number;
  date: string;
  period_type: string;
  pnl: number;
  cumulative_pnl: number;
  trade_count: number;
  win_count: number;
  loss_count: number;
  is_pinned: boolean;
}

export interface Stats {
  total_pnl: number;
  total_trades: number;
  win_count: number;
  loss_count: number;
  win_rate: number;
  avg_win: number;
  avg_loss: number;
  profit_factor: number;
  sharpe_ratio: number;
  sortino_ratio: number;
  max_drawdown: number;
  max_drawdown_percent: number;
  calmar_ratio: number;
  avg_trade_pnl: number;
  best_trade: number;
  worst_trade: number;
  total_fees: number;
  net_pnl: number;
  current_balance: number;
  roi_percent: number;
}

export interface PeriodPnl {
  period: string;
  period_type: string;
  pnl: number;
  cumulative_pnl: number;
  trade_count: number;
  win_count: number;
  loss_count: number;
  win_rate: number;
  drawdown: number;
  drawdown_percent: number;
  avg_pnl: number;
  best_trade: number;
  worst_trade: number;
  total_fees: number;
  profit_factor: number;
  is_pinned: boolean;
}

export interface TogglePinRequest {
  entity_type: 'bot' | 'account' | 'portfolio' | 'trade' | 'period';
  entity_id: number;
  field?: string;
  period_key?: string;
  period_type?: string;
  pinned: boolean;
}

export interface TradeGenerateRequest {
  start_date: string;
  end_date: string;
  num_trades?: number;
  win_rate_target?: number;
  avg_pnl_percent?: number;
  base_quantity?: number;
  base_leverage?: number;
  base_fee?: number;
  base_price?: number;
}

export interface MarketDataImportRequest {
  exchange: string;
  symbol?: string;
  symbols?: string[];
  timeframe?: string;
  since?: string;
  end_date?: string;
  limit?: number;
}

export interface SymbolPnl {
  symbol: string;
  total_pnl: number;
  total_trades: number;
  win_count: number;
  loss_count: number;
  win_rate: number;
  avg_pnl: number;
}

export interface Transaction {
  id: number;
  account_id: number;
  type: 'deposit' | 'withdrawal';
  amount: number;
  note: string;
  date: string;
  created_at: string;
  updated_at: string;
}

export interface EquityCurvePoint {
  date: string;
  balance: number;
  cumulative_pnl: number;
  drawdown: number;
  drawdown_percent: number;
  peak_balance: number;
  daily_pnl: number;
  trade_count: number;
  win_count: number;
  loss_count: number;
  win_rate: number;
  deposits: number;
  withdrawals: number;
  net_deposits_cumulative: number;
}

export interface DateRange {
  start?: string;
  end?: string;
}

export interface RangeRegenerateRequest {
  start_date: string;
  end_date: string;
  target_net_pnl?: number;
  trades_per_day?: number;
  zero_activity_dates?: string[];
  seed?: number;
  regenerate_transactions?: boolean;
  deposit_total?: number;
  withdrawal_total?: number;
  transaction_count?: number;
}

export interface RangeRegenerateResult {
  start_date: string;
  end_date: string;
  deleted_trades: number;
  generated_trades: number;
  deleted_transactions: number;
  generated_transactions: number;
  net_pnl: number;
  bots_regenerated: number;
  bots_skipped_locked: number;
  preserved_rows: number;
  zero_activity_days: string[];
}

function qs(params: Record<string, string | number | undefined>): string {
  const search = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value !== undefined && value !== '') search.set(key, String(value));
  }
  const out = search.toString();
  return out ? `?${out}` : '';
}

function rangeParams(range?: DateRange): Record<string, string | undefined> {
  return { start_date: range?.start, end_date: range?.end };
}

export interface RecalculateResult {
  updated_trades: Trade[];
  updated_pnl_records: PnlRecord[];
  bot_stats: Stats | null;
  account_stats: Record<string, number> | null;
  portfolio_stats: Record<string, number> | null;
}

// Portfolios
export const api = {
  // Portfolios
  listPortfolios: () => request<Portfolio[]>('/api/portfolios'),
  createPortfolio: (data: { name: string; description?: string }) =>
    request<Portfolio>('/api/portfolios', { method: 'POST', body: JSON.stringify(data) }),
  getPortfolio: (id: number) => request<Portfolio>(`/api/portfolios/${id}`),
  updatePortfolio: (id: number, data: Partial<Portfolio>) =>
    request<Portfolio>(`/api/portfolios/${id}`, { method: 'PUT', body: JSON.stringify(data) }),
  deletePortfolio: (id: number) =>
    request<{ status: string }>(`/api/portfolios/${id}`, { method: 'DELETE' }),

  // Accounts
  listAccounts: (portfolioId: number) =>
    request<Account[]>(`/api/portfolios/${portfolioId}/accounts`),
  createAccount: (portfolioId: number, data: { name: string; exchange: string; initial_balance?: number }) =>
    request<Account>(`/api/portfolios/${portfolioId}/accounts`, { method: 'POST', body: JSON.stringify(data) }),
  getAccount: (id: number) => request<Account>(`/api/accounts/${id}`),
  updateAccount: (id: number, data: Partial<Account>) =>
    request<Account>(`/api/accounts/${id}`, { method: 'PUT', body: JSON.stringify(data) }),
  deleteAccount: (id: number) =>
    request<{ status: string }>(`/api/accounts/${id}`, { method: 'DELETE' }),

  // Bots
  listBots: (accountId: number) => request<Bot[]>(`/api/accounts/${accountId}/bots`),
  createBot: (accountId: number, data: { name: string; strategy_type?: string; symbol?: string; symbols?: string[] }) =>
    request<Bot>(`/api/accounts/${accountId}/bots`, { method: 'POST', body: JSON.stringify(data) }),
  getBot: (id: number) => request<Bot>(`/api/bots/${id}`),
  updateBot: (id: number, data: Partial<Bot>) =>
    request<Bot>(`/api/bots/${id}`, { method: 'PUT', body: JSON.stringify(data) }),
  deleteBot: (id: number) =>
    request<{ status: string }>(`/api/bots/${id}`, { method: 'DELETE' }),

  // Trades
  listTrades: (botId: number, range?: DateRange) =>
    request<Trade[]>(`/api/bots/${botId}/trades${qs(rangeParams(range))}`),
  createTrade: (botId: number, data: Omit<Trade, 'id' | 'bot_id' | 'pnl' | 'pnl_percent' | 'is_pinned' | 'created_at' | 'updated_at'>) =>
    request<Trade>(`/api/bots/${botId}/trades`, { method: 'POST', body: JSON.stringify(data) }),
  updateTrade: (id: number, data: Partial<Trade>) =>
    request<Trade>(`/api/trades/${id}`, { method: 'PUT', body: JSON.stringify(data) }),
  deleteTrade: (id: number) =>
    request<{ status: string }>(`/api/trades/${id}`, { method: 'DELETE' }),

  // PnL
  getPnlRecords: (botId: number, period?: string, range?: DateRange) =>
    request<PnlRecord[]>(`/api/bots/${botId}/pnl${qs({ period, ...rangeParams(range) })}`),
  updatePnlRecord: (id: number, data: Partial<PnlRecord>) =>
    request<PnlRecord>(`/api/pnl/${id}`, { method: 'PUT', body: JSON.stringify(data) }),

  // Recalculate
  recalculate: (data: { entity_type: string; entity_id: number; field: string; new_value: number; pinned_fields?: string[]; period_key?: string; period_type?: string }) =>
    request<RecalculateResult>('/api/recalculate', { method: 'POST', body: JSON.stringify(data) }),

  // Stats
  getPortfolioStats: (id: number, range?: DateRange) =>
    request<Stats>(`/api/stats/portfolio/${id}${qs(rangeParams(range))}`),
  getAccountStats: (id: number, range?: DateRange) =>
    request<Stats>(`/api/stats/account/${id}${qs(rangeParams(range))}`),
  getBotStats: (id: number, range?: DateRange) =>
    request<Stats>(`/api/stats/bot/${id}${qs(rangeParams(range))}`),

  // Market Data
  listExchanges: () => request<{ exchanges: { id: string; name: string; type: string }[] }>('/api/market-data/exchanges'),
  listSymbols: (exchange: string) => request<{ exchange: string; symbols: string[] }>(`/api/market-data/symbols/${exchange}`),
  importMarketData: (data: MarketDataImportRequest) =>
    request<{ imported: number; exchange: string; symbol?: string; symbols?: string[]; per_symbol?: Record<string, number> }>('/api/market-data/import', { method: 'POST', body: JSON.stringify(data) }),
  getSymbolPnl: (botId: number, range?: DateRange) =>
    request<SymbolPnl[]>(`/api/bots/${botId}/symbol-pnl${qs(rangeParams(range))}`),

  // Trade Generation
  generateTrades: (botId: number, data: TradeGenerateRequest) =>
    request<{ generated: number; bot_id: number }>(`/api/bots/${botId}/trades/generate`, { method: 'POST', body: JSON.stringify(data) }),

  // Period P&L
  getBotPeriodPnl: (botId: number, periodType?: string, range?: DateRange) =>
    request<PeriodPnl[]>(`/api/bots/${botId}/period-pnl${qs({ period_type: periodType, ...rangeParams(range) })}`),
  getAccountPeriodPnl: (accountId: number, periodType?: string, range?: DateRange) =>
    request<PeriodPnl[]>(`/api/accounts/${accountId}/period-pnl${qs({ period_type: periodType, ...rangeParams(range) })}`),
  getPortfolioPeriodPnl: (portfolioId: number, periodType?: string, range?: DateRange) =>
    request<PeriodPnl[]>(`/api/portfolios/${portfolioId}/period-pnl${qs({ period_type: periodType, ...rangeParams(range) })}`),
  updatePeriodPnl: (botId: number, periodKey: string, data: { pnl?: number; win_rate?: number; profit_factor?: number; is_pinned?: boolean }, periodType?: string) =>
    request<{ periods: PeriodPnl[]; bot_stats: Record<string, number> }>(
      `/api/bots/${botId}/period-pnl/${periodKey}${periodType ? `?period_type=${periodType}` : ''}`,
      { method: 'PUT', body: JSON.stringify(data) }
    ),
  updateAccountPeriodPnl: (accountId: number, periodKey: string, data: { pnl?: number }, periodType?: string) =>
    request<{ periods: PeriodPnl[]; account_stats: Record<string, number> }>(
      `/api/accounts/${accountId}/period-pnl/${periodKey}${periodType ? `?period_type=${periodType}` : ''}`,
      { method: 'PUT', body: JSON.stringify(data) }
    ),
  updatePortfolioPeriodPnl: (portfolioId: number, periodKey: string, data: { pnl?: number }, periodType?: string) =>
    request<{ periods: PeriodPnl[]; portfolio_stats: Record<string, number> }>(
      `/api/portfolios/${portfolioId}/period-pnl/${periodKey}${periodType ? `?period_type=${periodType}` : ''}`,
      { method: 'PUT', body: JSON.stringify(data) }
    ),

  // Pin/Lock
  togglePin: (data: TogglePinRequest) =>
    request<{ success: boolean; entity_type: string; entity_id: number; field?: string; pinned: boolean }>(
      '/api/toggle-pin', { method: 'POST', body: JSON.stringify(data) }
    ),
  setConstraint: (data: { entity_type: string; entity_id: number; field: string; value: number }) =>
    request<{ success: boolean; entity_type: string; entity_id: number; field: string; value: number }>(
      '/api/set-constraint', { method: 'POST', body: JSON.stringify(data) }
    ),

  // Regenerate
  regenerateBot: (botId: number, data?: { num_trades?: number; start_date?: string; end_date?: string }) =>
    request<{ generated: number; bot_id: number; constraints_applied: Record<string, number>; bot_stats: Record<string, number>; final_stats: Record<string, number> }>(
      `/api/bots/${botId}/regenerate`, { method: 'POST', body: JSON.stringify(data || {}) }
    ),
  regenerateAccount: (accountId: number, data?: { num_trades?: number; start_date?: string; end_date?: string }) =>
    request<{ account_id: number; bots_regenerated: number; bots_skipped_locked: number; account_stats: Record<string, number> }>(
      `/api/accounts/${accountId}/regenerate`, { method: 'POST', body: JSON.stringify(data || {}) }
    ),
  regeneratePortfolio: (portfolioId: number, data?: { num_trades?: number; start_date?: string; end_date?: string }) =>
    request<{ portfolio_id: number; bots_regenerated: number; bots_skipped_locked: number; portfolio_stats: Record<string, number> }>(
      `/api/portfolios/${portfolioId}/regenerate`, { method: 'POST', body: JSON.stringify(data || {}) }
    ),

  // Range-scoped regeneration (only touches data inside the window)
  regenerateBotRange: (botId: number, data: RangeRegenerateRequest) =>
    request<RangeRegenerateResult>(`/api/bots/${botId}/regenerate-range`, { method: 'POST', body: JSON.stringify(data) }),
  regenerateAccountRange: (accountId: number, data: RangeRegenerateRequest) =>
    request<RangeRegenerateResult>(`/api/accounts/${accountId}/regenerate-range`, { method: 'POST', body: JSON.stringify(data) }),
  regeneratePortfolioRange: (portfolioId: number, data: RangeRegenerateRequest) =>
    request<RangeRegenerateResult>(`/api/portfolios/${portfolioId}/regenerate-range`, { method: 'POST', body: JSON.stringify(data) }),

  // Equity Curve
  getAccountEquityCurve: (accountId: number, range?: DateRange) =>
    request<EquityCurvePoint[]>(`/api/accounts/${accountId}/equity-curve${qs(rangeParams(range))}`),
  getPortfolioEquityCurve: (portfolioId: number, range?: DateRange) =>
    request<EquityCurvePoint[]>(`/api/portfolios/${portfolioId}/equity-curve${qs(rangeParams(range))}`),

  // Transactions
  listTransactions: (accountId: number, range?: DateRange) =>
    request<Transaction[]>(`/api/accounts/${accountId}/transactions${qs(rangeParams(range))}`),
  listPortfolioTransactions: (portfolioId: number, range?: DateRange) =>
    request<Transaction[]>(`/api/portfolios/${portfolioId}/transactions${qs(rangeParams(range))}`),
  createTransaction: (accountId: number, data: { type: string; amount: number; note?: string; date: string }) =>
    request<Transaction>(`/api/accounts/${accountId}/transactions`, { method: 'POST', body: JSON.stringify(data) }),
  updateTransaction: (txId: number, data: Partial<Transaction>) =>
    request<Transaction>(`/api/transactions/${txId}`, { method: 'PUT', body: JSON.stringify(data) }),
  deleteTransaction: (txId: number) =>
    request<{ status: string }>(`/api/transactions/${txId}`, { method: 'DELETE' }),
};
