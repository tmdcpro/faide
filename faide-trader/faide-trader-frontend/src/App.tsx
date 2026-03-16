import { useState, useEffect, useCallback } from 'react';
import {
  api,
  type Portfolio,
  type Account,
  type Bot,
  type Trade,
  type Stats,
  type PnlRecord,
} from '@/lib/api';
import { StatsCard } from '@/components/StatsCard';
import { EditableStatsCard } from '@/components/EditableStatsCard';
import { TradeTable } from '@/components/TradeTable';
import { CreateDialog } from '@/components/CreateDialog';
import { CreateTradeDialog } from '@/components/CreateTradeDialog';
import { PnlChart } from '@/components/PnlChart';
import { PeriodPnlView } from '@/components/PeriodPnlView';
import { EditableField } from '@/components/EditableField';
import { MarketDataImportDialog } from '@/components/MarketDataImportDialog';
import { GenerateTradesDialog } from '@/components/GenerateTradesDialog';
import {
  ChevronRight,
  Plus,
  Trash2,
  ArrowLeft,
  BarChart3,
  Wallet,
  Bot as BotIcon,
  TrendingUp,
  RefreshCw,
  Download,
  Zap,
} from 'lucide-react';

type View =
  | { type: 'portfolios' }
  | { type: 'portfolio'; portfolioId: number }
  | { type: 'account'; accountId: number; portfolioId: number }
  | { type: 'bot'; botId: number; accountId: number; portfolioId: number };

function App() {
  const [view, setView] = useState<View>({ type: 'portfolios' });
  const [portfolios, setPortfolios] = useState<Portfolio[]>([]);
  const [accounts, setAccounts] = useState<Account[]>([]);
  const [bots, setBots] = useState<Bot[]>([]);
  const [trades, setTrades] = useState<Trade[]>([]);
  const [stats, setStats] = useState<Stats | null>(null);
  const [pnlRecords, setPnlRecords] = useState<PnlRecord[]>([]);
  const [loading, setLoading] = useState(false);
  const [showCreate, setShowCreate] = useState<string | null>(null);
  const [showMarketImport, setShowMarketImport] = useState(false);
  const [showGenerateTrades, setShowGenerateTrades] = useState(false);
  const [currentPortfolio, setCurrentPortfolio] = useState<Portfolio | null>(null);
  const [currentAccount, setCurrentAccount] = useState<Account | null>(null);
  const [currentBot, setCurrentBot] = useState<Bot | null>(null);

  // Load data based on current view
  const loadData = useCallback(async () => {
    setLoading(true);
    try {
      if (view.type === 'portfolios') {
        const data = await api.listPortfolios();
        setPortfolios(data);
      } else if (view.type === 'portfolio') {
        const [portfolio, accts] = await Promise.all([
          api.getPortfolio(view.portfolioId),
          api.listAccounts(view.portfolioId),
        ]);
        setCurrentPortfolio(portfolio);
        setAccounts(accts);
        if (accts.length > 0) {
          const s = await api.getPortfolioStats(view.portfolioId);
          setStats(s);
        } else {
          setStats(null);
        }
      } else if (view.type === 'account') {
        const [account, botList, s] = await Promise.all([
          api.getAccount(view.accountId),
          api.listBots(view.accountId),
          api.getAccountStats(view.accountId),
        ]);
        setCurrentAccount(account);
        setBots(botList);
        setStats(s);
      } else if (view.type === 'bot') {
        const [bot, tradeList, s, pnl] = await Promise.all([
          api.getBot(view.botId),
          api.listTrades(view.botId),
          api.getBotStats(view.botId),
          api.getPnlRecords(view.botId),
        ]);
        setCurrentBot(bot);
        setTrades(tradeList);
        setStats(s);
        setPnlRecords(pnl);
      }
    } catch (e) {
      console.error('Load failed:', e);
    } finally {
      setLoading(false);
    }
  }, [view]);

  useEffect(() => {
    loadData();
  }, [loadData]);

  const handleBack = () => {
    if (view.type === 'bot') {
      setView({ type: 'account', accountId: view.accountId, portfolioId: view.portfolioId });
    } else if (view.type === 'account') {
      setView({ type: 'portfolio', portfolioId: view.portfolioId });
    } else if (view.type === 'portfolio') {
      setView({ type: 'portfolios' });
    }
  };

  // Breadcrumb
  const renderBreadcrumb = () => {
    const crumbs: { label: string; onClick?: () => void }[] = [
      { label: 'Portfolios', onClick: () => setView({ type: 'portfolios' }) },
    ];

    if (view.type !== 'portfolios') {
      crumbs.push({
        label: currentPortfolio?.name || 'Portfolio',
        onClick: () => setView({ type: 'portfolio', portfolioId: view.portfolioId }),
      });
    }
    if (view.type === 'account' || view.type === 'bot') {
      crumbs.push({
        label: currentAccount?.name || 'Account',
        onClick: view.type === 'bot'
          ? () => setView({ type: 'account', accountId: view.accountId, portfolioId: view.portfolioId })
          : undefined,
      });
    }
    if (view.type === 'bot') {
      crumbs.push({ label: currentBot?.name || 'Bot' });
    }

    return (
      <div className="flex items-center gap-1 text-sm text-gray-400 mb-4">
        {crumbs.map((crumb, i) => (
          <span key={i} className="flex items-center gap-1">
            {i > 0 && <ChevronRight size={14} />}
            {crumb.onClick ? (
              <button onClick={crumb.onClick} className="hover:text-white transition-colors">
                {crumb.label}
              </button>
            ) : (
              <span className="text-white">{crumb.label}</span>
            )}
          </span>
        ))}
      </div>
    );
  };

  // Portfolios List View
  const renderPortfolios = () => (
    <div>
      <div className="flex items-center justify-between mb-6">
        <h1 className="text-2xl font-bold">Portfolios</h1>
        <button
          onClick={() => setShowCreate('portfolio')}
          className="flex items-center gap-2 px-4 py-2 bg-blue-600 hover:bg-blue-500 rounded-lg text-sm font-medium transition-colors"
        >
          <Plus size={16} /> New Portfolio
        </button>
      </div>

      {portfolios.length === 0 ? (
        <div className="text-center py-16 text-gray-500">
          <Wallet size={48} className="mx-auto mb-4 opacity-50" />
          <p className="text-lg mb-2">No portfolios yet</p>
          <p className="text-sm">Create your first simulated portfolio to get started.</p>
        </div>
      ) : (
        <div className="grid gap-4">
          {portfolios.map((p) => (
            <div
              key={p.id}
              onClick={() => setView({ type: 'portfolio', portfolioId: p.id })}
              className="bg-slate-800 border border-slate-700 rounded-lg p-4 cursor-pointer hover:border-blue-500/50 transition-colors"
            >
              <div className="flex items-center justify-between">
                <div>
                  <h3 className="font-semibold text-lg">{p.name}</h3>
                  <p className="text-sm text-gray-400">{p.description || 'No description'}</p>
                </div>
                <div className="text-right">
                  <div className={`text-lg font-mono font-bold ${p.total_pnl >= 0 ? 'text-green-400' : 'text-red-400'}`}>
                    ${p.total_pnl.toLocaleString(undefined, { minimumFractionDigits: 2 })}
                  </div>
                  <div className="text-xs text-gray-400">
                    {p.account_count} account{p.account_count !== 1 ? 's' : ''} | Balance: ${p.total_balance.toLocaleString(undefined, { minimumFractionDigits: 2 })}
                  </div>
                </div>
                <ChevronRight size={20} className="text-gray-500 ml-4" />
              </div>
            </div>
          ))}
        </div>
      )}

      {showCreate === 'portfolio' && (
        <CreateDialog
          title="Create Portfolio"
          fields={[
            { name: 'name', label: 'Portfolio Name', type: 'text', required: true, defaultValue: '' },
            { name: 'description', label: 'Description', type: 'text', defaultValue: '' },
          ]}
          onSubmit={async (data) => {
            await api.createPortfolio({ name: data.name as string, description: data.description as string });
            loadData();
          }}
          onClose={() => setShowCreate(null)}
        />
      )}
    </div>
  );

  // Portfolio Detail View
  const renderPortfolioDetail = () => {
    if (view.type !== 'portfolio') return null;
    return (
    <div>
      <div className="flex items-center justify-between mb-6">
        <div className="flex items-center gap-3">
          <button onClick={handleBack} className="p-2 hover:bg-slate-700 rounded-lg transition-colors">
            <ArrowLeft size={20} />
          </button>
          <div>
            <h1 className="text-2xl font-bold">{currentPortfolio?.name}</h1>
            <p className="text-sm text-gray-400">{currentPortfolio?.description}</p>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <button onClick={loadData} className="p-2 hover:bg-slate-700 rounded-lg transition-colors" title="Refresh">
            <RefreshCw size={16} />
          </button>
          <button
            onClick={() => setShowCreate('account')}
            className="flex items-center gap-2 px-4 py-2 bg-blue-600 hover:bg-blue-500 rounded-lg text-sm font-medium transition-colors"
          >
            <Plus size={16} /> Add Account
          </button>
          <button
            onClick={async () => {
              if (currentPortfolio && confirm('Delete this portfolio?')) {
                await api.deletePortfolio(currentPortfolio.id);
                setView({ type: 'portfolios' });
              }
            }}
            className="p-2 hover:bg-slate-700 rounded-lg text-gray-400 hover:text-red-400 transition-colors"
          >
            <Trash2 size={16} />
          </button>
        </div>
      </div>

      {stats && stats.total_trades > 0 && (
        <>
          <StatsCard stats={stats} title="Portfolio Statistics" />
          <div className="mt-4">
            <PeriodPnlView entityType="portfolio" entityId={view.portfolioId} onRecalculated={loadData} />
          </div>
        </>
      )}

      <div className="mt-6">
        <h2 className="text-lg font-semibold mb-4">Accounts</h2>
        {accounts.length === 0 ? (
          <div className="text-center py-12 text-gray-500">
            <Wallet size={40} className="mx-auto mb-3 opacity-50" />
            <p>No accounts yet. Add an exchange account to get started.</p>
          </div>
        ) : (
          <div className="grid gap-3">
            {accounts.map((a) => (
              <div
                key={a.id}
                onClick={() => setView({ type: 'account', accountId: a.id, portfolioId: view.portfolioId })}
                className="bg-slate-800 border border-slate-700 rounded-lg p-4 cursor-pointer hover:border-blue-500/50 transition-colors"
              >
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-3">
                    <div className="w-10 h-10 rounded-lg bg-slate-700 flex items-center justify-center">
                      <Wallet size={20} className="text-blue-400" />
                    </div>
                    <div>
                      <h3 className="font-medium">{a.name}</h3>
                      <p className="text-xs text-gray-400">
                        {a.exchange.replace('_', ' ').toUpperCase()} | {a.bot_count} bot{a.bot_count !== 1 ? 's' : ''} | {a.total_trades} trades
                      </p>
                    </div>
                  </div>
                  <div className="text-right flex items-center gap-4">
                    <div>
                      <div className="text-xs text-gray-400">Balance</div>
                      <div className="font-mono text-sm">
                        <EditableField
                          value={a.current_balance}
                          onSave={async (v) => {
                            await api.updateAccount(a.id, { current_balance: v as number });
                            loadData();
                          }}
                          prefix="$"
                        />
                      </div>
                    </div>
                    <div>
                      <div className="text-xs text-gray-400">P&L</div>
                      <div className={`font-mono text-sm font-medium ${a.total_pnl >= 0 ? 'text-green-400' : 'text-red-400'}`}>
                        ${a.total_pnl.toFixed(2)}
                      </div>
                    </div>
                    <div>
                      <div className="text-xs text-gray-400">Win Rate</div>
                      <div className="font-mono text-sm">{a.win_rate.toFixed(1)}%</div>
                    </div>
                    <ChevronRight size={20} className="text-gray-500" />
                  </div>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      {showCreate === 'account' && (
        <CreateDialog
          title="Add Exchange Account"
          fields={[
            { name: 'name', label: 'Account Name', type: 'text', required: true, defaultValue: '' },
            {
              name: 'exchange', label: 'Exchange', type: 'select',
              options: [
                { value: 'bitget_futures', label: 'Bitget Futures' },
                { value: 'phemex_futures', label: 'Phemex Futures' },
                { value: 'kraken', label: 'Kraken' },
              ],
              defaultValue: 'bitget_futures',
            },
            { name: 'initial_balance', label: 'Initial Balance ($)', type: 'number', defaultValue: 10000 },
          ]}
          onSubmit={async (data) => {
            await api.createAccount(view.portfolioId, {
              name: data.name as string,
              exchange: data.exchange as string,
              initial_balance: data.initial_balance as number,
            });
            loadData();
          }}
          onClose={() => setShowCreate(null)}
        />
      )}
    </div>
    );
  };

  // Account Detail View
  const renderAccountDetail = () => {
    if (view.type !== 'account') return null;
    return (
      <div>
        <div className="flex items-center justify-between mb-6">
          <div className="flex items-center gap-3">
            <button onClick={handleBack} className="p-2 hover:bg-slate-700 rounded-lg transition-colors">
              <ArrowLeft size={20} />
            </button>
            <div>
              <h1 className="text-2xl font-bold">{currentAccount?.name}</h1>
              <p className="text-xs text-gray-400">
                {currentAccount?.exchange.replace('_', ' ').toUpperCase()} | Initial: $
                {currentAccount?.initial_balance.toLocaleString()}
              </p>
            </div>
          </div>
          <div className="flex items-center gap-2">
            <button onClick={loadData} className="p-2 hover:bg-slate-700 rounded-lg transition-colors">
              <RefreshCw size={16} />
            </button>
            <button
              onClick={() => setShowCreate('bot')}
              className="flex items-center gap-2 px-4 py-2 bg-blue-600 hover:bg-blue-500 rounded-lg text-sm font-medium transition-colors"
            >
              <Plus size={16} /> Add Bot
            </button>
            <button
              onClick={async () => {
                if (currentAccount && confirm('Delete this account?')) {
                  await api.deleteAccount(currentAccount.id);
                  handleBack();
                }
              }}
              className="p-2 hover:bg-slate-700 rounded-lg text-gray-400 hover:text-red-400 transition-colors"
            >
              <Trash2 size={16} />
            </button>
          </div>
        </div>

        {stats && stats.total_trades > 0 && (
          <>
            <StatsCard stats={stats} title="Account Statistics" />
            <div className="mt-4">
              <PeriodPnlView entityType="account" entityId={view.accountId} onRecalculated={loadData} />
            </div>
          </>
        )}

        <div className="mt-6">
          <h2 className="text-lg font-semibold mb-4">Bots / Strategies</h2>
          {bots.length === 0 ? (
            <div className="text-center py-12 text-gray-500">
              <BotIcon size={40} className="mx-auto mb-3 opacity-50" />
              <p>No bots yet. Create a bot or strategy to start tracking trades.</p>
            </div>
          ) : (
            <div className="grid gap-3">
              {bots.map((b) => (
                <div
                  key={b.id}
                  onClick={() =>
                    setView({
                      type: 'bot',
                      botId: b.id,
                      accountId: view.accountId,
                      portfolioId: view.portfolioId,
                    })
                  }
                  className="bg-slate-800 border border-slate-700 rounded-lg p-4 cursor-pointer hover:border-blue-500/50 transition-colors"
                >
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-3">
                      <div className="w-10 h-10 rounded-lg bg-slate-700 flex items-center justify-center">
                        <BotIcon size={20} className={b.is_active ? 'text-green-400' : 'text-gray-400'} />
                      </div>
                      <div>
                        <h3 className="font-medium">{b.name}</h3>
                        <p className="text-xs text-gray-400">
                          {b.strategy_type} | {b.symbol} | {b.total_trades} trades
                        </p>
                      </div>
                    </div>
                    <div className="text-right flex items-center gap-4">
                      <div>
                        <div className="text-xs text-gray-400">P&L</div>
                        <div className={`font-mono text-sm font-medium ${b.total_pnl >= 0 ? 'text-green-400' : 'text-red-400'}`}>
                          ${b.total_pnl.toFixed(2)}
                        </div>
                      </div>
                      <div>
                        <div className="text-xs text-gray-400">Win Rate</div>
                        <div className="font-mono text-sm">{b.win_rate.toFixed(1)}%</div>
                      </div>
                      <div>
                        <div className="text-xs text-gray-400">Sharpe</div>
                        <div className="font-mono text-sm">{b.sharpe_ratio.toFixed(2)}</div>
                      </div>
                      <div>
                        <div className="text-xs text-gray-400">PF</div>
                        <div className="font-mono text-sm">{b.profit_factor.toFixed(2)}</div>
                      </div>
                      <ChevronRight size={20} className="text-gray-500" />
                    </div>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>

        {showCreate === 'bot' && (
          <CreateDialog
            title="Create Bot / Strategy"
            fields={[
              { name: 'name', label: 'Bot Name', type: 'text', required: true, defaultValue: '' },
              {
                name: 'strategy_type', label: 'Strategy Type', type: 'select',
                options: [
                  { value: 'manual', label: 'Manual Trading' },
                  { value: 'scalping', label: 'Scalping' },
                  { value: 'swing', label: 'Swing Trading' },
                  { value: 'grid', label: 'Grid Bot' },
                  { value: 'dca', label: 'DCA (Dollar Cost Avg)' },
                  { value: 'arbitrage', label: 'Arbitrage' },
                  { value: 'trend_following', label: 'Trend Following' },
                  { value: 'mean_reversion', label: 'Mean Reversion' },
                  { value: 'custom', label: 'Custom Algorithm' },
                ],
                defaultValue: 'manual',
              },
              { name: 'symbol', label: 'Trading Pair', type: 'text', defaultValue: 'BTC/USDT' },
            ]}
            onSubmit={async (data) => {
              await api.createBot(view.accountId, {
                name: data.name as string,
                strategy_type: data.strategy_type as string,
                symbol: data.symbol as string,
              });
              loadData();
            }}
            onClose={() => setShowCreate(null)}
          />
        )}
      </div>
    );
  };

  // Bot Detail View
  const renderBotDetail = () => {
    if (view.type !== 'bot') return null;
    return (
      <div>
        <div className="flex items-center justify-between mb-6">
          <div className="flex items-center gap-3">
            <button onClick={handleBack} className="p-2 hover:bg-slate-700 rounded-lg transition-colors">
              <ArrowLeft size={20} />
            </button>
            <div>
              <h1 className="text-2xl font-bold">{currentBot?.name}</h1>
              <p className="text-xs text-gray-400">
                {currentBot?.strategy_type} | {currentBot?.symbol} |{' '}
                <span className={currentBot?.is_active ? 'text-green-400' : 'text-gray-400'}>
                  {currentBot?.is_active ? 'Active' : 'Inactive'}
                </span>
              </p>
            </div>
          </div>
          <div className="flex items-center gap-2">
            <button onClick={loadData} className="p-2 hover:bg-slate-700 rounded-lg transition-colors">
              <RefreshCw size={16} />
            </button>
            <button
              onClick={() => setShowGenerateTrades(true)}
              className="flex items-center gap-2 px-4 py-2 bg-yellow-600 hover:bg-yellow-500 rounded-lg text-sm font-medium transition-colors"
            >
              <Zap size={16} /> Generate Trades
            </button>
            <button
              onClick={() => setShowCreate('trade')}
              className="flex items-center gap-2 px-4 py-2 bg-blue-600 hover:bg-blue-500 rounded-lg text-sm font-medium transition-colors"
            >
              <Plus size={16} /> Add Trade
            </button>
            <button
              onClick={async () => {
                if (currentBot && confirm('Delete this bot?')) {
                  await api.deleteBot(currentBot.id);
                  handleBack();
                }
              }}
              className="p-2 hover:bg-slate-700 rounded-lg text-gray-400 hover:text-red-400 transition-colors"
            >
              <Trash2 size={16} />
            </button>
          </div>
        </div>

        {/* Top-level editable stats */}
        {stats && (
          <div className="mb-4">
            <EditableStatsCard
              stats={stats}
              title="Bot Statistics"
              entityType="bot"
              entityId={view.botId}
              onRecalculated={loadData}
            />
          </div>
        )}

        {/* Period P&L Breakdown */}
        {stats && stats.total_trades > 0 && (
          <div className="mb-4">
            <PeriodPnlView entityType="bot" entityId={view.botId} onRecalculated={loadData} />
          </div>
        )}

        {/* P&L Chart */}
        {pnlRecords.length > 0 && (
          <div className="bg-slate-800 rounded-lg border border-slate-700 p-4 mb-4">
            <h3 className="text-sm font-medium text-gray-400 mb-3">P&L Charts</h3>
            <PnlChart records={pnlRecords} />
          </div>
        )}

        {/* Trades Table */}
        <div className="bg-slate-800 rounded-lg border border-slate-700 p-4">
          <div className="flex items-center justify-between mb-3">
            <h3 className="text-sm font-medium text-gray-400">
              Trades ({trades.length})
            </h3>
          </div>
          <TradeTable trades={trades} botId={view.botId} onRefresh={loadData} />
        </div>

        {showCreate === 'trade' && (
          <CreateTradeDialog
            botId={view.botId}
            defaultSymbol={currentBot?.symbol || 'BTC/USDT'}
            onClose={() => setShowCreate(null)}
            onCreated={loadData}
          />
        )}

        {showGenerateTrades && (
          <GenerateTradesDialog
            botId={view.botId}
            botSymbol={currentBot?.symbol || 'BTC/USDT'}
            onClose={() => setShowGenerateTrades(false)}
            onGenerated={loadData}
          />
        )}
      </div>
    );
  };

  return (
    <div className="min-h-screen bg-slate-900">
      {/* Header */}
      <header className="bg-slate-800/50 border-b border-slate-700 px-6 py-3">
        <div className="max-w-7xl mx-auto flex items-center justify-between">
          <div className="flex items-center gap-3">
            <TrendingUp size={24} className="text-blue-400" />
            <h1 className="text-lg font-bold">
              <span className="text-blue-400">Faide</span> Trader
            </h1>
            <span className="text-xs text-gray-500 bg-slate-700 px-2 py-0.5 rounded">Simulator</span>
          </div>
          <div className="flex items-center gap-4 text-sm text-gray-400">
            <button
              onClick={() => setShowMarketImport(true)}
              className="flex items-center gap-1 hover:text-blue-400 transition-colors"
            >
              <Download size={14} />
              Import Data
            </button>
            <span className="flex items-center gap-1">
              <BarChart3 size={14} />
              Simulator
            </span>
          </div>
        </div>
      </header>

      {/* Main Content */}
      <main className="max-w-7xl mx-auto px-6 py-6">
        {renderBreadcrumb()}

        {loading && (
          <div className="flex items-center justify-center py-4">
            <RefreshCw size={20} className="animate-spin text-blue-400" />
          </div>
        )}

        {view.type === 'portfolios' && renderPortfolios()}
        {view.type === 'portfolio' && renderPortfolioDetail()}
        {view.type === 'account' && renderAccountDetail()}
        {view.type === 'bot' && renderBotDetail()}
      </main>

      {showMarketImport && (
        <MarketDataImportDialog
          onClose={() => setShowMarketImport(false)}
          onImported={loadData}
        />
      )}
    </div>
  );
}

export default App;
