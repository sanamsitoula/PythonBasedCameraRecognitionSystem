import React from 'react';
import { format } from 'date-fns';

/**
 * DateRangePicker
 * Props: startDate, endDate, onChange({startDate, endDate}), label
 */
export default function DateRangePicker({ startDate, endDate, onChange, label = 'Date Range' }) {
  const fmt = (d) => (d ? format(new Date(d), 'yyyy-MM-dd') : '');

  return (
    <div className="d-flex align-items-center gap-2 flex-wrap">
      {label && <span className="text-muted" style={{ fontSize: 13, whiteSpace: 'nowrap' }}>{label}:</span>}
      <div className="d-flex align-items-center gap-2">
        <input
          type="date"
          className="form-control form-control-sm"
          style={{ background: '#0d1117', border: '1px solid #30363d', color: '#e6edf3', width: 150 }}
          value={fmt(startDate)}
          max={fmt(endDate) || undefined}
          onChange={(e) => onChange({ startDate: e.target.value, endDate })}
        />
        <span className="text-muted">–</span>
        <input
          type="date"
          className="form-control form-control-sm"
          style={{ background: '#0d1117', border: '1px solid #30363d', color: '#e6edf3', width: 150 }}
          value={fmt(endDate)}
          min={fmt(startDate) || undefined}
          onChange={(e) => onChange({ startDate, endDate: e.target.value })}
        />
      </div>
    </div>
  );
}
