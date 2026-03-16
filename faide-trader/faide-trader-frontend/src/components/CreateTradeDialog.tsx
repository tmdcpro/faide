import { useState } from 'react';
import { X } from 'lucide-react';
import { api } from '@/lib/api';

interface CreateTradeDialogProps {
  botId: number;
  defaultSymbol: string;
  onClose: () => void;
  onCreated: () => void;
}

export function CreateTradeDialog({ botId, defaultSymbol, onClose, onCreated }: CreateTradeDialogProps) {
  const [form, setForm] = useState({
    symbol: defaultSymbol,
    direction: 'long',
    status: 'closed',
    entry_price: 0,
    exit_price: 0,
    quantity: 0.1,
    leverage: 1,
    fee: 0,
    entry_time: new Date().toISOString().slice(0, 16),
    exit_time: new Date().toISOString().slice(0, 16),
  });
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState('');

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setSubmitting(true);
    setError('');
    try {
      await api.createTrade(botId, {
        symbol: form.symbol,
        direction: form.direction,
        status: form.status,
        entry_price: form.entry_price,
        exit_price: form.exit_price || null,
        quantity: form.quantity,
        leverage: form.leverage,
        fee: form.fee,
        entry_time: new Date(form.entry_time).toISOString(),
        exit_time: form.exit_time ? new Date(form.exit_time).toISOString() : null,
      });
      onCreated();
      onClose();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to create trade');
    } finally {
      setSubmitting(false);
    }
  };

  const update = (field: string, value: string | number) => {
    setForm({ ...form, [field]: value });
  };

  return (
    <div className="fixed inset-0 bg-black/60 flex items-center justify-center z-50" onClick={onClose}>
      <div className="bg-slate-800 border border-slate-700 rounded-lg w-full max-w-lg p-6" onClick={(e) => e.stopPropagation()}>
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-lg font-semibold">Add Trade</h2>
          <button onClick={onClose} className="text-gray-400 hover:text-white"><X size={20} /></button>
        </div>

        {error && <div className="bg-red-900/30 border border-red-700 text-red-400 text-sm rounded px-3 py-2 mb-4">{error}</div>}

        <form onSubmit={handleSubmit} className="space-y-3">
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="block text-xs text-gray-400 mb-1">Symbol</label>
              <input type="text" value={form.symbol} onChange={(e) => update('symbol', e.target.value)}
                className="w-full bg-slate-700 border border-slate-600 rounded px-3 py-2 text-sm outline-none focus:border-blue-500" />
            </div>
            <div>
              <label className="block text-xs text-gray-400 mb-1">Direction</label>
              <select value={form.direction} onChange={(e) => update('direction', e.target.value)}
                className="w-full bg-slate-700 border border-slate-600 rounded px-3 py-2 text-sm outline-none focus:border-blue-500">
                <option value="long">Long</option>
                <option value="short">Short</option>
              </select>
            </div>
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="block text-xs text-gray-400 mb-1">Entry Price</label>
              <input type="number" step="any" value={form.entry_price} onChange={(e) => update('entry_price', parseFloat(e.target.value) || 0)}
                className="w-full bg-slate-700 border border-slate-600 rounded px-3 py-2 text-sm outline-none focus:border-blue-500" />
            </div>
            <div>
              <label className="block text-xs text-gray-400 mb-1">Exit Price</label>
              <input type="number" step="any" value={form.exit_price} onChange={(e) => update('exit_price', parseFloat(e.target.value) || 0)}
                className="w-full bg-slate-700 border border-slate-600 rounded px-3 py-2 text-sm outline-none focus:border-blue-500" />
            </div>
          </div>

          <div className="grid grid-cols-3 gap-3">
            <div>
              <label className="block text-xs text-gray-400 mb-1">Quantity</label>
              <input type="number" step="any" value={form.quantity} onChange={(e) => update('quantity', parseFloat(e.target.value) || 0)}
                className="w-full bg-slate-700 border border-slate-600 rounded px-3 py-2 text-sm outline-none focus:border-blue-500" />
            </div>
            <div>
              <label className="block text-xs text-gray-400 mb-1">Leverage</label>
              <input type="number" step="any" value={form.leverage} onChange={(e) => update('leverage', parseFloat(e.target.value) || 1)}
                className="w-full bg-slate-700 border border-slate-600 rounded px-3 py-2 text-sm outline-none focus:border-blue-500" />
            </div>
            <div>
              <label className="block text-xs text-gray-400 mb-1">Fee</label>
              <input type="number" step="any" value={form.fee} onChange={(e) => update('fee', parseFloat(e.target.value) || 0)}
                className="w-full bg-slate-700 border border-slate-600 rounded px-3 py-2 text-sm outline-none focus:border-blue-500" />
            </div>
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="block text-xs text-gray-400 mb-1">Entry Time</label>
              <input type="datetime-local" value={form.entry_time} onChange={(e) => update('entry_time', e.target.value)}
                className="w-full bg-slate-700 border border-slate-600 rounded px-3 py-2 text-sm outline-none focus:border-blue-500" />
            </div>
            <div>
              <label className="block text-xs text-gray-400 mb-1">Exit Time</label>
              <input type="datetime-local" value={form.exit_time} onChange={(e) => update('exit_time', e.target.value)}
                className="w-full bg-slate-700 border border-slate-600 rounded px-3 py-2 text-sm outline-none focus:border-blue-500" />
            </div>
          </div>

          <div className="flex gap-2 pt-2">
            <button type="button" onClick={onClose}
              className="flex-1 px-4 py-2 bg-slate-700 hover:bg-slate-600 rounded text-sm transition-colors">Cancel</button>
            <button type="submit" disabled={submitting}
              className="flex-1 px-4 py-2 bg-blue-600 hover:bg-blue-500 rounded text-sm font-medium transition-colors disabled:opacity-50">
              {submitting ? 'Adding...' : 'Add Trade'}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
