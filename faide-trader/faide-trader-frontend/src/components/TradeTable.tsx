import { useState } from 'react';
import { type Trade, api } from '@/lib/api';
import { EditableField } from './EditableField';
import { Trash2, Pin, PinOff } from 'lucide-react';

interface TradeTableProps {
  trades: Trade[];
  botId: number;
  onRefresh: () => void;
}

export function TradeTable({ trades, botId: _botId, onRefresh }: TradeTableProps) {
  void _botId;
  const [loading, setLoading] = useState(false);

  const handleUpdateField = async (tradeId: number, field: string, value: number | string) => {
    setLoading(true);
    try {
      await api.updateTrade(tradeId, { [field]: value } as Partial<Trade>);
      onRefresh();
    } catch (e) {
      console.error('Update failed:', e);
    } finally {
      setLoading(false);
    }
  };

  const handleDelete = async (tradeId: number) => {
    if (!confirm('Delete this trade?')) return;
    try {
      await api.deleteTrade(tradeId);
      onRefresh();
    } catch (e) {
      console.error('Delete failed:', e);
    }
  };

  const handleTogglePin = async (trade: Trade) => {
    try {
      await api.updateTrade(trade.id, { is_pinned: !trade.is_pinned });
      onRefresh();
    } catch (e) {
      console.error('Pin toggle failed:', e);
    }
  };

  if (trades.length === 0) {
    return (
      <div className="text-center py-8 text-gray-500">
        No trades yet. Add a trade to get started.
      </div>
    );
  }

  return (
    <div className={`overflow-x-auto ${loading ? 'opacity-60' : ''}`}>
      <table className="w-full text-sm">
        <thead>
          <tr className="text-gray-400 text-xs border-b border-slate-700">
            <th className="text-left py-2 px-2">Symbol</th>
            <th className="text-left py-2 px-2">Dir</th>
            <th className="text-right py-2 px-2">Entry</th>
            <th className="text-right py-2 px-2">Exit</th>
            <th className="text-right py-2 px-2">Qty</th>
            <th className="text-right py-2 px-2">Lev</th>
            <th className="text-right py-2 px-2">P&L</th>
            <th className="text-right py-2 px-2">P&L %</th>
            <th className="text-right py-2 px-2">Fee</th>
            <th className="text-left py-2 px-2">Entry Time</th>
            <th className="text-left py-2 px-2">Exit Time</th>
            <th className="text-center py-2 px-2">Actions</th>
          </tr>
        </thead>
        <tbody>
          {trades.map((trade) => (
            <tr
              key={trade.id}
              className={`border-b border-slate-800 hover:bg-slate-800/50 ${trade.is_pinned ? 'bg-yellow-900/10' : ''}`}
            >
              <td className="py-1.5 px-2 font-mono text-xs">{trade.symbol}</td>
              <td className="py-1.5 px-2">
                <span className={`text-xs font-medium px-1.5 py-0.5 rounded ${trade.direction === 'long' ? 'bg-green-900/30 text-green-400' : 'bg-red-900/30 text-red-400'}`}>
                  {trade.direction.toUpperCase()}
                </span>
              </td>
              <td className="py-1.5 px-2 text-right">
                <EditableField
                  value={trade.entry_price}
                  onSave={(v) => handleUpdateField(trade.id, 'entry_price', v as number)}
                  prefix="$"
                  decimals={2}
                />
              </td>
              <td className="py-1.5 px-2 text-right">
                <EditableField
                  value={trade.exit_price ?? 0}
                  onSave={(v) => handleUpdateField(trade.id, 'exit_price', v as number)}
                  prefix="$"
                  decimals={2}
                />
              </td>
              <td className="py-1.5 px-2 text-right">
                <EditableField
                  value={trade.quantity}
                  onSave={(v) => handleUpdateField(trade.id, 'quantity', v as number)}
                  decimals={4}
                />
              </td>
              <td className="py-1.5 px-2 text-right">
                <EditableField
                  value={trade.leverage}
                  onSave={(v) => handleUpdateField(trade.id, 'leverage', v as number)}
                  suffix="x"
                  decimals={1}
                />
              </td>
              <td className="py-1.5 px-2 text-right">
                <EditableField
                  value={trade.pnl}
                  onSave={(v) => handleUpdateField(trade.id, 'pnl', v as number)}
                  prefix="$"
                  decimals={2}
                  isPinned={trade.is_pinned}
                  onTogglePin={() => handleTogglePin(trade)}
                />
              </td>
              <td className="py-1.5 px-2 text-right">
                <span className={`font-mono text-xs ${trade.pnl_percent > 0 ? 'text-green-400' : trade.pnl_percent < 0 ? 'text-red-400' : 'text-gray-400'}`}>
                  {trade.pnl_percent > 0 ? '+' : ''}{trade.pnl_percent.toFixed(2)}%
                </span>
              </td>
              <td className="py-1.5 px-2 text-right">
                <EditableField
                  value={trade.fee}
                  onSave={(v) => handleUpdateField(trade.id, 'fee', v as number)}
                  prefix="$"
                  decimals={2}
                />
              </td>
              <td className="py-1.5 px-2 text-xs text-gray-400">
                {new Date(trade.entry_time).toLocaleDateString()}
              </td>
              <td className="py-1.5 px-2 text-xs text-gray-400">
                {trade.exit_time ? new Date(trade.exit_time).toLocaleDateString() : '-'}
              </td>
              <td className="py-1.5 px-2 text-center">
                <div className="flex items-center justify-center gap-1">
                  <button
                    onClick={() => handleTogglePin(trade)}
                    className={`p-1 rounded hover:bg-slate-700 ${trade.is_pinned ? 'text-yellow-400' : 'text-gray-500'}`}
                    title={trade.is_pinned ? 'Unpin' : 'Pin'}
                  >
                    {trade.is_pinned ? <Pin size={14} /> : <PinOff size={14} />}
                  </button>
                  <button
                    onClick={() => handleDelete(trade.id)}
                    className="p-1 rounded hover:bg-slate-700 text-gray-500 hover:text-red-400"
                    title="Delete trade"
                  >
                    <Trash2 size={14} />
                  </button>
                </div>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
