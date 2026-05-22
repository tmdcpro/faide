import { useState, useEffect, useCallback } from 'react';
import {
  ComposedChart,
  Area,
  Line,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  ReferenceDot,
} from 'recharts';
import { api, type EquityCurvePoint } from '@/lib/api';
import {
  TrendingUp,
  Eye,
  EyeOff,
} from 'lucide-react';

interface EquityChartProps {
  entityType: 'account' | 'portfolio';
  entityId: number;
}

interface ToggleState {
  balance: boolean;
  pnl: boolean;
  drawdown: boolean;
  deposits: boolean;
  withdrawals: boolean;
  dailyPnl: boolean;
  peakBalance: boolean;
}

function formatCurrency(v: number): string {
  return `$${v.toLocaleString(undefined, { minimumFractionDigits: 0, maximumFractionDigits: 0 })}`;
}

function formatDate(dateStr: string): string {
  const d = new Date(dateStr + 'T00:00:00');
  return d.toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: '2-digit' });
}

function CustomTooltip({ active, payload }: { active?: boolean; payload?: Array<{ dataKey: string; value: number; color: string }> }) {
  if (!active || !payload || payload.length === 0) return null;

  const point = payload[0]?.payload as EquityCurvePoint & { _dateFormatted: string };
  if (!point) return null;

  return (
    <div className="bg-slate-800 border border-slate-600 rounded-lg p-3 shadow-xl text-xs min-w-[220px]">
      <div className="text-gray-300 font-medium mb-2 border-b border-slate-700 pb-1">
        {new Date(point.date + 'T00:00:00').toLocaleDateString('en-US', { weekday: 'short', month: 'short', day: 'numeric', year: 'numeric' })}
      </div>

      <div className="space-y-1">
        <div className="flex justify-between">
          <span className="text-gray-400">Balance</span>
          <span className="text-white font-mono font-medium">{formatCurrency(point.balance)}</span>
        </div>
        <div className="flex justify-between">
          <span className="text-gray-400">Cumul. P&L</span>
          <span className={`font-mono font-medium ${point.cumulative_pnl >= 0 ? 'text-green-400' : 'text-red-400'}`}>
            {formatCurrency(point.cumulative_pnl)}
          </span>
        </div>
        <div className="flex justify-between">
          <span className="text-gray-400">Daily P&L</span>
          <span className={`font-mono ${point.daily_pnl >= 0 ? 'text-green-400' : 'text-red-400'}`}>
            {point.daily_pnl !== 0 ? formatCurrency(point.daily_pnl) : '-'}
          </span>
        </div>

        {point.drawdown > 0 && (
          <div className="flex justify-between">
            <span className="text-gray-400">Drawdown</span>
            <span className="text-red-400 font-mono">
              {formatCurrency(point.drawdown)} ({point.drawdown_percent.toFixed(1)}%)
            </span>
          </div>
        )}

        {point.trade_count > 0 && (
          <div className="flex justify-between border-t border-slate-700 pt-1 mt-1">
            <span className="text-gray-400">Trades</span>
            <span className="text-gray-300 font-mono">
              {point.trade_count} ({point.win_count}W / {point.loss_count}L) — {point.win_rate}%
            </span>
          </div>
        )}

        {point.deposits > 0 && (
          <div className="flex justify-between">
            <span className="text-green-400">↑ Deposit</span>
            <span className="text-green-400 font-mono font-medium">{formatCurrency(point.deposits)}</span>
          </div>
        )}
        {point.withdrawals > 0 && (
          <div className="flex justify-between">
            <span className="text-orange-400">↓ Withdrawal</span>
            <span className="text-orange-400 font-mono font-medium">{formatCurrency(point.withdrawals)}</span>
          </div>
        )}

        <div className="flex justify-between border-t border-slate-700 pt-1 mt-1">
          <span className="text-gray-400">Net Deposits</span>
          <span className="text-blue-400 font-mono">{formatCurrency(point.net_deposits_cumulative)}</span>
        </div>
        <div className="flex justify-between">
          <span className="text-gray-400">Peak</span>
          <span className="text-gray-300 font-mono">{formatCurrency(point.peak_balance)}</span>
        </div>
      </div>
    </div>
  );
}

const TOGGLE_BUTTONS: { key: keyof ToggleState; label: string; color: string }[] = [
  { key: 'balance', label: 'Balance', color: '#3b82f6' },
  { key: 'pnl', label: 'Trading P&L', color: '#22c55e' },
  { key: 'drawdown', label: 'Drawdown', color: '#ef4444' },
  { key: 'deposits', label: 'Deposits', color: '#4ade80' },
  { key: 'withdrawals', label: 'Withdrawals', color: '#fb923c' },
  { key: 'dailyPnl', label: 'Daily P&L', color: '#a78bfa' },
  { key: 'peakBalance', label: 'Peak', color: '#94a3b8' },
];

export function EquityChart({ entityType, entityId }: EquityChartProps) {
  const [data, setData] = useState<EquityCurvePoint[]>([]);
  const [loading, setLoading] = useState(false);
  const [toggles, setToggles] = useState<ToggleState>({
    balance: true,
    pnl: true,
    drawdown: true,
    deposits: true,
    withdrawals: true,
    dailyPnl: false,
    peakBalance: false,
  });

  const loadData = useCallback(async () => {
    setLoading(true);
    try {
      const curve = entityType === 'account'
        ? await api.getAccountEquityCurve(entityId)
        : await api.getPortfolioEquityCurve(entityId);
      setData(curve);
    } catch (e) {
      console.error('Failed to load equity curve:', e);
    } finally {
      setLoading(false);
    }
  }, [entityType, entityId]);

  useEffect(() => {
    loadData();
  }, [loadData]);

  const toggle = (key: keyof ToggleState) => {
    setToggles((prev) => ({ ...prev, [key]: !prev[key] }));
  };

  if (loading) {
    return (
      <div className="bg-slate-800 rounded-lg border border-slate-700 p-4">
        <div className="text-center py-12 text-gray-500 text-sm">Loading equity curve...</div>
      </div>
    );
  }

  if (data.length === 0) {
    return (
      <div className="bg-slate-800 rounded-lg border border-slate-700 p-4">
        <div className="text-center py-12 text-gray-500 text-sm">No equity data available</div>
      </div>
    );
  }

  // Prepare chart data with formatted date for XAxis
  const chartData = data.map((p) => ({
    ...p,
    _dateFormatted: formatDate(p.date),
    _drawdownNeg: -p.drawdown,
    _drawdownPctNeg: -p.drawdown_percent,
  }));

  // Compute summary stats
  const lastPoint = data[data.length - 1];
  const firstPoint = data[0];
  const maxDrawdown = Math.max(...data.map((d) => d.drawdown));
  const maxDrawdownPct = Math.max(...data.map((d) => d.drawdown_percent));
  const totalDeposits = data.reduce((sum, d) => sum + d.deposits, 0);
  const totalWithdrawals = data.reduce((sum, d) => sum + d.withdrawals, 0);
  const depositDays = data.filter((d) => d.deposits > 0);
  const withdrawalDays = data.filter((d) => d.withdrawals > 0);

  // Determine tick interval based on data length
  const tickInterval = data.length > 365 ? Math.floor(data.length / 12) : data.length > 90 ? Math.floor(data.length / 8) : undefined;

  return (
    <div className="bg-slate-800 rounded-lg border border-slate-700 p-4">
      <div className="flex items-center justify-between mb-3">
        <h3 className="text-sm font-medium text-gray-400 flex items-center gap-2">
          <TrendingUp size={16} />
          Equity Curve
        </h3>
        <div className="flex items-center gap-3 text-xs">
          <div className="text-gray-400">
            Balance: <span className="text-white font-mono font-medium">{formatCurrency(lastPoint.balance)}</span>
          </div>
          <div className="text-gray-400">
            P&L: <span className={`font-mono font-medium ${lastPoint.cumulative_pnl >= 0 ? 'text-green-400' : 'text-red-400'}`}>
              {formatCurrency(lastPoint.cumulative_pnl)}
            </span>
          </div>
          <div className="text-gray-400">
            Max DD: <span className="text-red-400 font-mono">{formatCurrency(maxDrawdown)} ({maxDrawdownPct.toFixed(1)}%)</span>
          </div>
        </div>
      </div>

      {/* Toggle buttons */}
      <div className="flex flex-wrap gap-1.5 mb-3">
        {TOGGLE_BUTTONS.map(({ key, label, color }) => (
          <button
            key={key}
            onClick={() => toggle(key)}
            className={`flex items-center gap-1 px-2 py-1 rounded text-xs font-medium transition-all ${
              toggles[key]
                ? 'bg-slate-700 text-white border border-slate-500'
                : 'bg-slate-800 text-gray-500 border border-slate-700 hover:border-slate-600'
            }`}
          >
            <div
              className="w-2 h-2 rounded-full"
              style={{ backgroundColor: toggles[key] ? color : '#475569' }}
            />
            {toggles[key] ? <Eye size={10} /> : <EyeOff size={10} />}
            {label}
          </button>
        ))}
      </div>

      {/* Main Chart */}
      <ResponsiveContainer width="100%" height={400}>
        <ComposedChart data={chartData} margin={{ top: 5, right: 10, left: 10, bottom: 5 }}>
          <defs>
            <linearGradient id="balanceGrad" x1="0" y1="0" x2="0" y2="1">
              <stop offset="5%" stopColor="#3b82f6" stopOpacity={0.3} />
              <stop offset="95%" stopColor="#3b82f6" stopOpacity={0.02} />
            </linearGradient>
            <linearGradient id="pnlGrad" x1="0" y1="0" x2="0" y2="1">
              <stop offset="5%" stopColor="#22c55e" stopOpacity={0.2} />
              <stop offset="95%" stopColor="#22c55e" stopOpacity={0.02} />
            </linearGradient>
            <linearGradient id="drawdownGrad" x1="0" y1="1" x2="0" y2="0">
              <stop offset="5%" stopColor="#ef4444" stopOpacity={0.3} />
              <stop offset="95%" stopColor="#ef4444" stopOpacity={0.02} />
            </linearGradient>
          </defs>
          <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" />
          <XAxis
            dataKey="_dateFormatted"
            tick={{ fontSize: 10, fill: '#64748b' }}
            interval={tickInterval}
            angle={-30}
            textAnchor="end"
            height={50}
          />
          <YAxis
            yAxisId="left"
            tick={{ fontSize: 10, fill: '#64748b' }}
            tickFormatter={(v) => `$${(v / 1000).toFixed(0)}k`}
            width={55}
          />
          {toggles.dailyPnl && (
            <YAxis
              yAxisId="right"
              orientation="right"
              tick={{ fontSize: 10, fill: '#64748b' }}
              tickFormatter={(v) => `$${v}`}
              width={50}
            />
          )}
          <Tooltip content={<CustomTooltip />} />

          {/* Drawdown zone (below zero on left axis) */}
          {toggles.drawdown && (
            <Area
              yAxisId="left"
              type="monotone"
              dataKey="_drawdownNeg"
              stroke="none"
              fill="url(#drawdownGrad)"
              fillOpacity={1}
              isAnimationActive={false}
            />
          )}

          {/* Balance area */}
          {toggles.balance && (
            <Area
              yAxisId="left"
              type="monotone"
              dataKey="balance"
              stroke="#3b82f6"
              fill="url(#balanceGrad)"
              strokeWidth={2}
              isAnimationActive={false}
            />
          )}

          {/* Peak balance line */}
          {toggles.peakBalance && (
            <Line
              yAxisId="left"
              type="monotone"
              dataKey="peak_balance"
              stroke="#64748b"
              strokeWidth={1}
              strokeDasharray="4 4"
              dot={false}
              isAnimationActive={false}
            />
          )}

          {/* Cumulative P&L line */}
          {toggles.pnl && (
            <Line
              yAxisId="left"
              type="monotone"
              dataKey="cumulative_pnl"
              stroke="#22c55e"
              strokeWidth={1.5}
              dot={false}
              isAnimationActive={false}
            />
          )}

          {/* Daily P&L bars */}
          {toggles.dailyPnl && (
            <Bar
              yAxisId="right"
              dataKey="daily_pnl"
              fill="#a78bfa"
              opacity={0.5}
              isAnimationActive={false}
            />
          )}

          {/* Deposit markers */}
          {toggles.deposits && depositDays.map((d) => (
            <ReferenceDot
              key={`dep-${d.date}`}
              x={formatDate(d.date)}
              y={chartData.find((c) => c.date === d.date)?.balance ?? 0}
              yAxisId="left"
              r={4}
              fill="#4ade80"
              stroke="#166534"
              strokeWidth={1}
            />
          ))}

          {/* Withdrawal markers */}
          {toggles.withdrawals && withdrawalDays.map((d) => (
            <ReferenceDot
              key={`wd-${d.date}`}
              x={formatDate(d.date)}
              y={chartData.find((c) => c.date === d.date)?.balance ?? 0}
              yAxisId="left"
              r={4}
              fill="#fb923c"
              stroke="#9a3412"
              strokeWidth={1}
            />
          ))}

          {/* Drawdown line */}
          {toggles.drawdown && (
            <Line
              yAxisId="left"
              type="monotone"
              dataKey="_drawdownNeg"
              stroke="#ef4444"
              strokeWidth={1}
              dot={false}
              isAnimationActive={false}
            />
          )}
        </ComposedChart>
      </ResponsiveContainer>

      {/* Summary stats below chart */}
      <div className="grid grid-cols-2 sm:grid-cols-4 lg:grid-cols-6 gap-3 mt-4 text-xs">
        <div className="bg-slate-700/50 rounded-lg p-2">
          <div className="text-gray-500 mb-0.5">Starting Balance</div>
          <div className="text-white font-mono font-medium">{formatCurrency(firstPoint.balance)}</div>
        </div>
        <div className="bg-slate-700/50 rounded-lg p-2">
          <div className="text-gray-500 mb-0.5">Current Balance</div>
          <div className="text-white font-mono font-medium">{formatCurrency(lastPoint.balance)}</div>
        </div>
        <div className="bg-slate-700/50 rounded-lg p-2">
          <div className="text-gray-500 mb-0.5">Trading P&L</div>
          <div className={`font-mono font-medium ${lastPoint.cumulative_pnl >= 0 ? 'text-green-400' : 'text-red-400'}`}>
            {formatCurrency(lastPoint.cumulative_pnl)}
          </div>
        </div>
        <div className="bg-slate-700/50 rounded-lg p-2">
          <div className="text-gray-500 mb-0.5">Max Drawdown</div>
          <div className="text-red-400 font-mono font-medium">
            {formatCurrency(maxDrawdown)} <span className="text-gray-500">({maxDrawdownPct.toFixed(1)}%)</span>
          </div>
        </div>
        <div className="bg-slate-700/50 rounded-lg p-2">
          <div className="text-gray-500 mb-0.5">Total Deposits</div>
          <div className="text-green-400 font-mono font-medium">
            {formatCurrency(totalDeposits)} <span className="text-gray-500">({depositDays.length}x)</span>
          </div>
        </div>
        <div className="bg-slate-700/50 rounded-lg p-2">
          <div className="text-gray-500 mb-0.5">Total Withdrawals</div>
          <div className="text-orange-400 font-mono font-medium">
            {formatCurrency(totalWithdrawals)} <span className="text-gray-500">({withdrawalDays.length}x)</span>
          </div>
        </div>
      </div>
    </div>
  );
}
