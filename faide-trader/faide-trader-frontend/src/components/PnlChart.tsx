import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Area, AreaChart } from 'recharts';
import { type PnlRecord } from '@/lib/api';

interface PnlChartProps {
  records: PnlRecord[];
  height?: number;
}

export function PnlChart({ records, height = 300 }: PnlChartProps) {
  if (records.length === 0) {
    return (
      <div className="flex items-center justify-center text-gray-500" style={{ height }}>
        No P&L data available
      </div>
    );
  }

  const data = records.map((r) => ({
    date: new Date(r.date).toLocaleDateString('en-US', { month: 'short', day: 'numeric' }),
    pnl: r.pnl,
    cumulative: r.cumulative_pnl,
    trades: r.trade_count,
    wins: r.win_count,
  }));

  return (
    <div className="space-y-4">
      <div>
        <h4 className="text-xs text-gray-400 mb-2">Cumulative P&L</h4>
        <ResponsiveContainer width="100%" height={height}>
          <AreaChart data={data}>
            <defs>
              <linearGradient id="colorPnl" x1="0" y1="0" x2="0" y2="1">
                <stop offset="5%" stopColor="#22c55e" stopOpacity={0.3} />
                <stop offset="95%" stopColor="#22c55e" stopOpacity={0} />
              </linearGradient>
            </defs>
            <CartesianGrid strokeDasharray="3 3" stroke="#334155" />
            <XAxis dataKey="date" tick={{ fontSize: 11, fill: '#94a3b8' }} />
            <YAxis tick={{ fontSize: 11, fill: '#94a3b8' }} tickFormatter={(v) => `$${v}`} />
            <Tooltip
              contentStyle={{ backgroundColor: '#1e293b', border: '1px solid #334155', borderRadius: '8px' }}
              labelStyle={{ color: '#94a3b8' }}
              formatter={(value: number) => [`$${value.toFixed(2)}`, 'Cumulative P&L']}
            />
            <Area
              type="monotone"
              dataKey="cumulative"
              stroke="#22c55e"
              fill="url(#colorPnl)"
              strokeWidth={2}
            />
          </AreaChart>
        </ResponsiveContainer>
      </div>

      <div>
        <h4 className="text-xs text-gray-400 mb-2">Daily P&L</h4>
        <ResponsiveContainer width="100%" height={180}>
          <LineChart data={data}>
            <CartesianGrid strokeDasharray="3 3" stroke="#334155" />
            <XAxis dataKey="date" tick={{ fontSize: 11, fill: '#94a3b8' }} />
            <YAxis tick={{ fontSize: 11, fill: '#94a3b8' }} tickFormatter={(v) => `$${v}`} />
            <Tooltip
              contentStyle={{ backgroundColor: '#1e293b', border: '1px solid #334155', borderRadius: '8px' }}
              labelStyle={{ color: '#94a3b8' }}
              formatter={(value: number, name: string) => {
                if (name === 'pnl') return [`$${value.toFixed(2)}`, 'Daily P&L'];
                return [value, name];
              }}
            />
            <Line type="monotone" dataKey="pnl" stroke="#60a5fa" strokeWidth={2} dot={{ r: 3 }} />
          </LineChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}
