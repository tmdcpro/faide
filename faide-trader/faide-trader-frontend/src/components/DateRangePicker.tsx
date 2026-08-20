import { useState } from 'react';
import { Calendar, X } from 'lucide-react';
import type { DateRange } from '@/lib/api';

interface DateRangePickerProps {
  value: DateRange;
  onChange: (range: DateRange) => void;
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

function formatDisplay(value: string): string {
  const d = new Date(value);
  if (Number.isNaN(d.getTime())) return value;
  const hasTime = value.length > 10 && !value.endsWith('T00:00');
  return d.toLocaleString('en-US', {
    month: 'short',
    day: 'numeric',
    year: 'numeric',
    ...(hasTime ? { hour: 'numeric', minute: '2-digit' } : {}),
  });
}

export function periodLabel(range: DateRange): string {
  if (!range.start && !range.end) return 'All time';
  if (range.start && !range.end) return `From ${formatDisplay(range.start)}`;
  if (!range.start && range.end) return `Until ${formatDisplay(range.end)}`;
  if (range.start === range.end) return formatDisplay(range.start!);
  return `${formatDisplay(range.start!)} → ${formatDisplay(range.end!)}`;
}

export function DateRangePicker({ value, onChange }: DateRangePickerProps) {
  const [open, setOpen] = useState(false);
  const active = Boolean(value.start || value.end);

  const applyPreset = (days: number) => {
    const end = new Date();
    const start = new Date(end.getTime() - (days - 1) * 24 * 60 * 60 * 1000);
    onChange({ start: toLocalDate(start), end: toLocalDate(end) });
  };

  return (
    <div className="relative">
      <button
        onClick={() => setOpen(!open)}
        className={`flex items-center gap-2 px-3 py-2 rounded-lg text-sm font-medium transition-colors border ${
          active
            ? 'bg-blue-600/20 border-blue-500 text-blue-200'
            : 'bg-slate-800 border-slate-700 text-gray-300 hover:border-slate-500'
        }`}
        title="Choose the period shown across stats, tables and charts"
      >
        <Calendar size={14} />
        <span>{periodLabel(value)}</span>
      </button>

      {active && (
        <button
          onClick={() => onChange({})}
          className="absolute -right-7 top-2 p-1 text-gray-400 hover:text-white"
          title="Clear period (show all time)"
        >
          <X size={14} />
        </button>
      )}

      {open && (
        <div className="absolute right-0 mt-2 w-80 bg-slate-800 border border-slate-700 rounded-lg p-4 z-50 shadow-xl">
          <div className="flex items-center justify-between mb-3">
            <span className="text-xs font-semibold text-gray-300 uppercase tracking-wide">Period</span>
            <button onClick={() => setOpen(false)} className="text-gray-400 hover:text-white">
              <X size={14} />
            </button>
          </div>

          <div className="flex gap-2 mb-4">
            {PRESETS.map((p) => (
              <button
                key={p.label}
                onClick={() => applyPreset(p.days)}
                className="flex-1 px-2 py-1 bg-slate-700 hover:bg-slate-600 rounded text-xs transition-colors"
              >
                {p.label}
              </button>
            ))}
          </div>

          <label className="block text-xs text-gray-400 mb-1">From</label>
          <input
            type="datetime-local"
            value={toInput(value.start)}
            onChange={(e) => onChange({ ...value, start: e.target.value || undefined })}
            className="w-full mb-3 px-2 py-1.5 bg-slate-900 border border-slate-600 rounded text-sm"
          />

          <label className="block text-xs text-gray-400 mb-1">To</label>
          <input
            type="datetime-local"
            value={toInput(value.end)}
            onChange={(e) => onChange({ ...value, end: e.target.value || undefined })}
            className="w-full mb-1 px-2 py-1.5 bg-slate-900 border border-slate-600 rounded text-sm"
          />
          <p className="text-[11px] text-gray-500 mb-3">
            Leave the time at 00:00 to include the whole day. A single day = same From and To date.
          </p>

          <div className="flex justify-between">
            <button
              onClick={() => onChange({})}
              className="px-3 py-1.5 bg-slate-700 hover:bg-slate-600 rounded text-xs transition-colors"
            >
              All time
            </button>
            <button
              onClick={() => setOpen(false)}
              className="px-3 py-1.5 bg-blue-600 hover:bg-blue-500 rounded text-xs font-medium transition-colors"
            >
              Done
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
