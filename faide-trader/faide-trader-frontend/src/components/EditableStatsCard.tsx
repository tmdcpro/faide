import { useState } from 'react';
import { type Stats, api } from '@/lib/api';
import { Loader2, Lock, Unlock } from 'lucide-react';

interface EditableStatsCardProps {
  stats: Stats;
  title?: string;
  entityType?: 'bot' | 'account' | 'portfolio';
  entityId?: number;
  pinnedStats?: string[];
  onRecalculated?: () => void;
}

function formatNum(n: number, decimals = 2): string {
  return n.toLocaleString(undefined, { minimumFractionDigits: decimals, maximumFractionDigits: decimals });
}

function pnlColor(n: number): string {
  return n > 0 ? 'text-green-400' : n < 0 ? 'text-red-400' : 'text-gray-400';
}

interface StatItemEditableProps {
  label: string;
  value: string;
  rawValue: number;
  color?: string;
  field: string;
  entityType?: string;
  entityId?: number;
  isPinned?: boolean;
  onTogglePin?: (field: string) => void;
  onRecalculated?: () => void;
  periodKey?: string;
  periodType?: string;
}

function StatItemEditable({
  label,
  value,
  rawValue,
  color = 'text-white',
  field,
  entityType,
  entityId,
  isPinned,
  onTogglePin,
  onRecalculated,
  periodKey,
  periodType,
}: StatItemEditableProps) {
  const [editing, setEditing] = useState(false);
  const [editValue, setEditValue] = useState(String(rawValue));
  const [saving, setSaving] = useState(false);

  const handleSave = async () => {
    const newVal = parseFloat(editValue);
    if (isNaN(newVal) || newVal === rawValue) {
      setEditing(false);
      return;
    }

    if (entityType === 'bot' && entityId) {
      setSaving(true);
      try {
        await api.recalculate({
          entity_type: 'bot',
          entity_id: entityId,
          field,
          new_value: newVal,
          ...(periodKey && periodType ? { period_key: periodKey, period_type: periodType } : {}),
        });
        onRecalculated?.();
      } catch (e) {
        console.error('Recalculation failed:', e);
      } finally {
        setSaving(false);
        setEditing(false);
      }
    } else {
      setEditing(false);
    }
  };

  if (editing) {
    return (
      <div className="flex flex-col">
        <span className="text-xs text-gray-500">{label}</span>
        <div className="flex items-center gap-1">
          <input
            type="number"
            value={editValue}
            onChange={(e) => setEditValue(e.target.value)}
            onBlur={handleSave}
            onKeyDown={(e) => {
              if (e.key === 'Enter') handleSave();
              if (e.key === 'Escape') setEditing(false);
            }}
            autoFocus
            step="any"
            className="bg-slate-700 border border-blue-500 rounded px-1.5 py-0.5 text-sm outline-none w-24 font-mono"
          />
          {saving && <Loader2 size={12} className="animate-spin text-blue-400" />}
        </div>
      </div>
    );
  }

  const canEdit = entityType === 'bot' && entityId;
  return (
    <div className="flex flex-col group">
      <div className="flex items-center gap-1">
        <span className="text-xs text-gray-500">{label}</span>
        {onTogglePin && (
          <button
            onClick={() => onTogglePin(field)}
            className={`opacity-0 group-hover:opacity-100 transition-opacity ${isPinned ? 'text-yellow-400 !opacity-100' : 'text-gray-500 hover:text-yellow-400'}`}
            title={isPinned ? 'Unlock (value will recalculate)' : 'Lock (value stays fixed)'}
          >
            {isPinned ? <Lock size={10} /> : <Unlock size={10} />}
          </button>
        )}
      </div>
      <span
        onClick={() => {
          if (canEdit && !isPinned) {
            setEditValue(String(rawValue));
            setEditing(true);
          }
        }}
        className={`text-sm font-mono font-medium ${color} ${canEdit && !isPinned ? 'cursor-pointer hover:bg-slate-700 rounded px-0.5 transition-colors' : ''} ${isPinned ? 'opacity-75' : ''}`}
        title={isPinned ? 'Locked — unlock to edit' : canEdit ? 'Click to edit & back-calculate' : undefined}
      >
        {value}
        {isPinned && <Lock size={10} className="inline ml-1 text-yellow-400" />}
      </span>
    </div>
  );
}

export function EditableStatsCard({ stats, title, entityType, entityId, pinnedStats = [], onRecalculated }: EditableStatsCardProps) {
  const handleTogglePin = async (field: string) => {
    if (entityType !== 'bot' || !entityId) return;
    const isPinned = pinnedStats.includes(field);
    try {
      await api.togglePin({
        entity_type: 'bot',
        entity_id: entityId,
        field,
        pinned: !isPinned,
      });
      onRecalculated?.();
    } catch (e) {
      console.error('Toggle pin failed:', e);
    }
  };

  const commonProps = { entityType, entityId, onRecalculated, onTogglePin: entityType === 'bot' ? handleTogglePin : undefined };

  const isFieldPinned = (field: string) => pinnedStats.includes(field);

  return (
    <div className="bg-slate-800 rounded-lg border border-slate-700 p-4">
      {title && (
        <div className="flex items-center justify-between mb-3">
          <h3 className="text-sm font-medium text-gray-400">{title}</h3>
          {entityType === 'bot' && (
            <span className="text-xs text-gray-500">Click to edit · Lock to protect</span>
          )}
        </div>
      )}
      <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 gap-3">
        <StatItemEditable label="Total P&L" value={`$${formatNum(stats.total_pnl)}`} rawValue={stats.total_pnl} color={pnlColor(stats.total_pnl)} field="total_pnl" isPinned={isFieldPinned('total_pnl')} {...commonProps} />
        <StatItemEditable label="ROI" value={`${formatNum(stats.roi_percent)}%`} rawValue={stats.roi_percent} color={pnlColor(stats.roi_percent)} field="roi_percent" isPinned={isFieldPinned('roi_percent')} {...commonProps} />
        <StatItemEditable label="Win Rate" value={`${formatNum(stats.win_rate)}%`} rawValue={stats.win_rate} color={stats.win_rate >= 50 ? 'text-green-400' : 'text-red-400'} field="win_rate" isPinned={isFieldPinned('win_rate')} {...commonProps} />
        <StatItemEditable label="Trades" value={`${stats.total_trades}`} rawValue={stats.total_trades} field="total_trades" isPinned={isFieldPinned('total_trades')} {...commonProps} />
        <StatItemEditable label="Wins" value={`${stats.win_count}`} rawValue={stats.win_count} field="win_count" isPinned={isFieldPinned('win_count')} {...commonProps} />
        <StatItemEditable label="Losses" value={`${stats.loss_count}`} rawValue={stats.loss_count} field="loss_count" isPinned={isFieldPinned('loss_count')} {...commonProps} />
        <StatItemEditable label="Sharpe" value={formatNum(stats.sharpe_ratio, 4)} rawValue={stats.sharpe_ratio} color={stats.sharpe_ratio > 1 ? 'text-green-400' : stats.sharpe_ratio > 0 ? 'text-yellow-400' : 'text-red-400'} field="sharpe_ratio" isPinned={isFieldPinned('sharpe_ratio')} {...commonProps} />
        <StatItemEditable label="Sortino" value={formatNum(stats.sortino_ratio, 4)} rawValue={stats.sortino_ratio} field="sortino_ratio" isPinned={isFieldPinned('sortino_ratio')} {...commonProps} />
        <StatItemEditable label="Max DD $" value={`$${formatNum(stats.max_drawdown)}`} rawValue={stats.max_drawdown} color="text-red-400" field="max_drawdown" isPinned={isFieldPinned('max_drawdown')} {...commonProps} />
        <StatItemEditable label="Max DD %" value={`${formatNum(stats.max_drawdown_percent)}%`} rawValue={stats.max_drawdown_percent} color="text-red-400" field="max_drawdown_percent" isPinned={isFieldPinned('max_drawdown_percent')} {...commonProps} />
        <StatItemEditable label="Profit Factor" value={formatNum(stats.profit_factor)} rawValue={stats.profit_factor} color={stats.profit_factor > 1 ? 'text-green-400' : 'text-red-400'} field="profit_factor" isPinned={isFieldPinned('profit_factor')} {...commonProps} />
        <StatItemEditable label="Avg Win" value={`$${formatNum(stats.avg_win)}`} rawValue={stats.avg_win} color="text-green-400" field="avg_win" isPinned={isFieldPinned('avg_win')} {...commonProps} />
        <StatItemEditable label="Avg Loss" value={`$${formatNum(stats.avg_loss)}`} rawValue={stats.avg_loss} color="text-red-400" field="avg_loss" isPinned={isFieldPinned('avg_loss')} {...commonProps} />
        <StatItemEditable label="Best Trade" value={`$${formatNum(stats.best_trade)}`} rawValue={stats.best_trade} color="text-green-400" field="best_trade" isPinned={isFieldPinned('best_trade')} {...commonProps} />
        <StatItemEditable label="Worst Trade" value={`$${formatNum(stats.worst_trade)}`} rawValue={stats.worst_trade} color="text-red-400" field="worst_trade" isPinned={isFieldPinned('worst_trade')} {...commonProps} />
        <StatItemEditable label="Avg Trade" value={`$${formatNum(stats.avg_trade_pnl)}`} rawValue={stats.avg_trade_pnl} color={pnlColor(stats.avg_trade_pnl)} field="avg_trade_pnl" isPinned={isFieldPinned('avg_trade_pnl')} {...commonProps} />
        <StatItemEditable label="Total Fees" value={`$${formatNum(stats.total_fees)}`} rawValue={stats.total_fees} field="total_fees" isPinned={isFieldPinned('total_fees')} {...commonProps} />
        <StatItemEditable label="Net P&L" value={`$${formatNum(stats.net_pnl)}`} rawValue={stats.net_pnl} color={pnlColor(stats.net_pnl)} field="net_pnl" isPinned={isFieldPinned('net_pnl')} {...commonProps} />
        <StatItemEditable label="Calmar" value={formatNum(stats.calmar_ratio, 4)} rawValue={stats.calmar_ratio} field="calmar_ratio" isPinned={isFieldPinned('calmar_ratio')} {...commonProps} />
        <StatItemEditable label="Balance" value={`$${formatNum(stats.current_balance)}`} rawValue={stats.current_balance} field="current_balance" isPinned={isFieldPinned('current_balance')} {...commonProps} />
      </div>
    </div>
  );
}
