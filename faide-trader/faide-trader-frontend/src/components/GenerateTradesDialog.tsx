import { useState } from 'react';
import { api } from '@/lib/api';
import { X, Zap, Loader2 } from 'lucide-react';

interface GenerateTradesDialogProps {
  botId: number;
  botSymbol: string;
  onClose: () => void;
  onGenerated: () => void;
}

export function GenerateTradesDialog({ botId, botSymbol, onClose, onGenerated }: GenerateTradesDialogProps) {
  const [startDate, setStartDate] = useState(() => {
    const d = new Date();
    d.setMonth(d.getMonth() - 3);
    return d.toISOString().split('T')[0];
  });
  const [endDate, setEndDate] = useState(() => new Date().toISOString().split('T')[0]);
  const [numTrades, setNumTrades] = useState(50);
  const [winRate, setWinRate] = useState(55);
  const [avgPnlPct, setAvgPnlPct] = useState(2.0);
  const [baseQuantity, setBaseQuantity] = useState(0.1);
  const [baseLeverage, setBaseLeverage] = useState(5.0);
  const [baseFee, setBaseFee] = useState(2.0);
  const [basePrice, setBasePrice] = useState(50000);
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<{ generated: number } | null>(null);
  const [error, setError] = useState<string | null>(null);

  const handleGenerate = async () => {
    setLoading(true);
    setError(null);
    setResult(null);
    try {
      const res = await api.generateTrades(botId, {
        start_date: startDate,
        end_date: endDate,
        num_trades: numTrades,
        win_rate_target: winRate,
        avg_pnl_percent: avgPnlPct,
        base_quantity: baseQuantity,
        base_leverage: baseLeverage,
        base_fee: baseFee,
        base_price: basePrice,
      });
      setResult(res);
      onGenerated();
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Generation failed');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50" onClick={onClose}>
      <div className="bg-slate-800 border border-slate-700 rounded-lg w-full max-w-lg p-6 max-h-[90vh] overflow-y-auto" onClick={(e) => e.stopPropagation()}>
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-lg font-semibold flex items-center gap-2">
            <Zap size={20} className="text-yellow-400" />
            Generate Simulated Trades
          </h2>
          <button onClick={onClose} className="p-1 hover:bg-slate-700 rounded">
            <X size={18} />
          </button>
        </div>

        <p className="text-xs text-gray-400 mb-4">
          Generate realistic simulated trades for <span className="text-blue-400">{botSymbol}</span>.
          Uses imported market data for realistic prices when available.
        </p>

        <div className="space-y-3">
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="block text-xs text-gray-400 mb-1">Start Date</label>
              <input
                type="date"
                value={startDate}
                onChange={(e) => setStartDate(e.target.value)}
                className="w-full bg-slate-700 border border-slate-600 rounded px-3 py-2 text-sm"
              />
            </div>
            <div>
              <label className="block text-xs text-gray-400 mb-1">End Date</label>
              <input
                type="date"
                value={endDate}
                onChange={(e) => setEndDate(e.target.value)}
                className="w-full bg-slate-700 border border-slate-600 rounded px-3 py-2 text-sm"
              />
            </div>
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="block text-xs text-gray-400 mb-1"># Trades</label>
              <input
                type="number"
                value={numTrades}
                onChange={(e) => setNumTrades(parseInt(e.target.value) || 1)}
                min={1}
                max={1000}
                className="w-full bg-slate-700 border border-slate-600 rounded px-3 py-2 text-sm"
              />
            </div>
            <div>
              <label className="block text-xs text-gray-400 mb-1">Target Win Rate (%)</label>
              <input
                type="number"
                value={winRate}
                onChange={(e) => setWinRate(parseFloat(e.target.value) || 50)}
                min={0}
                max={100}
                step={1}
                className="w-full bg-slate-700 border border-slate-600 rounded px-3 py-2 text-sm"
              />
            </div>
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="block text-xs text-gray-400 mb-1">Avg P&L per Trade (%)</label>
              <input
                type="number"
                value={avgPnlPct}
                onChange={(e) => setAvgPnlPct(parseFloat(e.target.value) || 1)}
                min={0.1}
                step={0.5}
                className="w-full bg-slate-700 border border-slate-600 rounded px-3 py-2 text-sm"
              />
            </div>
            <div>
              <label className="block text-xs text-gray-400 mb-1">Base Price ($)</label>
              <input
                type="number"
                value={basePrice}
                onChange={(e) => setBasePrice(parseFloat(e.target.value) || 50000)}
                min={0.01}
                step={100}
                className="w-full bg-slate-700 border border-slate-600 rounded px-3 py-2 text-sm"
              />
              <p className="text-xs text-gray-500 mt-0.5">Used if no market data imported</p>
            </div>
          </div>

          <div className="grid grid-cols-3 gap-3">
            <div>
              <label className="block text-xs text-gray-400 mb-1">Quantity</label>
              <input
                type="number"
                value={baseQuantity}
                onChange={(e) => setBaseQuantity(parseFloat(e.target.value) || 0.1)}
                min={0.001}
                step={0.01}
                className="w-full bg-slate-700 border border-slate-600 rounded px-3 py-2 text-sm"
              />
            </div>
            <div>
              <label className="block text-xs text-gray-400 mb-1">Leverage</label>
              <input
                type="number"
                value={baseLeverage}
                onChange={(e) => setBaseLeverage(parseFloat(e.target.value) || 1)}
                min={1}
                max={125}
                step={1}
                className="w-full bg-slate-700 border border-slate-600 rounded px-3 py-2 text-sm"
              />
            </div>
            <div>
              <label className="block text-xs text-gray-400 mb-1">Fee ($)</label>
              <input
                type="number"
                value={baseFee}
                onChange={(e) => setBaseFee(parseFloat(e.target.value) || 0)}
                min={0}
                step={0.5}
                className="w-full bg-slate-700 border border-slate-600 rounded px-3 py-2 text-sm"
              />
            </div>
          </div>

          {error && (
            <div className="bg-red-900/30 border border-red-700 rounded p-3 text-sm text-red-400">
              {error}
            </div>
          )}

          {result && (
            <div className="bg-green-900/30 border border-green-700 rounded p-3 text-sm text-green-400">
              Generated {result.generated} trades successfully!
            </div>
          )}

          <div className="flex justify-end gap-2 pt-2">
            <button
              onClick={onClose}
              className="px-4 py-2 text-sm rounded bg-slate-700 hover:bg-slate-600 transition-colors"
            >
              Close
            </button>
            <button
              onClick={handleGenerate}
              disabled={loading}
              className="px-4 py-2 text-sm rounded bg-yellow-600 hover:bg-yellow-500 disabled:opacity-50 disabled:cursor-not-allowed transition-colors flex items-center gap-2"
            >
              {loading && <Loader2 size={14} className="animate-spin" />}
              {loading ? 'Generating...' : 'Generate Trades'}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
