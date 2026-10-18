import { useEffect, useState } from 'react';
import type { DateRange } from '@/lib/api';

interface PeriodFieldsProps {
  value: DateRange;
  onChange: (range: DateRange) => void;
}

function datePart(value?: string): string {
  return value ? value.slice(0, 10) : '';
}

function timePart(value?: string): string {
  return value && value.length > 10 ? value.slice(11, 16) : '';
}

function combine(date: string, timeValue: string): string | undefined {
  if (!date) return undefined;
  return timeValue ? `${date}T${timeValue}` : date;
}

const inputClass =
  'w-full px-2 py-1.5 bg-slate-900 border border-slate-600 rounded text-sm text-white [color-scheme:dark]';

/**
 * Date/time inputs keep their own draft state so a half-typed date is never
 * wiped by the parent re-rendering with an empty value.
 */
export function PeriodFields({ value, onChange }: PeriodFieldsProps) {
  const [draft, setDraft] = useState({
    startDate: datePart(value.start),
    startTime: timePart(value.start),
    endDate: datePart(value.end),
    endTime: timePart(value.end),
  });

  useEffect(() => {
    setDraft((prev) => {
      const next = {
        startDate: datePart(value.start),
        startTime: timePart(value.start),
        endDate: datePart(value.end),
        endTime: timePart(value.end),
      };
      const unchanged =
        combine(prev.startDate, prev.startTime) === value.start &&
        combine(prev.endDate, prev.endTime) === value.end;
      return unchanged ? prev : next;
    });
  }, [value.start, value.end]);

  const update = (patch: Partial<typeof draft>) => {
    const next = { ...draft, ...patch };
    setDraft(next);
    onChange({
      ...value,
      start: combine(next.startDate, next.startTime),
      end: combine(next.endDate, next.endTime),
    });
  };

  const bounds = [
    { key: 'start' as const, label: 'From', dateKey: 'startDate' as const, timeKey: 'startTime' as const },
    { key: 'end' as const, label: 'To', dateKey: 'endDate' as const, timeKey: 'endTime' as const },
  ];

  return (
    <div className="space-y-3">
      {bounds.map(({ key, label, dateKey, timeKey }) => (
        <div key={key}>
          <label className="block text-xs text-gray-400 mb-1">{label}</label>
          <div className="flex gap-2">
            <input
              type="date"
              value={draft[dateKey]}
              onChange={(e) => update({ [dateKey]: e.target.value })}
              className={inputClass}
            />
            <input
              type="time"
              value={draft[timeKey]}
              onChange={(e) => update({ [timeKey]: e.target.value })}
              disabled={!draft[dateKey]}
              className={`${inputClass} w-28 disabled:opacity-40`}
              title="Optional — leave empty to cover the whole day"
            />
          </div>
        </div>
      ))}
    </div>
  );
}
