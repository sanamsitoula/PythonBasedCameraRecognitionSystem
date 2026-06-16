import React from 'react';
import {
  ResponsiveContainer, LineChart, Line, XAxis, YAxis,
  CartesianGrid, Tooltip, Legend,
} from 'recharts';

const CustomTooltip = ({ active, payload, label }) => {
  if (!active || !payload?.length) return null;
  return (
    <div style={{ background: '#1c2128', border: '1px solid #30363d', borderRadius: 6, padding: '8px 12px', fontSize: 12 }}>
      <p className="text-muted mb-1">{label}</p>
      {payload.map((p) => (
        <div key={p.dataKey} style={{ color: p.color }}>
          {p.name}: <strong>{p.value}</strong>
        </div>
      ))}
    </div>
  );
};

export default function OccupancyChart({ data = [] }) {
  return (
    <div className="card h-100" style={{ background: '#161b22', border: '1px solid #30363d', borderRadius: 10 }}>
      <div className="card-header px-3 py-2" style={{ background: 'transparent', borderBottom: '1px solid #30363d' }}>
        <span className="fw-semibold text-white" style={{ fontSize: 14 }}>Occupancy Trend (24h)</span>
      </div>
      <div className="card-body p-2">
        <ResponsiveContainer width="100%" height={220}>
          <LineChart data={data} margin={{ top: 5, right: 10, left: -10, bottom: 0 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="#21262d" />
            <XAxis
              dataKey="time"
              tick={{ fill: '#8b949e', fontSize: 11 }}
              axisLine={{ stroke: '#30363d' }}
              tickLine={false}
            />
            <YAxis
              tick={{ fill: '#8b949e', fontSize: 11 }}
              axisLine={{ stroke: '#30363d' }}
              tickLine={false}
            />
            <Tooltip content={<CustomTooltip />} />
            <Legend
              wrapperStyle={{ fontSize: 12, color: '#8b949e', paddingTop: 8 }}
              iconType="circle"
              iconSize={8}
            />
            <Line type="monotone" dataKey="total" name="Total" stroke="#58a6ff" strokeWidth={2} dot={false} activeDot={{ r: 4 }} />
            <Line type="monotone" dataKey="employees" name="Employees" stroke="#3fb950" strokeWidth={2} dot={false} activeDot={{ r: 4 }} />
            <Line type="monotone" dataKey="visitors" name="Visitors" stroke="#d29922" strokeWidth={2} dot={false} activeDot={{ r: 4 }} />
          </LineChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}
