import { api, type Portfolio, type Account, type Stats, type PeriodPnl, type EquityCurvePoint, type Transaction } from './api';

interface AccountData {
  account: Account;
  stats: Stats | null;
  equityCurve: EquityCurvePoint[];
  periodPnl: PeriodPnl[];
  transactions: Transaction[];
}

interface ExportData {
  portfolio: Portfolio;
  stats: Stats | null;
  equityCurve: EquityCurvePoint[];
  periodPnl: PeriodPnl[];
  transactions: Transaction[];
  accounts: AccountData[];
}

async function fetchExportData(portfolioId: number): Promise<ExportData> {
  const [portfolio, stats, equityCurve, periodPnl, transactions, accounts] = await Promise.all([
    api.getPortfolio(portfolioId),
    api.getPortfolioStats(portfolioId).catch(() => null),
    api.getPortfolioEquityCurve(portfolioId).catch(() => []),
    api.getPortfolioPeriodPnl(portfolioId, 'monthly').catch(() => []),
    api.listPortfolioTransactions(portfolioId).catch(() => []),
    api.listAccounts(portfolioId),
  ]);

  const accountsData: AccountData[] = await Promise.all(
    accounts.map(async (account) => {
      const [accStats, accEquity, accPeriod, accTx] = await Promise.all([
        api.getAccountStats(account.id).catch(() => null),
        api.getAccountEquityCurve(account.id).catch(() => []),
        api.getAccountPeriodPnl(account.id, 'monthly').catch(() => []),
        api.listTransactions(account.id).catch(() => []),
      ]);
      return { account, stats: accStats, equityCurve: accEquity, periodPnl: accPeriod, transactions: accTx };
    })
  );

  return { portfolio, stats, equityCurve, periodPnl, transactions, accounts: accountsData };
}

function fmt(v: number, decimals = 2): string {
  return v.toLocaleString(undefined, { minimumFractionDigits: decimals, maximumFractionDigits: decimals });
}

function fmtCurrency(v: number): string {
  const sign = v < 0 ? '-' : '';
  return `${sign}$${fmt(Math.abs(v))}`;
}

function pnlColor(v: number): string {
  return v >= 0 ? '#4ade80' : '#f87171';
}

function renderStatsGrid(stats: Stats): string {
  const items: [string, string, string?][] = [
    ['Total P&L', fmtCurrency(stats.total_pnl), pnlColor(stats.total_pnl)],
    ['ROI', `${fmt(stats.roi_percent)}%`],
    ['Win Rate', `${fmt(stats.win_rate)}%`],
    ['Trades', `${stats.total_trades}`],
    ['Wins', `${stats.win_count}`],
    ['Losses', `${stats.loss_count}`],
    ['Sharpe', `${fmt(stats.sharpe_ratio, 4)}`],
    ['Sortino', `${fmt(stats.sortino_ratio, 4)}`],
    ['Max DD $', fmtCurrency(stats.max_drawdown)],
    ['Max DD %', `${fmt(stats.max_drawdown_percent)}%`],
    ['Profit Factor', `${fmt(stats.profit_factor)}`],
    ['Avg Win', fmtCurrency(stats.avg_win)],
    ['Avg Loss', fmtCurrency(stats.avg_loss)],
    ['Best Trade', fmtCurrency(stats.best_trade)],
    ['Worst Trade', fmtCurrency(stats.worst_trade)],
    ['Avg Trade', fmtCurrency(stats.avg_trade_pnl)],
    ['Total Fees', fmtCurrency(stats.total_fees)],
    ['Net P&L', fmtCurrency(stats.net_pnl), pnlColor(stats.net_pnl)],
    ['Calmar', `${fmt(stats.calmar_ratio, 4)}`],
    ['Balance', fmtCurrency(stats.current_balance)],
  ];

  return `<div class="stats-grid">${items.map(([label, val, color]) =>
    `<div class="stat-item"><div class="stat-label">${label}</div><div class="stat-value" ${color ? `style="color:${color}"` : ''}>${val}</div></div>`
  ).join('')}</div>`;
}

function renderPeriodTable(periods: PeriodPnl[]): string {
  if (periods.length === 0) return '';
  return `
    <table>
      <thead><tr>
        <th>Period</th><th>P&L</th><th>Cumul.</th><th>Trades</th>
        <th>W/L</th><th>Win %</th><th>Avg</th><th>PF</th><th>DD $</th><th>DD %</th>
      </tr></thead>
      <tbody>${periods.map(p => `<tr>
        <td>${p.period}</td>
        <td style="color:${pnlColor(p.pnl)}">${fmtCurrency(p.pnl)}</td>
        <td>${fmtCurrency(p.cumulative_pnl)}</td>
        <td>${p.trade_count}</td>
        <td>${p.win_count}/${p.loss_count}</td>
        <td>${fmt(p.win_rate)}%</td>
        <td>${fmtCurrency(p.avg_pnl)}</td>
        <td>${fmt(p.profit_factor)}</td>
        <td>${p.drawdown > 0 ? fmtCurrency(p.drawdown) : '-'}</td>
        <td>${p.drawdown_percent > 0 ? fmt(p.drawdown_percent) + '%' : '-'}</td>
      </tr>`).join('')}</tbody>
    </table>`;
}

function renderTransactionsTable(transactions: Transaction[]): string {
  if (transactions.length === 0) return '<p class="muted">No transactions</p>';
  const deps = transactions.filter(t => t.type === 'deposit');
  const wds = transactions.filter(t => t.type === 'withdrawal');
  const totalDeps = deps.reduce((s, t) => s + t.amount, 0);
  const totalWds = wds.reduce((s, t) => s + t.amount, 0);

  return `
    <div class="tx-summary">
      <span>Deposits: <span style="color:#4ade80">${fmtCurrency(totalDeps)}</span> (${deps.length}x)</span>
      <span>Withdrawals: <span style="color:#fb923c">${fmtCurrency(totalWds)}</span> (${wds.length}x)</span>
      <span>Net: <span style="color:#60a5fa">${fmtCurrency(totalDeps - totalWds)}</span></span>
    </div>
    <table>
      <thead><tr><th>Date</th><th>Type</th><th>Amount</th><th>Note</th></tr></thead>
      <tbody>${transactions.map(t => `<tr>
        <td>${new Date(t.date).toLocaleDateString()}</td>
        <td><span class="badge ${t.type}">${t.type}</span></td>
        <td style="color:${t.type === 'deposit' ? '#4ade80' : '#fb923c'}">${t.type === 'deposit' ? '+' : '-'}${fmtCurrency(t.amount)}</td>
        <td class="muted">${t.note || ''}</td>
      </tr>`).join('')}</tbody>
    </table>`;
}

function renderEquitySummary(curve: EquityCurvePoint[]): string {
  if (curve.length === 0) return '';
  const first = curve[0];
  const last = curve[curve.length - 1];
  const maxDD = Math.max(...curve.map(d => d.drawdown));
  const maxDDPct = Math.max(...curve.map(d => d.drawdown_percent));
  const totalDeps = curve.reduce((s, d) => s + d.deposits, 0);
  const totalWds = curve.reduce((s, d) => s + d.withdrawals, 0);
  const depCount = curve.filter(d => d.deposits > 0).length;
  const wdCount = curve.filter(d => d.withdrawals > 0).length;

  return `<div class="equity-summary">
    <div class="stat-item"><div class="stat-label">Starting Balance</div><div class="stat-value">${fmtCurrency(first.balance)}</div></div>
    <div class="stat-item"><div class="stat-label">Current Balance</div><div class="stat-value">${fmtCurrency(last.balance)}</div></div>
    <div class="stat-item"><div class="stat-label">Trading P&L</div><div class="stat-value" style="color:${pnlColor(last.cumulative_pnl)}">${fmtCurrency(last.cumulative_pnl)}</div></div>
    <div class="stat-item"><div class="stat-label">Max Drawdown</div><div class="stat-value" style="color:#f87171">${fmtCurrency(maxDD)} (${fmt(maxDDPct, 1)}%)</div></div>
    <div class="stat-item"><div class="stat-label">Total Deposits</div><div class="stat-value" style="color:#4ade80">${fmtCurrency(totalDeps)} (${depCount}x)</div></div>
    <div class="stat-item"><div class="stat-label">Total Withdrawals</div><div class="stat-value" style="color:#fb923c">${fmtCurrency(totalWds)} (${wdCount}x)</div></div>
  </div>`;
}

function generateHTML(data: ExportData): string {
  const now = new Date().toLocaleString();

  const accountSections = data.accounts.map((ad, i) => `
    <div class="section">
      <h2>${ad.account.name} <span class="badge exchange">${ad.account.exchange.replace('_', ' ').toUpperCase()}</span></h2>
      <p class="muted">${ad.account.bot_count} bot${ad.account.bot_count !== 1 ? 's' : ''} · ${ad.account.total_trades} trades · Initial: ${fmtCurrency(ad.account.initial_balance)}</p>
      ${ad.stats ? renderStatsGrid(ad.stats) : '<p class="muted">No trading data</p>'}
      ${ad.equityCurve.length > 0 ? `
        <h3>Equity Curve</h3>
        <canvas id="chart-account-${i}" height="250"></canvas>
        ${renderEquitySummary(ad.equityCurve)}
      ` : ''}
      ${ad.periodPnl.length > 0 ? `<h3>Monthly P&L</h3>${renderPeriodTable(ad.periodPnl)}` : ''}
      ${ad.transactions.length > 0 ? `<h3>Transactions (${ad.transactions.length})</h3>${renderTransactionsTable(ad.transactions)}` : ''}
    </div>
  `).join('');

  const equityCurveData = JSON.stringify(data.equityCurve.map(d => ({
    date: d.date, balance: d.balance, pnl: d.cumulative_pnl,
    dd: -d.drawdown, peak: d.peak_balance
  })));

  const accountCurveScripts = data.accounts.map((ad, i) => {
    if (ad.equityCurve.length === 0) return '';
    const curveData = JSON.stringify(ad.equityCurve.map(d => ({
      date: d.date, balance: d.balance, pnl: d.cumulative_pnl,
      dd: -d.drawdown, peak: d.peak_balance
    })));
    return `renderEquityChart('chart-account-${i}', ${curveData});`;
  }).join('\n');

  return `<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>${data.portfolio.name} — Portfolio Report</title>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4"></script>
<style>
  * { margin: 0; padding: 0; box-sizing: border-box; }
  body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; background: #0f172a; color: #e2e8f0; line-height: 1.5; padding: 24px; max-width: 1200px; margin: 0 auto; }
  h1 { font-size: 1.75rem; margin-bottom: 4px; }
  h2 { font-size: 1.25rem; margin-bottom: 8px; border-bottom: 1px solid #334155; padding-bottom: 8px; }
  h3 { font-size: 0.95rem; color: #94a3b8; margin: 16px 0 8px; }
  .muted { color: #64748b; font-size: 0.85rem; }
  .header { margin-bottom: 24px; }
  .header p { color: #94a3b8; }
  .generated { color: #475569; font-size: 0.75rem; margin-top: 8px; }
  .section { background: #1e293b; border: 1px solid #334155; border-radius: 8px; padding: 16px; margin-bottom: 16px; }
  .stats-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(140px, 1fr)); gap: 8px; margin: 8px 0; }
  .stat-item { background: #334155; border-radius: 6px; padding: 8px 12px; }
  .stat-label { color: #64748b; font-size: 0.7rem; text-transform: uppercase; letter-spacing: 0.5px; }
  .stat-value { font-family: 'SF Mono', 'Fira Code', monospace; font-size: 0.85rem; font-weight: 600; }
  .equity-summary { display: grid; grid-template-columns: repeat(auto-fill, minmax(150px, 1fr)); gap: 8px; margin: 12px 0; }
  table { width: 100%; border-collapse: collapse; font-size: 0.8rem; margin: 8px 0; }
  th { background: #334155; color: #94a3b8; font-weight: 600; text-align: left; padding: 6px 10px; font-size: 0.75rem; text-transform: uppercase; letter-spacing: 0.3px; }
  td { padding: 5px 10px; border-bottom: 1px solid #1e293b; font-family: 'SF Mono', 'Fira Code', monospace; font-size: 0.8rem; }
  tr:hover { background: #334155; }
  .badge { padding: 2px 8px; border-radius: 4px; font-size: 0.7rem; font-weight: 600; text-transform: uppercase; }
  .badge.deposit { background: #166534; color: #4ade80; }
  .badge.withdrawal { background: #9a3412; color: #fb923c; }
  .badge.exchange { background: #1e40af; color: #60a5fa; font-size: 0.65rem; }
  .tx-summary { display: flex; gap: 24px; margin: 8px 0; font-size: 0.85rem; }
  canvas { margin: 8px 0; }
  .footer { text-align: center; color: #475569; font-size: 0.7rem; margin-top: 32px; padding-top: 16px; border-top: 1px solid #1e293b; }
  @media print { body { background: #fff; color: #1e293b; } .section { border-color: #e2e8f0; } th { background: #f1f5f9; color: #475569; } td { border-color: #e2e8f0; } .stat-item { background: #f1f5f9; } .stat-label { color: #64748b; } }
</style>
</head>
<body>
<div class="header">
  <h1>${data.portfolio.name}</h1>
  <p>${data.portfolio.description || ''}</p>
  <p class="muted">${data.accounts.length} account${data.accounts.length !== 1 ? 's' : ''} · Balance: ${fmtCurrency(data.portfolio.total_balance)} · P&L: <span style="color:${pnlColor(data.portfolio.total_pnl)}">${fmtCurrency(data.portfolio.total_pnl)}</span></p>
  <p class="generated">Report generated: ${now}</p>
</div>

${data.stats ? `<div class="section"><h2>Portfolio Statistics</h2>${renderStatsGrid(data.stats)}</div>` : ''}

${data.equityCurve.length > 0 ? `
<div class="section">
  <h2>Portfolio Equity Curve</h2>
  <canvas id="chart-portfolio" height="300"></canvas>
  ${renderEquitySummary(data.equityCurve)}
</div>
` : ''}

${data.periodPnl.length > 0 ? `<div class="section"><h2>Monthly P&L</h2>${renderPeriodTable(data.periodPnl)}</div>` : ''}

${data.transactions.length > 0 ? `<div class="section"><h2>Deposits & Withdrawals (${data.transactions.length})</h2>${renderTransactionsTable(data.transactions)}</div>` : ''}

<h2 style="margin: 24px 0 12px;">Accounts</h2>
${accountSections}

<div class="footer">Faide Trader · Portfolio Report · ${now}</div>

<script>
function renderEquityChart(canvasId, data) {
  const ctx = document.getElementById(canvasId);
  if (!ctx || !data.length) return;
  const labels = data.map(d => d.date);
  new Chart(ctx, {
    type: 'line',
    data: {
      labels,
      datasets: [
        { label: 'Balance', data: data.map(d => d.balance), borderColor: '#3b82f6', backgroundColor: 'rgba(59,130,246,0.1)', fill: true, borderWidth: 1.5, pointRadius: 0, tension: 0.1 },
        { label: 'Trading P&L', data: data.map(d => d.pnl), borderColor: '#22c55e', borderWidth: 1, pointRadius: 0, tension: 0.1 },
        { label: 'Peak', data: data.map(d => d.peak), borderColor: '#64748b', borderWidth: 1, borderDash: [4,4], pointRadius: 0, tension: 0.1 },
        { label: 'Drawdown', data: data.map(d => d.dd), borderColor: '#ef4444', backgroundColor: 'rgba(239,68,68,0.1)', fill: true, borderWidth: 1, pointRadius: 0, tension: 0.1 },
      ]
    },
    options: {
      responsive: true,
      interaction: { mode: 'index', intersect: false },
      plugins: { legend: { labels: { color: '#94a3b8', font: { size: 11 } } }, tooltip: { backgroundColor: '#1e293b', titleColor: '#e2e8f0', bodyColor: '#94a3b8', borderColor: '#334155', borderWidth: 1, callbacks: { label: function(ctx) { return ctx.dataset.label + ': $' + ctx.raw.toLocaleString(undefined, {minimumFractionDigits:0, maximumFractionDigits:0}); } } } },
      scales: {
        x: { ticks: { color: '#64748b', font: { size: 10 }, maxTicksLimit: 12 }, grid: { color: '#1e293b' } },
        y: { ticks: { color: '#64748b', font: { size: 10 }, callback: v => '$' + (v/1000).toFixed(0) + 'k' }, grid: { color: '#1e293b' } }
      }
    }
  });
}

document.addEventListener('DOMContentLoaded', function() {
  renderEquityChart('chart-portfolio', ${equityCurveData});
  ${accountCurveScripts}
});
</script>
</body>
</html>`;
}

export async function exportPortfolioReport(portfolioId: number): Promise<void> {
  const data = await fetchExportData(portfolioId);
  const html = generateHTML(data);
  const blob = new Blob([html], { type: 'text/html' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = `${data.portfolio.name.replace(/[^a-zA-Z0-9]/g, '_')}_Report_${new Date().toISOString().slice(0, 10)}.html`;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
}
