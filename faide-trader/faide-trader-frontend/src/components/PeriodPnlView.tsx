import { useState, useEffect, useCallback } from 'react';
import { api, type PeriodPnl } from '@/lib/api';
import { EditableField } from '@/components/EditableField';
import { BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Cell } from 'recharts';
import { TrendingDown } from 'lucide-react';

interface PeriodPnlViewProps {
  entityType: 'bot' | 'account' | 'portfolio';
  entityId: number;
  onRecalculated?: () => void;
}

const PERIOD_TABS = [
  { key: 'monthly', label: 'Monthly' },
  { key: 'weekly', label: 'Weekly' },
  { key: 'daily', label: 'Daily' },
];

function formatNum(n: number, decimals = 2): string {
  return n.toLocaleString(undefined, { minimumFractionDigits: decimals, maximumFractionDigits: decimals });
}

export function PeriodPnlView({ entityType, entityId, onRecalculated }: PeriodPnlViewProps) {
  const [periodType, setPeriodType] = useState('monthly');
  const [periods, setPeriods] = useState<PeriodPnl[]>([]);
  const [loading, setLoading] = useState(false);

  const loadPeriods = useCallback(async () => {
    setLoading(true);
    try {
      let data: PeriodPnl[];
      if (entityType === 'bot') {
        data = await api.getBotPeriodPnl(entityId, periodType);
      } else if (entityType === 'account') {
        data = await api.getAccountPeriodPnl(entityId, periodType);
      } else {
        data = await api.getPortfolioPeriodPnl(entityId, periodType);
      }
      setPeriods(data);
    } catch (e) {
      console.error('Failed to load period P&L:', e);
    } finally {
      setLoading(false);
    }
  }, [entityType, entityId, periodType]);

  useEffect(() => {
    loadPeriods();
  }, [loadPeriods]);

  const handlePeriodPnlEdit = async (periodKey: string, newPnl: number) => {
    if (entityType !== 'bot') return;
    try {
      await api.updatePeriodPnl(entityId, periodKey, { pnl: newPnl }, periodType);
      await loadPeriods();
      onRecalculated?.();
    } catch (e) {
      console.error('Failed to update period P&L:', e);
    }
  };

  const chartData = periods.map((p) => ({
    period: p.period,
    pnl: p.pnl,
    drawdown: -p.drawdown,
  }));

  return (
    <div className="bg-slate-800 rounded-lg border border-slate-700 p-4">
      <div className="flex items-center justify-between mb-3">
        <h3 className="text-sm font-medium text-gray-400 flex items-center gap-2">
          <TrendingDown size={16} />
          Period P&L Breakdown
        </h3>
        <div className="flex gap-1">
          {PERIOD_TABS.map((tab) => (
            <button
              key={tab.key}
              onClick={() => setPeriodType(tab.key)}
              className={`px-3 py-1 text-xs rounded transition-colors ${
                periodType === tab.key
                  ? 'bg-blue-600 text-white'
                  : 'bg-slate-700 text-gray-400 hover:bg-slate-600'
              }`}
            >
              {tab.label}
            </button>
          ))}
        </div>
      </div>

      {loading ? (
        <div className="text-center py-8 text-gray-500 text-sm">Loading...</div>
      ) : periods.length === 0 ? (
        <div className="text-center py-8 text-gray-500 text-sm">No data for this period type</div>
      ) : (
        <>
          {/* P&L Bar Chart */}
          <div className="mb-4">
            <ResponsiveContainer width="100%" height={200}>
              <BarChart data={chartData}>
                <CartesianGrid strokeDasharray="3 3" stroke="#334155" />
                <XAxis
                  dataKey="period"
                  tick={{ fontSize: 10, fill: '#94a3b8' }}
                  angle={-45}
                  textAnchor="end"
                  height={60}
                />
                <YAxis tick={{ fontSize: 11, fill: '#94a3b8' }} tickFormatter={(v) => `$${v}`} />
                <Tooltip
                  contentStyle={{ backgroundColor: '#1e293b', border: '1px solid #334155', borderRadius: '8px' }}
                  labelStyle={{ color: '#94a3b8' }}
                  formatter={(value: number) => [`$${formatNum(value)}`, 'P&L']}
                />
                <Bar dataKey="pnl" radius={[2, 2, 0, 0]}>
                  {chartData.map((entry, index) => (
                    <Cell key={index} fill={entry.pnl >= 0 ? '#22c55e' : '#ef4444'} />
                  ))}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          </div>

          {/* Period Table */}
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="text-xs text-gray-500 border-b border-slate-700">
                  <th className="text-left py-2 px-2">Period</th>
                  <th className="text-right py-2 px-2">P&L</th>
                  <th className="text-right py-2 px-2">Cumulative</th>
                  <th className="text-right py-2 px-2">Trades</th>
                  <th className="text-right py-2 px-2">W/L</th>
                  <th className="text-right py-2 px-2">Win %</th>
                  <th className="text-right py-2 px-2">DD $</th>
                  <th className="text-right py-2 px-2">DD %</th>
                </tr>
              </thead>
              <tbody>
                {periods.map((p) => (
                  <tr key={p.period} className="border-b border-slate-700/50 hover:bg-slate-700/30">
                    <td className="py-2 px-2 font-mono text-xs">{p.period}</td>
                    <td className="text-right py-2 px-2">
                      {entityType === 'bot' ? (
                        <EditableField
                          value={p.pnl}
                          onSave={(v) => handlePeriodPnlEdit(p.period, v as number)}
                          prefix="$"
                          className={p.pnl >= 0 ? 'text-green-400' : 'text-red-400'}
                        />
                      ) : (
                        <span className={`font-mono ${p.pnl >= 0 ? 'text-green-400' : 'text-red-400'}`}>
                          ${formatNum(p.pnl)}
                        </span>
                      )}
                    </td>
                    <td className={`text-right py-2 px-2 font-mono ${p.cumulative_pnl >= 0 ? 'text-green-400' : 'text-red-400'}`}>
                      ${formatNum(p.cumulative_pnl)}
                    </td>
                    <td className="text-right py-2 px-2 font-mono">{p.trade_count}</td>
                    <td className="text-right py-2 px-2 font-mono text-xs">
                      <span className="text-green-400">{p.win_count}</span>
                      /
                      <span className="text-red-400">{p.loss_count}</span>
                    </td>
                    <td className={`text-right py-2 px-2 font-mono ${p.win_rate >= 50 ? 'text-green-400' : 'text-red-400'}`}>
                      {formatNum(p.win_rate)}%
                    </td>
                    <td className="text-right py-2 px-2 font-mono text-red-400">
                      {p.drawdown > 0 ? `$${formatNum(p.drawdown)}` : '-'}
                    </td>
                    <td className="text-right py-2 px-2 font-mono text-red-400">
                      {p.drawdown_percent > 0 ? `${formatNum(p.drawdown_percent)}%` : '-'}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      )}
    </div>
  );
}
