import React, { useState, useEffect } from 'react';
import {
  ResponsiveContainer, AreaChart, Area, BarChart, Bar,
  LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, Legend,
} from 'recharts';
import { RiBarChartLine, RiRefreshLine } from 'react-icons/ri';

function mockHourly() {
  return Array.from({ length: 24 }, (_, h) => ({
    hour: `${String(h).padStart(2, '0')}:00`,
    employees: Math.floor(20 + Math.sin(h / 3) * 15 + Math.random() * 5),
    visitors: Math.floor(5 + Math.sin(h / 4) * 5 + Math.random() * 3),
    alerts: Math.floor(Math.random() * 4),
  }));
}

function mockWeekly() {
  const days = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'];
  return days.map(d => ({
    day: d,
    present: Math.floor(50 + Math.random() * 30),
    late: Math.floor(Math.random() * 8),
    absent: Math.floor(Math.random() * 15),
  }));
}

function mockDepts() {
  return [
    { dept: 'Engineering', present: 32, absent: 3, utilization: 91 },
    { dept: 'HR',          present: 8,  absent: 1, utilization: 88 },
    { dept: 'Finance',     present: 12, absent: 2, utilization: 85 },
    { dept: 'Operations',  present: 20, absent: 4, utilization: 83 },
    { dept: 'Sales',       present: 15, absent: 5, utilization: 75 },
    { dept: 'Admin',       present: 5,  absent: 0, utilization: 100 },
  ];
}

const CARD_STYLE = { background: '#161b22', border: '1px solid #30363d', borderRadius: 12 };
const CHART_OPTS = { background: 'transparent', fontSize: 12 };

function StatCard({ label, value, sub, color = '#58a6ff' }) {
  return (
    <div className="col-md-3 col-6">
      <div className="p-3 rounded-3 text-center" style={CARD_STYLE}>
        <div style={{ fontSize: 28, fontWeight: 700, color }}>{value}</div>
        <div style={{ fontSize: 13, color: '#8b949e' }}>{label}</div>
        {sub && <div style={{ fontSize: 11, color: '#484f58', marginTop: 2 }}>{sub}</div>}
      </div>
    </div>
  );
}

export default function AnalyticsPage() {
  const [hourly] = useState(mockHourly);
  const [weekly] = useState(mockWeekly);
  const [depts] = useState(mockDepts);
  const [range, setRange] = useState('today');

  const totalPresent = depts.reduce((s, d) => s + d.present, 0);
  const totalAbsent  = depts.reduce((s, d) => s + d.absent, 0);
  const peakHour     = hourly.reduce((m, h) => h.employees > m.employees ? h : m, hourly[0]);

  return (
    <div style={{ padding: '24px', color: '#e6edf3' }}>
      <div className="d-flex align-items-center justify-content-between mb-4">
        <div className="d-flex align-items-center gap-2">
          <RiBarChartLine size={22} color="#58a6ff" />
          <h4 className="mb-0 fw-bold">Analytics</h4>
        </div>
        <div className="d-flex gap-2 align-items-center">
          {['today', 'week', 'month'].map(r => (
            <button
              key={r}
              className={`btn btn-sm ${range === r ? 'btn-primary' : 'btn-outline-secondary'}`}
              onClick={() => setRange(r)}
            >
              {r.charAt(0).toUpperCase() + r.slice(1)}
            </button>
          ))}
          <button className="btn btn-sm btn-outline-secondary" title="Refresh">
            <RiRefreshLine />
          </button>
        </div>
      </div>

      {/* KPI row */}
      <div className="row g-3 mb-4">
        <StatCard label="Total Present" value={totalPresent} sub="employees today" color="#3fb950" />
        <StatCard label="Total Absent"  value={totalAbsent}  sub="employees today" color="#f85149" />
        <StatCard label="Peak Occupancy" value={peakHour.employees} sub={`at ${peakHour.hour}`} color="#d29922" />
        <StatCard label="Avg Utilization" value={`${Math.round(depts.reduce((s,d)=>s+d.utilization,0)/depts.length)}%`} sub="across departments" color="#58a6ff" />
      </div>

      {/* Occupancy over time */}
      <div className="row g-3 mb-4">
        <div className="col-12">
          <div className="p-3 rounded-3" style={CARD_STYLE}>
            <p className="fw-semibold small mb-3">Occupancy Over Time (hourly)</p>
            <ResponsiveContainer width="100%" height={220}>
              <AreaChart data={hourly} {...CHART_OPTS}>
                <defs>
                  <linearGradient id="emp" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="5%"  stopColor="#1f6feb" stopOpacity={0.4} />
                    <stop offset="95%" stopColor="#1f6feb" stopOpacity={0.0} />
                  </linearGradient>
                  <linearGradient id="vis" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="5%"  stopColor="#3fb950" stopOpacity={0.4} />
                    <stop offset="95%" stopColor="#3fb950" stopOpacity={0.0} />
                  </linearGradient>
                </defs>
                <CartesianGrid stroke="#21262d" vertical={false} />
                <XAxis dataKey="hour" tick={{ fill: '#8b949e', fontSize: 11 }} interval={3} />
                <YAxis tick={{ fill: '#8b949e', fontSize: 11 }} />
                <Tooltip contentStyle={{ background: '#161b22', border: '1px solid #30363d', color: '#e6edf3', fontSize: 12 }} />
                <Legend wrapperStyle={{ fontSize: 12, color: '#8b949e' }} />
                <Area type="monotone" dataKey="employees" stroke="#1f6feb" fill="url(#emp)" name="Employees" />
                <Area type="monotone" dataKey="visitors"  stroke="#3fb950" fill="url(#vis)" name="Visitors" />
              </AreaChart>
            </ResponsiveContainer>
          </div>
        </div>
      </div>

      {/* Weekly attendance + Department table */}
      <div className="row g-3">
        <div className="col-lg-6">
          <div className="p-3 rounded-3" style={CARD_STYLE}>
            <p className="fw-semibold small mb-3">Weekly Attendance Breakdown</p>
            <ResponsiveContainer width="100%" height={220}>
              <BarChart data={weekly} {...CHART_OPTS}>
                <CartesianGrid stroke="#21262d" vertical={false} />
                <XAxis dataKey="day" tick={{ fill: '#8b949e', fontSize: 11 }} />
                <YAxis tick={{ fill: '#8b949e', fontSize: 11 }} />
                <Tooltip contentStyle={{ background: '#161b22', border: '1px solid #30363d', color: '#e6edf3', fontSize: 12 }} />
                <Legend wrapperStyle={{ fontSize: 12, color: '#8b949e' }} />
                <Bar dataKey="present" stackId="a" fill="#3fb950" name="Present" radius={[0,0,0,0]} />
                <Bar dataKey="late"    stackId="a" fill="#d29922" name="Late" />
                <Bar dataKey="absent"  stackId="a" fill="#f85149" name="Absent" radius={[4,4,0,0]} />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </div>

        <div className="col-lg-6">
          <div className="p-3 rounded-3" style={{ ...CARD_STYLE, height: '100%' }}>
            <p className="fw-semibold small mb-3">Department Utilization</p>
            <table className="table table-sm mb-0" style={{ fontSize: 13, color: '#e6edf3' }}>
              <thead>
                <tr style={{ color: '#8b949e', borderColor: '#30363d' }}>
                  <th>Department</th><th>Present</th><th>Absent</th><th>Util.</th>
                </tr>
              </thead>
              <tbody>
                {depts.map(d => (
                  <tr key={d.dept} style={{ borderColor: '#21262d' }}>
                    <td>{d.dept}</td>
                    <td style={{ color: '#3fb950' }}>{d.present}</td>
                    <td style={{ color: '#f85149' }}>{d.absent}</td>
                    <td>
                      <div className="d-flex align-items-center gap-2">
                        <div style={{ flex: 1, height: 6, background: '#21262d', borderRadius: 3 }}>
                          <div style={{ width: `${d.utilization}%`, height: '100%', background: d.utilization >= 90 ? '#3fb950' : d.utilization >= 75 ? '#d29922' : '#f85149', borderRadius: 3 }} />
                        </div>
                        <span style={{ fontSize: 11, color: '#8b949e', minWidth: 32 }}>{d.utilization}%</span>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      </div>

      <p className="text-muted mt-3" style={{ fontSize: 12 }}>
        Note: Charts show mock data. Connect <code>GET /api/v1/analytics/daily</code> to display live data.
      </p>
    </div>
  );
}
