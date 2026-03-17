import { useState, useEffect } from 'react';
import { api, type SymbolPnl } from '@/lib/api';
import { TrendingUp, TrendingDown } from 'lucide-react';

interface SymbolPnlViewProps {
  botId: number;
  onRefresh?: () => void;
}

export function SymbolPnlView({ botId }: SymbolPnlViewProps) {
  const [symbolPnls, setSymbolPnls] = useState<SymbolPnl[]>([]);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    setLoading(true);
    api.getSymbolPnl(botId)
      .then(setSymbolPnls)
      .catch(console.error)
      .finally(() => setLoading(false));
  }, [botId]);

  if (loading) {
    return (
      <div className="bg-slate-800 rounded-lg border border-slate-700 p-4">
        <h3 className="text-sm font-medium text-gray-400 mb-3">Per-Symbol P&L</h3>
        <div className="text-center py-4 text-gray-500 text-sm">Loading...</div>
      </div>
    );
  }

  if (symbolPnls.length <= 1) {
    return null;
  }

  const totalPnl = symbolPnls.reduce((sum, s) => sum + s.total_pnl, 0);

  return (
    <div className="bg-slate-800 rounded-lg border border-slate-700 p-4">
      <h3 className="text-sm font-medium text-gray-400 mb-3">Per-Symbol P&L Breakdown</h3>
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="text-xs text-gray-500 border-b border-slate-700">
              <th className="text-left py-2 px-2">Symbol</th>
              <th className="text-right py-2 px-2">P&L</th>
              <th className="text-right py-2 px-2">% of Total</th>
              <th className="text-right py-2 px-2">Trades</th>
              <th className="text-right py-2 px-2">W/L</th>
              <th className="text-right py-2 px-2">Win Rate</th>
              <th className="text-right py-2 px-2">Avg P&L</th>
            </tr>
          </thead>
          <tbody>
            {symbolPnls.map((sp) => (
              <tr key={sp.symbol} className="border-b border-slate-700/50 hover:bg-slate-700/30">
                <td className="py-2 px-2 font-medium">{sp.symbol}</td>
                <td className={`py-2 px-2 text-right font-mono ${sp.total_pnl >= 0 ? 'text-green-400' : 'text-red-400'}`}>
                  <span className="inline-flex items-center gap-1">
                    {sp.total_pnl >= 0 ? <TrendingUp size={12} /> : <TrendingDown size={12} />}
                    ${sp.total_pnl.toLocaleString(undefined, { minimumFractionDigits: 2 })}
                  </span>
                </td>
                <td className="py-2 px-2 text-right font-mono text-gray-400">
                  {totalPnl !== 0 ? `${((sp.total_pnl / totalPnl) * 100).toFixed(1)}%` : '-'}
                </td>
                <td className="py-2 px-2 text-right font-mono">{sp.total_trades}</td>
                <td className="py-2 px-2 text-right font-mono">
                  <span className="text-green-400">{sp.win_count}</span>
                  <span className="text-gray-500">/</span>
                  <span className="text-red-400">{sp.loss_count}</span>
                </td>
                <td className="py-2 px-2 text-right font-mono">{sp.win_rate.toFixed(1)}%</td>
                <td className={`py-2 px-2 text-right font-mono ${sp.avg_pnl >= 0 ? 'text-green-400' : 'text-red-400'}`}>
                  ${sp.avg_pnl.toFixed(2)}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
