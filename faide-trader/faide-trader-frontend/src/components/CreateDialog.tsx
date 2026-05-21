import { useState } from 'react';
import { X } from 'lucide-react';

interface Field {
  name: string;
  label: string;
  type: 'text' | 'number' | 'select';
  options?: { value: string; label: string }[];
  defaultValue?: string | number;
  required?: boolean;
}

interface CreateDialogProps {
  title: string;
  fields: Field[];
  onSubmit: (data: Record<string, string | number>) => Promise<void>;
  onClose: () => void;
  submitLabel?: string;
}

export function CreateDialog({ title, fields, onSubmit, onClose, submitLabel }: CreateDialogProps) {
  const [values, setValues] = useState<Record<string, string | number>>(() => {
    const initial: Record<string, string | number> = {};
    fields.forEach((f) => {
      initial[f.name] = f.defaultValue ?? (f.type === 'number' ? 0 : '');
    });
    return initial;
  });
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState('');

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setSubmitting(true);
    setError('');
    try {
      await onSubmit(values);
      onClose();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed');
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="fixed inset-0 bg-black/60 flex items-center justify-center z-50" onClick={onClose}>
      <div
        className="bg-slate-800 border border-slate-700 rounded-lg w-full max-w-md p-6"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-lg font-semibold">{title}</h2>
          <button onClick={onClose} className="text-gray-400 hover:text-white">
            <X size={20} />
          </button>
        </div>

        {error && (
          <div className="bg-red-900/30 border border-red-700 text-red-400 text-sm rounded px-3 py-2 mb-4">
            {error}
          </div>
        )}

        <form onSubmit={handleSubmit} className="space-y-4">
          {fields.map((field) => (
            <div key={field.name}>
              <label className="block text-sm text-gray-400 mb-1">{field.label}</label>
              {field.type === 'select' ? (
                <select
                  value={values[field.name]}
                  onChange={(e) => setValues({ ...values, [field.name]: e.target.value })}
                  className="w-full bg-slate-700 border border-slate-600 rounded px-3 py-2 text-sm outline-none focus:border-blue-500"
                >
                  {field.options?.map((opt) => (
                    <option key={opt.value} value={opt.value}>{opt.label}</option>
                  ))}
                </select>
              ) : (
                <input
                  type={field.type}
                  value={values[field.name]}
                  onChange={(e) =>
                    setValues({
                      ...values,
                      [field.name]: field.type === 'number' ? parseFloat(e.target.value) || 0 : e.target.value,
                    })
                  }
                  className="w-full bg-slate-700 border border-slate-600 rounded px-3 py-2 text-sm outline-none focus:border-blue-500"
                  required={field.required}
                  step={field.type === 'number' ? 'any' : undefined}
                />
              )}
            </div>
          ))}

          <div className="flex gap-2 pt-2">
            <button
              type="button"
              onClick={onClose}
              className="flex-1 px-4 py-2 bg-slate-700 hover:bg-slate-600 rounded text-sm transition-colors"
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={submitting}
              className="flex-1 px-4 py-2 bg-blue-600 hover:bg-blue-500 rounded text-sm font-medium transition-colors disabled:opacity-50"
            >
              {submitting ? 'Saving...' : (submitLabel || 'Create')}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
