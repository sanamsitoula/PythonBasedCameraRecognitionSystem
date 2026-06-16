import React from 'react';

const PRESETS = {
  online:      { bg: 'rgba(63,185,80,0.15)',  color: '#3fb950', dot: '#3fb950',  label: 'Online' },
  offline:     { bg: 'rgba(248,81,73,0.15)',  color: '#f85149', dot: '#f85149',  label: 'Offline' },
  active:      { bg: 'rgba(63,185,80,0.15)',  color: '#3fb950', dot: '#3fb950',  label: 'Active' },
  inactive:    { bg: 'rgba(139,148,158,0.15)',color: '#8b949e', dot: '#8b949e',  label: 'Inactive' },
  present:     { bg: 'rgba(63,185,80,0.15)',  color: '#3fb950', dot: '#3fb950',  label: 'Present' },
  absent:      { bg: 'rgba(248,81,73,0.15)',  color: '#f85149', dot: '#f85149',  label: 'Absent' },
  late:        { bg: 'rgba(210,153,34,0.15)', color: '#d29922', dot: '#d29922',  label: 'Late' },
  'half-day':  { bg: 'rgba(88,166,255,0.15)', color: '#58a6ff', dot: '#58a6ff',  label: 'Half Day' },
  critical:    { bg: 'rgba(248,81,73,0.15)',  color: '#f85149', dot: '#f85149',  label: 'Critical' },
  warning:     { bg: 'rgba(210,153,34,0.15)', color: '#d29922', dot: '#d29922',  label: 'Warning' },
  info:        { bg: 'rgba(88,166,255,0.15)', color: '#58a6ff', dot: '#58a6ff',  label: 'Info' },
  completed:   { bg: 'rgba(63,185,80,0.15)',  color: '#3fb950', dot: '#3fb950',  label: 'Completed' },
  pending:     { bg: 'rgba(210,153,34,0.15)', color: '#d29922', dot: '#d29922',  label: 'Pending' },
  generating:  { bg: 'rgba(88,166,255,0.15)', color: '#58a6ff', dot: '#58a6ff',  label: 'Generating' },
  failed:      { bg: 'rgba(248,81,73,0.15)',  color: '#f85149', dot: '#f85149',  label: 'Failed' },
  degraded:    { bg: 'rgba(210,153,34,0.15)', color: '#d29922', dot: '#d29922',  label: 'Degraded' },
  error:       { bg: 'rgba(248,81,73,0.15)',  color: '#f85149', dot: '#f85149',  label: 'Error' },
  unknown:     { bg: 'rgba(139,148,158,0.15)',color: '#8b949e', dot: '#8b949e',  label: 'Unknown' },
};

/**
 * StatusBadge
 * @param {string} status  - key from PRESETS (or custom)
 * @param {string} label   - override display label
 * @param {boolean} dot    - show dot indicator
 * @param {string} size    - 'sm' | 'md'
 */
export default function StatusBadge({ status = 'unknown', label, dot = true, size = 'md' }) {
  const key = (status || 'unknown').toLowerCase().replace(/\s+/g, '-');
  const preset = PRESETS[key] || PRESETS.unknown;
  const displayLabel = label || preset.label || status;
  const fontSize = size === 'sm' ? 10 : 12;

  return (
    <span
      style={{
        display: 'inline-flex',
        alignItems: 'center',
        gap: 5,
        padding: size === 'sm' ? '2px 7px' : '3px 9px',
        borderRadius: 20,
        background: preset.bg,
        color: preset.color,
        fontSize,
        fontWeight: 500,
        whiteSpace: 'nowrap',
      }}
    >
      {dot && (
        <span
          style={{
            width: size === 'sm' ? 5 : 6,
            height: size === 'sm' ? 5 : 6,
            borderRadius: '50%',
            background: preset.dot,
            flexShrink: 0,
          }}
        />
      )}
      {displayLabel}
    </span>
  );
}
