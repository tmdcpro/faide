import { useState } from 'react';
import { type Stats, api } from '@/lib/api';
import { Loader2, Lock, Unlock } from 'lucide-react';

interface EditableStatsCardProps {
  stats: Stats;
  title?: string;
  entityType?: 'bot' | 'account' | 'portfolio';
  entityId?: number;
  pinnedStats?: string[];
  pinnedStatValues?: Record<string, number | null>;
  editableFields?: string[];
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
  constraintValue?: number;
  color?: string;
  field: string;
  entityType?: string;
  entityId?: number;
  isPinned?: boolean;
  isEditable?: boolean;
  onTogglePin?: (field: string) => void;
  onRecalculated?: () => void;
  periodKey?: string;
  periodType?: string;
}

function StatItemEditable({
  label,
  value,
  rawValue,
  constraintValue,
  color = 'text-white',
  field,
  entityType,
  entityId,
  isPinned,
  isEditable = true,
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

    if (entityType && entityId) {
      setSaving(true);
      try {
        if (isPinned) {
          // Editing a locked stat: update the constraint value
          await api.setConstraint({
            entity_type: entityType,
            entity_id: entityId,
            field,
            value: newVal,
          });
        } else if (isEditable) {
          await api.recalculate({
            entity_type: entityType as 'bot' | 'account' | 'portfolio',
            entity_id: entityId,
            field,
            new_value: newVal,
            ...(periodKey && periodType ? { period_key: periodKey, period_type: periodType } : {}),
          });
        }
        onRecalculated?.();
      } catch (e) {
        console.error('Save failed:', e);
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

  const canEdit = entityType && entityId && isEditable;
  const canInteract = entityType && entityId;
  return (
    <div className="flex flex-col group">
      <div className="flex items-center gap-1">
        <span className="text-xs text-gray-500">{label}</span>
        {onTogglePin && canInteract && (
          <button
            onClick={() => onTogglePin(field)}
            className={`opacity-0 group-hover:opacity-100 transition-opacity ${isPinned ? 'text-yellow-400 !opacity-100' : 'text-gray-500 hover:text-yellow-400'}`}
            title={isPinned ? `Unlock (value will recalculate freely)` : `Lock at ${value} (stays fixed during regeneration)`}
          >
            {isPinned ? <Lock size={10} /> : <Unlock size={10} />}
          </button>
        )}
      </div>
      <span
        onClick={() => {
          if (canEdit || isPinned) {
            setEditValue(String(isPinned && constraintValue !== undefined ? constraintValue : rawValue));
            setEditing(true);
          }
        }}
        className={`text-sm font-mono font-medium ${color} ${(canEdit || isPinned) ? 'cursor-pointer hover:bg-slate-700 rounded px-0.5 transition-colors' : ''}`}
        title={isPinned ? `Locked at ${value} — click to edit constraint value` : canEdit ? 'Click to edit & back-calculate' : undefined}
      >
        {value}
        {isPinned && <Lock size={10} className="inline ml-1 text-yellow-400" />}
        {isPinned && constraintValue !== undefined && constraintValue !== rawValue && (
          <span className="text-xs text-yellow-400 ml-1" title="Constraint target (will be applied on Regenerate)">
            → {formatNum(constraintValue)}
          </span>
        )}
      </span>
    </div>
  );
}

export function EditableStatsCard({ stats, title, entityType, entityId, pinnedStats = [], pinnedStatValues = {}, editableFields, onRecalculated }: EditableStatsCardProps) {
  const handleTogglePin = async (field: string) => {
    if (!entityType || !entityId) return;
    const isPinned = pinnedStats.includes(field);
    try {
      await api.togglePin({
        entity_type: entityType,
        entity_id: entityId,
        field,
        pinned: !isPinned,
      });
      onRecalculated?.();
    } catch (e) {
      console.error('Toggle pin failed:', e);
    }
  };

  const isFieldEditable = (field: string) => !editableFields || editableFields.includes(field);
  const commonProps = { entityType, entityId, onRecalculated, onTogglePin: entityType ? handleTogglePin : undefined };

  const isFieldPinned = (field: string) => pinnedStats.includes(field);
  const getConstraintValue = (field: string, computedValue: number): number => {
    const cv = pinnedStatValues[field];
    return (cv !== undefined && cv !== null) ? cv : computedValue;
  };

  return (
    <div className="bg-slate-800 rounded-lg border border-slate-700 p-4">
      {title && (
        <div className="flex items-center justify-between mb-3">
          <h3 className="text-sm font-medium text-gray-400">{title}</h3>
          {entityType && (
            <span className="text-xs text-gray-500">Click to edit · Hover to lock/unlock</span>
          )}
        </div>
      )}
      <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 gap-3">
        <StatItemEditable label="Total P&L" value={`$${formatNum(stats.total_pnl)}`} rawValue={stats.total_pnl} constraintValue={getConstraintValue('total_pnl', stats.total_pnl)} color={pnlColor(stats.total_pnl)} field="total_pnl" isPinned={isFieldPinned('total_pnl')} isEditable={isFieldEditable('total_pnl')} {...commonProps} />
        <StatItemEditable label="ROI" value={`${formatNum(stats.roi_percent)}%`} rawValue={stats.roi_percent} constraintValue={getConstraintValue('roi_percent', stats.roi_percent)} color={pnlColor(stats.roi_percent)} field="roi_percent" isPinned={isFieldPinned('roi_percent')} isEditable={isFieldEditable('roi_percent')} {...commonProps} />
        <StatItemEditable label="Win Rate" value={`${formatNum(stats.win_rate)}%`} rawValue={stats.win_rate} constraintValue={getConstraintValue('win_rate', stats.win_rate)} color={stats.win_rate >= 50 ? 'text-green-400' : 'text-red-400'} field="win_rate" isPinned={isFieldPinned('win_rate')} isEditable={isFieldEditable('win_rate')} {...commonProps} />
        <StatItemEditable label="Trades" value={`${stats.total_trades}`} rawValue={stats.total_trades} constraintValue={getConstraintValue('total_trades', stats.total_trades)} field="total_trades" isPinned={isFieldPinned('total_trades')} isEditable={isFieldEditable('total_trades')} {...commonProps} />
        <StatItemEditable label="Wins" value={`${stats.win_count}`} rawValue={stats.win_count} constraintValue={getConstraintValue('win_count', stats.win_count)} field="win_count" isPinned={isFieldPinned('win_count')} isEditable={isFieldEditable('win_count')} {...commonProps} />
        <StatItemEditable label="Losses" value={`${stats.loss_count}`} rawValue={stats.loss_count} constraintValue={getConstraintValue('loss_count', stats.loss_count)} field="loss_count" isPinned={isFieldPinned('loss_count')} isEditable={isFieldEditable('loss_count')} {...commonProps} />
        <StatItemEditable label="Sharpe" value={formatNum(stats.sharpe_ratio, 4)} rawValue={stats.sharpe_ratio} constraintValue={getConstraintValue('sharpe_ratio', stats.sharpe_ratio)} color={stats.sharpe_ratio > 1 ? 'text-green-400' : stats.sharpe_ratio > 0 ? 'text-yellow-400' : 'text-red-400'} field="sharpe_ratio" isPinned={isFieldPinned('sharpe_ratio')} isEditable={isFieldEditable('sharpe_ratio')} {...commonProps} />
        <StatItemEditable label="Sortino" value={formatNum(stats.sortino_ratio, 4)} rawValue={stats.sortino_ratio} constraintValue={getConstraintValue('sortino_ratio', stats.sortino_ratio)} field="sortino_ratio" isPinned={isFieldPinned('sortino_ratio')} isEditable={isFieldEditable('sortino_ratio')} {...commonProps} />
        <StatItemEditable label="Max DD $" value={`$${formatNum(stats.max_drawdown)}`} rawValue={stats.max_drawdown} constraintValue={getConstraintValue('max_drawdown', stats.max_drawdown)} color="text-red-400" field="max_drawdown" isPinned={isFieldPinned('max_drawdown')} isEditable={isFieldEditable('max_drawdown')} {...commonProps} />
        <StatItemEditable label="Max DD %" value={`${formatNum(stats.max_drawdown_percent)}%`} rawValue={stats.max_drawdown_percent} constraintValue={getConstraintValue('max_drawdown_percent', stats.max_drawdown_percent)} color="text-red-400" field="max_drawdown_percent" isPinned={isFieldPinned('max_drawdown_percent')} isEditable={isFieldEditable('max_drawdown_percent')} {...commonProps} />
        <StatItemEditable label="Profit Factor" value={formatNum(stats.profit_factor)} rawValue={stats.profit_factor} constraintValue={getConstraintValue('profit_factor', stats.profit_factor)} color={stats.profit_factor > 1 ? 'text-green-400' : 'text-red-400'} field="profit_factor" isPinned={isFieldPinned('profit_factor')} isEditable={isFieldEditable('profit_factor')} {...commonProps} />
        <StatItemEditable label="Avg Win" value={`$${formatNum(stats.avg_win)}`} rawValue={stats.avg_win} constraintValue={getConstraintValue('avg_win', stats.avg_win)} color="text-green-400" field="avg_win" isPinned={isFieldPinned('avg_win')} isEditable={isFieldEditable('avg_win')} {...commonProps} />
        <StatItemEditable label="Avg Loss" value={`$${formatNum(stats.avg_loss)}`} rawValue={stats.avg_loss} constraintValue={getConstraintValue('avg_loss', stats.avg_loss)} color="text-red-400" field="avg_loss" isPinned={isFieldPinned('avg_loss')} isEditable={isFieldEditable('avg_loss')} {...commonProps} />
        <StatItemEditable label="Best Trade" value={`$${formatNum(stats.best_trade)}`} rawValue={stats.best_trade} constraintValue={getConstraintValue('best_trade', stats.best_trade)} color="text-green-400" field="best_trade" isPinned={isFieldPinned('best_trade')} isEditable={isFieldEditable('best_trade')} {...commonProps} />
        <StatItemEditable label="Worst Trade" value={`$${formatNum(stats.worst_trade)}`} rawValue={stats.worst_trade} constraintValue={getConstraintValue('worst_trade', stats.worst_trade)} color="text-red-400" field="worst_trade" isPinned={isFieldPinned('worst_trade')} isEditable={isFieldEditable('worst_trade')} {...commonProps} />
        <StatItemEditable label="Avg Trade" value={`$${formatNum(stats.avg_trade_pnl)}`} rawValue={stats.avg_trade_pnl} constraintValue={getConstraintValue('avg_trade_pnl', stats.avg_trade_pnl)} color={pnlColor(stats.avg_trade_pnl)} field="avg_trade_pnl" isPinned={isFieldPinned('avg_trade_pnl')} isEditable={isFieldEditable('avg_trade_pnl')} {...commonProps} />
        <StatItemEditable label="Total Fees" value={`$${formatNum(stats.total_fees)}`} rawValue={stats.total_fees} constraintValue={getConstraintValue('total_fees', stats.total_fees)} field="total_fees" isPinned={isFieldPinned('total_fees')} isEditable={isFieldEditable('total_fees')} {...commonProps} />
        <StatItemEditable label="Net P&L" value={`$${formatNum(stats.net_pnl)}`} rawValue={stats.net_pnl} color={pnlColor(stats.net_pnl)} field="net_pnl" isPinned={isFieldPinned('net_pnl')} isEditable={isFieldEditable('net_pnl')} {...commonProps} />
        <StatItemEditable label="Calmar" value={formatNum(stats.calmar_ratio, 4)} rawValue={stats.calmar_ratio} field="calmar_ratio" isPinned={isFieldPinned('calmar_ratio')} isEditable={isFieldEditable('calmar_ratio')} {...commonProps} />
        <StatItemEditable label="Balance" value={`$${formatNum(stats.current_balance)}`} rawValue={stats.current_balance} field="current_balance" isPinned={isFieldPinned('current_balance')} isEditable={isFieldEditable('current_balance')} {...commonProps} />
      </div>
    </div>
  );
}
