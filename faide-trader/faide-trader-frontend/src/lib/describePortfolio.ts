import type { Portfolio } from './api';

export function describePortfolio(p: Portfolio): string {
  if (!p.data_end) return p.description;
  const end = new Date(p.data_end).toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' });
  return p.description.replace(/\bpresent\b/i, end);
}
