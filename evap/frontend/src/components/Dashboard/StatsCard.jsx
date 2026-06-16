import React, { useEffect, useRef, useState } from 'react';
import { RiArrowUpLine, RiArrowDownLine, RiSubtractLine } from 'react-icons/ri';

function useCountUp(target, duration = 800) {
  const [value, setValue] = useState(0);
  const raf = useRef(null);
  const prev = useRef(0);

  useEffect(() => {
    if (target === null || target === undefined) return;
    const numTarget = parseFloat(target);
    if (isNaN(numTarget)) { setValue(target); return; }

    const start = prev.current;
    const diff = numTarget - start;
    const startTime = performance.now();

    function step(now) {
      const elapsed = now - startTime;
      const progress = Math.min(elapsed / duration, 1);
      const eased = 1 - Math.pow(1 - progress, 3); // ease-out cubic
      const current = start + diff * eased;
      setValue(typeof target === 'string' ? current.toFixed(1) : Math.round(current));
      if (progress < 1) raf.current = requestAnimationFrame(step);
      else prev.current = numTarget;
    }

    raf.current = requestAnimationFrame(step);
    return () => cancelAnimationFrame(raf.current);
  }, [target, duration]);

  return value;
}

const COLORS = {
  blue:   { bg: 'rgba(31,111,235,0.15)', icon: '#1f6feb', border: 'rgba(31,111,235,0.3)' },
  green:  { bg: 'rgba(63,185,80,0.15)',  icon: '#3fb950', border: 'rgba(63,185,80,0.3)' },
  orange: { bg: 'rgba(249,115,22,0.15)', icon: '#f97316', border: 'rgba(249,115,22,0.3)' },
  red:    { bg: 'rgba(248,81,73,0.15)',  icon: '#f85149', border: 'rgba(248,81,73,0.3)' },
  purple: { bg: 'rgba(139,92,246,0.15)', icon: '#8b5cf6', border: 'rgba(139,92,246,0.3)' },
  yellow: { bg: 'rgba(210,153,34,0.15)', icon: '#d29922', border: 'rgba(210,153,34,0.3)' },
};

export default function StatsCard({ title, value, subtitle, icon: Icon, color = 'blue', trend, trendValue }) {
  const animatedValue = useCountUp(typeof value === 'number' ? value : null);
  const displayValue = typeof value === 'number' ? animatedValue : (value ?? '—');
  const palette = COLORS[color] || COLORS.blue;

  const TrendIcon = trend === 'up' ? RiArrowUpLine : trend === 'down' ? RiArrowDownLine : RiSubtractLine;
  const trendColor = trend === 'up' ? '#3fb950' : trend === 'down' ? '#f85149' : '#8b949e';

  return (
    <div
      className="card h-100"
      style={{
        background: '#161b22',
        border: `1px solid ${palette.border}`,
        borderRadius: 10,
      }}
    >
      <div className="card-body p-3">
        <div className="d-flex align-items-start justify-content-between">
          <div className="flex-grow-1">
            <div className="text-muted mb-1" style={{ fontSize: 12, textTransform: 'uppercase', letterSpacing: '0.05em' }}>
              {title}
            </div>
            <div className="text-white fw-bold" style={{ fontSize: 28, lineHeight: 1.2 }}>
              {displayValue}
            </div>
            {(subtitle || (trend && trendValue)) && (
              <div className="d-flex align-items-center gap-1 mt-1">
                {trend && trendValue && (
                  <span style={{ color: trendColor, fontSize: 12, display: 'flex', alignItems: 'center', gap: 2 }}>
                    <TrendIcon size={13} />
                    {trendValue}
                  </span>
                )}
                {subtitle && (
                  <span className="text-muted" style={{ fontSize: 12 }}>{subtitle}</span>
                )}
              </div>
            )}
          </div>
          {Icon && (
            <div
              className="d-flex align-items-center justify-content-center rounded"
              style={{
                width: 44,
                height: 44,
                background: palette.bg,
                border: `1px solid ${palette.border}`,
                flexShrink: 0,
              }}
            >
              <Icon size={22} color={palette.icon} />
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
