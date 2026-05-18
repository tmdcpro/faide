import { type Stats } from '@/lib/api';

interface StatsCardProps {
  stats: Stats;
  title?: string;
}

function formatNum(n: number, decimals = 2): string {
  return n.toLocaleString(undefined, { minimumFractionDigits: decimals, maximumFractionDigits: decimals });
}

function pnlColor(n: number): string {
  return n > 0 ? 'text-green-400' : n < 0 ? 'text-red-400' : 'text-gray-400';
}

export function StatsCard({ stats, title }: StatsCardProps) {
  return (
    <div className="bg-slate-800 rounded-lg border border-slate-700 p-4">
      {title && <h3 className="text-sm font-medium text-gray-400 mb-3">{title}</h3>}
      <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 gap-3">
        <StatItem label="Total P&L" value={`$${formatNum(stats.total_pnl)}`} color={pnlColor(stats.total_pnl)} />
        <StatItem label="ROI" value={`${formatNum(stats.roi_percent)}%`} color={pnlColor(stats.roi_percent)} />
        <StatItem label="Win Rate" value={`${formatNum(stats.win_rate)}%`} color={stats.win_rate >= 50 ? 'text-green-400' : 'text-red-400'} />
        <StatItem label="Trades" value={`${stats.total_trades}`} />
        <StatItem label="W/L" value={`${stats.win_count}/${stats.loss_count}`} />
        <StatItem label="Sharpe" value={formatNum(stats.sharpe_ratio, 4)} color={stats.sharpe_ratio > 1 ? 'text-green-400' : stats.sharpe_ratio > 0 ? 'text-yellow-400' : 'text-red-400'} />
        <StatItem label="Sortino" value={formatNum(stats.sortino_ratio, 4)} />
        <StatItem label="Max DD" value={`$${formatNum(stats.max_drawdown)}`} color="text-red-400" />
        <StatItem label="Max DD %" value={`${formatNum(stats.max_drawdown_percent)}%`} color="text-red-400" />
        <StatItem label="Profit Factor" value={formatNum(stats.profit_factor)} color={stats.profit_factor > 1 ? 'text-green-400' : 'text-red-400'} />
        <StatItem label="Avg Win" value={`$${formatNum(stats.avg_win)}`} color="text-green-400" />
        <StatItem label="Avg Loss" value={`$${formatNum(stats.avg_loss)}`} color="text-red-400" />
        <StatItem label="Best Trade" value={`$${formatNum(stats.best_trade)}`} color="text-green-400" />
        <StatItem label="Worst Trade" value={`$${formatNum(stats.worst_trade)}`} color="text-red-400" />
        <StatItem label="Balance" value={`$${formatNum(stats.current_balance)}`} />
      </div>
    </div>
  );
}

function StatItem({ label, value, color = 'text-white' }: { label: string; value: string; color?: string }) {
  return (
    <div className="flex flex-col">
      <span className="text-xs text-gray-500">{label}</span>
      <span className={`text-sm font-mono font-medium ${color}`}>{value}</span>
    </div>
  );
}
