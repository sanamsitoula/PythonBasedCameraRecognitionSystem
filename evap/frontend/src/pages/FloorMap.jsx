import React, { useState } from 'react';
import { RiMapLine, RiFullscreenLine, RiRefreshLine } from 'react-icons/ri';

const ZONES = [
  { id: 'lobby',    label: 'Lobby',      x: 40,  y: 60,  w: 160, h: 80,  count: 12, color: '#1f6feb' },
  { id: 'canteen',  label: 'Canteen',    x: 220, y: 60,  w: 140, h: 80,  count: 34, color: '#3fb950' },
  { id: 'office_a', label: 'Office A',   x: 40,  y: 160, w: 140, h: 100, count: 28, color: '#1f6feb' },
  { id: 'office_b', label: 'Office B',   x: 200, y: 160, w: 160, h: 100, count: 21, color: '#1f6feb' },
  { id: 'conf_1',   label: 'Conf Room 1',x: 40,  y: 280, w: 100, h: 70,  count: 6,  color: '#d29922' },
  { id: 'conf_2',   label: 'Conf Room 2',x: 160, y: 280, w: 100, h: 70,  count: 0,  color: '#8b949e' },
  { id: 'server',   label: 'Server Room',x: 280, y: 280, w: 80,  h: 70,  count: 2,  color: '#f85149' },
];

function heatColor(count) {
  if (count === 0) return 'rgba(139,148,158,0.15)';
  if (count < 5)  return 'rgba(31,111,235,0.25)';
  if (count < 15) return 'rgba(63,185,80,0.25)';
  if (count < 30) return 'rgba(210,153,34,0.25)';
  return 'rgba(248,81,73,0.35)';
}

export default function FloorMapPage() {
  const [selected, setSelected] = useState(null);
  const [heatmap, setHeatmap] = useState(false);

  const zone = ZONES.find(z => z.id === selected);

  return (
    <div style={{ padding: '24px', color: '#e6edf3' }}>
      <div className="d-flex align-items-center justify-content-between mb-4">
        <div className="d-flex align-items-center gap-2">
          <RiMapLine size={22} color="#58a6ff" />
          <h4 className="mb-0 fw-bold">Floor Map</h4>
        </div>
        <div className="d-flex gap-2">
          <button
            className={`btn btn-sm ${heatmap ? 'btn-warning' : 'btn-outline-secondary'}`}
            onClick={() => setHeatmap(h => !h)}
          >
            {heatmap ? 'Heatmap ON' : 'Heatmap OFF'}
          </button>
          <button className="btn btn-sm btn-outline-secondary" title="Refresh">
            <RiRefreshLine />
          </button>
          <button className="btn btn-sm btn-outline-secondary" title="Fullscreen">
            <RiFullscreenLine />
          </button>
        </div>
      </div>

      <div className="row g-3">
        {/* SVG floor plan */}
        <div className="col-lg-8">
          <div className="card border-0 rounded-3" style={{ background: '#161b22', border: '1px solid #30363d' }}>
            <div className="card-body p-3">
              <p className="text-muted small mb-2">Ground Floor — click a zone for details</p>
              <svg width="100%" viewBox="0 0 400 400" style={{ background: '#0d1117', borderRadius: 8, border: '1px solid #21262d' }}>
                {/* Outer walls */}
                <rect x="30" y="40" width="340" height="330" fill="none" stroke="#30363d" strokeWidth="3" rx="4" />
                {/* Zones */}
                {ZONES.map(z => (
                  <g key={z.id} onClick={() => setSelected(z.id === selected ? null : z.id)} style={{ cursor: 'pointer' }}>
                    <rect
                      x={z.x} y={z.y} width={z.w} height={z.h}
                      fill={heatmap ? heatColor(z.count) : (selected === z.id ? 'rgba(31,111,235,0.25)' : 'rgba(33,38,45,0.8)')}
                      stroke={selected === z.id ? '#58a6ff' : '#30363d'}
                      strokeWidth={selected === z.id ? 2 : 1}
                      rx="4"
                    />
                    <text x={z.x + z.w / 2} y={z.y + z.h / 2 - 6} textAnchor="middle" fill="#c9d1d9" fontSize="11" fontWeight="500">
                      {z.label}
                    </text>
                    <text x={z.x + z.w / 2} y={z.y + z.h / 2 + 10} textAnchor="middle" fill="#58a6ff" fontSize="13" fontWeight="700">
                      {z.count}
                    </text>
                    <text x={z.x + z.w / 2} y={z.y + z.h / 2 + 24} textAnchor="middle" fill="#8b949e" fontSize="9">
                      people
                    </text>
                  </g>
                ))}
                {/* Corridors */}
                <line x1="30" y1="150" x2="370" y2="150" stroke="#21262d" strokeWidth="1" strokeDasharray="4,4" />
                <line x1="30" y1="265" x2="370" y2="265" stroke="#21262d" strokeWidth="1" strokeDasharray="4,4" />
                <text x="200" y="390" textAnchor="middle" fill="#484f58" fontSize="10">Corridor</text>
              </svg>
              {/* Legend */}
              {heatmap && (
                <div className="d-flex gap-3 mt-2">
                  {[['Low (0–4)', '#1f6feb'], ['Medium (5–14)', '#3fb950'], ['High (15–29)', '#d29922'], ['Critical (30+)', '#f85149']].map(([label, color]) => (
                    <div key={label} className="d-flex align-items-center gap-1">
                      <div style={{ width: 12, height: 12, background: color, borderRadius: 3, opacity: 0.7 }} />
                      <span style={{ fontSize: 11, color: '#8b949e' }}>{label}</span>
                    </div>
                  ))}
                </div>
              )}
            </div>
          </div>
        </div>

        {/* Zone detail / summary */}
        <div className="col-lg-4">
          {zone ? (
            <div className="card border-0 rounded-3 mb-3" style={{ background: '#161b22', border: '1px solid #30363d' }}>
              <div className="card-body p-3">
                <h6 className="fw-bold mb-3" style={{ color: '#58a6ff' }}>{zone.label}</h6>
                <div className="d-flex justify-content-between mb-2">
                  <span className="text-muted small">Current occupancy</span>
                  <span className="fw-bold">{zone.count}</span>
                </div>
                <div className="d-flex justify-content-between mb-2">
                  <span className="text-muted small">Zone ID</span>
                  <span className="small text-muted">{zone.id}</span>
                </div>
                <div className="progress mt-3" style={{ height: 6, background: '#21262d' }}>
                  <div
                    className="progress-bar"
                    style={{ width: `${Math.min(zone.count * 2, 100)}%`, background: zone.count > 30 ? '#f85149' : '#1f6feb' }}
                  />
                </div>
                <p className="text-muted" style={{ fontSize: 11, marginTop: 4 }}>
                  {Math.min(zone.count * 2, 100)}% capacity
                </p>
              </div>
            </div>
          ) : (
            <div className="card border-0 rounded-3 mb-3" style={{ background: '#161b22', border: '1px solid #30363d' }}>
              <div className="card-body p-3 text-center text-muted">
                <RiMapLine size={32} style={{ opacity: 0.3 }} className="mb-2" />
                <p className="small mb-0">Click a zone on the floor plan to see details</p>
              </div>
            </div>
          )}

          {/* Summary table */}
          <div className="card border-0 rounded-3" style={{ background: '#161b22', border: '1px solid #30363d' }}>
            <div className="card-body p-3">
              <p className="fw-semibold small mb-2">All Zones</p>
              <table className="table table-sm mb-0" style={{ fontSize: 13, color: '#e6edf3' }}>
                <thead><tr style={{ color: '#8b949e' }}><th>Zone</th><th className="text-end">People</th></tr></thead>
                <tbody>
                  {ZONES.map(z => (
                    <tr
                      key={z.id}
                      style={{ cursor: 'pointer', background: selected === z.id ? 'rgba(31,111,235,0.1)' : 'transparent' }}
                      onClick={() => setSelected(z.id === selected ? null : z.id)}
                    >
                      <td>{z.label}</td>
                      <td className="text-end fw-bold" style={{ color: z.count > 30 ? '#f85149' : z.count > 15 ? '#d29922' : '#58a6ff' }}>
                        {z.count}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
