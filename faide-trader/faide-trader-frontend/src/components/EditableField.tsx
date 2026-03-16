import { useState, useRef, useEffect } from 'react';

interface EditableFieldProps {
  value: number | string;
  onSave: (value: number | string) => void;
  type?: 'number' | 'text';
  prefix?: string;
  suffix?: string;
  decimals?: number;
  className?: string;
  isPinned?: boolean;
  onTogglePin?: () => void;
}

export function EditableField({
  value,
  onSave,
  type = 'number',
  prefix = '',
  suffix = '',
  decimals = 2,
  className = '',
  isPinned,
  onTogglePin,
}: EditableFieldProps) {
  const [editing, setEditing] = useState(false);
  const [editValue, setEditValue] = useState(String(value));
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (editing && inputRef.current) {
      inputRef.current.focus();
      inputRef.current.select();
    }
  }, [editing]);

  const displayValue = type === 'number'
    ? `${prefix}${Number(value).toLocaleString(undefined, { minimumFractionDigits: decimals, maximumFractionDigits: decimals })}${suffix}`
    : `${prefix}${value}${suffix}`;

  const pnlColor = type === 'number' && typeof value === 'number'
    ? value > 0 ? 'text-green-400' : value < 0 ? 'text-red-400' : 'text-gray-400'
    : '';

  const handleSave = () => {
    setEditing(false);
    const newVal = type === 'number' ? parseFloat(editValue) : editValue;
    if (type === 'number' && isNaN(newVal as number)) return;
    if (newVal !== value) {
      onSave(newVal);
    }
  };

  if (editing) {
    return (
      <input
        ref={inputRef}
        type={type === 'number' ? 'number' : 'text'}
        value={editValue}
        onChange={(e) => setEditValue(e.target.value)}
        onBlur={handleSave}
        onKeyDown={(e) => {
          if (e.key === 'Enter') handleSave();
          if (e.key === 'Escape') setEditing(false);
        }}
        className={`bg-slate-700 border border-blue-500 rounded px-2 py-0.5 text-sm outline-none w-full ${className}`}
        step="any"
      />
    );
  }

  return (
    <div className="flex items-center gap-1 group">
      <span
        onClick={() => {
          setEditValue(String(value));
          setEditing(true);
        }}
        className={`cursor-pointer hover:bg-slate-700 rounded px-1 py-0.5 transition-colors text-sm ${pnlColor} ${className}`}
        title="Click to edit"
      >
        {displayValue}
      </span>
      {onTogglePin && (
        <button
          onClick={onTogglePin}
          className={`opacity-0 group-hover:opacity-100 transition-opacity text-xs ${isPinned ? 'text-yellow-400' : 'text-gray-500 hover:text-yellow-400'}`}
          title={isPinned ? 'Unpin (value will recalculate)' : 'Pin (value stays fixed)'}
        >
          {isPinned ? '📌' : '📌'}
        </button>
      )}
    </div>
  );
}
