import React, { useState } from 'react';
import { RiFileTextLine, RiDownload2Line, RiLoader4Line } from 'react-icons/ri';

const REPORT_TYPES = [
  {
    id: 'attendance_daily',
    title: 'Daily Attendance Report',
    desc: 'Present / late / absent for all employees for a selected date.',
    endpoint: '/api/v1/attendance?format=csv',
    format: 'CSV',
    color: '#3fb950',
  },
  {
    id: 'attendance_monthly',
    title: 'Monthly Attendance Summary',
    desc: 'Month-level attendance totals per employee.',
    endpoint: '/api/v1/attendance/monthly-report',
    format: 'CSV',
    color: '#3fb950',
  },
  {
    id: 'visitor_log',
    title: 'Visitor Log',
    desc: 'Full list of visitors with entry / exit times and zone history.',
    endpoint: '/api/v1/visitors?format=csv',
    format: 'CSV',
    color: '#58a6ff',
  },
  {
    id: 'alerts_export',
    title: 'Alerts Export',
    desc: 'All smart alerts with severity, type and acknowledgement status.',
    endpoint: '/api/v1/alerts?format=csv',
    format: 'CSV',
    color: '#d29922',
  },
  {
    id: 'occupancy_hourly',
    title: 'Hourly Occupancy Report',
    desc: 'Occupancy snapshots aggregated by hour for a date range.',
    endpoint: '/api/v1/analytics/daily',
    format: 'JSON',
    color: '#a5d6ff',
  },
  {
    id: 'vehicle_log',
    title: 'Vehicle Log',
    desc: 'License plate detections with timestamps and camera source.',
    endpoint: '/api/v1/vehicles?format=csv',
    format: 'CSV',
    color: '#ff9bce',
  },
];

export default function ReportsPage() {
  const [dateFrom, setDateFrom] = useState(new Date().toISOString().slice(0, 10));
  const [dateTo,   setDateTo]   = useState(new Date().toISOString().slice(0, 10));
  const [loading, setLoading]   = useState(null);

  async function handleDownload(report) {
    setLoading(report.id);
    try {
      const token = localStorage.getItem('token');
      const url = `http://localhost:8000${report.endpoint}${report.endpoint.includes('?') ? '&' : '?'}date_from=${dateFrom}&date_to=${dateTo}`;
      const res = await fetch(url, { headers: { Authorization: `Bearer ${token}` } });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const blob = await res.blob();
      const a = document.createElement('a');
      a.href = URL.createObjectURL(blob);
      a.download = `${report.id}_${dateFrom}.${report.format.toLowerCase()}`;
      a.click();
    } catch (err) {
      alert(`Download failed: ${err.message}`);
    } finally {
      setLoading(null);
    }
  }

  return (
    <div style={{ padding: '24px', color: '#e6edf3' }}>
      <div className="d-flex align-items-center gap-2 mb-4">
        <RiFileTextLine size={22} color="#58a6ff" />
        <h4 className="mb-0 fw-bold">Reports</h4>
      </div>

      {/* Date range picker */}
      <div className="p-3 rounded-3 mb-4 d-flex flex-wrap gap-3 align-items-end" style={{ background: '#161b22', border: '1px solid #30363d' }}>
        <div>
          <label className="form-label small text-muted mb-1">From</label>
          <input type="date" className="form-control form-control-sm" style={{ background: '#0d1117', border: '1px solid #30363d', color: '#e6edf3' }}
            value={dateFrom} onChange={e => setDateFrom(e.target.value)} />
        </div>
        <div>
          <label className="form-label small text-muted mb-1">To</label>
          <input type="date" className="form-control form-control-sm" style={{ background: '#0d1117', border: '1px solid #30363d', color: '#e6edf3' }}
            value={dateTo} onChange={e => setDateTo(e.target.value)} />
        </div>
        <p className="text-muted small mb-0">Select a date range, then click Download on any report below.</p>
      </div>

      {/* Report cards */}
      <div className="row g-3">
        {REPORT_TYPES.map(r => (
          <div className="col-md-6 col-lg-4" key={r.id}>
            <div className="p-3 h-100 rounded-3 d-flex flex-column" style={{ background: '#161b22', border: '1px solid #30363d' }}>
              <div className="d-flex align-items-center gap-2 mb-2">
                <RiFileTextLine size={18} color={r.color} />
                <span className="fw-semibold" style={{ fontSize: 14 }}>{r.title}</span>
                <span className="badge ms-auto" style={{ background: '#21262d', color: '#8b949e', fontSize: 10 }}>{r.format}</span>
              </div>
              <p className="text-muted small flex-grow-1" style={{ fontSize: 12 }}>{r.desc}</p>
              <code className="text-muted d-block mb-3" style={{ fontSize: 10, wordBreak: 'break-all' }}>{r.endpoint}</code>
              <button
                className="btn btn-sm btn-outline-primary w-100"
                onClick={() => handleDownload(r)}
                disabled={loading === r.id}
              >
                {loading === r.id
                  ? <><RiLoader4Line className="spin me-1" />Downloading…</>
                  : <><RiDownload2Line className="me-1" />Download</>
                }
              </button>
            </div>
          </div>
        ))}
      </div>

      <style>{`.spin { animation: spin 1s linear infinite; } @keyframes spin { from{transform:rotate(0deg)} to{transform:rotate(360deg)} }`}</style>
    </div>
  );
}
