import { useState } from 'react';
import { RefreshCw, ShieldCheck, AlertTriangle } from 'lucide-react';
import { api, type DateRange, type RangeRegenerateResult } from '@/lib/api';
import { periodLabel } from '@/components/DateRangePicker';

interface RangeRegenerateDialogProps {
  entityType: 'bot' | 'account' | 'portfolio';
  entityId: number;
  range: DateRange;
  onRangeChange: (range: DateRange) => void;
  onClose: () => void;
  onDone: () => void;
}

const PRESETS: { label: string; days: number }[] = [
  { label: '7D', days: 7 },
  { label: '30D', days: 30 },
  { label: '90D', days: 90 },
  { label: '1Y', days: 365 },
];

function toInput(value?: string): string {
  if (!value) return '';
  return value.length <= 10 ? `${value}T00:00` : value.slice(0, 16);
}

function toLocalDate(d: Date): string {
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
}

export function RangeRegenerateDialog({
  entityType,
  entityId,
  range,
  onRangeChange,
  onClose,
  onDone,
}: RangeRegenerateDialogProps) {
  const [targetNetPnl, setTargetNetPnl] = useState('');
  const [tradesPerDay, setTradesPerDay] = useState('');
  const [seed, setSeed] = useState('');
  const [withTransactions, setWithTransactions] = useState(false);
  const [depositTotal, setDepositTotal] = useState('');
  const [withdrawalTotal, setWithdrawalTotal] = useState('');
  const [transactionCount, setTransactionCount] = useState('2');
  const [running, setRunning] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<RangeRegenerateResult | null>(null);

  const ready = Boolean(range.start && range.end);
  const reversed = Boolean(
    range.start && range.end && new Date(range.start) > new Date(range.end)
  );

  const applyPreset = (days: number) => {
    const end = new Date();
    const start = new Date(end.getTime() - (days - 1) * 24 * 60 * 60 * 1000);
    onRangeChange({ start: toLocalDate(start), end: toLocalDate(end) });
  };

  const submit = async () => {
    if (!ready || reversed) return;
    setRunning(true);
    setError(null);
    try {
      const payload = {
        start_date: range.start!,
        end_date: range.end!,
        target_net_pnl: targetNetPnl === '' ? undefined : parseFloat(targetNetPnl),
        trades_per_day: tradesPerDay === '' ? undefined : parseFloat(tradesPerDay),
        seed: seed === '' ? undefined : parseInt(seed, 10),
        regenerate_transactions: withTransactions,
        deposit_total: depositTotal === '' ? undefined : parseFloat(depositTotal),
        withdrawal_total: withdrawalTotal === '' ? undefined : parseFloat(withdrawalTotal),
        transaction_count: parseInt(transactionCount, 10) || 2,
      };
      const res =
        entityType === 'bot'
          ? await api.regenerateBotRange(entityId, payload)
          : entityType === 'account'
            ? await api.regenerateAccountRange(entityId, payload)
            : await api.regeneratePortfolioRange(entityId, payload);
      setResult(res);
      onDone();
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Regeneration failed');
    } finally {
      setRunning(false);
    }
  };

  return (
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
      <div className="bg-slate-800 rounded-lg border border-slate-700 p-6 w-full max-w-lg max-h-[90vh] overflow-y-auto">
        <h2 className="text-lg font-bold mb-1">Generate / Regenerate Period Data</h2>
        <p className="text-sm text-gray-400 mb-4">
          Selected period: <span className="text-white font-medium">{periodLabel(range)}</span>
        </p>

        {!result && (
          <div className="bg-slate-900/60 border border-slate-700 rounded-lg p-3 mb-4">
            <div className="flex items-center justify-between mb-2">
              <span className="text-xs font-semibold text-gray-300 uppercase tracking-wide">
                Period to generate
              </span>
              <div className="flex gap-1">
                {PRESETS.map((p) => (
                  <button
                    key={p.label}
                    onClick={() => applyPreset(p.days)}
                    className="px-2 py-1 bg-slate-700 hover:bg-slate-600 rounded text-xs transition-colors"
                  >
                    {p.label}
                  </button>
                ))}
              </div>
            </div>
            <div className="grid grid-cols-2 gap-3">
              <label className="text-xs text-gray-400">
                From
                <input
                  type="datetime-local"
                  value={toInput(range.start)}
                  onChange={(e) => onRangeChange({ ...range, start: e.target.value || undefined })}
                  className="mt-1 w-full px-2 py-1.5 bg-slate-900 border border-slate-600 rounded text-sm text-white"
                />
              </label>
              <label className="text-xs text-gray-400">
                To
                <input
                  type="datetime-local"
                  value={toInput(range.end)}
                  onChange={(e) => onRangeChange({ ...range, end: e.target.value || undefined })}
                  className="mt-1 w-full px-2 py-1.5 bg-slate-900 border border-slate-600 rounded text-sm text-white"
                />
              </label>
            </div>
            <p className="text-[11px] text-gray-500 mt-2">
              Leave the time at 00:00 to include the whole day. A single day = same From and To date.
              This also sets the period shown across stats, tables and charts.
            </p>
          </div>
        )}

        {!ready || reversed ? (
          <div className="flex items-start gap-2 bg-yellow-500/10 border border-yellow-600/40 rounded-lg p-3 text-sm text-yellow-200">
            <AlertTriangle size={16} className="mt-0.5 shrink-0" />
            {reversed
              ? 'The start is after the end — fix the From/To dates to continue.'
              : 'Set both a From and a To date above — regeneration is only ever applied inside an explicit period.'}
          </div>
        ) : result ? (
          <div className="space-y-2 text-sm">
            <div className="flex items-start gap-2 bg-emerald-500/10 border border-emerald-600/40 rounded-lg p-3 text-emerald-200">
              <ShieldCheck size={16} className="mt-0.5 shrink-0" />
              {result.preserved_rows} rows outside the period were verified unchanged.
            </div>
            <div className="grid grid-cols-2 gap-2 text-gray-300">
              <span>Trades replaced</span>
              <span className="font-mono text-right">
                -{result.deleted_trades} / +{result.generated_trades}
              </span>
              <span>Transactions replaced</span>
              <span className="font-mono text-right">
                -{result.deleted_transactions} / +{result.generated_transactions}
              </span>
              <span>Period net P&amp;L</span>
              <span className={`font-mono text-right ${result.net_pnl >= 0 ? 'text-green-400' : 'text-red-400'}`}>
                ${result.net_pnl.toFixed(2)}
              </span>
              <span>Bots regenerated</span>
              <span className="font-mono text-right">
                {result.bots_regenerated}
                {result.bots_skipped_locked > 0 ? ` (${result.bots_skipped_locked} locked skipped)` : ''}
              </span>
            </div>
          </div>
        ) : (
          <>
            <div className="flex items-start gap-2 bg-slate-700/50 rounded-lg p-3 mb-4 text-xs text-gray-300">
              <ShieldCheck size={14} className="mt-0.5 shrink-0 text-emerald-400" />
              Only unpinned trades that open <em>and</em> close inside the period are replaced. Pinned
              trades, locked bots/accounts, trades crossing a period boundary and every row outside
              the period stay exactly as they are — the run aborts if anything outside would change.
            </div>

            <div className="grid grid-cols-2 gap-3 mb-4">
              <label className="text-xs text-gray-400">
                Target net P&amp;L ($)
                <input
                  type="number"
                  value={targetNetPnl}
                  onChange={(e) => setTargetNetPnl(e.target.value)}
                  placeholder="random"
                  className="mt-1 w-full px-2 py-1.5 bg-slate-900 border border-slate-600 rounded text-sm text-white"
                />
              </label>
              <label className="text-xs text-gray-400">
                Trades per day
                <input
                  type="number"
                  step="0.1"
                  value={tradesPerDay}
                  onChange={(e) => setTradesPerDay(e.target.value)}
                  placeholder="by strategy"
                  className="mt-1 w-full px-2 py-1.5 bg-slate-900 border border-slate-600 rounded text-sm text-white"
                />
              </label>
              <label className="text-xs text-gray-400">
                Seed (repeatable runs)
                <input
                  type="number"
                  value={seed}
                  onChange={(e) => setSeed(e.target.value)}
                  placeholder="auto"
                  className="mt-1 w-full px-2 py-1.5 bg-slate-900 border border-slate-600 rounded text-sm text-white"
                />
              </label>
            </div>

            {entityType !== 'bot' && (
              <label className="flex items-center gap-2 text-sm text-gray-300 mb-3">
                <input
                  type="checkbox"
                  checked={withTransactions}
                  onChange={(e) => setWithTransactions(e.target.checked)}
                />
                Also regenerate deposits/withdrawals inside the period
              </label>
            )}

            {entityType !== 'bot' && withTransactions && (
              <div className="grid grid-cols-3 gap-3 mb-4">
                <label className="text-xs text-gray-400">
                  Deposits total ($)
                  <input
                    type="number"
                    value={depositTotal}
                    onChange={(e) => setDepositTotal(e.target.value)}
                    className="mt-1 w-full px-2 py-1.5 bg-slate-900 border border-slate-600 rounded text-sm text-white"
                  />
                </label>
                <label className="text-xs text-gray-400">
                  Withdrawals total ($)
                  <input
                    type="number"
                    value={withdrawalTotal}
                    onChange={(e) => setWithdrawalTotal(e.target.value)}
                    className="mt-1 w-full px-2 py-1.5 bg-slate-900 border border-slate-600 rounded text-sm text-white"
                  />
                </label>
                <label className="text-xs text-gray-400">
                  Count each
                  <input
                    type="number"
                    value={transactionCount}
                    onChange={(e) => setTransactionCount(e.target.value)}
                    className="mt-1 w-full px-2 py-1.5 bg-slate-900 border border-slate-600 rounded text-sm text-white"
                  />
                </label>
              </div>
            )}
          </>
        )}

        {error && (
          <div className="bg-red-500/10 border border-red-600/40 rounded-lg p-3 text-sm text-red-200 mt-3">
            {error}
          </div>
        )}

        <div className="flex justify-end gap-3 mt-5">
          <button
            onClick={onClose}
            className="px-4 py-2 bg-slate-700 hover:bg-slate-600 rounded-lg text-sm transition-colors"
            disabled={running}
          >
            {result ? 'Close' : 'Cancel'}
          </button>
          {!result && (
            <button
              onClick={submit}
              disabled={running || !ready || reversed}
              className="flex items-center gap-2 px-4 py-2 bg-purple-600 hover:bg-purple-500 disabled:bg-purple-900 disabled:text-gray-400 rounded-lg text-sm font-medium transition-colors"
            >
              <RefreshCw size={14} className={running ? 'animate-spin' : ''} />
              {running ? 'Generating...' : 'Generate for period'}
            </button>
          )}
        </div>
      </div>
    </div>
  );
}
