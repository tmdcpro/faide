import { useState } from 'react';
import { X } from 'lucide-react';
import { SymbolSelector } from '@/components/SymbolSelector';

interface CreateBotDialogProps {
  accountExchange: string;
  onSubmit: (data: { name: string; strategy_type: string; symbol: string; symbols: string[] }) => Promise<void>;
  onClose: () => void;
}

const STRATEGY_OPTIONS = [
  { value: 'manual', label: 'Manual Trading' },
  { value: 'scalping', label: 'Scalping' },
  { value: 'swing', label: 'Swing Trading' },
  { value: 'grid', label: 'Grid Bot' },
  { value: 'dca', label: 'DCA (Dollar Cost Avg)' },
  { value: 'arbitrage', label: 'Arbitrage' },
  { value: 'trend_following', label: 'Trend Following' },
  { value: 'mean_reversion', label: 'Mean Reversion' },
  { value: 'custom', label: 'Custom Algorithm' },
];

export function CreateBotDialog({ accountExchange, onSubmit, onClose }: CreateBotDialogProps) {
  const [name, setName] = useState('');
  const [strategyType, setStrategyType] = useState('manual');
  const [selectedSymbols, setSelectedSymbols] = useState<string[]>([]);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState('');

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!name.trim()) return;
    if (selectedSymbols.length === 0) {
      setError('Select at least one trading symbol');
      return;
    }
    setSubmitting(true);
    setError('');
    try {
      await onSubmit({
        name: name.trim(),
        strategy_type: strategyType,
        symbol: selectedSymbols[0],
        symbols: selectedSymbols,
      });
      onClose();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed');
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="fixed inset-0 bg-black/60 flex items-center justify-center z-50" onClick={onClose}>
      <div
        className="bg-slate-800 border border-slate-700 rounded-lg w-full max-w-md p-6"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-lg font-semibold">Create Bot / Strategy</h2>
          <button onClick={onClose} className="text-gray-400 hover:text-white">
            <X size={20} />
          </button>
        </div>

        {error && (
          <div className="bg-red-900/30 border border-red-700 text-red-400 text-sm rounded px-3 py-2 mb-4">
            {error}
          </div>
        )}

        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label className="block text-sm text-gray-400 mb-1">Bot Name</label>
            <input
              type="text"
              value={name}
              onChange={(e) => setName(e.target.value)}
              className="w-full bg-slate-700 border border-slate-600 rounded px-3 py-2 text-sm outline-none focus:border-blue-500"
              required
              placeholder="My Trading Bot"
            />
          </div>

          <div>
            <label className="block text-sm text-gray-400 mb-1">Strategy Type</label>
            <select
              value={strategyType}
              onChange={(e) => setStrategyType(e.target.value)}
              className="w-full bg-slate-700 border border-slate-600 rounded px-3 py-2 text-sm outline-none focus:border-blue-500"
            >
              {STRATEGY_OPTIONS.map((opt) => (
                <option key={opt.value} value={opt.value}>{opt.label}</option>
              ))}
            </select>
          </div>

          <div>
            <label className="block text-sm text-gray-400 mb-1">
              Trading Symbols ({selectedSymbols.length} selected)
            </label>
            <SymbolSelector
              exchange={accountExchange}
              selectedSymbols={selectedSymbols}
              onChange={setSelectedSymbols}
              multiple={true}
              placeholder="Search and select trading pairs..."
            />
            <p className="text-xs text-gray-500 mt-1">
              Select one or more symbols. Trades will be tracked per symbol.
            </p>
          </div>

          <div className="flex gap-2 pt-2">
            <button
              type="button"
              onClick={onClose}
              className="flex-1 px-4 py-2 bg-slate-700 hover:bg-slate-600 rounded text-sm transition-colors"
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={submitting || selectedSymbols.length === 0}
              className="flex-1 px-4 py-2 bg-blue-600 hover:bg-blue-500 rounded text-sm font-medium transition-colors disabled:opacity-50"
            >
              {submitting ? 'Creating...' : 'Create'}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
