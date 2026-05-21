import { useState, useEffect } from 'react';
import { api, type Transaction } from '@/lib/api';
import { Plus, Trash2, ArrowUpRight, ArrowDownRight } from 'lucide-react';

interface TransactionsViewProps {
  accountId?: number;
  portfolioId?: number;
  onChanged?: () => void;
}

export function TransactionsView({ accountId, portfolioId, onChanged }: TransactionsViewProps) {
  const [transactions, setTransactions] = useState<Transaction[]>([]);
  const [showAdd, setShowAdd] = useState(false);
  const [newTx, setNewTx] = useState({ type: 'deposit', amount: '', note: '', date: '' });
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    loadTransactions();
  }, [accountId, portfolioId]);

  const loadTransactions = async () => {
    try {
      if (accountId) {
        const data = await api.listTransactions(accountId);
        setTransactions(data);
      } else if (portfolioId) {
        const data = await api.listPortfolioTransactions(portfolioId);
        setTransactions(data);
      }
    } catch {
      setTransactions([]);
    }
  };

  const totalDeposits = transactions.filter(t => t.type === 'deposit').reduce((s, t) => s + t.amount, 0);
  const totalWithdrawals = transactions.filter(t => t.type === 'withdrawal').reduce((s, t) => s + t.amount, 0);
  const netFlow = totalDeposits - totalWithdrawals;

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!accountId || !newTx.amount || !newTx.date) return;
    setSubmitting(true);
    try {
      await api.createTransaction(accountId, {
        type: newTx.type,
        amount: parseFloat(newTx.amount),
        note: newTx.note,
        date: newTx.date,
      });
      setShowAdd(false);
      setNewTx({ type: 'deposit', amount: '', note: '', date: '' });
      loadTransactions();
      onChanged?.();
    } catch (err) {
      alert(err instanceof Error ? err.message : 'Failed to add transaction');
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="bg-slate-800/50 border border-slate-700 rounded-lg p-4">
      <div className="flex items-center justify-between mb-4">
        <h3 className="text-sm font-semibold text-gray-300">
          Deposits & Withdrawals ({transactions.length})
        </h3>
        <div className="flex items-center gap-3">
          <div className="flex gap-4 text-xs">
            <span className="text-green-400">Deposits: ${totalDeposits.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}</span>
            <span className="text-red-400">Withdrawals: ${totalWithdrawals.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}</span>
            <span className={netFlow >= 0 ? 'text-green-400' : 'text-red-400'}>
              Net: ${netFlow.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
            </span>
          </div>
          {accountId && (
            <button
              onClick={() => setShowAdd(!showAdd)}
              className="flex items-center gap-1 px-2 py-1 bg-blue-600 hover:bg-blue-500 rounded text-xs font-medium transition-colors"
            >
              <Plus size={12} /> Add
            </button>
          )}
        </div>
      </div>

      {showAdd && (
        <form onSubmit={handleSubmit} className="mb-4 bg-slate-700/50 rounded-lg p-3 flex flex-wrap gap-3 items-end">
          <div>
            <label className="text-xs text-gray-400 block mb-1">Type</label>
            <select
              value={newTx.type}
              onChange={e => setNewTx({ ...newTx, type: e.target.value })}
              className="bg-slate-600 border border-slate-500 rounded px-2 py-1.5 text-sm"
            >
              <option value="deposit">Deposit</option>
              <option value="withdrawal">Withdrawal</option>
            </select>
          </div>
          <div>
            <label className="text-xs text-gray-400 block mb-1">Amount ($)</label>
            <input
              type="number"
              step="0.01"
              value={newTx.amount}
              onChange={e => setNewTx({ ...newTx, amount: e.target.value })}
              className="bg-slate-600 border border-slate-500 rounded px-2 py-1.5 text-sm w-28"
              required
            />
          </div>
          <div>
            <label className="text-xs text-gray-400 block mb-1">Date</label>
            <input
              type="date"
              value={newTx.date}
              onChange={e => setNewTx({ ...newTx, date: e.target.value })}
              className="bg-slate-600 border border-slate-500 rounded px-2 py-1.5 text-sm"
              required
            />
          </div>
          <div>
            <label className="text-xs text-gray-400 block mb-1">Note</label>
            <input
              type="text"
              value={newTx.note}
              onChange={e => setNewTx({ ...newTx, note: e.target.value })}
              className="bg-slate-600 border border-slate-500 rounded px-2 py-1.5 text-sm w-40"
              placeholder="Optional"
            />
          </div>
          <button
            type="submit"
            disabled={submitting}
            className="px-3 py-1.5 bg-green-600 hover:bg-green-500 rounded text-sm font-medium transition-colors disabled:opacity-50"
          >
            {submitting ? 'Adding...' : 'Add'}
          </button>
        </form>
      )}

      {transactions.length === 0 ? (
        <p className="text-center text-gray-500 text-sm py-4">No deposits or withdrawals recorded.</p>
      ) : (
        <div className="max-h-64 overflow-y-auto">
          <table className="w-full text-sm">
            <thead className="text-xs text-gray-400 sticky top-0 bg-slate-800/90">
              <tr>
                <th className="text-left py-1 px-2">Date</th>
                <th className="text-left py-1 px-2">Type</th>
                <th className="text-right py-1 px-2">Amount</th>
                <th className="text-left py-1 px-2">Note</th>
                {accountId && <th className="text-right py-1 px-2">Actions</th>}
              </tr>
            </thead>
            <tbody>
              {transactions.map(tx => (
                <tr key={tx.id} className="border-t border-slate-700/50 hover:bg-slate-700/30">
                  <td className="py-1.5 px-2 text-gray-300">
                    {new Date(tx.date).toLocaleDateString()}
                  </td>
                  <td className="py-1.5 px-2">
                    <span className={`flex items-center gap-1 text-xs font-medium ${tx.type === 'deposit' ? 'text-green-400' : 'text-red-400'}`}>
                      {tx.type === 'deposit' ? <ArrowDownRight size={12} /> : <ArrowUpRight size={12} />}
                      {tx.type === 'deposit' ? 'Deposit' : 'Withdrawal'}
                    </span>
                  </td>
                  <td className={`py-1.5 px-2 text-right font-mono ${tx.type === 'deposit' ? 'text-green-400' : 'text-red-400'}`}>
                    {tx.type === 'deposit' ? '+' : '-'}${tx.amount.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
                  </td>
                  <td className="py-1.5 px-2 text-gray-400 text-xs">{tx.note}</td>
                  {accountId && (
                    <td className="py-1.5 px-2 text-right">
                      <button
                        onClick={async () => {
                          if (confirm('Delete this transaction?')) {
                            await api.deleteTransaction(tx.id);
                            loadTransactions();
                            onChanged?.();
                          }
                        }}
                        className="text-gray-400 hover:text-red-400 transition-colors"
                        title="Delete"
                      >
                        <Trash2 size={12} />
                      </button>
                    </td>
                  )}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
