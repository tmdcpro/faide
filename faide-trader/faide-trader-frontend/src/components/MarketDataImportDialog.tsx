import { useState } from 'react';
import { api } from '@/lib/api';
import { X, Download, Loader2 } from 'lucide-react';

interface MarketDataImportDialogProps {
  onClose: () => void;
  onImported?: () => void;
}

const EXCHANGES = [
  { id: 'bitget_futures', name: 'Bitget Futures' },
  { id: 'phemex_futures', name: 'Phemex Futures' },
  { id: 'kraken', name: 'Kraken' },
];

const TIMEFRAMES = [
  { value: '1m', label: '1 Minute' },
  { value: '5m', label: '5 Minutes' },
  { value: '15m', label: '15 Minutes' },
  { value: '1h', label: '1 Hour' },
  { value: '4h', label: '4 Hours' },
  { value: '1d', label: '1 Day' },
  { value: '1w', label: '1 Week' },
];

export function MarketDataImportDialog({ onClose, onImported }: MarketDataImportDialogProps) {
  const [exchange, setExchange] = useState('bitget_futures');
  const [symbol, setSymbol] = useState('BTC/USDT:USDT');
  const [timeframe, setTimeframe] = useState('1d');
  const [startDate, setStartDate] = useState(() => {
    const d = new Date();
    d.setMonth(d.getMonth() - 1);
    return d.toISOString().split('T')[0];
  });
  const [endDate, setEndDate] = useState(() => new Date().toISOString().split('T')[0]);
  const [limit, setLimit] = useState(365);
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<{ imported: number; exchange: string; symbol: string } | null>(null);
  const [error, setError] = useState<string | null>(null);

  const handleImport = async () => {
    setLoading(true);
    setError(null);
    setResult(null);
    try {
      const res = await api.importMarketData({
        exchange,
        symbol,
        timeframe,
        since: startDate,
        end_date: endDate,
        limit,
      });
      setResult(res);
      onImported?.();
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Import failed');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50" onClick={onClose}>
      <div className="bg-slate-800 border border-slate-700 rounded-lg w-full max-w-lg p-6" onClick={(e) => e.stopPropagation()}>
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-lg font-semibold flex items-center gap-2">
            <Download size={20} className="text-blue-400" />
            Import Market Data
          </h2>
          <button onClick={onClose} className="p-1 hover:bg-slate-700 rounded">
            <X size={18} />
          </button>
        </div>

        <div className="space-y-4">
          <div>
            <label className="block text-xs text-gray-400 mb-1">Exchange</label>
            <select
              value={exchange}
              onChange={(e) => setExchange(e.target.value)}
              className="w-full bg-slate-700 border border-slate-600 rounded px-3 py-2 text-sm"
            >
              {EXCHANGES.map((ex) => (
                <option key={ex.id} value={ex.id}>{ex.name}</option>
              ))}
            </select>
          </div>

          <div>
            <label className="block text-xs text-gray-400 mb-1">Symbol</label>
            <input
              type="text"
              value={symbol}
              onChange={(e) => setSymbol(e.target.value)}
              placeholder="BTC/USDT:USDT"
              className="w-full bg-slate-700 border border-slate-600 rounded px-3 py-2 text-sm"
            />
            <p className="text-xs text-gray-500 mt-1">
              Futures: BTC/USDT:USDT | Spot: BTC/USDT
            </p>
          </div>

          <div>
            <label className="block text-xs text-gray-400 mb-1">Timeframe</label>
            <select
              value={timeframe}
              onChange={(e) => setTimeframe(e.target.value)}
              className="w-full bg-slate-700 border border-slate-600 rounded px-3 py-2 text-sm"
            >
              {TIMEFRAMES.map((tf) => (
                <option key={tf.value} value={tf.value}>{tf.label}</option>
              ))}
            </select>
          </div>

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

          <div>
            <label className="block text-xs text-gray-400 mb-1">Max Candles</label>
            <input
              type="number"
              value={limit}
              onChange={(e) => setLimit(parseInt(e.target.value) || 365)}
              className="w-full bg-slate-700 border border-slate-600 rounded px-3 py-2 text-sm"
            />
          </div>

          {error && (
            <div className="bg-red-900/30 border border-red-700 rounded p-3 text-sm text-red-400">
              {error}
            </div>
          )}

          {result && (
            <div className="bg-green-900/30 border border-green-700 rounded p-3 text-sm text-green-400">
              Imported {result.imported} candles for {result.symbol} on {result.exchange}
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
              onClick={handleImport}
              disabled={loading || !symbol}
              className="px-4 py-2 text-sm rounded bg-blue-600 hover:bg-blue-500 disabled:opacity-50 disabled:cursor-not-allowed transition-colors flex items-center gap-2"
            >
              {loading && <Loader2 size={14} className="animate-spin" />}
              {loading ? 'Importing...' : 'Import Data'}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
